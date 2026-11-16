#!/usr/bin/env python3
"""Build an isolated build34-derived pre-IB sync pair; never install/load/run it."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from prepare_source import export_archive

BASE = "64f3d991a4ddc3af5bbf30cbced9f11d3e7dd50c"
SOURCE = "src/phxbringup/PhxBringup.cpp"
SOURCE_SHA256 = "beffab5dc13e4018ff2ab9f90c82d85c0982ce7e3563e3175999399c7bc083e5"
HEADER = "PhxIbFetchSync.h"
BUILD = 42
REPLACEMENTS = (
    ('#include "PhxNativeABI.h"\n', '#include "PhxNativeABI.h"\n#include "PhxIbFetchSync.h"\n'),
    ('#define PHX_KEXT_BUILD 34u', '#define PHX_KEXT_BUILD 42u'),
    ('    const uint32_t need = n * 4 + 8;',
     '    const uint32_t syncDw = PHX_IB_FETCH_SYNC && !q.gfx ? phxIbFetchSyncDwords : 0;\n'
     '    const uint32_t need = syncDw + n * 4 + 8;'),
    ('    uint32_t k = 0;\n    for (uint32_t i = 0; i < n; i++) {',
     '    uint32_t k = 0;\n'
     '    // Synchronize compute command visibility before fetching the first user IB.\n'
     '    for (uint32_t i = 0; i < syncDw; ++i)\n'
     '        ringPut(q, k++, phxIbFetchSyncPacket[i]);\n'
     '    for (uint32_t i = 0; i < n; i++) {'),
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def transform(data):
    if sha(data) != SOURCE_SHA256:
        raise ValueError("Fixed build34 source hash mismatch")
    text = data.decode()
    for before, after in REPLACEMENTS:
        if text.count(before) != 1:
            raise ValueError("Fixed source insertion is missing or ambiguous")
        text = text.replace(before, after)
    restored = text
    for before, after in reversed(REPLACEMENTS):
        restored = restored.replace(after, before)
    if restored.encode() != data:
        raise ValueError("Changes outside the reviewed four sites")
    return text.encode()


def materialize(destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Output already exists; never overwrite a prior candidate")
    base = subprocess.check_output(["git", "show", BASE + ":" + SOURCE], cwd=ROOT, timeout=20)
    candidate = transform(base)
    archive = subprocess.check_output(["git", "archive", BASE, "src/phxbringup", "src/amd/phx_topology.h", "LICENSE", "LICENSES",
                                       "THIRD_PARTY_NOTICES.md"], cwd=ROOT, timeout=30)
    destination.mkdir(parents=True, mode=0o700)
    source = destination / "source"
    export_archive(archive, source)
    (source / SOURCE).write_bytes(candidate)
    header = (ROOT / "src/phxbringup" / HEADER).read_bytes()
    (source / "src/phxbringup" / HEADER).write_bytes(header)
    record = {"base_commit": BASE, "base_source_sha256": sha(base), "candidate_build": BUILD,
              "candidate_source_sha256": sha(candidate), "header_sha256": sha(header),
              "recipe_sha256": sha(Path(__file__).read_bytes()),
              "policies": {"control": 0, "fetch-sync": 1},
              "policy_macro": "PHX_IB_FETCH_SYNC", "original_build34_image": False,
              "wait_correction_or_MEC_range_change_included": False,
              "source_files_sha256": {str(p.relative_to(source)): sha(p.read_bytes())
                                      for p in sorted(source.rglob("*")) if p.is_file()},
              "installed": False, "GPU_executed": False}
    (destination / "source-manifest.json").write_text(json.dumps(record, indent=2) + "\n")
    return source, record


def compile_pair(destination, source, record, sdk):
    if sys.platform != "darwin":
        raise RuntimeError("Kernel compilation requires macOS")
    sdk = Path(sdk).resolve()
    if not (sdk / "Headers/IOKit/IOLib.h").is_file() or not (sdk / "Library/x86_64").is_dir():
        raise ValueError("MacKernelSDK headers/libraries missing")
    flags = ["-arch", "x86_64", "-mmacosx-version-min=11.0", "-mkernel", "-fno-builtin", "-fno-common",
             "-nostdinc", "-I" + str(sdk / "Headers"), "-DKERNEL", "-DKERNEL_PRIVATE", "-DDRIVER_PRIVATE",
             "-DAPPLE", "-DNeXT", "-Os", "-Wall"]
    component = source / "src/phxbringup"
    binaries = {}
    for policy, number in record["policies"].items():
        output = destination / policy
        bundle = output / "PhxBringup.kext/Contents"
        (bundle / "MacOS").mkdir(parents=True)
        binary = bundle / "MacOS/PhxBringup"
        commands = [
            ["/usr/bin/xcrun", "clang", "-x", "c", *flags, "-c", str(component / "kmod_info.c"), "-o", str(output / "kmod.o")],
            ["/usr/bin/xcrun", "clang++", *flags, "-std=c++17", "-fapple-kext", "-fno-rtti", "-fno-exceptions",
             "-DPHX_IB_FETCH_SYNC=" + str(number), "-c", str(component / "PhxBringup.cpp"), "-o", str(output / "kernel.o")],
            ["/usr/bin/xcrun", "clang++", "-arch", "x86_64", "-mmacosx-version-min=11.0", "-nostdlib", "-Xlinker", "-kext",
             "-L" + str(sdk / "Library/x86_64"), "-lkmod", "-lcc_kext", str(output / "kmod.o"), str(output / "kernel.o"), "-o", str(binary)],
        ]
        with (output / "compile.log").open("xb") as log:
            for command in commands:
                result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log, timeout=120)
                if result.returncode:
                    raise RuntimeError("Kernel compile/link failed; inspect private log")
        shutil.copyfile(component / "Info.plist", bundle / "Info.plist")
        for command in (["/usr/bin/codesign", "--force", "--sign", "-", str(bundle.parent)],
                        ["/usr/bin/codesign", "--verify", "--strict", str(bundle.parent)],
                        ["/usr/bin/lipo", str(binary), "-verify_arch", "x86_64"]):
            subprocess.run(command, check=True, capture_output=True, stdin=subprocess.DEVNULL, timeout=30)
        binaries[policy] = sha(binary.read_bytes())
    record = {**record, "binaries_sha256": binaries, "native_compile_sign_arch_passed": True,
              "native_binaries_run": False}
    (destination / "native-build.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--sdk", type=Path, help="Compile both policies against this MacKernelSDK; never load")
    args = parser.parse_args()
    source, record = materialize(args.destination)
    if args.sdk:
        record = compile_pair(args.destination.resolve(), source, record, args.sdk)
    print(json.dumps({"candidate_build": BUILD, "compiled": bool(args.sdk), "installed": False, "GPU_executed": False}))
