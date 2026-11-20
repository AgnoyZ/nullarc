#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Revalidate the frozen R1a artifacts offline; no installation or GPU access.

This separate gate does not change historical build34 admission. It admits only
the already-reviewed monotonic-wait artifacts, not a rebuild with unknown bytes.
"""
import argparse
import copy
import json
from pathlib import Path
import subprocess

import build34_wait_deadline as source

EXE = "Contents/MacOS/PhxBringup"
ACTIVE = "OC/Kexts/PhxBringup.kext/"
RECIPE_SHA = "b5f0fc93e4af721ae25f63f1cf378270468a9e1c32e2a0479341df314923e7da"
PLIST_SHA = "aaeef27a947e0a2a70b358628ff21216a5edaf0a5d65f32651f8654cef654af7"
RESOURCES_SHA = "6686de10a28a2fe11b36cbb86dcbacc827cfc4ea116b4dabf1845e5aee629e9b"
BINARY_SHA = {
    "baseline": "7c2f8d4d68b63f32fba120f60fec0877e1e58607e70253c94d7394883f7cf8e1",
    "candidate": "fab1c35b3be1485bb60aa2e03731f971db922ac56508029057c02d4e40bc16fe",
}
WARNINGS = {"declaration shadows a field of 'PhxBringup' [-Wshadow]": 3}


def expected_files(role):
    return {
        "Contents/Info.plist": {"sha256": PLIST_SHA, "bytes": 1644},
        EXE: {"sha256": BINARY_SHA[role], "bytes": 92112 if role == "baseline" else 92192},
        "Contents/_CodeSignature/CodeResources": {"sha256": RESOURCES_SHA, "bytes": 2200},
    }


def manifest(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("regular bundle directory required")
    result = {}
    for p in sorted(root.rglob("*")):
        if p.is_symlink() or not (p.is_file() or p.is_dir()):
            raise ValueError("linked or special bundle member")
        if p.is_file():
            result[p.relative_to(root).as_posix()] = {
                "sha256": source.sha(p.read_bytes()), "bytes": p.stat().st_size}
    return result


def derive_efi_manifest(before):
    """Retain every exact EFI record, including external Microsoft boot files."""
    if len(before) != 357:
        raise ValueError("fresh complete 357-file accepted EFI required")
    current = {name[len(ACTIVE):]: value for name, value in before.items() if name.startswith(ACTIVE)}
    if current != expected_files("baseline"):
        raise ValueError("active kernel is not the accepted R1a control")
    after = copy.deepcopy(before)
    for name, value in expected_files("candidate").items():
        after[ACTIVE + name] = value
    changed = {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}
    if changed != {ACTIVE + EXE}:
        raise ValueError("R1a must change only the active executable")
    return after


def validate_report(report):
    required = {
        "status": "built-and-statically-verified-not-installed",
        "base_commit": source.BASE, "kernel_build": 34,
        "candidate_source_sha256": source.CANDIDATE_SHA,
        "sdk_commit": source.common.SDK_PIN, "recipe_sha256": RECIPE_SHA,
        "installed": False, "loaded": False, "GPU_executed": False,
        "old_admission_modified": False, "hardware_acceptance": False,
        "warning_multisets_equal": True,
    }
    for key, expected in required.items():
        if key not in report or type(report[key]) is not type(expected) or report[key] != expected:
            raise ValueError("unreviewed native report: " + key)
    if set(report["roles"]) != set(BINARY_SHA):
        raise ValueError("exact baseline/candidate pair required")
    checks = [role + "-" + suffix for role in BINARY_SHA
              for suffix in ("compile", "sign", "signature", "architecture")]
    if [v["name"] for v in report["checks"]] != checks:
        raise ValueError("missing, duplicated or unexpected native check")
    if any(type(v["returncode"]) is not int or v["returncode"] != 0 for v in report["checks"]):
        raise ValueError("native check did not succeed")
    for role, binary in BINARY_SHA.items():
        item = report["roles"][role]
        if (item["binary_sha256"] != binary or item["packaged_plist_sha256"] != PLIST_SHA
                or item["warning_multiset"] != WARNINGS
                or item["bundle_files_sha256_private"] != {
                    name: v["sha256"] for name, v in expected_files(role).items()}):
            raise ValueError("native artifact identity differs: " + role)


def verify(native, sdk):
    native = Path(native)
    baseline, candidate = source.read_sources()
    report = json.loads((native / "build-report-private.json").read_text())
    validate_report(report)
    if source.sha(Path(source.__file__).read_bytes()) != RECIPE_SHA:
        raise ValueError("reviewed build recipe changed")
    if report["source_sha256"] != {name: source.sha(blob) for name, blob in candidate.items()}:
        raise ValueError("native report source set differs")
    sdk_blobs = source.common.sdk_inputs(sdk)
    if report["sdk_files_sha256_private"] != {name: source.sha(blob) for name, blob in sdk_blobs.items()}:
        raise ValueError("SDK source identity differs")
    sdk_snapshot = native / "MacKernelSDK-pinned-private"
    if source.common.tree_files(sdk_snapshot) != report["sdk_files_sha256_private"]:
        raise ValueError("native SDK snapshot differs")
    for role, blobs in (("baseline", baseline), ("candidate", candidate)):
        snapshot = source.common.tree_files(native / role / "source")
        inputs = {name: value for name, value in snapshot.items()
                  if not name.startswith("src/phxbringup/build/")}
        if inputs != {name: source.sha(blob) for name, blob in blobs.items()}:
            raise ValueError("unexpected native source snapshot files")
        for name, blob in blobs.items():
            p = native / role / "source" / name
            if p.is_symlink() or p.read_bytes() != blob:
                raise ValueError("native source snapshot differs")
        bundle = native / role / "PhxBringup.kext"
        if manifest(bundle) != expected_files(role):
            raise ValueError("native bundle bytes differ: " + role)
        identity = source.common.macho_identity((bundle / EXE).read_bytes())
        if identity != report["roles"][role]["identity_private"]:
            raise ValueError("native Mach-O identity differs")
        subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(bundle)],
                       check=True, capture_output=True, timeout=20)
    for item in report["checks"]:
        if source.sha((native / (item["name"] + ".log")).read_bytes()) != item["log_sha256"]:
            raise ValueError("native check log differs")
    return dict(status="passed-frozen-R1a-artifacts-offline", kernel_build=34,
                exact_source_recipe_SDK_and_bundle_pair=True, strict_signatures=True,
                driver_change_only_doWaitSeq=True, installation_performed=False,
                runtime_installation_state_checked=False, GPU_calls=0,
                hardware_acceptance_evaluated=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--sdk", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.native, args.sdk), sort_keys=True))
