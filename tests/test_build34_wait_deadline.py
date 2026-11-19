#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run the actual build34 wait method against CPU clocks/fences; never use IOKit.

PHX34_WAIT_TEST_SOURCE optionally selects a frozen baseline for regression
replay. It is a CPU test input, never a driver admission or deployment gate.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get("PHX34_WAIT_TEST_SOURCE", ROOT / "src/phxbringup/PhxBringup.cpp"))
CASES = (
    "not-hello", "bad-shape", "future-sequence", "not-adopted", "already-retired",
    "last-sequence", "zero-target", "zero-pending", "zero-ready", "one-nanosecond",
    "normal-fast-timeout", "delay-overshoot", "delay-boundary", "initial-poll-over-budget",
    "elapsed-phase", "sleep-overshoot", "cap-budget", "non-unit-timebase", "clock-wrap",
    "completion-after-delay", "completion-at-deadline", "completion-after-oversleep",
    "completion-after-sleep", "pending-retained", "fence-published", "newer-fence-retained",
    "missing-fence-bo", "short-fence-bo", "unmapped-fence-bo",
)


def wait_method(text):
    signature = "IOReturn IOAccelPhxNativeClient::doWaitSeq("
    if text.count(signature) != 1:
        raise ValueError("require one production wait method")
    start = text.index(signature)
    brace = text.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


class WaitDeadline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="phx34-wait-CPU-")
        cls.addClassCleanup(cls.temp.cleanup)
        directory = Path(cls.temp.name)
        fixture = (ROOT / "tests/test_build34_wait_deadline.cpp").read_text()
        marker = "// PHX34_EXTRACTED_WAIT_SEQ_METHOD"
        if fixture.count(marker) != 1:
            raise ValueError("CPU fixture marker drift")
        code = fixture.replace(marker, wait_method(SOURCE.read_text()))
        source = directory / "wait.cpp"
        source.write_text(code)
        cls.binary = directory / "wait-CPU-only"
        compile_result = subprocess.run([
            "xcrun", "clang++", "-std=c++17", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-function", "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
            "-fno-omit-frame-pointer", "-I" + str(ROOT / "src/phxbringup"),
            str(source), "-o", str(cls.binary),
        ], capture_output=True, text=True, timeout=90)
        if compile_result.returncode:
            raise RuntimeError(compile_result.stderr)
        linked = subprocess.check_output(["otool", "-L", str(cls.binary)], text=True, timeout=15)
        if "IOKit.framework" in linked or "Metal.framework" in linked:
            raise RuntimeError("CPU fixture linked a device framework")

    def run_case(self, name):
        result = subprocess.run([str(self.binary), name], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        row = json.loads(result.stdout)
        self.assertEqual(row["case"], name)
        self.assertIs(row["passed"], True)
        self.assertIs(row["GPU_executed"], False)


def case_method(name):
    def test(self):
        self.run_case(name)
    return test


for case in CASES:
    setattr(WaitDeadline, "test_" + case.replace("-", "_"), case_method(case))

if __name__ == "__main__":
    unittest.main()
