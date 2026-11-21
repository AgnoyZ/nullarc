#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the real adapter's admission and rollback with offline inputs."""
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_build34_map_observer_host as prior

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import build34_pci_irq_observer_host as host


def fixture():
    c = prior.fixture()
    before = c['Map_after_EFI_private']
    image = {'sha256': host.OBSERVER, 'bytes': 21}
    current = c['jobs'].copy()
    c.update(PCI_source_checkpoint=host.SOURCE, PCI_trial_authorized=False,
             PCI_GPU_pressure_authorized=False, PCI_IRQ_registration_authorized=False, PCI_ordinary_restart_limit=1,
             PCI_prepared_boot='new-PCI-preparation', PCI_retained_jobs=current,
             PCI_before_EFI_private=before, PCI_after_EFI_private={**before, host.KERNEL: image},
             PCI_observer_bundle_private={**c['Map_observer_bundle_private'], host.EXE: image},
             PCI_after_uuid_private=prior.OBSERVER_UUID.replace('b', 'c'),
             jobs={p: 'pci-' + p for p in current}, PCI_recovery_jobs={}, watcher_job_sha256='new-watcher')
    for path, digest in current.items():
        backup = 'pci-backup-' + path
        c['PCI_recovery_jobs'][path] = dict(backup=backup, sha256=digest)
        c['sealed'][backup] = digest
    c['sealed'].update({host.RESTORE_FILE: host.RESTORE, host.OBSERVER_FILE: host.OBSERVER, host.REPORT: 'report',
                        host.WATCHER: c['watcher_job_sha256'], 'build34_map_observer_host.py': 'old-host',
                        'build34_pci_irq_observation.py': 'passive-reader', 'owner-startup-private.py': 'new-host'})
    return c


def metadata(mode='msi-enable-set'):
    return dict(start_time_config_classification=mode, status='start-time-pci-config-classification',
                pci='1002:1900', PhxBringup_build=34, os_build='25G332', direct_pci_provider_matched=True,
                device_opened=False, raw_registry_saved=False, active_interrupt_mode_proved=False,
                active_isr_proved=False, eop_delivery_proved=False, ih_consumer_ownership_proved=False,
                fence_visibility_proved=False)


