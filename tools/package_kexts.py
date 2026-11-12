"""Package two compiled kexts and corresponding sources; never install or load them."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile

from prepare_source import git, verify_checkout, verify_no_local_edits
from verify_artifacts import inspect_kext

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = {"PhxBringup": "org.drip.PhxBringup", "PhxAccel": "com.luuumi.PhxAccel"}
SOURCE_PATHS = ("src/phxbringup", "src/phxaccel", "src/amd/phx_topology.h",
                "tools/package_kexts.py", "tools/verify_artifacts.py", "upstream.lock.json",
                ".github/workflows/kext-artifacts.yml", "LICENSE", "LICENSES",
                "THIRD_PARTY_NOTICES.md", "docs/KEXT-ARTIFACTS.md",
                "docs/KEXT-PROVENANCE.md", "docs/KEXT-INSTALL-zh.md", "docs/kext-notices",
                "docs/LEGACY-BOOT.md", "tools/phx_legacy_boot.py", "tools/phx_edid.py")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_bundle(bundle, component):
    """Fail closed rather than uploading stray logs, user plists or extra code."""
    bundle = Path(bundle)
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("Expected a real kext directory")
    allowed = {"Contents/Info.plist", "Contents/MacOS/" + component,
               "Contents/_CodeSignature/CodeResources"}
    files = {}
    for path in sorted(bundle.rglob("*")):
        if path.is_symlink():
            raise ValueError("Kext symlinks are not accepted")
        if path.is_dir():
            continue
        name = path.relative_to(bundle).as_posix()
        if not path.is_file() or name not in allowed:
            raise ValueError("Unexpected kext file: " + name)
        files[name] = sha256(path)
    metadata = inspect_kext(bundle, COMPONENTS[component])
    return {**metadata, "files_sha256": files}


def source_archive(root, paths, destination, prefix):
    """Export committed, allowlisted source blobs only, including original modes."""
    data = git(root, "archive", "--format=tar", "--prefix=" + prefix, "HEAD", *paths)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for item in archive:
            if not (item.isfile() or item.isdir()):
                raise ValueError("Source archive contains non-regular entries")
            name = Path(item.name)
            if name.is_absolute() or ".." in name.parts:
                raise ValueError("Unsafe source archive path")
    # Do not extract into the working tree or archive any untracked files.
    import gzip
    with Path(destination).open("wb") as target:
        with gzip.GzipFile(fileobj=target, mode="wb", mtime=0) as compressed:
            compressed.write(data)


def package(sdk, out, root=ROOT):
    root, sdk, out = Path(root).resolve(), Path(sdk).resolve(), Path(out).resolve()
    if platform.system() != "Darwin" or platform.machine() != "x86_64":
        raise RuntimeError("Packaging real signed kexts requires the native Intel macOS build host")
    if out.exists() or not out.is_relative_to(root / "build"):
        raise RuntimeError("Use a fresh output directory under this checkout's build/")
    verify_no_local_edits(root)
    lock = json.loads((root / "upstream.lock.json").read_text())
    verify_checkout(sdk, lock["MacKernelSDK"]["commit"])
    commit = git(root, "rev-parse", "HEAD").decode().strip()
    reports = {}
    for component in COMPONENTS:
        bundle = root / "src" / component.lower() / "build" / (component + ".kext")
        reports[component] = check_bundle(bundle, component)
        subprocess.run(["codesign", "--verify", "--strict", str(bundle)], check=True)
    out.mkdir(parents=True)
    stage = out / ("nullarc-kexts-" + commit[:12])
    stage.mkdir()
    for component in COMPONENTS:
        source = root / "src" / component.lower() / "build" / (component + ".kext")
        target = stage / (component + ".kext")
        shutil.copytree(source, target)
        if check_bundle(target, component) != reports[component]:
            raise RuntimeError("Staged kext bytes changed")
        subprocess.run(["codesign", "--verify", "--strict", str(target)], check=True)
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(root / name, stage / name)
    shutil.copytree(root / "LICENSES", stage / "LICENSES")
    shutil.copytree(root / "docs/kext-notices", stage / "SUPPLEMENTAL-NOTICES")
    shutil.copy2(sdk / "LICENSE.txt", stage / "MacKernelSDK-LICENSE.txt")
    shutil.copy2(root / "docs/KEXT-INSTALL-zh.md", stage / "INSTALL-zh.md")
    shutil.copy2(root / "docs/KEXT-PROVENANCE.md", stage / "KEXT-PROVENANCE.md")
    shutil.copy2(root / "docs/LEGACY-BOOT.md", stage / "LEGACY-BOOT.md")
    (stage / "SOURCE").mkdir()
    source_archive(root, SOURCE_PATHS, stage / "SOURCE/nullarc-source.tar.gz", "nullarc/")
    source_archive(sdk, ("Headers", "Library/kmod", "LICENSE.txt", "README.md"),
                   stage / "SOURCE/MacKernelSDK-source.tar.gz", "MacKernelSDK/")
    report = {"schema": 1, "source_commit": commit, "sdk_commit": lock["MacKernelSDK"]["commit"],
              "upstream_commit": lock["nullarc"]["commit"],
              "compiler": subprocess.check_output(["xcrun", "clang", "--version"], text=True),
              "build_host": subprocess.check_output(["sw_vers"], text=True),
              "kexts": reports, "signing": "ad-hoc; codesign --verify --strict passed before and after staging",
              "use": "experimental noncommercial testing; component licences apply",
              "source_archives_sha256": {p.name: sha256(p) for p in sorted((stage / "SOURCE").iterdir())},
              "installed": False, "hardware_tested": False, "complete_metal_stack": False,
              "private_data_included": False}
    (stage / "build-report.json").write_text(json.dumps(report, indent=2) + "\n")
    checksums = "".join(sha256(p) + "  " + p.relative_to(stage).as_posix() + "\n"
                        for p in sorted(stage.rglob("*")) if p.is_file())
    (stage / "SHA256SUMS").write_text(checksums)
    upload = out / "upload"
    upload.mkdir()
    archive_path = upload / (stage.name + ".tar.gz")
    with tarfile.open(archive_path, "w:gz", dereference=False) as archive:
        archive.add(stage, arcname=stage.name)
    (upload / "SHA256SUMS").write_text(sha256(archive_path) + "  " + archive_path.name + "\n")
    print(json.dumps({"archive": str(archive_path), "sha256": sha256(archive_path), **report}, indent=2))
    return archive_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    package(args.sdk, args.out)
