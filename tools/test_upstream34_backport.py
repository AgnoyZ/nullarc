#!/usr/bin/env python3
"""Validate the isolated upstream34 backport; never load/install drivers or use a GPU."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = "90bb06f6f9255cb5a16cc5eb87e78032566b2000"
VULKAN_PIN = "6802bb4733b63ed5efd3adb308a6c885ef180ea1"
A1_SOURCE = {
    "src/nmplugin/NVMTLEventSync.m", "src/nmplugin/NVMTLObjects.m",
    "src/nmplugin/nvmtl_vk.c", "src/nmplugin/nvmtl_vk.h",
    "src/nmplugin/nvmtl_sampler_key.h", "src/nmplugin/nvmtl_surface_key.h",
}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=30)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protected_inputs():
    names = git("ls-tree", "-r", "--name-only", BASE, "src", "tools/phxctl",
                "LICENSE", "LICENSES", "THIRD_PARTY_NOTICES.md").decode().splitlines()
    protected = {}
    for name in names:
        if name in A1_SOURCE:
            continue
        path = ROOT / name
        expected = hashlib.sha256(git("show", BASE + ":" + name)).hexdigest()
        if not path.is_file() or digest(path) != expected:
            raise RuntimeError("Unrelated baseline input changed: " + name)
        protected[name] = expected
    changed = set(git("diff", "--name-only", BASE, "--", "src").decode().splitlines())
    changed.update(git("ls-files", "--others", "--exclude-standard", "src").decode().splitlines())
    if changed != A1_SOURCE:
        raise RuntimeError("Source delta is not exactly A1: " + repr(sorted(changed)))
    return protected


def validate(args):
    if platform.system() != "Darwin" or platform.machine() != "x86_64":
        raise RuntimeError("This native validation requires Intel macOS")
    headers = args.vulkan_headers.resolve()
    pin = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=headers, text=True).strip()
    if pin != VULKAN_PIN or not (headers / "include/vulkan/vulkan.h").is_file():
        raise RuntimeError("Use the reviewed pinned Vulkan-Headers checkout")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {
        "stage": "a1", "baseline": BASE, "result": "running",
        "upstream_kernel_build": 34,
        "os_version": subprocess.check_output(["sw_vers", "-productVersion"], text=True).strip(),
        "os_build": subprocess.check_output(["sw_vers", "-buildVersion"], text=True).strip(),
        "compiler": subprocess.check_output(["xcrun", "clang", "--version"], text=True).splitlines()[0],
        "vulkan_headers_commit": pin, "checks": [],
        "hardware_executed": False, "installed": False, "plugin_loaded": False,
        "fps_measured": False,
    }
    env = dict(os.environ, CPPFLAGS="-I" + str(headers / "include"))

    def save():
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    def run(name, command, timeout=180):
        print("CHECK", name, flush=True)
        log = out / (name + ".log")
        with log.open("wb") as stream:
            result = subprocess.run(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                    stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
        report["checks"].append({"name": name, "exit_code": result.returncode,
                                 "log_sha256": digest(log)})
        save()
        if result.returncode:
            raise RuntimeError(name + " failed; inspect " + str(log))

    try:
        report["protected_inputs_sha256"] = protected_inputs()
        report["source_sha256"] = {name: digest(ROOT / name) for name in sorted(A1_SOURCE)}
        run("baseline-unit", ["make", "test", "CXX=clang++"])
        run("baseline-layout", ["make", "test-upstream34-layout"])
        run("sampler-keys", ["make", "test-nmplugin-sampler-key"])
        run("surface-keys", ["make", "test-nmplugin-surface-key"])
        run("descriptor-masks", ["make", "test-nmplugin-descriptor-mask"])
        binary = out / "NVMTLDriver"
        command = ["xcrun", "clang", "-arch", "x86_64", "-mmacosx-version-min=15.0",
                   "-bundle", "-fobjc-arc", "-O1", "-DNVMTL_RELEASE=1",
                   "-Wno-protocol", "-Wno-incomplete-implementation",
                   "-Werror=unguarded-availability-new", "-I" + str(headers / "include"),
                   str(ROOT / "src/nmplugin/NVMTLDevice.m"), "-o", str(binary)]
        for framework in ["Foundation", "Metal", "IOSurface", "IOKit", "CoreFoundation"]:
            command += ["-framework", framework]
        run("native-plugin-build", command)
        run("native-plugin-sign", ["codesign", "--force", "--sign", "-", str(binary)])
        run("native-plugin-signature", ["codesign", "--verify", "--strict", str(binary)])
        run("native-plugin-arch", ["lipo", str(binary), "-verify_arch", "x86_64"])
        exports = subprocess.check_output(["xcrun", "nm", "-gU", str(binary)], text=True)
        if "_OBJC_CLASS_$_NVMTLDevice" not in exports or "_OBJC_METACLASS_$_NVMTLDevice" not in exports:
            raise RuntimeError("Native plugin lacks its device entry point")
        report["plugin_sha256"] = digest(binary)
        run("diff-whitespace", ["git", "diff", "--check"])
        report["result"] = "passed"
    except Exception:
        report["result"] = "failed"
        raise
    finally:
        save()
    print(json.dumps({"stage": report["stage"], "result": report["result"],
                      "checks": len(report["checks"]), "hardware_executed": False,
                      "installed": False}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vulkan-headers", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    validate(parser.parse_args())
