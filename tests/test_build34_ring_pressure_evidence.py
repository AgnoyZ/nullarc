# SPDX-License-Identifier: MIT
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build34_ring_pressure_evidence import parse


class PressureEvidence(unittest.TestCase):
    def test_requires_exact_overlap_and_success_receipts(self):
        probe = ["GFX 0 0 10 20 1 0 1"]
        for burst in range(1, 5):
            for i in range(1, 5):
                t = (burst * 10 + i) * 1_000_000
                probe.append(f"CMP {burst} {i} {t} {t + 900_000} {burst * 10 + 2 * i}")
            if burst == 1:
                probe.append("GFX 1 1 14300000 14500000 17 12 17")
            probe.append(f"ARENA {burst} {int(burst == 1)} 16384")
        probe.append("DONE pressure probe; both connections closed")
        probe = "\n".join(probe)
        trace = "READY\nWAIT_BLOCK 72 14100000 14700000 3000000 3600000 2\nEND\n\n"
        self.assertEqual(parse(probe, trace, 0, 0, "")["gfx_completions_inside_pressure_sleep"], 1)
        for description, p, t, probe_exit, trace_exit, diag in [
            ("no pressure", probe, "READY\nEND\n", 0, 0, ""),
            ("before GFX completion", probe, trace.replace("14700000", "14400000").replace("3600000", "3300000"), 0, 0, ""),
            ("floor already passed seq", probe.replace("17 12 17", "17 17 17"), trace, 0, 0, ""),
            ("unverified instruction", probe, trace.replace("3600000 2", "3600000 0"), 0, 0, ""),
            ("legacy helper return", probe, trace.replace("WAIT_BLOCK", "WAIT").replace("3600000 2", "3600000 1"), 0, 0, ""),
            ("truncated helper span", probe, trace.replace("14700000", "14105000").replace("3600000", "3005000"), 0, 0, ""),
            ("clock step", probe, trace.replace("3600000", "3200000"), 0, 0, ""),
            ("missing guard test", probe.replace("ARENA 4 0 16384\n", ""), trace, 0, 0, ""),
            ("unclean exit", probe, trace, 74, 0, ""),
            ("trace drops", probe, trace, 0, 0, "drops"),
            ("unclean trace", probe, trace, 0, 1, ""),
        ]:
            with self.subTest(description=description), self.assertRaises(ValueError):
                parse(p, t, probe_exit, trace_exit, diag)


if __name__ == "__main__":
    unittest.main()
