#!/usr/bin/env python3
"""Execute the generated build34 CLI with fake IOKit only; stop before scheduler setup."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from upstream34_layout import mec_range

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = "fake-mec-range "
COUNTERS = ("lookups", "opens", "hellos", "kiq_reads", "kiq_register_writes", "kiq_vram_writes",
            "range_writes", "range_reads", "range_events", "scheduler_entered", "closes")
ARGS = ("arg-missing", "arg-extra", "arg-null", "arg-layout", "arg-sched", "arg-viakiq",
        "arg-all", "arg-gart", "arg-gfx")
GEOMETRY = ("wrong-build", "wrong-build41", "wrong-build42", "wrong-mc", "missing-geometry", "wrong-type", "zero-physical",
            "negative-physical", "unaligned-physical", "overflow-physical", "small-vram", "small-aperture")
HELLO = ("hello-ABI", "hello-build", "hello-build41", "hello-build42", "hello-short", "hello-long", "hello-status")
RANGE_FAULTS = ("write-status", "write-short", "write-long", "write-bad", "write-ones",
                "read-status", "read-short", "read-long", "read-bad", "read-ones")


def cases(policy):
    yield from ("ok", *ARGS, "no-service", *GEOMETRY, "open-status", *HELLO)
    yield from ("kiq-read-status-1", "kiq-read-status-2")
    yield from (f"kiq-register-status-{i}" for i in range(1, 24))
    yield from (f"kiq-vram-status-{i}" for i in (1, 512, 513, 542, 543, 1566, 1567, 1598))
    if policy:
        for step in (1, 2):
            yield from (f"{name}-{step}" for name in RANGE_FAULTS)


def expected_result(policy, fault):
    if type(policy) is not int or policy not in (0, 1) or fault not in cases(policy):
        raise ValueError("Unknown policy or test case")
    c = dict.fromkeys(COUNTERS, 0)
    if fault in ARGS:
        return 64, c
    c["lookups"] = 1
    if fault == "no-service":
        return 1, c
    if fault in GEOMETRY:
        return 1, c
    c["opens"] = 1
    if fault == "open-status":
        return 1, c
    c["hellos"] = 1
    if fault in HELLO:
        return (75 if fault in ("hello-ABI", "hello-build", "hello-build41", "hello-build42") else 74), c
    # Pinned KIQ order: read; 2 register writes; 1598 VRAM writes
    # (512 MQD zeros + 30 MQD fields + 1024 ring zeros + 32 WB zeros);
    # 21 HQD/selection writes; final read. Range init follows all of them.
    events = [("kiq_reads", 1)] + [("kiq_register_writes", i) for i in (1, 2)]
    events += [("kiq_vram_writes", i) for i in range(1, 1599)]
    events += [("kiq_register_writes", i) for i in range(3, 24)] + [("kiq_reads", 2)]
    prefixes = {"kiq_reads": "kiq-read-status", "kiq_register_writes": "kiq-register-status",
                "kiq_vram_writes": "kiq-vram-status"}
    for field, index in events:
        c[field] = index
        if fault == f"{prefixes[field]}-{index}":
            return 74, c
    if policy:
        for step in (1, 2):
            c["range_writes"] = step
            c["range_events"] += 1
            if fault.startswith("write-") and fault.endswith("-" + str(step)):
                return (75 if fault.startswith(("write-bad-", "write-ones-")) else 74), c
            c["range_reads"] = step
            c["range_events"] += 1
            if fault.startswith("read-") and fault.endswith("-" + str(step)):
                return (75 if fault.startswith(("read-bad-", "read-ones-")) else 74), c
    c["scheduler_entered"] = 1
    return 0, c


def check_result(result, policy, fault):
    lines = [line[len(SUMMARY):] for line in result.stdout.splitlines() if line.startswith(SUMMARY)]
    status, expected = expected_result(policy, fault)
    if result.returncode != status or len(lines) != 1:
        raise RuntimeError(f"MEC range case {policy}/{fault}: bad exit/summary: {result.returncode}: {result.stderr}")
    observed = json.loads(lines[0])
    if observed != expected or any(type(value) is not int for value in observed.values()):
        raise RuntimeError(f"MEC range case {policy}/{fault}: incorrect continuation: {observed}; expected {expected}")
    if "Sanitizer" in result.stderr or "DIAGNOSTIC-PASS" in result.stdout:
        raise RuntimeError("Sanitizer error or inappropriate GPU acceptance marker")
    if policy and fault.startswith(("write-bad-", "write-ones-", "read-bad-", "read-ones-")):
        step = int(fault.rsplit("-", 1)[1])
        phase = "write-readback" if fault.startswith("write-") else " readback"
        if f"mec-range trial: step={step}" not in result.stderr or phase not in result.stderr:
            raise RuntimeError("Missing step/readback refusal diagnostic")
    return observed


def exercise(destination):
    if sys.platform != "darwin":
        raise RuntimeError("This harness uses real CoreFoundation and fake IOKit on macOS")
    destination = Path(destination).resolve()
    source, provenance = mec_range.materialize(destination)
    fixture = ROOT / "tests/fixtures/upstream34_mec_range_fake_iokit.c"
    results = []
    for name, policy in provenance["policies"].items():
        binary = destination / ("fake-" + name)
        command = ["/usr/bin/xcrun", "clang", "-std=c11", "-D_DEFAULT_SOURCE", "-O1", "-g", "-Wall", "-Wextra",
                   "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer",
                   "-DPHX34_MEC_RANGE_TRIAL=" + str(policy),
                   '-DPHX34_SOURCE="' + str(source / "mesboot.c") + '"',
                   str(fixture), "-framework", "CoreFoundation", "-o", str(binary)]
        build = subprocess.run(command, capture_output=True, timeout=90)
        (destination / ("fake-build-" + name + ".log")).write_bytes(build.stdout + build.stderr)
        if build.returncode:
            raise RuntimeError("Fake IOKit compilation failed; inspect retained compiler log")
        linked = subprocess.check_output(["/usr/bin/otool", "-L", str(binary)], text=True, timeout=15)
        if "IOKit.framework" in linked:
            raise RuntimeError("Fake CLI must not link IOKit")
        for fault in cases(policy):
            result = subprocess.run([str(binary), fault], capture_output=True, text=True, timeout=10,
                                    env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
            observed = check_result(result, policy, fault)
            results.append({"policy": name, "case": fault, "exit_code": result.returncode, **observed})
    for value in (None, "2", "-1"):
        args = ["/usr/bin/xcrun", "clang", "-std=c11", "-fsyntax-only", str(source / "mesboot.c")]
        if value is not None:
            args += ["-DPHX34_MEC_RANGE_TRIAL=" + value]
        result = subprocess.run(args, capture_output=True, timeout=45)
        if not result.returncode or b"error:" not in result.stderr or b"PHX34_MEC_RANGE_TRIAL" not in result.stderr:
            raise RuntimeError("Missing/nonboolean compile policy was not refused")
    report = {"source_provenance": provenance,
              "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
              "cases": results, "compile_policy_refusals": 3,
              "linked_real_IOKit": False, "hardware_executed": False,
              "limitation": "Actual CLI stops at the first scheduler MQD write. No scheduler, firmware, GPU, CP-idle or output-integrity simulation."}
    (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"cases": len(results), "compile_policy_refusals": 3,
                      "sanitizers": "ASan/UBSan", "hardware_executed": False}))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    exercise(parser.parse_args().out)
