#!/usr/bin/env python3
"""Exercise the real recovery journal with inert host operations."""

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import tempfile
from threading import Barrier
import unittest


SPEC = importlib.util.spec_from_file_location(
    "build34_startup_recovery",
    Path(__file__).resolve().parents[1] / "tools/build34_startup_recovery.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class StartupRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.recovery = m.StartupRecovery(self.root)
        self.events = []

    def arm(self, restart):
        self.recovery.prepare("preparation", permit_recovery_restart=restart)
        self.assertTrue(self.recovery.begin_trial("trial"))

    def actions(self):
        def checked(event):
            self.events.append(event)
            return True

        def power():
            self.assertEqual(json.loads((self.root / "recovery-restart.intent").read_text()),
                             {"boot": "trial", "requests": 1})
            checked("restart")

        return dict(quiesce=lambda: checked("stop"), restore=lambda: checked("restore"),
                    verify=lambda: checked("readback"),
                    prepare_restart=lambda: checked("panel-armed"), request_restart=power)

    def call(self, boot="trial", **changes):
        return self.recovery.recover(
            boot, reason="framebuffer-admission", **dict(self.actions(), **changes))

    def test_failure_restores_and_reads_back_before_one_restart(self):
        self.arm(True)
        self.assertTrue(self.call())
        self.assertEqual(self.events, ["stop", "restore", "readback", "panel-armed", "restart"])
        self.assertFalse(self.recovery.begin_trial("recovery-boot"))
        self.assertFalse(self.recovery.startup_accepted("trial"))
        self.assertFalse(self.call("recovery-boot"))
        self.assertFalse(self.call())
        self.assertEqual(self.events.count("restart"), 1)

    def test_disk_only_permission_cannot_dispatch_power(self):
        self.arm(False)
        self.assertTrue(self.call())
        self.assertEqual(self.events, ["stop", "restore", "readback"])
        self.assertFalse((self.root / "recovery-restart.intent").exists())

    def test_success_closes_startup_only_recovery(self):
        self.arm(True)
        self.assertTrue(self.recovery.accept_startup("trial"))
        self.assertTrue(self.recovery.startup_accepted("trial"))
        self.assertFalse(self.recovery.startup_accepted("next-day"))
        self.assertFalse(self.call())
        self.assertFalse(self.recovery.begin_trial("next-day"))
        self.assertEqual(self.events, [])

    def test_watch_automatically_recovers_on_explicit_failure(self):
        self.recovery.prepare("preparation", permit_recovery_restart=True)
        states = iter([None, "framebuffer-admission"])
        self.assertEqual(self.recovery.watch("trial", read_admission=lambda: next(states),
                                             sleep=lambda _: None, recovery_actions=self.actions()),
                         "rolled-back-on-disk")
        self.assertEqual(self.events.count("restart"), 1)
        outcome = json.loads((self.root / "outcome.json").read_text())
        self.assertEqual(outcome["reason"], "framebuffer-admission")

    def test_watch_times_out_a_missing_boot_receipt_without_retrying(self):
        self.recovery.prepare("preparation", permit_recovery_restart=True)
        now = 0

        def sleep(duration):
            nonlocal now
            self.assertGreater(duration, 0)
            self.assertLessEqual(duration, 1)
            now += duration

        args = dict(read_admission=lambda: None, monotonic=lambda: now,
                    sleep=sleep, recovery_actions=self.actions())
        self.assertEqual(self.recovery.watch("trial", **args), "rolled-back-on-disk")
        self.assertEqual(now, 300)
        self.assertEqual(self.recovery.watch("trial", **args), "closed")
        self.assertEqual(self.events.count("restart"), 1)
        outcome = json.loads((self.root / "outcome.json").read_text())
        self.assertEqual(outcome["reason"], "startup-deadline")

    def test_watch_accepts_success_and_runs_no_recovery_actions(self):
        self.recovery.prepare("preparation", permit_recovery_restart=True)
        args = dict(read_admission=lambda: True, recovery_actions=self.actions())
        self.assertEqual(self.recovery.watch("trial", **args), "accepted")
        self.assertEqual(self.recovery.watch("trial", **args), "closed")
        self.assertTrue(self.recovery.startup_accepted("trial"))
        self.assertEqual(self.events, [])

    def test_unarmed_preparation_and_later_boot_are_refused(self):
        self.assertFalse(self.recovery.begin_trial("trial"))
        self.assertFalse(self.call())
        self.recovery.prepare("preparation", permit_recovery_restart=True)
        self.assertFalse(self.recovery.begin_trial("preparation"))
        self.assertFalse(self.call("preparation"))
        self.assertTrue(self.recovery.begin_trial("trial"))
        self.assertTrue(self.recovery.begin_trial("trial"))
        self.assertFalse(self.recovery.begin_trial("unrelated"))
        self.assertFalse(self.recovery.accept_startup("unrelated"))
        self.assertFalse(self.call("unrelated"))
        self.assertEqual(self.events, [])

    def test_unknown_worker_stops_recovery_before_disk_mutation(self):
        self.arm(True)
        with self.assertRaisesRegex(RuntimeError, "trial stopped"):
            self.call(quiesce=lambda: False)
        self.assertEqual(self.events, [])
        self.assertFalse(self.call())

    def test_unknown_efi_prevents_power_and_never_replays_rollback(self):
        self.arm(True)
        with self.assertRaisesRegex(RuntimeError, "independent readback"):
            self.call(verify=lambda: False)
        self.assertEqual(self.events, ["stop", "restore"])
        self.assertFalse(self.call())
        self.assertFalse((self.root / "recovery-restart.intent").exists())

    def test_panel_arm_missing_after_prepare_prevents_power(self):
        self.arm(True)
        with self.assertRaisesRegex(RuntimeError, "not ready"):
            self.call(prepare_restart=lambda: False)
        self.assertFalse(self.call())
        self.assertFalse((self.root / "recovery-restart.intent").exists())

    def test_uncertain_power_result_does_not_allow_second_call(self):
        self.arm(True)

        def timeout():
            self.assertTrue((self.root / "recovery-restart.intent").is_file())
            self.events.append("power submitted")
            raise TimeoutError("unknown exit")

        with self.assertRaises(TimeoutError):
            self.call(request_restart=timeout)
        self.assertFalse(self.call())
        self.assertEqual(self.events.count("power submitted"), 1)
        self.assertNotIn("restart", self.events)

    def test_simultaneous_guardian_and_worker_failures_issue_once(self):
        self.arm(True)
        ready = Barrier(2)

        def report():
            ready.wait(timeout=2)
            return self.call()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.submit(report), pool.submit(report)
            self.assertEqual(sorted([first.result(), second.result()]), [False, True])
        self.assertEqual(self.events.count("restart"), 1)

    def test_symlink_instead_of_trial_record_is_not_followed(self):
        self.recovery.prepare("preparation", permit_recovery_restart=True)
        (self.root / "trial.json").symlink_to("prepared.json")
        with self.assertRaises(OSError):
            self.recovery.begin_trial("trial")
        self.assertEqual(self.events, [])

    def test_unknown_existing_outcome_blocks_mutation(self):
        self.arm(True)
        (self.root / "outcome.json").touch(mode=0o600)
        with self.assertRaises(ValueError):
            self.call()
        self.assertEqual(self.events, [])


if __name__ == "__main__":
    unittest.main()
