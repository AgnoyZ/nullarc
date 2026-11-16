#!/usr/bin/env python3
"""Check actual pre-IB ring emission; host fakes are not GPU/cache validation."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import resource
import shutil
import subprocess

from prepare_source import ROOT, prepare
from test_queue_retirement import CASES, check_result, extract_source
from upstream34_layout import ib_fetch_sync

BEFORE = "7ef3aa6634c9de47bfe4a65e586aa57ee1d212d1"
PACKET_CASES = tuple(case for case in CASES if case.startswith("packet-"))
METHOD = r"^IOReturn PhxBringup::gpuSubmit\([^\n]*\) \{.*?^\}\n"


def replace_submit(source, replacement):
    bodies = re.findall(METHOD, replacement, re.M | re.S)
    if len(bodies) != 1 or len(re.findall(METHOD, source, re.M | re.S)) != 1:
        raise ValueError("Missing or ambiguous actual submission method")
    return re.sub(METHOD, lambda _: bodies[0], source, flags=re.M | re.S)


def check_regression(result):
    if (result.returncode == 0 or result.stdout or "Assertion" not in result.stderr or
            "p.memory.words == expected && selected.wptr == start + needed" not in result.stderr):
        raise RuntimeError("Previous compute packet did not fail the specific prefix/space assertion")


def exercise(destination):
    compiler = shutil.which("clang++")
    if platform.system() not in ("Darwin", "Linux") or not compiler:
        raise RuntimeError("POSIX Clang++ required; no hardware test is available here")
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Choose a fresh output directory")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    stage = destination / "stage"
    provenance = prepare(stage)
    source = (stage / "src/phxbringup/PhxBringup.cpp").read_text()
    previous = subprocess.check_output(["git", "show", BEFORE + ":src/phxbringup/PhxBringup.cpp"],
                                       cwd=ROOT, text=True, timeout=20)
    backport, backport_provenance = ib_fetch_sync.materialize(destination / "build34-derived")
    backport_source = (backport / ib_fetch_sync.SOURCE).read_text()
    variants = {"downstream-sync": (source, 1), "downstream-control": (source, 0),
                "build34-sync": (replace_submit(source, backport_source), 1),
                "build34-control": (replace_submit(source, backport_source), 0),
                "previous": (replace_submit(source, previous), 0)}
    rows = []
    method_hashes = {}
    for name, (text, policy) in variants.items():
        out = destination / name
        out.mkdir()
        constants, declarations, methods, hashes = extract_source(text)
        for filename, value in zip(("queue-retire-constants.inc", "queue-retire-structures.inc", "queue-retire-methods.inc"),
                                   (constants, declarations, methods)):
            (out / filename).write_text(value + "\n")
        method_hashes[name] = hashes["gpuSubmit"]
        binary = out / "test"
        command = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-g", "-pthread",
                   "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-DPHX_IB_FETCH_SYNC=" + str(policy),
                   "-I" + str(out), "-I" + str(stage / "src/phxbringup"),
                   str(ROOT / "tests/test_queue_retirement.cpp"), "-o", str(binary)]
        build = subprocess.run(command, capture_output=True, timeout=120)
        (out / "compile.log").write_bytes(build.stdout + build.stderr)
        if build.returncode:
            raise RuntimeError("Actual-method test build failed; inspect private log")
        if name == "previous":
            result = subprocess.run([str(binary), "packet-compute"], capture_output=True, text=True, timeout=20)
            check_regression(result)
            continue
        for case in PACKET_CASES:
            chosen = case if policy else case.replace("packet-", "packet-control-", 1)
            result = subprocess.run([str(binary), chosen], capture_output=True, text=True, timeout=20)
            row = check_result(result, chosen)
            rows.append({"variant": name, **row})
    for policy in ("2", "-1"):
        result = subprocess.run([compiler, "-std=c++17", "-x", "c++", "-fsyntax-only", "-include", "stdint.h",
                                 "-I" + str(stage / "src/phxbringup"), "-DPHX_IB_FETCH_SYNC=" + policy, "-"],
                                input='#include "PhxIbFetchSync.h"\n', text=True, capture_output=True, timeout=30)
        if result.returncode == 0 or "PHX_IB_FETCH_SYNC must be 0 or 1" not in result.stderr:
            raise RuntimeError("Nonboolean policy accepted")
    expected = {(variant, case if policy else case.replace("packet-", "packet-control-", 1))
                for variant, (_, policy) in variants.items() if variant != "previous" for case in PACKET_CASES}
    if len(rows) != len(expected) or {(row["variant"], row["case"]) for row in rows} != expected:
        raise RuntimeError("Incomplete or duplicate packet matrix")
    report = {"source_provenance": provenance, "build34_provenance": backport_provenance,
              "actual_submit_method_sha256": method_hashes, "cases": rows,
              "previous_packet_regression_reproduced": True, "invalid_policy_compile_refusals": 2,
              "harness_sha256": hashlib.sha256((ROOT / "tests/test_queue_retirement.cpp").read_bytes()).hexdigest(),
              "hardware_executed": False, "kernel_loaded": False,
              "limitation": "Actual submit/ring/history code with fake VM binding, aperture, doorbell and retirement. "
                            "The build34 check substitutes only its actual submit body into the fake class. "
                            "Packet/space assertions do not reproduce or fix a real GPU cache or output mismatch."}
    (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"packet_scenarios": len(rows), "previous_packet_regression_reproduced": True,
                      "hardware_executed": False}))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    exercise(parser.parse_args().out)
