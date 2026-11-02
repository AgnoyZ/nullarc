"""Export this repository at a commit into a NEW staging directory; never install or execute.

The downstream changes are ordinary commits here, so staging copies the committed tree instead of
applying a patch series. The historical patch files under patches/ stay in the repository for
traceability and for the tests that reconstruct pre-patch methods; they are hashed, never applied.
"""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
from firmware_profile import checked_header

ROOT = Path(__file__).resolve().parents[1]

EXPORT = ("src/phxbringup", "src/phxaccel", "src/nmplugin",
          "tools/phxctl/mesboot.c", "tools/phxctl/phxctl.c",
          "tools/phxctl/mes_v11_api_def.h", "tools/phxctl/csb_gfx11.h",
          "tools/phxctl/gfx11_shader_probe.h",
          "LICENSE", "LICENSES", "THIRD_PARTY_NOTICES.md")

# Canonical downstream headers at src/; the component directories carry the copies the build uses.
HEADERS = ("PhxHardwarePolicy.hpp", "PhxPspLayout.h", "PhxBootMemory.h",
           "PhxGartLayout.h", "PhxMesQueueLayout.h", "PhxFirmwareProfile.h")

def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args])

def verify_no_local_edits(path):
    # Untracked build output does not change what git archive exports, so only local edits block staging.
    if git(path, "status", "--porcelain", "--untracked-files=no").strip():
        raise RuntimeError(f"Source checkout has uncommitted changes: {path}")

def verify_clean(path):
    if git(path, "status", "--porcelain", "--untracked-files=all").strip():
        raise RuntimeError(f"Source checkout must be clean: {path}")

def verify_checkout(path, expected):
    actual = git(path, "rev-parse", "HEAD").decode().strip()
    if actual != expected:
        raise RuntimeError(f"Unexpected source revision: {actual}; expected {expected}")
    verify_clean(path)

def export_archive(data, destination):
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for item in archive:
            target = (destination / item.name).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise RuntimeError("Archive path leaves staging directory")
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif item.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(item) as stream:
                    target.write_bytes(stream.read())
            else:
                raise RuntimeError(f"Unsupported archive entry: {item.name}")

def prepare(destination, root=ROOT):
    destination = Path(destination).resolve()
    if destination.exists():
        raise RuntimeError("Staging directory already exists; choose a fresh output, do not overwrite")
    root = Path(root).resolve()
    # Fail on stale reviewed metadata before touching the worktree or creating output.
    firmware_profile = checked_header(root)
    verify_no_local_edits(root)
    commit = git(root, "rev-parse", "HEAD").decode().strip()
    lock = json.loads((root / "upstream.lock.json").read_text())
    archive = git(root, "archive", commit, *EXPORT)
    destination.mkdir(parents=True)
    export_archive(archive, destination)
    for name in HEADERS:
        canonical = (root / "src" / name).read_bytes()
        staged = (destination / "src/phxbringup" / name).read_bytes()
        if staged != canonical:
            raise RuntimeError(f"Component header differs from src/{name}")
    if (destination / "src/phxaccel/PhxHardwarePolicy.hpp").read_bytes() != (root / "src/PhxHardwarePolicy.hpp").read_bytes():
        raise RuntimeError("PhxAccel policy copy differs from src/PhxHardwarePolicy.hpp")
    if (destination / "src/nmplugin/PhxRuntimePath.h").read_bytes() != (root / "src/PhxRuntimePath.h").read_bytes():
        raise RuntimeError("Plugin path helper differs from src/PhxRuntimePath.h")
    historical = {}
    for name in lock.get("patches", []):
        path = root / name
        if not path.is_file():
            raise RuntimeError(f"Historical patch is missing: {name}")
        historical[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = {"source_commit": commit, "historical_patches_sha256": historical,
              "policy_sha256": hashlib.sha256((root / "src/PhxHardwarePolicy.hpp").read_bytes()).hexdigest(),
              "psp_layout_sha256": hashlib.sha256((root / "src/PhxPspLayout.h").read_bytes()).hexdigest(),
              "firmware_profile_sha256": hashlib.sha256(firmware_profile).hexdigest(),
              "boot_memory_sha256": hashlib.sha256((root / "src/PhxBootMemory.h").read_bytes()).hexdigest(),
              "gart_layout_sha256": hashlib.sha256((root / "src/PhxGartLayout.h").read_bytes()).hexdigest(),
              "mes_queue_layout_sha256": hashlib.sha256((root / "src/PhxMesQueueLayout.h").read_bytes()).hexdigest(),
              "runtime_path_sha256": hashlib.sha256((root / "src/PhxRuntimePath.h").read_bytes()).hexdigest(),
              "hardware_tested": False}
    (destination / "source-provenance.json").write_text(json.dumps(result, indent=2) + "\n")
    return result

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.destination), indent=2))