class ObserverScope(unittest.TestCase):
    def test_prior_grant_cannot_start_the_inactive_scope(self):
        c = fixture()
        host.validate_delta(c, require_authorized=False)
        with patch.object(host.parent, 'contract', return_value=c), \
             self.assertRaisesRegex(AssertionError, 'fresh PCI observer trial authorization missing'):
            host.PCIObserverHost('/synthetic')

    def test_refuses_extra_EFI_changes_old_recovery_target_and_added_power(self):
        for mutate in (
            lambda c: c['PCI_after_EFI_private'].update({'extra': {}}),
            lambda c: c['PCI_after_EFI_private'].update({'other/0': {'sha256': 'unknown'}}),
            lambda c: c['sealed'].update({host.RESTORE_FILE: host.mapping.BASE_BINARY}),
            lambda c: c['PCI_recovery_jobs']['startup'].update(sha256='old-R2a-startup'),
            lambda c: c.update(daily_recovery_restart_limit=1),
            lambda c: c.update(automatic_recovery_reboots=2),
            lambda c: c.update(PCI_IRQ_registration_authorized=True),
            lambda c: c.update(PCI_prepared_boot=c['Map_prepared_boot']),
        ):
            c = fixture(); mutate(c)
            with self.subTest(mutate=mutate), self.assertRaises(AssertionError):
                host.validate_delta(c, require_authorized=False)

    def test_ordinary_intent_is_exact_to_new_scope_and_boot(self):
        c = fixture(); c['PCI_trial_authorized'] = True
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            h = host.PCIObserverHost.__new__(host.PCIObserverHost)
            h.scope = p
            with patch.object(host.parent, 'contract', return_value=c), patch.object(host, 'validate_inputs'), \
                 patch.object(host.base, 'secure'):
                with self.assertRaises(FileNotFoundError): h.contract()
                good = host.intent_record(c, p)
                for stale in (dict(good, prepared_boot_private=c['Map_prepared_boot']),
                              dict(good, scope='/prior'), dict(good, ordinary_requests=2)):
                    (p / host.INTENT).write_text(json.dumps(stale))
                    with self.assertRaises(AssertionError): h.contract()
                (p / host.INTENT).write_text(json.dumps(good))
                self.assertIs(h.contract(), c)

    def test_all_preparation_boot_entrypoints_refuse(self):
        h = host.PCIObserverHost.__new__(host.PCIObserverHost)
        h.config = fixture()
        h.boot = lambda: h.config['PCI_prepared_boot']
        operations = (h.watch, lambda: h.supervise('startup'), lambda: h.worker('guardian'),
                      lambda: h.note_failure('test'), h._read_admission, h.restore, h.verify_restore,
                      h.prepare_restart, h.request_restart)
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaisesRegex(AssertionError, 'preparation boot'):
                operation()

    def test_geometry_only_adds_the_validated_properties_and_keeps_stage(self):
        c = fixture()
        record = prior.baseline_record(c)
        original = copy.deepcopy(record)
        out = host.derive(record, c, 'contract', prior.observation(), metadata())
        self.assertEqual(out['candidate_image_uuid'], c['PCI_after_uuid_private'])
        self.assertEqual(out['candidate_binary_sha256'], host.OBSERVER)
        self.assertEqual(out['baseline_node_geometry'], {**record['baseline_node_geometry'],
            **dict(zip(host.mapping.MAP_PROPERTIES, (0x400, 4, 1))), host.irq.START_CONFIG: 'msi-enable-set'})
        self.assertEqual(original, record)
        self.assertEqual(host.derive(record, c, 'stage'), record)
        for changes in (dict(start_time_config_classification='unavailable'), dict(os_build='25G333'),
                        dict(active_isr_proved=True), dict(direct_pci_provider_matched=False)):
            with self.assertRaises(AssertionError):
                host.derive(record, c, 'contract', prior.observation(), dict(metadata(), **changes))

    def test_receipt_waits_for_admission_and_refuses_contradictory_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            h = host.PCIObserverHost.__new__(host.PCIObserverHost)
            h.scope = Path(temp); h.config = fixture(); h.boot = lambda: 'pci-trial'
            h.admission_mode = 'msi-enable-set'
            with patch.object(host.base.Host, '_read_admission', return_value=None), patch.object(host.irq, 'collect') as read:
                self.assertIsNone(h._read_admission())
                read.assert_not_called()
            with patch.object(host.base.Host, '_read_admission', return_value=True), \
                 patch.object(host.irq, 'collect', return_value=metadata('both-message-enables-clear')):
                with self.assertRaises(AssertionError): h._read_admission()
            self.assertEqual(list(h.scope.iterdir()), [])
            with patch.object(host.base.Host, '_read_admission', return_value=True), \
                 patch.object(host.irq, 'collect', return_value=metadata()):
                self.assertTrue(h._read_admission())
            receipt = json.loads((h.scope / 'pci-observation-pci-trial.json').read_bytes())
            self.assertEqual(receipt['classification'], 'msi-enable-set')
            self.assertEqual(receipt['candidate_binary_sha256'], host.OBSERVER)

    def test_restore_touches_only_exact_current_kernel_and_jobs(self):
        c = fixture()
        with tempfile.TemporaryDirectory() as temp:
            h = host.PCIObserverHost.__new__(host.PCIObserverHost)
            h.scope = Path(temp)
            (h.scope / host.RESTORE_FILE).write_bytes(b'current-mapping-executable')
            for record in c['PCI_recovery_jobs'].values():
                (h.scope / record['backup']).write_bytes(record['sha256'].encode())
            h.check_restore_inputs = Mock(return_value=c)
            writes = []
            state = c['PCI_after_EFI_private']

            @contextmanager
            def efi(unused, *, writable):
                self.assertTrue(writable)
                yield h.scope

            def atomic(path, data, allowed):
                nonlocal state
                writes.append((path, data, allowed))
                if path == h.scope / host.KERNEL:
                    state = c['PCI_before_EFI_private']

            h.route = lambda: SimpleNamespace(efi=efi, static=lambda: None, files=lambda root: state)
            h.readonly = SimpleNamespace(atomic_file=atomic)
            h.retire_watcher = Mock()
            with patch.object(host.subprocess, 'run') as run, patch.object(host.Path, 'exists', return_value=False):
                h.restore()
            self.assertEqual(writes[0], (h.scope / host.KERNEL, b'current-mapping-executable', [host.RESTORE, host.OBSERVER]))
            self.assertEqual(writes[1:], [(p, c['PCI_retained_jobs'][p].encode(), [c['jobs'][p], c['PCI_retained_jobs'][p]])
                                          for p in c['PCI_retained_jobs']])
            self.assertNotIn('/sbin/shutdown', [call.args[0][0] for call in run.call_args_list])
            h.retire_watcher.assert_called_once()

    def test_recovery_refuses_unrecognized_EFI_before_first_write(self):
        c = fixture()
        h = host.PCIObserverHost.__new__(host.PCIObserverHost)
        h.config = c; h.boot = lambda: 'pci-trial'; h.contract = lambda: c

        @contextmanager
        def efi(unused):
            yield Path('/synthetic')

        h.route = lambda: SimpleNamespace(efi=efi, static=lambda: None, files=lambda root: {'unknown': {}})
        h.readonly = SimpleNamespace(atomic_file=Mock())
        with self.assertRaises(AssertionError): h.restore()
        h.readonly.atomic_file.assert_not_called()


if __name__ == '__main__':
    unittest.main()
