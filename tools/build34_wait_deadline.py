#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build the exact default34 elapsed-wait candidate offline; never install/load.

Historical original34 admission is deliberately unchanged. This separate gate
admits one reviewed wait-method delta from the owner-selected default branch.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess

from upstream34_layout import ring_padding_candidate as common

ROOT = Path(__file__).resolve().parents[1]
BASE = "4e9000e54447c7df2bc9482fa9863d3ef31df24c"
DRIVER = "src/phxbringup/PhxBringup.cpp"
BASE_SHA = "fffd2bdfea25ca87312679e194949f2538807b43610d157f06c9dde0d33a70d0"
CANDIDATE_SHA = "b4174f7f2498f8b3e1e7204059ef9c06041f30a808435cda703a34e0f9439267"
INPUTS = common.SOURCE_INPUTS


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def method(blob):
    signature = b"IOReturn IOAccelPhxNativeClient::doWaitSeq("
    if blob.count(signature) != 1:
        raise ValueError("ambiguous wait method")
    start = blob.index(signature)
    return blob[start:blob.index(b"\n}\n", start) + 3]


def verify_blobs(baseline, current):
    if set(baseline) != set(INPUTS) or set(current) != set(INPUTS):
        raise ValueError("source input set differs")
    if sha(baseline[DRIVER]) != BASE_SHA or sha(current[DRIVER]) != CANDIDATE_SHA:
        raise ValueError("unreviewed complete build34 source")
    before, after = method(baseline[DRIVER]), method(current[DRIVER])
    if baseline[DRIVER].replace(before, after) != current[DRIVER]:
        raise ValueError("change outside the wait method")
    for name in INPUTS:
        if name != DRIVER and baseline[name] != current[name]:
            raise ValueError("protected source changed: " + name)
    if b"#define PHX_KEXT_BUILD 34u\n" not in current[DRIVER]:
        raise ValueError("default build34 identity required")
    return {name: sha(blob) for name, blob in current.items()}


def read_sources():
    baseline = {name: subprocess.check_output(["git", "show", BASE + ":" + name], cwd=ROOT, timeout=15)
                for name in INPUTS}
    current = {}
    for name in INPUTS:
        path = ROOT / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("nonregular source: " + name)
        current[name] = path.read_bytes()
    verify_blobs(baseline, current)
    return baseline, current


def build(sdk, destination):
    if platform.system() != "Darwin" or platform.machine() != "x86_64":
        raise RuntimeError("native Intel macOS required")
    destination = Path(destination).resolve()
    if ROOT / "build" not in destination.parents or destination.exists():
        raise ValueError("fresh private output inside worktree build required")
    baseline, current = read_sources()
    sdk_blobs = common.sdk_inputs(sdk)
    recipe = Path(__file__).read_bytes()
    destination.mkdir(parents=True, mode=0o700)
    sdk_copy = destination / "MacKernelSDK-pinned-private"
    for name, blob in sdk_blobs.items():
        path = sdk_copy / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    report = {
        "status": "building-offline", "base_commit": BASE, "kernel_build": 34,
        "candidate_source_sha256": CANDIDATE_SHA, "sdk_commit": common.SDK_PIN,
        "source_sha256": {name: sha(blob) for name, blob in current.items()},
        "sdk_files_sha256_private": {name: sha(blob) for name, blob in sdk_blobs.items()},
        "recipe_sha256": sha(recipe), "roles": {}, "checks": [],
        "installed": False, "loaded": False, "GPU_executed": False,
        "old_admission_modified": False, "hardware_acceptance": False,
    }

    def save():
        (destination / "build-report-private.json").write_text(json.dumps(report, indent=2) + "\n")

    def run(name, command, cwd):
        result = subprocess.run(command, cwd=cwd, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=180)
        log = result.stdout + result.stderr
        (destination / (name + ".log")).write_bytes(log)
        report["checks"].append({"name": name, "returncode": result.returncode, "log_sha256": sha(log)})
        save()
        if result.returncode:
            raise RuntimeError(name + " failed; retain private log")
        return log.decode(errors="replace")

    try:
        save()
        warnings = {}
        for role, blobs in (("baseline", baseline), ("candidate", current)):
            source = destination / role / "source"
            for name, blob in blobs.items():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(blob)
            log = run(role + "-compile", ["nice", "-n", "10", "/bin/sh",
                      str(source / "src/phxbringup/build.sh"), str(sdk_copy)], source)
            warnings[role] = Counter(line.split("warning:", 1)[1].strip()
                                     for line in log.splitlines() if "warning:" in line)
            bundle = destination / role / "PhxBringup.kext"
            shutil.copytree(source / "src/phxbringup/build/PhxBringup.kext", bundle)
            packaged = common.control_metadata(blobs["src/phxbringup/Info.plist"])
            (bundle / "Contents/Info.plist").write_bytes(packaged)
            binary = bundle / "Contents/MacOS/PhxBringup"
            identity = common.macho_identity(binary.read_bytes())
            run(role + "-sign", ["codesign", "--force", "--sign", "-", str(bundle)], source)
            run(role + "-signature", ["codesign", "--verify", "--strict", str(bundle)], source)
            run(role + "-architecture", ["lipo", str(binary), "-verify_arch", "x86_64"], source)
            signed_identity = common.macho_identity(binary.read_bytes())
            if any(signed_identity[key] != identity[key] for key in (
                    "architecture", "filetype", "image_uuid_private")):
                raise ValueError("Mach-O identity drift during signing")
            for name, blob in blobs.items():
                if (source / name).read_bytes() != blob:
                    raise ValueError("frozen source drift")
            report["roles"][role] = {
                "binary_sha256": sha(binary.read_bytes()), "identity_private": signed_identity,
                "bundle_files_sha256_private": common.tree_files(bundle),
                "packaged_plist_sha256": sha(packaged),
                "warning_multiset": dict(warnings[role]),
            }
            save()
        if warnings["baseline"] != warnings["candidate"]:
            raise ValueError("baseline/candidate warning multiset differs")
        if read_sources() != (baseline, current) or Path(__file__).read_bytes() != recipe:
            raise ValueError("build inputs drifted")
        for name, blob in sdk_blobs.items():
            if (sdk_copy / name).read_bytes() != blob:
                raise ValueError("SDK snapshot drift")
        report.update(status="built-and-statically-verified-not-installed", warning_multisets_equal=True)
        save()
    except BaseException as error:
        report.update(status="failed-retained-for-review", error_type=type(error).__name__)
        save()
        raise
    print(json.dumps({key: report[key] for key in (
        "status", "kernel_build", "warning_multisets_equal", "installed", "loaded", "GPU_executed")}))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    build(args.sdk, args.out)
