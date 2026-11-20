#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build the reviewed R1b ring-space candidate in a private directory."""
import argparse
from collections import Counter
import json
from pathlib import Path
import platform
import subprocess

from build34_wait_deadline import CANDIDATE_SHA as R1A_SHA
from upstream34_layout import ring_padding_candidate as common

ROOT = Path(__file__).resolve().parents[1]
BASE = "568e80b205c10b00cba4f21c6d324d239d725bfd"
CANDIDATE_SHA = "81f45aa2e8166bc6ebed4106129bebebfd70f9b4bbea6dbe389be46263e3c699"
DRIVER = common.DRIVER
INPUTS = common.SOURCE_INPUTS


def submit_method(blob):
    signature = b"IOReturn PhxBringup::gpuSubmit("
    if blob.count(signature) != 1:
        raise ValueError("require exactly one gpuSubmit method")
    start = blob.index(signature)
    return blob[start:blob.index(b"\n}\n", start) + 3]


def verify_sources(base, candidate):
    if set(base) != set(INPUTS) or set(candidate) != set(INPUTS):
        raise ValueError("source inputs differ from the reviewed set")
    if common.sha(base[DRIVER]) != R1A_SHA or common.sha(candidate[DRIVER]) != CANDIDATE_SHA:
        raise ValueError("unreviewed build34 driver bytes")
    boundary = b"    const uint32_t vmid = vmBind(handle);\n"
    before, after = (submit_method(source[DRIVER]) for source in (base, candidate))
    if (before.count(boundary) != 1 or after.count(boundary) != 1 or
            before.split(boundary)[1] != after.split(boundary)[1] or
            base[DRIVER].replace(before, after, 1) != candidate[DRIVER]):
        raise ValueError("change outside gpuSubmit ring-space admission")
    if any(base[name] != candidate[name] for name in INPUTS if name != DRIVER):
        raise ValueError("protected build input changed")


def read_sources():
    base, candidate = {}, {}
    for name in INPUTS:
        base[name] = subprocess.check_output(["/usr/bin/git", "show", BASE + ":" + name], cwd=ROOT, timeout=15)
        path = ROOT / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("regular source required: " + name)
        candidate[name] = path.read_bytes()
    verify_sources(base, candidate)
    return candidate


def freeze(directory, inputs):
    for name, blob in inputs.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)


def build(sdk, out):
    if platform.system() != "Darwin" or platform.machine() != "x86_64":
        raise RuntimeError("Intel macOS required")
    out = out.resolve()
    if ROOT / "build" not in out.parents or out.exists():
        raise ValueError("fresh output directory inside the ignored worktree build directory required")
    inputs = read_sources()
    sdk_inputs = common.sdk_inputs(sdk)
    recipe = Path(__file__).read_bytes()
    out.mkdir(parents=True, mode=0o700)
    source = out / "source"
    sdk_copy = out / "MacKernelSDK-pinned-private"
    freeze(source, inputs)
    freeze(sdk_copy, sdk_inputs)

    def run(label, *args):
        result = subprocess.run(args, cwd=source, stdin=subprocess.DEVNULL, capture_output=True, timeout=180)
        (out / (label + ".log")).write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(label + " failed; see private log")
        return result.stderr.decode(errors="replace")

    log = run("compile", "/usr/bin/nice", "-n", "10", "/bin/sh",
              str(source / "src/phxbringup/build.sh"), str(sdk_copy))
    bundle = source / "src/phxbringup/build/PhxBringup.kext"
    binary = bundle / "Contents/MacOS/PhxBringup"
    plist = common.control_metadata(inputs["src/phxbringup/Info.plist"])
    (bundle / "Contents/Info.plist").write_bytes(plist)
    identity = common.macho_identity(binary.read_bytes())
    run("sign", "/usr/bin/codesign", "--force", "--sign", "-", str(bundle))
    run("signature", "/usr/bin/codesign", "--verify", "--strict", str(bundle))
    run("architecture", "/usr/bin/lipo", str(binary), "-verify_arch", "x86_64")
    signed = common.macho_identity(binary.read_bytes())
    if any(signed[key] != identity[key] for key in ("architecture", "filetype", "image_uuid_private")):
        raise ValueError("Mach-O identity drift during signing")
    if read_sources() != inputs or Path(__file__).read_bytes() != recipe:
        raise ValueError("worktree inputs drifted during build")
    if any((source / name).read_bytes() != blob for name, blob in inputs.items()):
        raise ValueError("frozen source drift")
    if common.tree_files(sdk_copy) != {name: common.sha(blob) for name, blob in sdk_inputs.items()}:
        raise ValueError("frozen SDK drift")
    report = {
        "status": "built-and-statically-verified", "kernel_build": 34, "r1a_source_commit": BASE,
        "driver_sha256": CANDIDATE_SHA, "sdk_commit": common.SDK_PIN, "recipe_sha256": common.sha(recipe),
        "bundle_files_sha256_private": common.tree_files(bundle), "identity_private": signed,
        "warnings": dict(Counter(line.split("warning:", 1)[1].strip() for line in log.splitlines()
                                 if "warning:" in line)),
        "installed": False, "loaded": False, "GPU_executed": False,
    }
    (out / "build-report-private.json").write_text(json.dumps(report, indent=2) + "\n")
    print("build34 R1b candidate compiled and signed in private output")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    build(args.sdk, args.out)
