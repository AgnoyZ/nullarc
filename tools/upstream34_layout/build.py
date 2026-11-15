#!/usr/bin/env python3
"""Materialize/build only the pinned upstream-34 user helpers; never install or run them."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
HEADER = ROOT / "tools/phxctl/PhxUpstream34Layout.h"
UPSTREAM = "9dd76b604fca5e0125bd3caa5723df0f611ff27f"
FILES = ["mesboot.c", "phxctl.c", "mes_v11_api_def.h", "csb_gfx11.h", "bringup5.sh", "full.sh"]


def run(args, **kwargs):
    result = subprocess.run(args, stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=120, **kwargs)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return result.stdout


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def materialize(destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Destination must not exist; never overwrite a prior candidate")
    destination.mkdir(parents=True, mode=0o700)
    source = destination / "source/tools/phxctl"
    source.mkdir(parents=True)
    pins = {}
    for name in FILES:
        blob = run(["git", "show", UPSTREAM + ":tools/phxctl/" + name], cwd=ROOT)
        (source / name).write_bytes(blob)
        pins[name] = digest(source / name)
    for name in ["LICENSE", "THIRD_PARTY_NOTICES.md", "LICENSES/MIT.txt", "LICENSES/GPL-2.0-only.txt"]:
        p = destination / "source" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(run(["git", "show", UPSTREAM + ":" + name], cwd=ROOT))
    # Stop repository discovery at this generated tree, even when it is under build/.
    environment = dict(os.environ, GIT_CEILING_DIRECTORIES=str(destination))
    patch = str(HERE / "layout-fix.patch")
    run(["git", "apply", "--check", patch], cwd=destination / "source", env=environment)
    run(["git", "apply", patch], cwd=destination / "source", env=environment)
    shutil.copyfile(HEADER, source / "PhxUpstream34Layout.h")
    for candidate in source.iterdir():
        checked_in = ROOT / "tools/phxctl" / candidate.name
        if candidate.read_bytes() != checked_in.read_bytes():
            raise ValueError("Checked-in helper differs from pinned patch: " + candidate.name)
    record = {"upstream_commit": UPSTREAM, "upstream_build": 34,
              "upstream_inputs_sha256": pins,
              "recipe_sha256": {p.name: digest(p) for p in [Path(__file__), HERE / "layout-fix.patch", HEADER]},
              "modified_source_sha256": {p.name: digest(p) for p in source.iterdir()},
              "kernel_source_or_build_label_modified": False,
              "driver_compiled_installed_or_executed": False}
    (destination / "source-manifest.json").write_text(json.dumps(record, indent=2) + "\n")
    return source, record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--compile", action="store_true")
    args = parser.parse_args()
    source, record = materialize(args.destination)
    if args.compile:
        binaries = args.destination.resolve() / "bin"
        binaries.mkdir()
        for name in ["mesboot", "phxctl"]:
            p = binaries / name
            result = subprocess.run(
                ["/usr/bin/xcrun", "clang", "-arch", "x86_64", "-mmacosx-version-min=12.0",
                 "-O2", "-Wall", "-Wextra", str(source / (name + ".c")),
                 "-framework", "IOKit", "-framework", "CoreFoundation", "-o", str(p)],
                stdin=subprocess.DEVNULL, capture_output=True, timeout=120)
            (args.destination / ("native-build-" + name + ".log")).write_bytes(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError("Native build failed; inspect the retained compiler log")
            run(["/usr/bin/codesign", "--force", "--sign", "-", str(p)])
            run(["/usr/bin/codesign", "--verify", "--strict", str(p)])
            run(["/usr/bin/lipo", str(p), "-verify_arch", "x86_64"])
        record["binaries_sha256"] = {p.name: digest(p) for p in binaries.iterdir()}
        (args.destination / "native-build.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"upstream_commit": UPSTREAM, "build": 34, "compiled": args.compile,
                      "kernel_modified": False, "installed": False, "GPU_executed": False}))


if __name__ == "__main__":
    main()
