"""Package one signed RADV library and committed corresponding source; never install or load it."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
import posixpath
import re
import shutil
import subprocess
import tarfile

from build_radv import system_dependencies
from prepare_source import ROOT, git, verify_checkout, verify_no_local_edits
from verify_artifacts import inspect_macho

LIBRARY = "libvulkan_radeon.dylib"
SOURCE_PATHS = (
    "tools/build_radv.py", "tools/prepare_radv.py", "tools/fetch_radv.py",
    "tools/prepare_source.py", "tools/firmware_profile.py", "tools/verify_artifacts.py",
    "tools/package_radv.py", "tools/radv_no_device.c", "tools/radv-build-requirements.txt",
    "tools/test_radv_cmd_init.py", "tests/test_radv_abi.c", "tests/test_radv_cmd_init.c",
    "tools/test_radv_allocation_diagnostic.py", "tests/test_radv_allocation_diagnostic.c",
    "tests/test_radv_allocation_diagnostic_runner.py", "tests/radv_iokit_stubs.h",
    "tests/fixtures/radv_iokit_transport.c",
    "tests/test_radv.py", "tests/test_radv_package.py", "tests/fixtures/radv_cmd_buffer_constructor.c",
    "src/phxbringup/PhxNativeABI.h", "src/amd/phx_topology.h", "patches/radv",
    "upstream.lock.json", ".github/workflows/radv-artifacts.yml", "LICENSE", "LICENSES",
    "THIRD_PARTY_NOTICES.md", "docs/kext-notices", "docs/RADV-PROVENANCE.md",
)
COBALT_PATHS = ("mesa-patches", "LICENSE", "third-party/THIRD-PARTY-LICENSES.txt",
                "src/navi48-bringup/src/Navi48NativeABI.h")
PHOENIX_PATHS = ("mesa-patches-phoenix", "LICENSE", "LICENSES", "THIRD_PARTY_NOTICES.md")
PROVENANCE_KEYS = {"mesa_commit", "cobalt_commit", "nullarc_commit", "patches",
                   "hardware_tested", "deployment_performed"}
REPORT_KEYS = PROVENANCE_KEYS | {
    "architecture", "macho_type", "sha256", "bytes", "runtime_tests",
    "native_transport_layout_verified", "host", "metal_stack_complete", "dependencies",
    "runtime_dependency_policy", "runtime_layout", "meson_version", "ninja_version",
    "glslang_version", "compiler", "project_commit",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha256(path):
    with Path(path).open("rb") as stream:
        result = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
        return result.hexdigest()


def committed_files(root, commit, paths):
    names = git(root, "ls-tree", "-r", "--name-only", commit, "--", *paths).decode().splitlines()
    return {name: git(root, "show", commit + ":" + name) for name in names}


def patch_inputs(root, cobalt, lock, commit):
    """Read original Git blobs, preserving the same order/CRLF rule as prepare_radv."""
    series = []
    for component, source, revision, spec in (
        ("Cobalt64", cobalt, lock["Cobalt64"]["commit"], lock["Cobalt64"]),
        ("radv-phoenix", root, lock["nullarc"]["commit"], lock["radv-phoenix"]),
    ):
        files = committed_files(source, revision, (spec["patch_directory"],))
        patches = [(name, data) for name, data in sorted(files.items()) if name.endswith(".patch")]
        if len(patches) != spec["patch_count"] or [Path(n).name[:4] for n, _ in patches] != [
                f"{i:04d}" for i in range(1, spec["patch_count"] + 1)]:
            raise ValueError("Unexpected committed patch series: " + component)
        series.extend((component, Path(name).name, data) for name, data in patches)
    for name in lock["radv-patches"]:
        data = git(root, "show", commit + ":" + name).replace(b"\r\n", b"\n")
        series.append(("downstream", Path(name).name, data))
    if [part for part, _, _ in series] != ["Cobalt64"] * 9 + ["radv-phoenix"] * 7 + ["downstream"] * 3:
        raise ValueError("RADV publication requires the reviewed 9 + 7 + 3 patch series")
    return series


def provenance(lock, series):
    return {"mesa_commit": lock["Mesa"]["commit"], "cobalt_commit": lock["Cobalt64"]["commit"],
            "nullarc_commit": lock["nullarc"]["commit"], "hardware_tested": False,
            "deployment_performed": False,
            "patches": [{"component": c, "name": n, "sha256": digest(d)} for c, n, d in series]}


def notice_inputs(mesa, cobalt, lock, expected):
    files = {"licenses/" + name.removeprefix("licenses/"): data for name, data in
             committed_files(mesa, lock["Mesa"]["commit"], ("licenses",)).items()}
    for repo, revision, source, target in (
        (mesa, lock["Mesa"]["commit"], "docs/license.rst", "Mesa-license.rst"),
        (cobalt, lock["Cobalt64"]["commit"], "LICENSE", "Cobalt64-LICENSE"),
        (cobalt, lock["Cobalt64"]["commit"], "mesa-patches/README.txt", "Cobalt64-patches-README.txt"),
    ):
        files[target] = git(repo, "show", revision + ":" + source)
    if not any(name.startswith("licenses/") for name in files):
        raise ValueError("Missing Mesa license collection")
    files["source-provenance.json"] = (json.dumps(expected, indent=2) + "\n").encode()
    return {"DEPENDENCY-LICENSES/Mesa-RADV/" + n: d for n, d in files.items()}


def check_inputs(artifacts, expected_notices, expected, commit):
    artifacts = Path(artifacts)
    if artifacts.is_symlink() or not artifacts.is_dir():
        raise ValueError("Expected a real standalone artifact directory")
    allowed = set(expected_notices) | {"nvmtl/" + name for name in
                                     (LIBRARY, "radeon_icd.json", "radv-build-report.json")}
    seen = set()
    allowed_dirs = {str(parent) for name in allowed for parent in PurePosixPath(name).parents if str(parent) != "."}
    for path in artifacts.rglob("*"):
        name = path.relative_to(artifacts).as_posix()
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("Artifact symlinks and special files are forbidden")
        if path.is_dir():
            if name not in allowed_dirs:
                raise ValueError("Unexpected artifact directory: " + name)
        elif name not in allowed:
            raise ValueError("Unexpected artifact file: " + name)
        else:
            seen.add(name)
    if seen != allowed:
        raise ValueError("Missing required artifact files")
    for name, data in expected_notices.items():
        actual = (artifacts / name).read_bytes()
        matches = (json.loads(actual) == json.loads(data) if name.endswith("/source-provenance.json")
                   else actual == data)
        if not matches:
            raise ValueError("Notice/provenance differs from pinned source: " + name)
    library = artifacts / "nvmtl" / LIBRARY
    metadata = inspect_macho(library, 6)
    report = json.loads((artifacts / "nvmtl/radv-build-report.json").read_text())
    if set(report) != REPORT_KEYS or any(report[k] != v for k, v in {**expected, **metadata, "project_commit": commit}.items()):
        raise ValueError("Build report source, patch order or binary identity mismatch")
    if (report["native_transport_layout_verified"] is not True or report["metal_stack_complete"] is not False
            or report["runtime_dependency_policy"] != "system-only" or report["runtime_layout"] != "standalone-nvmtl"):
        raise ValueError("Missing ABI evidence or wrong runtime policy")
    tests = {name: {"runtime_loaded": True, "physical_devices": 0, "gpu_submitted": False}
             for name in ("native", "reject_mock", "reject_host_only", "reject_other_gpu")}
    if report["runtime_tests"] != tests:
        raise ValueError("All four no-device refusals are required")
    dependencies = report["dependencies"]
    if not isinstance(dependencies, list) or not dependencies or any(
            not isinstance(d, str) or not d.startswith(("/usr/lib/", "/System/Library/")) for d in dependencies):
        raise ValueError("Only system dependencies are permitted")
    if re.search(r"/(?:Users|Volumes|home|private)/|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", json.dumps(report)):
        raise ValueError("Private path or identity in build report")
    icd = json.loads((artifacts / "nvmtl/radeon_icd.json").read_text())
    if (set(icd) != {"file_format_version", "ICD"} or set(icd["ICD"]) not in (
            {"library_path", "api_version"}, {"library_path", "api_version", "library_arch"})
            or icd["ICD"].get("library_arch", "64") != "64"
            or icd["ICD"]["library_path"] != "./" + LIBRARY
            or not re.fullmatch(r"\d+\.\d+\.\d+", icd["ICD"]["api_version"])
            or not re.fullmatch(r"\d+\.\d+\.\d+", icd["file_format_version"])):
        raise ValueError("Expected standalone relocatable ICD metadata")
    return report


def check_native(library, expected_dependencies):
    subprocess.run(["codesign", "--verify", "--strict", str(library)], check=True)
    dependencies = system_dependencies(subprocess.check_output(["xcrun", "otool", "-L", str(library)], text=True))
    if dependencies != expected_dependencies:
        raise ValueError("Actual dependencies differ from build report")
    exports = subprocess.check_output(["xcrun", "nm", "-gU", str(library)], text=True)
    names = {line.split()[-1] for line in exports.splitlines() if line.split()}
    if not {"_vk_icdGetInstanceProcAddr", "_radv_darwin_set_service_class"}.issubset(names):
        raise ValueError("Missing required RADV exports")


def safe_member(item, prefix):
    """Permit source symlinks only when they stay inside their own component."""
    name = PurePosixPath(item.name)
    if (name.is_absolute() or ".." in name.parts or "\\" in item.name
            or not name.parts or name.parts[0] != prefix or str(name) != item.name.rstrip("/")):
        raise ValueError("Unsafe source archive path")
    if item.issym():
        target = PurePosixPath(item.linkname)
        resolved = PurePosixPath(posixpath.normpath(str(name.parent / target)))
        if target.is_absolute() or "\\" in item.linkname or not resolved.parts or resolved.parts[0] != prefix:
            raise ValueError("Source symlink leaves component")
    elif not (item.isfile() or item.isdir()):
        raise ValueError("Source hard links and special files are forbidden")
    item.uid = item.gid = item.mtime = 0
    item.uname = item.gname = ""
    item.pax_headers = {}
    return item


def source_archive(root, commit, paths, destination, prefix):
    """Stream only committed Git source, never include a worktree or Git metadata."""
    command = ["git", "-C", str(root), "archive", "--format=tar", "--prefix=" + prefix + "/", commit, *paths]
    with Path(destination).open("xb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w|") as target:
                proc = subprocess.Popen(command, stdout=subprocess.PIPE)
                try:
                    with tarfile.open(fileobj=proc.stdout, mode="r|") as source:
                        for item in source:
                            safe_member(item, prefix)
                            target.addfile(item, source.extractfile(item) if item.isfile() else None)
                    if proc.wait() != 0:
                        raise RuntimeError("Committed source export failed")
                finally:
                    proc.stdout.close()
                    if proc.poll() is None:
                        proc.terminate()
                    proc.wait()


def tree_archive(stage, destination):
    with Path(destination).open("xb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w|") as archive:
                for path in [stage, *sorted(stage.rglob("*"))]:
                    if path.is_symlink() or not (path.is_file() or path.is_dir()):
                        raise ValueError("Only regular package files are permitted")
                    item = archive.gettarinfo(str(path), arcname=path.relative_to(stage.parent).as_posix())
                    safe_member(item, stage.name)
                    item.mode = 0o755 if path.is_dir() else 0o644
                    if path.is_file():
                        with path.open("rb") as stream:
                            archive.addfile(item, stream)
                    else:
                        archive.addfile(item)


def package(mesa, cobalt, headers, artifacts, out, root=ROOT):
    if platform.system() != "Darwin" or platform.machine() != "x86_64":
        raise RuntimeError("Real RADV packaging requires the native Intel macOS build host")
    root, mesa, cobalt, headers, artifacts, out = map(lambda p: Path(p).resolve(),
                                                    (root, mesa, cobalt, headers, artifacts, out))
    if out.exists() or not out.is_relative_to(root / "build"):
        raise RuntimeError("Use a fresh output directory under this checkout's build/")
    verify_no_local_edits(root)
    lock = json.loads((root / "upstream.lock.json").read_text())
    for path, key in ((mesa, "Mesa"), (cobalt, "Cobalt64"), (headers, "Vulkan-Headers")):
        verify_checkout(path, lock[key]["commit"])
    commit = git(root, "rev-parse", "HEAD").decode().strip()
    series = patch_inputs(root, cobalt, lock, commit)
    expected = provenance(lock, series)
    notices = notice_inputs(mesa, cobalt, lock, expected)
    report = check_inputs(artifacts, notices, expected, commit)
    check_native(artifacts / "nvmtl" / LIBRARY, report["dependencies"])
    out.mkdir(parents=True)
    stage = out / ("nullarc-radv-" + commit[:12])
    stage.mkdir()
    for name in (LIBRARY, "radeon_icd.json", "radv-build-report.json"):
        shutil.copyfile(artifacts / "nvmtl" / name, stage / name)
    if inspect_macho(stage / LIBRARY, 6) != inspect_macho(artifacts / "nvmtl" / LIBRARY, 6):
        raise RuntimeError("Staged library changed")
    check_native(stage / LIBRARY, report["dependencies"])
    for name, data in notices.items():
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    for name, data in committed_files(root, commit, ("LICENSE", "LICENSES", "THIRD_PARTY_NOTICES.md", "docs/kext-notices")).items():
        target = stage / "NOTICES" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    for source, key, paths in ((headers, "Vulkan-Headers", ("LICENSE.md", "LICENSES")),
                               (cobalt, "Cobalt64", ("LICENSE", "third-party/THIRD-PARTY-LICENSES.txt")),
                               (root, "nullarc", ("LICENSE", "LICENSES", "THIRD_PARTY_NOTICES.md"))):
        for name, data in committed_files(source, lock[key]["commit"], paths).items():
            target = stage / "NOTICES" / key / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    shutil.copyfile(root / "docs/RADV-PROVENANCE.md", stage / "RADV-PROVENANCE.md")
    sources = stage / "SOURCE"
    sources.mkdir()
    for source, revision, paths, filename, prefix in (
        (mesa, lock["Mesa"]["commit"], (), "mesa-base", "mesa"),
        (headers, lock["Vulkan-Headers"]["commit"], (), "vulkan-headers", "Vulkan-Headers"),
        (cobalt, lock["Cobalt64"]["commit"], COBALT_PATHS, "cobalt-radv", "Cobalt64"),
        (root, lock["nullarc"]["commit"], PHOENIX_PATHS, "phoenix-radv", "nullarc-phoenix"),
        (root, commit, SOURCE_PATHS, "nullarc-radv", "nullarc"),
    ):
        source_archive(source, revision, paths, sources / (filename + ".tar.gz"), prefix)
    entries = []
    for i, (component, name, data) in enumerate(series, 1):
        relative = "patches/" + f"{i:02d}-" + component + "-" + name
        path = sources / relative
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
        entries.append({"order": i, "path": relative, "component": component,
                        "original_name": name, "sha256": digest(data)})
    (sources / "patch-series.json").write_text(json.dumps({"apply_to": "mesa", "patches": entries}, indent=2) + "\n")
    packaged = {"schema": 1, "source_commit": commit, "source_provenance": expected,
                "vulkan_headers_commit": lock["Vulkan-Headers"]["commit"],
                "library": inspect_macho(stage / LIBRARY, 6), "dependencies": report["dependencies"],
                "source_archives_sha256": {p.name: sha256(p) for p in sorted(sources.glob("*.tar.gz"))},
                "signing": "ad-hoc; strict verification before and after staging",
                "runtime_binaries": [LIBRARY], "installed": False, "hardware_tested": False,
                "desktop_tested": False, "metal_stack_complete": False}
    (stage / "package-report.json").write_text(json.dumps(packaged, indent=2) + "\n")
    (stage / "SHA256SUMS").write_text("".join(sha256(p) + "  " + p.relative_to(stage).as_posix() + "\n"
                                            for p in sorted(stage.rglob("*")) if p.is_file()))
    upload = out / "upload"
    upload.mkdir()
    archive = upload / (stage.name + ".tar.gz")
    tree_archive(stage, archive)
    (upload / "SHA256SUMS").write_text(sha256(archive) + "  " + archive.name + "\n")
    print(json.dumps({"archive_name": archive.name, "archive_sha256": sha256(archive), **packaged}, indent=2))
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesa", type=Path, required=True)
    parser.add_argument("--cobalt", type=Path, required=True)
    parser.add_argument("--vulkan-headers", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    package(args.mesa, args.cobalt, args.vulkan_headers, args.artifacts, args.out)
