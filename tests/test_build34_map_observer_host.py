#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual adapter methods with CPU/filesystem doubles; no device/root/power."""
import contextlib
import copy
import importlib.util
import json
from pathlib import Path
import plistlib
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

BASE_UUID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
OBSERVER_UUID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'

spec = importlib.util.spec_from_file_location('MapHost_CPU', Path(__file__).resolve().parents[1] /
                                             'tools/build34_map_observer_host.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture():
    control = {m.EXE: {'sha256': m.BASE_BINARY, 'bytes': 10},
               'Contents/Info.plist': {'sha256': 'same-plist', 'bytes': 1},
               'Contents/_CodeSignature/CodeResources': {'sha256': 'same-signature', 'bytes': 2}}
    observer = copy.deepcopy(control)
    observer[m.EXE] = {'sha256': m.OBSERVER_BINARY, 'bytes': 20}
    before = {'OC/Kexts/PhxBringup.kext/' + n: copy.deepcopy(v) for n, v in control.items()}
    before.update({'other/' + str(i): {'sha256': str(i), 'bytes': i} for i in range(355)})
    after = copy.deepcopy(before)
    after[m.KERNEL] = copy.deepcopy(observer[m.EXE])
    return dict(Map_source_checkpoint=m.SOURCE, Map_driver_sha256=m.DRIVER_SHA,
                Map_full_R3_enabled=False, Map_native_reader_bound=False, Map_trial_authorized=True,
                Map_native_report_sha256=m.NATIVE_REPORT_SHA,
                Map_before_EFI_private=before, Map_after_EFI_private=after,
                EFI_after_private=copy.deepcopy(before), R2a_parent_EFI_private=copy.deepcopy(before),
                Map_control_bundle_private=control, Map_observer_bundle_private=observer,
                R1b_kernel_files_private=copy.deepcopy(control), R1b_image_uuid_private=BASE_UUID,
                Map_before_uuid_private=BASE_UUID, Map_after_uuid_private=OBSERVER_UUID,
                prepared_boot='historical-R2a-preparation', Map_prepared_boot='current-preparation',
                jobs={'startup': 'new-startup', 'guardian': 'new-guardian'},
                Map_new_jobs={'startup': 'new-startup', 'guardian': 'new-guardian'},
                Map_retained_jobs={'startup': 'retained-R2a-startup', 'guardian': 'retained-R2a-guardian'},
                Map_recovery_jobs={'startup': {'sha256': 'retained-R2a-startup', 'backup': 'retained-startup.plist'},
                                   'guardian': {'sha256': 'retained-R2a-guardian', 'backup': 'retained-guardian.plist'}},
                startup_limits_seconds=[45, 150, 300], automatic_recovery_reboots=1,
                daily_recovery_restart_limit=0, resident_monitor_enabled=False, pressure_probe_enabled=False,
                sealed={'map-native-report-private.json': m.NATIVE_REPORT_SHA,
                        'build34_map_observation.py': m.READER_SHA,
                        'map-control-kernel.bin': m.BASE_BINARY, 'map-observer-kernel.bin': m.OBSERVER_BINARY,
                        'retained-startup.plist': 'retained-R2a-startup', 'retained-guardian.plist': 'retained-R2a-guardian'})


def observation():
    return dict(status='mapping-options-observed-not-reader-admitted',
                native_reader_admitted=False, effective_cache_proven=False,
                kernel_build=34, observation_version=1, map_options=0x400,
                cache_option=4, BAR0_bytes=268435456)


def baseline_record(c):
    return dict(candidate_files=copy.deepcopy(c['Map_control_bundle_private']),
                candidate_binary_sha256=m.BASE_BINARY, candidate_image_uuid=BASE_UUID,
                baseline_node_geometry={'phx-build': 34, 'phx-fb-aper-len': 268435456,
                                        'phx-retained-property': 123})


class DeltaTests(unittest.TestCase):
    def test_exact_delta_preserves_historical_fields_and_input(self):
        c = fixture()
        before = copy.deepcopy(c)
        m.validate_delta(c)
        self.assertEqual(c, before)

    def test_historical_uppercase_identity_is_preserved_and_alias_is_not_distinct(self):
        c = fixture()
        c['R1b_image_uuid_private'] = c['Map_before_uuid_private'] = BASE_UUID.upper()
        before = copy.deepcopy(c)
        m.validate_delta(c)
        self.assertEqual(c, before)
        c['Map_after_uuid_private'] = BASE_UUID
        with self.assertRaises(AssertionError): m.validate_delta(c)

    def test_inactive_preparation_does_not_grant_runtime_authorization(self):
        c = fixture(); c['Map_trial_authorized'] = False
        # Old parent grants remain history and cannot satisfy the new gate.
        c['R2a_sequential_trial_authorized'] = True
        m.validate_delta(c, require_authorized=False)
        with self.assertRaisesRegex(AssertionError, 'fresh mapping-observer trial authorization missing'): m.validate_delta(c)

    def test_unknown_source_identity_protocol_image_and_policy_refuse(self):
        changes = [('Map_source_checkpoint', 'unknown'), ('Map_driver_sha256', 'unknown'),
                   ('Map_full_R3_enabled', True), ('Map_native_reader_bound', True),
                   ('Map_trial_authorized', 1), ('Map_native_report_sha256', 'unknown'),
                   ('Map_before_uuid_private', 'unknown'), ('Map_after_uuid_private', BASE_UUID),
                   ('Map_prepared_boot', ''), ('startup_limits_seconds', [45, 150, 301]),
                   ('automatic_recovery_reboots', 2), ('daily_recovery_restart_limit', 1),
                   ('resident_monitor_enabled', True), ('pressure_probe_enabled', True)]
        for key, value in changes:
            c = fixture(); c[key] = value
            with self.subTest(key=key), self.assertRaises(AssertionError): m.validate_delta(c)

    def test_unknown_EFI_bundle_reader_or_recovery_backup_refuses(self):
        bad = []
        c = fixture(); c['Map_after_EFI_private']['extra'] = {}; bad.append(c)
        c = fixture(); c['Map_after_EFI_private']['other/0']['sha256'] = 'unknown'; bad.append(c)
        c = fixture(); c['Map_observer_bundle_private']['Contents/Info.plist']['sha256'] = 'unknown'; bad.append(c)
        c = fixture(); c['Map_observer_bundle_private'][m.EXE]['sha256'] = 'unknown'; bad.append(c)
        c = fixture(); c['sealed']['build34_map_observation.py'] = 'unknown'; bad.append(c)
        c = fixture(); c['Map_recovery_jobs']['startup']['sha256'] = 'old-R1a'; bad.append(c)
        c = fixture(); c['sealed']['retained-guardian.plist'] = 'old-R1b'; bad.append(c)
        c = fixture(); c['jobs'] = dict(c['Map_retained_jobs']); c['Map_new_jobs'] = dict(c['jobs']); bad.append(c)
        for value in bad:
            with self.subTest(value=bad.index(value)), self.assertRaises(AssertionError): m.validate_delta(value)

    def test_only_exact_kernel_identity_is_overlaid_and_stage_is_unchanged(self):
        c = fixture()
        record = dict(candidate_files=copy.deepcopy(c['Map_control_bundle_private']), candidate_binary_sha256=m.BASE_BINARY,
                      candidate_image_uuid=BASE_UUID, ABI='retained', plugin='R2a-accepted', protected={'firmware': 'same'})
        original = copy.deepcopy(record)
        out = m.derive_observer(record, c, 'contract')
        self.assertEqual(record, original)
        self.assertEqual(out['candidate_binary_sha256'], m.OBSERVER_BINARY)
        self.assertEqual(out['candidate_files'], c['Map_observer_bundle_private'])
        self.assertEqual(out['candidate_image_uuid'], OBSERVER_UUID)
        for key in ('ABI', 'plugin', 'protected'): self.assertEqual(out[key], record[key])
        self.assertEqual(m.derive_observer(record, c, 'stage'), record)
        for key in ('candidate_files', 'candidate_binary_sha256', 'candidate_image_uuid'):
            bad = copy.deepcopy(record); bad[key] = 'unknown'
            with self.subTest(key=key), self.assertRaises(AssertionError): m.derive_observer(bad, c, 'contract')

    def test_pre_restart_live_check_preserves_candidate_disk_manifest(self):
        c = fixture()
        proposed = dict(candidate_files=copy.deepcopy(c['Map_observer_bundle_private']), candidate_binary_sha256=m.OBSERVER_BINARY,
                        candidate_image_uuid=OBSERVER_UUID, accelerator='accepted-R2a')
        original = copy.deepcopy(proposed)
        live = m.pre_restart_live_contract(proposed, c)
        self.assertEqual(proposed, original)
        self.assertEqual(live['candidate_files'], proposed['candidate_files'])
        self.assertEqual(live['candidate_binary_sha256'], m.OBSERVER_BINARY)
        self.assertEqual(live['candidate_image_uuid'], BASE_UUID)
        live['candidate_image_uuid'] = OBSERVER_UUID
        self.assertEqual(live, proposed)


class GeometryTests(unittest.TestCase):
    def test_only_three_validated_properties_extend_the_original_strict_geometry(self):
        record = baseline_record(fixture()); original = copy.deepcopy(record)
        out = m.observed_geometry(record, observation())
        actual = {**record['baseline_node_geometry'], **dict(zip(m.MAP_PROPERTIES, (0x400, 4, 1)))}
        self.assertNotEqual(record['baseline_node_geometry'], actual)  # Old admission refuses.
        self.assertEqual(out['baseline_node_geometry'], actual)
        self.assertEqual(record, original)
        for key in record:
            if key != 'baseline_node_geometry': self.assertEqual(out[key], record[key])
        for changed in ('phx-retained-property', 'phx-build', 'phx-fb-aper-len'):
            bad = dict(actual); bad[changed] += 1
            self.assertNotEqual(out['baseline_node_geometry'], bad)
        self.assertNotEqual(out['baseline_node_geometry'], {**actual, 'phx-unknown': 1})

    def test_bad_metadata_or_already_extended_baseline_refuses(self):
        for key, value in [('status', 'mapping-metadata-unavailable'), ('native_reader_admitted', True),
                           ('effective_cache_proven', True), ('kernel_build', 42), ('observation_version', 2),
                           ('map_options', True), ('map_options', 1 << 32), ('cache_option', 0), ('BAR0_bytes', 1)]:
            metadata = observation(); metadata[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(AssertionError):
                m.observed_geometry(baseline_record(fixture()), metadata)
        record = baseline_record(fixture()); record['baseline_node_geometry'][m.MAP_PROPERTIES[0]] = 0x400
        with self.assertRaises(AssertionError): m.observed_geometry(record, observation())

    def test_runtime_derivation_always_binds_geometry_after_new_boot_and_keeps_stage(self):
        c = fixture(); record = baseline_record(c)
        with tempfile.TemporaryDirectory() as folder:
            scope = Path(folder); accepted = scope/'accepted'; accepted.mkdir()
            (accepted/'contract-private.json').write_text(json.dumps(dict(
                scope_kind=m.parent.PresentCopyHost.SCOPE_KIND,
                EFI_after_private=c['Map_before_EFI_private'], jobs=c['Map_retained_jobs'])))
            c.update(Map_parent_scope=str(accepted), Map_parent_contract_sha256='parent-hash')

            def fake_parent(h, directory):
                h.scope = directory; h.config = c
                h.readonly = SimpleNamespace(derive=Mock(return_value=copy.deepcopy(record)))
                h.boot = Mock(return_value='later-trial-boot')

            with patch.object(m.parent.PresentCopyHost, '__init__', new=fake_parent), \
                    patch.object(m.base, 'secure'), patch.object(m.base, 'sha', return_value='parent-hash'):
                h = m.MappingObserverHost(scope)
            h.collect_metadata = Mock(return_value=observation())
            self.assertEqual(h.readonly.derive(record, c, 'stage'), record)
            h.collect_metadata.assert_not_called()
            derived = h.readonly.derive(record, c, 'contract')
            self.assertEqual(derived['candidate_binary_sha256'], m.OBSERVER_BINARY)
            self.assertEqual(derived, m.observed_geometry(m.derive_observer(record, c, 'contract'), observation()))
            h.collect_metadata.assert_called_once_with()
            h.collect_metadata.reset_mock(); h.boot.return_value = c['Map_prepared_boot']
            with self.assertRaises(AssertionError): h.readonly.derive(record, c, 'contract')
            h.collect_metadata.assert_not_called()


class BootAndMetadataTests(unittest.TestCase):
    def host(self):
        h = m.MappingObserverHost.__new__(m.MappingObserverHost)
        h.config = fixture(); h.boot = Mock(return_value='current-preparation')
        return h

    def test_all_new_boot_entrypoints_refuse_preparation_boot_before_parent_or_power(self):
        h = self.host()
        for name, args in [('watch', ()), ('worker', ('startup',)), ('supervise', ('guardian',)),
                           ('prepare_restart', ()), ('request_restart', ()), ('_read_admission', ()), ('note_failure', ('reason',))]:
            with self.subTest(name=name), patch.object(m.subprocess, 'run') as run, \
                    patch.object(m.parent.PresentCopyHost, name, create=True) as inherited:
                with self.assertRaises(AssertionError): getattr(h, name)(*args)
                inherited.assert_not_called(); run.assert_not_called()

    def test_actual_new_boot_enters_existing_serial_policy(self):
        h = self.host(); h.boot.return_value = 'later-trial-boot'
        for name, args in [('watch', ()), ('worker', ('startup',)), ('supervise', ('guardian',)), ('prepare_restart', ())]:
            with self.subTest(name=name), patch.object(m.parent.PresentCopyHost, name, return_value='entered') as inherited:
                self.assertEqual(getattr(h, name)(*args), 'entered')
                inherited.assert_called_once_with(*args)
        self.assertIs(m.MappingObserverHost.refuse_daily_power, m.parent.PresentCopyHost.refuse_daily_power)

    def test_pending_startup_does_not_read_metadata(self):
        h = self.host(); h.boot.return_value = 'trial-boot'
        with patch.object(m.parent.PresentCopyHost, '_read_admission', return_value=None), patch.object(m, 'load') as reader:
            self.assertIsNone(h._read_admission())
            reader.assert_not_called()

    def test_missing_metadata_refuses_and_valid_metadata_is_not_reader_acceptance(self):
        h = self.host(); h.boot.return_value = 'trial-boot'; h.put = Mock()
        with tempfile.TemporaryDirectory() as folder:
            h.scope = Path(folder)
            reader = SimpleNamespace(collect=Mock(return_value={'status': 'mapping-metadata-unavailable'}))
            with patch.object(m.parent.PresentCopyHost, '_read_admission', return_value=True), patch.object(m, 'load', return_value=reader):
                with self.assertRaises(AssertionError): h._read_admission()
                h.put.assert_not_called()
                metadata = dict(status='mapping-options-observed-not-reader-admitted', native_reader_admitted=False,
                                effective_cache_proven=False, cache_option=15)
                reader.collect.return_value = metadata
                self.assertTrue(h._read_admission())
                args = h.put.call_args.args
                self.assertEqual(args[1]['candidate_binary_sha256'], m.OBSERVER_BINARY)
                self.assertFalse(args[1]['metadata']['native_reader_admitted'])
                self.assertEqual(args[1]['metadata']['cache_option'], 15)

    def test_repeated_metadata_receipt_must_match_same_boot_exactly(self):
        h = self.host(); h.boot.return_value = 'trial-boot'; h.put = Mock()
        metadata = dict(status='mapping-options-observed-not-reader-admitted', native_reader_admitted=False,
                        effective_cache_proven=False, cache_option=4)
        with tempfile.TemporaryDirectory() as folder:
            h.scope = Path(folder)
            receipt = dict(boot_private='trial-boot', candidate_binary_sha256=m.OBSERVER_BINARY, metadata=metadata)
            (h.scope/'mapping-observation-trial-boot.json').write_text(json.dumps(receipt))
            reader = SimpleNamespace(collect=Mock(return_value=copy.deepcopy(metadata)))
            with patch.object(m.parent.PresentCopyHost, '_read_admission', return_value=True), \
                    patch.object(m, 'load', return_value=reader), patch.object(m.base, 'secure'):
                self.assertTrue(h._read_admission()); h.put.assert_not_called()
                reader.collect.return_value['cache_option'] = 1
                with self.assertRaises(AssertionError): h._read_admission()


class NativeAndJobTests(unittest.TestCase):
    def test_uuid_join_accepts_case_only_and_refuses_other_spellings(self):
        self.assertEqual(m.canonical_uuid(BASE_UUID.upper()), BASE_UUID)
        for value in (None, 1, BASE_UUID.replace('-', ''), '{' + BASE_UUID + '}',
                      'z' + BASE_UUID[1:], BASE_UUID.replace('-', '_')):
            with self.subTest(value=value), self.assertRaises(AssertionError):
                m.canonical_uuid(value)

    @contextlib.contextmanager
    def packet(self):
        c = fixture()
        with tempfile.TemporaryDirectory() as folder:
            scope = Path(folder)
            jobs = {'/Library/LaunchDaemons/local.phxboot.plist': 'new-startup',
                    '/Library/LaunchDaemons/dev.nullarc.admission.plist': 'new-guardian'}
            c['jobs'] = jobs
            c['Map_job_files'] = {path: ('startup.plist' if path.endswith('local.phxboot.plist') else 'guardian.plist') for path in jobs}
            for path, name in c['Map_job_files'].items():
                role = 'startup' if name == 'startup.plist' else 'guardian'
                c['sealed'][name] = jobs[path]
                (scope/name).write_bytes(plistlib.dumps(dict(ProgramArguments=[m.base.PYTHON, '-B', '-I', str(scope/'owner-startup-private.py'), role], RunAtLoad=True)))
            c['watcher_job_sha256'] = 'watcher-hash'; c['sealed']['watcher-job.plist'] = 'watcher-hash'
            (scope/'watcher-job.plist').write_bytes(plistlib.dumps(dict(ProgramArguments=[m.base.PYTHON, '-B', '-I', str(scope/'owner-startup-private.py'), 'watch'], RunAtLoad=True)))
            native = dict(status='built-private-map-observer-not-installed-or-hardware-accepted', observer_driver_sha256=m.DRIVER_SHA,
                          roles={'baseline': dict(bundle_files_private=c['Map_control_bundle_private'], identity_private={'image_uuid_private':BASE_UUID}),
                                 'observer': dict(bundle_files_private=c['Map_observer_bundle_private'], identity_private={'image_uuid_private':OBSERVER_UUID})})
            (scope/'map-native-report-private.json').write_text(json.dumps(native))
            yield c, scope, native

    def test_native_pair_and_all_job_arguments_are_scope_bound(self):
        with self.packet() as (c, scope, native), patch.object(m.base, 'sha', return_value=m.NATIVE_REPORT_SHA):
            m.validate_native_and_jobs(c, scope)
            for role in ('baseline', 'observer'):
                native['roles'][role]['identity_private']['image_uuid_private'] = native['roles'][role]['identity_private']['image_uuid_private'].upper()
            (scope/'map-native-report-private.json').write_text(json.dumps(native))
            m.validate_native_and_jobs(c, scope)
            native['roles']['baseline']['identity_private']['image_uuid_private'] = OBSERVER_UUID
            (scope/'map-native-report-private.json').write_text(json.dumps(native))
            with self.assertRaises(AssertionError): m.validate_native_and_jobs(c, scope)

    def test_unknown_native_identity_or_report_digest_refuses(self):
        with self.packet() as (c, scope, native):
            with patch.object(m.base, 'sha', return_value='unknown'), self.assertRaises(AssertionError): m.validate_native_and_jobs(c, scope)
            native['roles']['observer']['identity_private']['image_uuid_private'] = 'unknown'
            (scope/'map-native-report-private.json').write_text(json.dumps(native))
            with patch.object(m.base, 'sha', return_value=m.NATIVE_REPORT_SHA), self.assertRaises(AssertionError): m.validate_native_and_jobs(c, scope)

    def test_old_scope_arguments_or_resident_job_refuse(self):
        for name, kind in [('startup.plist', 'old-scope'), ('guardian.plist', 'resident'), ('watcher-job.plist', 'old-scope')]:
            with self.subTest(name=name, kind=kind), self.packet() as (c, scope, native):
                job = plistlib.loads((scope/name).read_bytes())
                if kind == 'old-scope': job['ProgramArguments'][3] = '/old/owner-startup-private.py'
                else: job['KeepAlive'] = True
                (scope/name).write_bytes(plistlib.dumps(job))
                with patch.object(m.base, 'sha', return_value=m.NATIVE_REPORT_SHA), self.assertRaises(AssertionError): m.validate_native_and_jobs(c, scope)


class RestoreTests(unittest.TestCase):
    def test_restore_input_check_requires_current_R2a_images(self):
        h = m.MappingObserverHost.__new__(m.MappingObserverHost); c = fixture(); h.contract = Mock(return_value=c)
        with tempfile.TemporaryDirectory() as folder:
            h.scope = Path(folder); h.readonly = SimpleNamespace(OLD=Path(folder))
            c['watcher_job'] = str(Path(folder)/'absent-watcher.plist')
            route = SimpleNamespace(static=Mock(), efi=Mock(return_value=contextlib.nullcontext(Path(folder))),
                                    files=Mock(return_value=c['Map_after_EFI_private']))
            old = {**m.parent.BEFORE, 'firmware': 'unchanged', 'startup': 'historical-startup', 'guardian': 'historical-guardian'}
            def digest(path):
                if str(path) in c['jobs']: return c['jobs'][str(path)]
                return next(rec['sha256'] for rec in c['Map_recovery_jobs'].values() if Path(path).name == rec['backup'])
            pending = Mock(); pending.exists.return_value = False
            with patch.object(m, 'load', return_value=route), patch.object(m.parent, 'physical_baseline', return_value=old), \
                    patch.object(m.parent, 'require_protected_file') as require, patch.object(m.base, 'secure'), patch.object(m.base, 'sha', side_effect=digest), \
                    patch.object(m, 'Path', side_effect=lambda p: pending if str(p)=='/var/db/phxboot.pending' else Path(p)):
                self.assertEqual(h.check_restore_inputs(), c)
            values = {call.args[0]:call.args[1] for call in require.call_args_list}
            for path, expected in m.parent.AFTER.items(): self.assertEqual(values[path], expected)
            self.assertEqual(values['firmware'], 'unchanged')
            self.assertNotIn('startup', values); self.assertNotIn('guardian', values)

    def test_unknown_preflight_refuses_before_any_restore_operation(self):
        h = m.MappingObserverHost.__new__(m.MappingObserverHost)
        h.check_restore_inputs = Mock(side_effect=AssertionError('unknown'))
        with patch.object(m, 'load') as load, patch.object(m.subprocess, 'run') as run, self.assertRaises(AssertionError): h.restore()
        load.assert_not_called(); run.assert_not_called()

    def test_restore_only_current_R1b_executable_and_R2a_jobs_without_power(self):
        h = m.MappingObserverHost.__new__(m.MappingObserverHost); c = fixture()
        h.check_restore_inputs = Mock(return_value=c); h.restore_jobs = Mock(); h.retire_watcher = Mock()
        with tempfile.TemporaryDirectory() as folder:
            h.scope = Path(folder); (h.scope/'map-control-kernel.bin').write_bytes(b'accepted-R1b')
            root = Path(folder)/'inactive-EFI'
            route = SimpleNamespace(static=Mock(return_value='exact-route'), efi=Mock(return_value=contextlib.nullcontext(root)),
                                    files=Mock(side_effect=[c['Map_after_EFI_private'], c['Map_before_EFI_private']]))
            h.readonly = SimpleNamespace(OLD=Path(folder), atomic_file=Mock())
            pending = Mock(); pending.exists.return_value = False
            with patch.object(m, 'load', return_value=route), patch.object(m, 'Path', return_value=pending), patch.object(m.subprocess, 'run') as run:
                h.restore()
            h.readonly.atomic_file.assert_called_once_with(root/m.KERNEL, b'accepted-R1b', [m.BASE_BINARY, m.OBSERVER_BINARY])
            h.restore_jobs.assert_called_once(); h.retire_watcher.assert_called_once()
            self.assertFalse(any('shutdown' in str(x) or 'reboot' in str(x) for x in run.call_args_list))

    def test_job_restore_preflights_all_current_targets_before_first_write(self):
        h = m.MappingObserverHost.__new__(m.MappingObserverHost); c = fixture(); h.contract = Mock(return_value=c)
        with tempfile.TemporaryDirectory() as folder:
            h.scope = Path(folder)
            for rec in c['Map_recovery_jobs'].values(): (h.scope/rec['backup']).write_bytes(b'retained-job')
            h.readonly = SimpleNamespace(atomic_file=Mock())

            def digest(path):
                name = str(path)
                if name in c['jobs']: return c['jobs'][name]
                for rec in c['Map_recovery_jobs'].values():
                    if Path(path).name == rec['backup']: return rec['sha256']
                raise AssertionError('unexpected path')

            with patch.object(m.base, 'secure'), patch.object(m.base, 'sha', side_effect=digest): h.restore_jobs()
            self.assertEqual(h.readonly.atomic_file.call_count, 2)
            for call, (path, rec) in zip(h.readonly.atomic_file.call_args_list, c['Map_recovery_jobs'].items()):
                self.assertEqual(call.args, (path, b'retained-job', [c['jobs'][path], rec['sha256']]))
            h.readonly.atomic_file.reset_mock()
            with patch.object(m.base, 'secure'), patch.object(m.base, 'sha', side_effect=lambda p: 'unknown' if str(p)=='guardian' else digest(p)), self.assertRaises(AssertionError):
                h.restore_jobs()
            h.readonly.atomic_file.assert_not_called()


if __name__ == '__main__': unittest.main()
