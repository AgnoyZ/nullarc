"""Exercise actual GART selector guards with fake IOKit; never open a GPU."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GartSelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("clang")
        if not compiler:
            raise RuntimeError("GART selector contracts require Clang")
        cls.temporary = tempfile.TemporaryDirectory(prefix="phx-gart-selector-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.binary = Path(cls.temporary.name) / "fake-gart"
        result = subprocess.run([
            compiler, "-std=c11", "-D_DEFAULT_SOURCE", "-g", "-Wall", "-Wextra",
            "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
            "-I" + str(ROOT / "tests/fake_iokit"), "-I" + str(ROOT / "tools/phxctl"),
            str(ROOT / "tests/test_gart_bootstrap.c"), "-o", str(cls.binary),
        ], capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise RuntimeError("Fake-only GART compile failed: " + result.stderr)

    def invoke(self, fault, relocated):
        result = subprocess.run([str(self.binary), fault] + (["relocated"] if relocated else []),
                                capture_output=True, text=True, timeout=15,
                                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
        rows = re.findall(r"^fake-gart-summary (.*)$", result.stderr, re.M)
        self.assertEqual(1, len(rows), result.stderr)
        counts = json.loads(rows[0])
        self.assertTrue(all(type(value) is int and value >= 0 for value in counts.values()))
        return result, counts

    def mismatch_matrix(self, mode):
        # Independent literal register/write oracle: 138 setup writes precede
        # 16 VMID selections, 31 banked writes and one final idle restoration.
        for relocated in (False, True):
            for ordinal in range(1, 18):
                vmid = ordinal - 1 if ordinal < 17 else 0
                if mode == "zero" and vmid == 0:
                    continue  # Zero is the correct value for these transitions.
                with self.subTest(mode=mode, ordinal=ordinal, relocated=relocated):
                    result, counts = self.invoke(f"vmid-{mode}-{ordinal}", relocated)
                    self.assertEqual(75, result.returncode, result.stderr)
                    requested = vmid * 16
                    immediate = (requested ^ 1 if mode in ("immediate", "both") else
                                 0 if mode == "zero" else
                                 0xffffffff if mode == "ones-immediate" else requested)
                    observed = (requested ^ 1 if mode in ("readback", "both") else
                                0 if mode == "zero" else
                                0xffffffff if mode == "ones-readback" else requested)
                    phase = "restore" if ordinal == 17 else "select"
                    self.assertIn(f"phase={phase} me=0 pipe=0 queue=0 vmid={vmid} "
                                  f"requested=0x{requested:08x} write-readback=0x{immediate:08x} "
                                  f"readback=0x{observed:08x}", result.stderr)
                    prior_banks = 0 if ordinal == 1 else 2 * ordinal - 3 if ordinal < 17 else 31
                    self.assertEqual(138 + ordinal + prior_banks, counts["reg_writes"])
                    self.assertEqual(18 + ordinal, counts["reg_reads"])
                    self.assertEqual(ordinal, counts["selector_writes"])
                    self.assertEqual(prior_banks, counts["bank_writes"])
                    self.assertEqual([1, 1, 1, 1, 2048, 2048, 4, 0, 0, 0],
                                     [counts[key] for key in ("lookups", "opens", "hellos", "snapshots",
                                      "vram_writes", "accepted_words", "vram_reads", "ack_reads", "sleeps", "closes")])
                    self.assertNotIn("gart complete:", result.stdout)

    def test_immediate_reply_mismatch_stops_before_banked_writes(self):
        self.mismatch_matrix("immediate")

    def test_subsequent_read_mismatch_stops_before_banked_writes(self):
        self.mismatch_matrix("readback")

    def test_both_readbacks_mismatched_stops_before_banked_writes(self):
        self.mismatch_matrix("both")

    def test_lost_nonzero_selection_stops_before_banked_writes(self):
        self.mismatch_matrix("zero")

    def test_all_ones_immediate_reply_stops_before_banked_writes(self):
        self.mismatch_matrix("ones-immediate")

    def test_all_ones_subsequent_read_stops_before_banked_writes(self):
        self.mismatch_matrix("ones-readback")

    def test_matching_readbacks_preserve_all_writes_and_invalidation(self):
        for relocated in (False, True):
            with self.subTest(relocated=relocated):
                result, counts = self.invoke("ok", relocated)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual([188, 50, 17, 31, 1, 1], [counts[key] for key in
                                 ("reg_writes", "reg_reads", "selector_writes", "bank_writes", "ack_reads", "closes")])
                self.assertIn("GPU execution unverified", result.stdout)


if __name__ == "__main__":
    unittest.main()
