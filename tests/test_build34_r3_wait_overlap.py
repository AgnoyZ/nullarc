# SPDX-License-Identifier: MIT
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build34_r3_wait_overlap import U64_MAX, check


def fixture():
    compute = dict(owner=4, serial=2, slot=0, sequence=100, queue=0, generation=2)
    gfx = dict(owner=5, serial=2, slot=0, sequence=101, queue=1, generation=3)

    def sample(ns, cmp_done, gfx_done, retired):
        return dict(service_epoch=7, ns=ns, retired=retired,
                    compute=dict(generation=2, submitted=100, completed=cmp_done),
                    gfx=dict(generation=3, submitted=101, completed=gfx_done))

    return dict(compute=compute, gfx=gfx,
                wait=dict(service_epoch=7, begin_ns=20, end_ns=30, reply=gfx.copy(), status=0),
                before=sample(10, 96, 97, 96), witness=sample(25, 96, 101, 99),
                after=sample(40, 96, 101, 99),
                drained=sample(50, 100, 101, 101))


def replace(records, path, value):
    names = path.split(".")
    for name in names[:-1]:
        records = records[name]
    records[names[-1]] = value


class OverlapEvidence(unittest.TestCase):
    def test_allows_safe_prefix_progress_below_compute(self):
        result = check(**fixture())
        self.assertEqual(result["status"], "consistent-r3-wait-overlap-records")
        self.assertIs(result["hardware_attested"], False)

    def test_cpu_queue_space_wait_is_not_a_pending_fence(self):
        records = fixture()
        records["after"]["compute"]["completed"] = 100
        with self.assertRaisesRegex(ValueError, "not still pending"):
            check(**records)

    def test_premature_reclaim_at_compute_sequence_refuses(self):
        records = fixture()
        records["after"]["retired"] = 100
        with self.assertRaisesRegex(ValueError, "crossed pending Compute"):
            check(**records)

    def test_completion_observed_only_after_reply_refuses(self):
        records = fixture()
        records["witness"]["gfx"]["completed"] = 97
        with self.assertRaisesRegex(ValueError, "before wait return"):
            check(**records)

    def test_rejects_other_counterexamples(self):
        for path, value in (
            ("wait.status", 1), ("wait.status", False), ("wait.reply.owner", 4),
            ("wait.reply.slot", 1), ("wait.reply.serial", 3), ("wait.reply.generation", 2),
            ("wait.reply.sequence", 100), ("wait.reply.queue", 0),
            ("compute.sequence", 102), ("compute.queue", 1), ("compute.owner", U64_MAX),
            ("after.service_epoch", 8), ("before.ns", 20), ("wait.begin_ns", 30),
            ("after.ns", 29), ("drained.ns", 40), ("witness.ns", 30),
            ("after.compute.generation", 3),
            ("after.gfx.generation", 4), ("before.gfx.completed", 101),
            ("after.gfx.completed", 100), ("after.gfx.submitted", 100),
            ("after.gfx.completed", 102), ("after.compute.completed", 95),
            ("after.retired", 95), ("drained.compute.completed", 99),
            ("drained.gfx.completed", 100), ("drained.retired", 100),
            ("drained.retired", 102), ("after.gfx", None), ("after", None),
        ):
            with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                records = fixture()
                replace(records, path, value)
                check(**records)

    def test_two_slots_from_same_receipt_identity_refuse(self):
        records = fixture()
        records["compute"].update(owner=5, slot=1)
        with self.assertRaisesRegex(ValueError, "distinct receipts"):
            check(**records)


if __name__ == "__main__":
    unittest.main()
