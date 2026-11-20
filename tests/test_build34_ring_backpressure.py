#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check actual gpuSubmit on CPU doubles, optionally against frozen R1a."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build34_ring_backpressure import submit_method

CASES = (
    "compute-fast", "gfx-fast", "ring-other-queue", "history-space-stolen",
    "new-preferred-queue", "readopt-smaller", "context-invalid", "queue-unready",
    "oversleep-completed", "timeout-exact-wrap", "initial-check-over-budget",
)


class RingBackpressure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory(prefix="phx34-ring-CPU-")
        cls.addClassCleanup(temp.cleanup)
        directory = Path(temp.name)
        fixture = (ROOT / "tests/test_build34_ring_backpressure.cpp").read_bytes()
        marker = b"// PHX34_EXTRACTED_GPU_SUBMIT_FUNCTION"
        if fixture.count(marker) != 1:
            raise ValueError("CPU fixture marker drift")
        driver = Path(os.environ.get("PHX34_RING_TEST_SOURCE", ROOT / "src/phxbringup/PhxBringup.cpp"))
        source = directory / "submit.cpp"
        source.write_bytes(fixture.replace(marker, submit_method(driver.read_bytes())))
        cls.binary = directory / "submit-CPU-only"
        result = subprocess.run([
            "xcrun", "clang++", "-std=c++17", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
            "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer",
            "-I" + str(ROOT / "src/phxbringup"), str(source), "-o", str(cls.binary),
        ], capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise RuntimeError(result.stderr)
        linked = subprocess.check_output(["otool", "-L", str(cls.binary)], text=True, timeout=15)
        if "IOKit.framework" in linked or "Metal.framework" in linked:
            raise RuntimeError("CPU fixture linked a device framework")

    def test_submit(self):
        for case in CASES:
            with self.subTest(case=case):
                result = subprocess.run([str(self.binary), case], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "passed (CPU only)\n")
                self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
