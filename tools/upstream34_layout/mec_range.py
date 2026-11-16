#!/usr/bin/env python3
"""Materialize/compile an isolated default-build34 MEC-range pair; never run/install."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASE = "64f3d991a4ddc3af5bbf30cbced9f11d3e7dd50c"
REFERENCE_PR_HEAD = "9f37791bb816092df580f3cb62a9db1e2357fb8f"
INPUTS = {
    "mesboot.c": "7a1e4de45589a40b3259bd33a790d9d537498e139fa56719145438801320a21f",
    "PhxUpstream34Layout.h": "2f7e3124a99e97469debc9ee5d9bb760092c769ef530f99814257bc314f54de1",
    "mes_v11_api_def.h": "7b1b1e895e0faba305f1832bb815c617b51cbbdc6701dea4aa2084b52806b71a",
    "csb_gfx11.h": "f7400527d24ec6a60200ab670a2a78ac0f123d11dda4cc6b745a48e7b1e0d805",
}
HEADER = "PhxMecDoorbellRangeTrial.h"
PROTECTED_PATHS = ("src/phxbringup", "tools/phxctl", "LICENSE", "LICENSES", "THIRD_PARTY_NOTICES.md")
SCHED = b"static void sched_test(void)\n{\n   sched_init();"
SCHED_TRIAL = (b'#include "PhxMecDoorbellRangeTrial.h"\n\n'
               b"static void sched_test(void)\n{\n   phx34_mec_range_init();\n   sched_init();")
ENTRY = b"int main(int argc, char **argv)\n{\n   if (open_kext()) return 1;"
ENTRY_TRIAL = (b"int main(int argc, char **argv)\n{\n"
               b'   if (argc != 2 || !argv || !argv[1] || strcmp(argv[1], "kiqsched")) {\n'
               b'      fprintf(stderr, "mec-range candidate: only kiqsched is supported; external bounded containment required\\n");\n'
               b"      return 64;\n   }\n   if (open_kext()) return 1;")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_base(path):
    return subprocess.check_output(["git", "show", BASE + ":" + path], cwd=ROOT, timeout=20)


def protected_base_inputs():
    names = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", BASE, "--", *PROTECTED_PATHS],
        cwd=ROOT, text=True, timeout=20).splitlines()
    if "src/phxbringup/PhxBringup.cpp" not in names or "tools/phxctl/mesboot.c" not in names:
        raise ValueError("Original build34 production inputs are unavailable")
    return {name: read_base(name) for name in names}


def verify_current_inputs(expected, current_root):
    """Refuse current production-source drift before creating a diagnostic pair."""
    for name, data in expected.items():
        path = current_root / name
        if not path.is_file() or path.read_bytes() != data:
            raise ValueError("Current source differs from original build34: " + name)
    return {name: sha(data) for name, data in expected.items()}


def transform(base):
    if sha(base) != INPUTS["mesboot.c"] or base.count(SCHED) != 1 or base.count(ENTRY) != 1:
        raise ValueError("Pinned original-build34 source/hash/anchors do not match")
    result = base.replace(SCHED, SCHED_TRIAL).replace(ENTRY, ENTRY_TRIAL)
    if result.replace(SCHED_TRIAL, SCHED).replace(ENTRY_TRIAL, ENTRY) != base:
        raise ValueError("Candidate changed bytes outside its two exact insertion sites")
    return result


def materialize(destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Destination must not exist; never overwrite a candidate")
    protected = protected_base_inputs()
    verified = verify_current_inputs(protected, ROOT)
    blobs = {name: read_base("tools/phxctl/" + name) for name in INPUTS}
    if any(sha(blobs[name]) != digest for name, digest in INPUTS.items()):
        raise ValueError("Pinned input hash mismatch; no candidate created")
    notices = {name: read_base(name) for name in
               ("LICENSE", "THIRD_PARTY_NOTICES.md", "LICENSES/MIT.txt", "LICENSES/GPL-2.0-only.txt")}
    candidate = transform(blobs["mesboot.c"])
    header = (HERE / HEADER).read_bytes()
    destination.mkdir(parents=True, mode=0o700)
    source = destination / "source/tools/phxctl"
    source.mkdir(parents=True)
    for name, data in blobs.items():
        (source / name).write_bytes(candidate if name == "mesboot.c" else data)
    (source / HEADER).write_bytes(header)
    for name, data in notices.items():
        target = destination / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    record = {
        "base_commit": BASE, "reference_PR_head": REFERENCE_PR_HEAD,
        "base_inputs_sha256": INPUTS,
        "recipe_sha256": sha(Path(__file__).read_bytes()), "trial_header_sha256": sha(header),
        "candidate_mesboot_sha256": sha(candidate),
        "notices_sha256": {name: sha(data) for name, data in notices.items()},
        "supported_command": "kiqsched", "policy_macro": "PHX34_MEC_RANGE_TRIAL",
        "policies": {"control": 0, "mec-range": 1},
        "current_production_inputs_sha256": verified,
        "kernel_or_production_helpers_modified": False,
        "build34_only": True, "installed": False, "GPU_executed": False,
    }
    (destination / "source-manifest.json").write_text(json.dumps(record, indent=2) + "\n")
    return source, record


def compile_pair(destination, source, record):
    if sys.platform != "darwin":
        raise RuntimeError("Native pair compilation requires macOS; materialization remains available")
    binaries = destination / "bin"
    binaries.mkdir()
    for policy, number in record["policies"].items():
        binary = binaries / ("mesboot-" + policy)
        command = ["/usr/bin/xcrun", "clang", "-arch", "x86_64", "-mmacosx-version-min=12.0",
                   "-std=c11", "-D_DEFAULT_SOURCE", "-O2", "-Wall", "-Wextra",
                   "-DPHX34_MEC_RANGE_TRIAL=" + str(number), str(source / "mesboot.c"),
                   "-framework", "IOKit", "-framework", "CoreFoundation", "-o", str(binary)]
        result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, timeout=90)
        (destination / ("native-build-" + policy + ".log")).write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError("Native compile failed; inspect retained compiler log")
        for args in (("/usr/bin/codesign", "--force", "--sign", "-", str(binary)),
                     ("/usr/bin/codesign", "--verify", "--strict", str(binary)),
                     ("/usr/bin/lipo", str(binary), "-verify_arch", "x86_64")):
            subprocess.run(args, check=True, stdin=subprocess.DEVNULL, capture_output=True, timeout=20)
    record = {**record, "binaries_sha256": {p.name: sha(p.read_bytes()) for p in binaries.iterdir()},
              "native_compiled_signed_arch_verified": True, "native_binaries_run": False}
    (destination / "native-build.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--compile", action="store_true")
    args = parser.parse_args()
    source, record = materialize(args.destination)
    if args.compile:
        record = compile_pair(args.destination.resolve(), source, record)
    print(json.dumps({"base_commit": BASE, "compiled": args.compile, "installed": False,
                      "GPU_executed": False, "candidate_mesboot_sha256": record["candidate_mesboot_sha256"]}))


if __name__ == "__main__":
    main()
