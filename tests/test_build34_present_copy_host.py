#!/usr/bin/env python3
"""CPU-only delta/identity/recovery fixtures; no driver, GPU or power access."""
import copy
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('R2a_host_CPU', Path(__file__).resolve().parents[1] /
                                             'tools/build34_present_copy_host.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture():
    changes = {p: dict(before=m.BEFORE[p], after=m.AFTER[p], backup='old-' + str(i), candidate='new-' + str(i))
               for i, p in enumerate(m.AFTER)}
    sealed = {v['backup']: v['before'] for v in changes.values()}
    sealed.update({v['candidate']: v['after'] for v in changes.values()})
    sealed['old-job'] = 'retained-job'
    return dict(R2a_source_checkpoint=m.SOURCE, R2a_sequential_trial_authorized=True,
                R2a_parent_EFI_private={'kernel': 'R1b', 'AML': 'accepted'},
                EFI_after_private={'kernel': 'R1b', 'AML': 'accepted'},
                R2a_changes=changes, sealed=sealed,
                R2a_before_protected={**m.BEFORE, 'config': 'original', 'firmware': 'unchanged', 'job': 'historical'},
                R2a_before_uuid_private='old-VBL', R2a_after_uuid_private='R2a',
                R2a_retained_jobs={'job': 'retained-job'}, jobs={'job': 'R2a-job'},
                recovery_jobs={'job': dict(sha256='retained-job', backup='old-job')},
                daily_configuration=dict(protected_path='config', original_sha256='original', configured_sha256='daily'))


class ContractTests(unittest.TestCase):
    def test_exact_two_images_and_current_R1b_recovery(self):
        c = fixture()
        original = copy.deepcopy(c)
        m.validate_delta(c)
        self.assertEqual(c, original)

    def test_unknown_image_EFI_source_and_recovery_job_are_refused(self):
        bad = []
        c = fixture(); c['R2a_changes']['extra'] = {}; bad.append(c)
        c = fixture(); c['R2a_changes'][m.ACCELERATOR]['before'] = 'older'; bad.append(c)
        c = fixture(); c['R2a_changes'][m.CACHE]['after'] = 'unknown'; bad.append(c)
        c = fixture(); c['EFI_after_private']['kernel'] = 'R1a'; bad.append(c)
        c = fixture(); c['R2a_source_checkpoint'] = 'unknown'; bad.append(c)
        c = fixture(); c['recovery_jobs']['job']['sha256'] = 'older'; bad.append(c)
        c = fixture(); c['sealed']['new-0'] = 'unknown'; bad.append(c)
        c = fixture(); c['R2a_sequential_trial_authorized'] = False; bad.append(c)
        for value in bad:
            with self.subTest(value=value), self.assertRaises(AssertionError): m.validate_delta(value)

    def record(self):
        c = fixture()
        return c, dict(protected=copy.deepcopy(c['R2a_before_protected']),
                       desktop_runtime=dict(accel_image_uuid='old-VBL'),
                       candidate_binary_sha256='R1b', candidate_image_uuid='R1b-image',
                       EFI='retained', ABI='build34')

    def test_only_two_hashes_and_accelerator_identity_are_derived(self):
        c, record = self.record(); original = copy.deepcopy(record)
        out = m.derive_present(record, c, 'contract')
        self.assertEqual(record, original)
        self.assertEqual(out['desktop_runtime']['accel_image_uuid'], 'R2a')
        for p in m.AFTER: self.assertEqual(out['protected'][p], m.AFTER[p])
        for key in ['candidate_binary_sha256', 'candidate_image_uuid', 'EFI', 'ABI']:
            self.assertEqual(out[key], record[key])
        self.assertEqual(m.derive_present(record, c, 'stage'), record)

    def test_unknown_input_protected_file_or_image_is_not_reinterpreted(self):
        for which in ['image', 'protected']:
            c, record = self.record()
            if which == 'image': record['desktop_runtime']['accel_image_uuid'] = 'unknown'
            else: record['protected']['firmware'] = 'unknown'
            with self.subTest(which=which), self.assertRaises(AssertionError): m.derive_present(record, c, 'contract')

    def test_pre_restart_live_identity_does_not_change_candidate_disk_checks(self):
        c, record = self.record(); candidate = m.derive_present(record, c, 'contract')
        original = copy.deepcopy(candidate); live = m.pre_restart_live_contract(candidate, c)
        self.assertEqual(candidate, original)
        self.assertEqual(live['desktop_runtime']['accel_image_uuid'], 'old-VBL')
        live['desktop_runtime']['accel_image_uuid'] = 'R2a'
        self.assertEqual(live, candidate)
        with self.assertRaises(AssertionError): m.pre_restart_live_contract(record, c)

    def test_physical_baseline_accounts_for_daily_configuration_and_current_jobs(self):
        c = fixture(); expected = m.physical_baseline(c)
        self.assertEqual(expected, {**m.BEFORE, 'config': 'daily', 'firmware': 'unchanged', 'job': 'retained-job'})
        self.assertEqual(c['R2a_before_protected']['config'], 'original')


class RecoveryTests(unittest.TestCase):
    def test_only_historical_disable_switch_requires_exact_absence(self):
        path = Mock(); path.is_symlink.return_value = False; path.exists.return_value = False
        with patch.object(m, 'Path', return_value=path):
            m.require_protected_file(m.DISABLE_MARKER, m.EMPTY_SHA256)
            with self.assertRaises(AssertionError): m.require_protected_file(m.DISABLE_MARKER, 'unknown')
            path.exists.return_value = True
            with self.assertRaises(AssertionError): m.require_protected_file(m.DISABLE_MARKER, m.EMPTY_SHA256)

    def test_unknown_missing_protected_file_and_symlink_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'required'
            with self.assertRaises(FileNotFoundError): m.require_protected_file(str(p), m.EMPTY_SHA256)
            p.write_bytes(b'')
            m.require_protected_file(str(p), m.EMPTY_SHA256)
            link = Path(folder) / 'link'; link.symlink_to(p)
            with self.assertRaises(AssertionError): m.require_protected_file(str(link), m.EMPTY_SHA256)

    def test_unknown_input_prevents_all_restore_writes(self):
        h = m.PresentCopyHost.__new__(m.PresentCopyHost)
        h.check_restore_inputs = Mock(side_effect=AssertionError('unknown'))
        with patch.object(m.r1b.acpi.vbl, 'atomic_image') as atomic, self.assertRaises(AssertionError): h.restore()
        atomic.assert_not_called()

    def test_restore_changes_only_two_images_jobs_and_own_watcher(self):
        h = m.PresentCopyHost.__new__(m.PresentCopyHost); c = fixture()
        with tempfile.TemporaryDirectory() as folder:
            h.scope = Path(folder); h.check_restore_inputs = Mock(return_value=c)
            h.restore_jobs = Mock(); h.retire_watcher = Mock()
            pending = Mock(); pending.exists.return_value = False
            with patch.object(m, 'Path', return_value=pending), \
                    patch.object(m.r1b.acpi.vbl, 'atomic_image') as atomic, patch.object(m.subprocess, 'run') as run:
                h.restore()
            self.assertEqual(atomic.call_count, 2)
            for call, path in zip(atomic.call_args_list, m.AFTER):
                self.assertEqual(call.args, (path, h.scope / c['R2a_changes'][path]['backup'],
                                            (m.BEFORE[path], m.AFTER[path])))
            h.restore_jobs.assert_called_once(); h.retire_watcher.assert_called_once()
            self.assertFalse(any('shutdown' in str(call) or 'reboot' in str(call) for call in run.call_args_list))

    def test_distinct_scope_and_inherited_no_daily_power_policy(self):
        self.assertNotEqual(m.PresentCopyHost.SCOPE_KIND, m.r1b.R1bHost.SCOPE_KIND)
        self.assertIs(m.PresentCopyHost.refuse_daily_power, m.r1b.R1bHost.refuse_daily_power)
        self.assertIs(m.PresentCopyHost.watch, m.r1b.R1bHost.watch)
        self.assertIs(m.PresentCopyHost.quiesce, m.r1b.R1bHost.quiesce)


if __name__ == '__main__': unittest.main()
