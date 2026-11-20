#!/usr/bin/env python3
"""CPU/tempfile-only coverage of VBL retention and R1a-only recovery."""

import copy
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


m = module("VBL_resume_CPU", "build34_vbl_resume_host.py")
journal = module("VBL_resume_journal_CPU", "build34_startup_recovery.py")


class DeriveTests(unittest.TestCase):
    def setUp(self):
        self.original = {
            "protected": {m.ACCELERATOR: "old-a", m.CACHE: "old-c", "untouched": "pin"},
            "desktop_runtime": {"accel_bundle_id": "com.luuumi.PhxAccel",
                                "accel_image_uuid": "old-image"},
            "kernel": "R1a", "plugin": "accepted", "ACPI": "original"}
        self.config = {"VBL_changes": {
            path: {"before": self.original["protected"][path], "after": digest}
            for path, digest in m.EXPECTED_CANDIDATES.items()},
            "VBL_before_uuid_private": "old-image", "VBL_after_uuid_private": "VBL-image"}

    def test_changes_only_two_protected_hashes_and_accelerator_identity(self):
        before = copy.deepcopy(self.original)
        after = m.derive_vbl(self.original, self.config, "contract")
        self.assertEqual(self.original, before)
        for path, digest in m.EXPECTED_CANDIDATES.items():
            self.assertEqual(after["protected"][path], digest)
            after["protected"][path] = before["protected"][path]
        self.assertEqual(after["desktop_runtime"]["accel_image_uuid"], "VBL-image")
        after["desktop_runtime"]["accel_image_uuid"] = "old-image"
        self.assertEqual(after, before)

    def test_stage_snapshot_is_not_modified(self):
        self.assertEqual(m.derive_vbl(self.original, self.config, "stage"), self.original)

    def test_drifted_original_hash_is_refused(self):
        self.original["protected"][m.CACHE] = "unknown"
        with self.assertRaises(AssertionError):
            m.derive_vbl(self.original, self.config, "contract")

    def test_wrong_accelerator_identity_is_refused(self):
        self.original["desktop_runtime"]["accel_image_uuid"] = "unknown"
        with self.assertRaises(AssertionError):
            m.derive_vbl(self.original, self.config, "contract")


class AtomicTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target, self.source = self.root / "image", self.root / "replacement"
        self.target.write_bytes(b"accepted")
        self.source.write_bytes(b"candidate")
        self.allowed = (m.base.sha(self.target), m.base.sha(self.source))

    def test_replaces_only_known_image_and_preserves_mode(self):
        self.target.chmod(0o640)
        with patch.object(m.base, "secure"):
            m.atomic_image(self.target, self.source, self.allowed)
        self.assertEqual(self.target.read_bytes(), b"candidate")
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o640)

    def test_unknown_target_is_refused_without_replacement(self):
        self.target.write_bytes(b"unknown")
        with patch.object(m.base, "secure"), self.assertRaises(AssertionError):
            m.atomic_image(self.target, self.source, self.allowed)
        self.assertEqual(self.target.read_bytes(), b"unknown")

    def test_preexisting_partial_file_is_not_overwritten_or_deleted(self):
        partial = self.target.with_name(self.target.name + ".nullarc-vbl-resume-next")
        partial.write_bytes(b"unknown")
        with patch.object(m.base, "secure"), self.assertRaises(FileExistsError):
            m.atomic_image(self.target, self.source, self.allowed)
        self.assertEqual(partial.read_bytes(), b"unknown")
        self.assertEqual(self.target.read_bytes(), b"accepted")


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.host = m.VBLHost.__new__(m.VBLHost)
        self.value = {"owner_authorized_VBL_restoration": True,
                      "VBL_source_checkpoint": m.VBL_SOURCE,
                      "Weather_candidate_enabled": False, "ACPI_candidate_enabled": False,
                      "daily_recovery_restart_limit": 0, "VBL_changes": {}, "sealed": {}}
        for i, (path, digest) in enumerate(m.EXPECTED_CANDIDATES.items()):
            candidate, backup = "candidate-" + str(i), "backup-" + str(i)
            self.value["VBL_changes"][path] = {
                "before": "accepted-" + str(i), "after": digest,
                "candidate": candidate, "backup": backup}
            self.value["sealed"].update({candidate: digest, backup: "accepted-" + str(i)})

    def test_original_R1a_scope_kind_stays_separate(self):
        self.assertEqual(m.base.Host.SCOPE_KIND, "accepted-R1a-startup-recovery")
        self.assertNotEqual(m.base.Host.SCOPE_KIND, m.VBLHost.SCOPE_KIND)
        with patch.object(m.base.Host, "contract", return_value=self.value):
            self.assertIs(self.host.contract(), self.value)

    def test_Weather_and_ACPI_cannot_be_combined_with_VBL_trial(self):
        for key in ("Weather_candidate_enabled", "ACPI_candidate_enabled"):
            value = copy.deepcopy(self.value)
            value[key] = True
            with patch.object(m.base.Host, "contract", return_value=value), self.assertRaises(AssertionError):
                self.host.contract()

    def test_unknown_cache_binary_is_not_admitted(self):
        self.value["VBL_changes"][m.CACHE]["after"] = "another-cache"
        with patch.object(m.base.Host, "contract", return_value=self.value), self.assertRaises(AssertionError):
            self.host.contract()


class RetentionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.host = m.VBLHost.__new__(m.VBLHost)
        self.host.scope = self.root
        self.host.config = {"prepared_boot": "preparation"}
        self.host.boot = lambda: "trial"
        for name in ("trial", "daily"):
            path = self.root / name
            path.mkdir(mode=0o700)
            setattr(self.host, "policy" if name == "trial" else "daily_policy",
                    journal.StartupRecovery(path))
        self.host.policy.prepare("preparation", permit_recovery_restart=True)
        self.host.daily_policy.prepare("preparation", permit_recovery_restart=False)

    def accept(self):
        self.assertTrue(self.host.policy.begin_trial("trial"))
        self.assertTrue(self.host.policy.accept_startup("trial"))

    def fake_runtime(self):
        runtime = SimpleNamespace(live_identity=Mock(), deployment=SimpleNamespace(
            future_startup=Mock(), future_guardian=Mock()))
        self.host.readonly = SimpleNamespace(build=Mock(return_value=(runtime, {}, {})))
        return runtime

    def test_success_keeps_candidate_jobs_and_retires_finite_watcher(self):
        self.host.policy = SimpleNamespace(watch=Mock(return_value="accepted"))
        self.host.retire_watcher = Mock()
        self.host.restore_jobs = Mock()
        self.host.watch()
        self.host.restore_jobs.assert_not_called()
        self.host.retire_watcher.assert_called_once()

    def test_retained_jobs_work_on_later_boot_without_reusing_trial(self):
        self.accept()
        self.host.boot = lambda: "daily-boot"
        runtime = self.fake_runtime()
        self.host.worker("startup")
        runtime.deployment.future_startup.assert_called_once()
        self.assertEqual(self.host.policy.accepted_boot(), "trial")
        self.assertFalse((self.root / "trial" / "recovery-restart.intent").exists())

    def test_closed_failed_trial_cannot_run_another_candidate_boot(self):
        self.assertTrue(self.host.policy.begin_trial("trial"))
        self.host.policy._decide("trial", {"decision": "rollback", "reason": "failure"})
        self.host.boot = lambda: "another-boot"
        self.fake_runtime()
        with self.assertRaises(AssertionError):
            self.host.worker("startup")
        self.host.readonly.build.assert_not_called()

    def actions(self):
        self.events = []
        actions = {name: Mock(side_effect=lambda name=name: self.events.append(name) or True)
                   for name in ("quiesce", "restore", "verify", "prepare_restart", "request_restart")}
        self.host.recovery_actions = lambda: actions
        return actions

    def test_later_startup_failure_restores_once_and_never_requests_power(self):
        self.accept()
        self.host.boot = lambda: "daily-boot"
        actions = self.actions()
        with patch.object(m.base.Host, "supervise", side_effect=RuntimeError("worker failed")):
            for _ in range(2):
                with self.assertRaises((RuntimeError, AssertionError)):
                    self.host.supervise("startup")
        self.assertEqual(self.events, ["quiesce", "restore", "verify"])
        actions["request_restart"].assert_not_called()
        self.assertFalse((self.root / "daily" / "recovery-restart.intent").exists())

    def test_even_incorrect_daily_permission_cannot_reach_real_power_callbacks(self):
        self.accept()
        self.host.boot = lambda: "daily-boot"
        (self.root / "daily" / "prepared.json").write_text(
            '{"boot":"preparation","permit_recovery_restart":true}')
        actions = self.actions()
        with patch.object(m.base.Host, "supervise", side_effect=RuntimeError("worker failed")), \
                self.assertRaisesRegex(RuntimeError, "cannot request power"):
            self.host.supervise("guardian")
        actions["prepare_restart"].assert_not_called()
        actions["request_restart"].assert_not_called()

    def test_first_trial_failure_is_left_to_its_finite_watcher(self):
        self.actions()
        with patch.object(m.base.Host, "supervise", side_effect=RuntimeError("worker failed")), \
                self.assertRaises(RuntimeError):
            self.host.supervise("startup")
        self.assertEqual(self.events, [])

    def test_restore_refuses_before_any_image_or_job_write(self):
        self.host.check_restore_inputs = Mock(side_effect=AssertionError("unknown second job"))
        self.host.restore_jobs = Mock()
        with patch.object(m, "atomic_image") as image, self.assertRaises(AssertionError):
            self.host.restore()
        image.assert_not_called()
        self.host.restore_jobs.assert_not_called()

    def test_unrecorded_worker_refuses_recovery_after_known_groups_exit(self):
        text = f"{m.base.PYTHON} -B -I {self.root}/owner-startup-private.py worker startup\n"
        with patch.object(m.base.Host, "quiesce", return_value=True), \
                patch.object(m.subprocess, "check_output", return_value=text):
            self.assertFalse(self.host.quiesce())


if __name__ == "__main__":
    unittest.main()
