#!/usr/bin/env python3
"""Run actual VBL callback/allocation/drain with CPU clock and scheduler doubles."""
import hashlib
from pathlib import Path
import subprocess

from test_upstream34_framebuffer import method

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = (ROOT / "src/phxaccel/accel/phxfb.cpp").read_text()
    allocation = source[source.index("    fVblTimer = thread_call_allocate"):
                        source.index("    static IOPMPowerState states[2]")]
    stop = method(source, "void PhxAMDFB::stop(IOService *provider)")
    drain = stop[stop.index("    __atomic_store_n(&fStopping"):
                 stop.index("    if (gAliasSysctl)")]
    template = (ROOT / "tests/build34_vbl_scheduling.cpp").read_text()
    for marker, value in {
        "// ACTUAL_VBL_CALLBACK": method(source, "static void vblFire("),
        "// ACTUAL_VBL_ALLOCATION": allocation,
        "// ACTUAL_VBL_DRAIN": drain,
    }.items():
        template = template.replace(marker, value)
    build = ROOT / "build/tests/build34-vbl-scheduling"
    build.mkdir(parents=True, exist_ok=True)
    generated = build / "production.cpp"
    generated.write_text(template)
    binary = build / "test"
    subprocess.run([
        "clang++", "-std=c++17", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
        "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
        "-fno-omit-frame-pointer", str(generated), "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True, timeout=20)
    print("extracted_production_harness_sha256=" + hashlib.sha256(generated.read_bytes()).hexdigest())
    print("hardware_executed=false; XNU scheduling/clock behavior is modeled, not measured")


if __name__ == "__main__":
    main()
