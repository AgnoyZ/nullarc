#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fresh mapping-only boot scope retaining the accepted R1b/R2a desktop.

No installer or ordinary-restart dispatcher. Runtime entry requires a separate
explicit fresh-scope grant. Historical parent fields remain history; they do
not grant this scope permission. Never use this host for full R3 transforms.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import uuid


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


parent = load('MapObserver_R2a_host', Path(__file__).with_name('build34_present_copy_host.py'))
base = parent.base
KERNEL = parent.r1b.KERNEL
EXE = parent.r1b.EXECUTABLE
BASE_BINARY = parent.r1b.R1B_BINARY
OBSERVER_BINARY = '923182fab482d5c584f484520622283922f67a9caaa2d310e638cd71d1fb1dc7'
SOURCE = '3d26409b1b151992d0dcaeb7093ce104a5c034dd'
DRIVER_SHA = '9826065e11adc6ec7363459210704b685d1fc5df29758271ca674163254cd0c3'
NATIVE_REPORT_SHA = '36ab22c4ac66bb81b1bbb3a7f277ad8efb3fd52304cb7196bfece89ac5f24106'
READER_SHA = 'ba9c8f9ff566a99f74646eaac8b2d72866b97d2d796b59e73cb8eadbce35ef4f'
MAP_PROPERTIES = ('phx-bar0-map-options', 'phx-bar0-map-cache-option',
                  'phx-bar0-map-observation-version')


def canonical_uuid(value):
    """Join native Mach-O and historical UUID spellings without changing identity."""
    assert type(value) is str and len(value) == 36
    try:
        result = str(uuid.UUID(value))
    except ValueError:
        raise AssertionError('invalid image UUID') from None
    assert result == value.lower()
    return result


def validate_delta(c, *, require_authorized=True):
    assert c['Map_source_checkpoint'] == SOURCE and c['Map_driver_sha256'] == DRIVER_SHA
    assert c['Map_full_R3_enabled'] is False and c['Map_native_reader_bound'] is False
    assert type(c['Map_trial_authorized']) is bool
    if require_authorized:
        assert c['Map_trial_authorized'] is True, 'fresh mapping-observer trial authorization missing'
    assert c['Map_native_report_sha256'] == NATIVE_REPORT_SHA
    assert c['sealed']['map-native-report-private.json'] == NATIVE_REPORT_SHA
    assert c['sealed']['build34_map_observation.py'] == READER_SHA
    before, after = c['Map_before_EFI_private'], c['Map_after_EFI_private']
    assert before == c['EFI_after_private'] == c['R2a_parent_EFI_private']
    assert len(before) == 358 and set(before) == set(after)
    assert {n for n in before if before[n] != after[n]} == {KERNEL}
    control, observer = c['Map_control_bundle_private'], c['Map_observer_bundle_private']
    assert control == c['R1b_kernel_files_private']
    assert set(control) == set(observer) and {n for n in control if control[n] != observer[n]} == {EXE}
    assert control[EXE]['sha256'] == BASE_BINARY and observer[EXE]['sha256'] == OBSERVER_BINARY
    assert before[KERNEL] == control[EXE] and after[KERNEL] == observer[EXE]
    assert c['sealed']['map-control-kernel.bin'] == BASE_BINARY
    assert c['sealed']['map-observer-kernel.bin'] == OBSERVER_BINARY
    assert c['Map_before_uuid_private'] == c['R1b_image_uuid_private']
    assert canonical_uuid(c['Map_before_uuid_private']) != canonical_uuid(c['Map_after_uuid_private'])
    # Parent prepared_boot must remain unchanged for its historical admission.
    # All new operational entrypoints separately require Map_prepared_boot.
    assert type(c['Map_prepared_boot']) is str and c['Map_prepared_boot']
    assert len(c['jobs']) == 2 and set(c['jobs']) == set(c['Map_retained_jobs']) == set(c['Map_recovery_jobs'])
    assert c['jobs'] == c['Map_new_jobs'] and c['jobs'] != c['Map_retained_jobs']
    for path, recovery in c['Map_recovery_jobs'].items():
        assert recovery['sha256'] == c['Map_retained_jobs'][path]
        assert c['sealed'][recovery['backup']] == recovery['sha256']
    assert c['startup_limits_seconds'] == [45, 150, 300]
    assert c['automatic_recovery_reboots'] == 1 and c['daily_recovery_restart_limit'] == 0
    assert c['resident_monitor_enabled'] is False and c['pressure_probe_enabled'] is False


def derive_observer(record, c, kind):
    assert kind in ('contract', 'stage')
    result = copy.deepcopy(record)
    if kind == 'contract':
        assert result['candidate_files'] == c['Map_control_bundle_private']
        assert result['candidate_binary_sha256'] == BASE_BINARY
        assert result['candidate_image_uuid'] == c['Map_before_uuid_private']
        result['candidate_files'] = copy.deepcopy(c['Map_observer_bundle_private'])
        result['candidate_binary_sha256'] = OBSERVER_BINARY
        result['candidate_image_uuid'] = c['Map_after_uuid_private']
    return result


def observed_geometry(record, metadata):
    """Extend the exact old geometry by only the validated observer properties."""
    assert metadata['status'] == 'mapping-options-observed-not-reader-admitted'
    assert metadata['native_reader_admitted'] is False and metadata['effective_cache_proven'] is False
    assert type(metadata['kernel_build']) is int and metadata['kernel_build'] == 34
    assert type(metadata['observation_version']) is int and metadata['observation_version'] == 1
    options, cache = metadata['map_options'], metadata['cache_option']
    assert type(options) is int and 0 <= options < 1 << 32
    assert type(cache) is int and cache == (options & 0xf00) >> 8
    result = copy.deepcopy(record)
    geometry = result['baseline_node_geometry']
    assert not set(MAP_PROPERTIES) & set(geometry)
    assert geometry['phx-build'] == 34
    assert geometry['phx-fb-aper-len'] == metadata['BAR0_bytes']
    geometry.update(zip(MAP_PROPERTIES, (options, cache, 1)))
    return result


def pre_restart_live_contract(candidate, c):
    """Disk remains observer; loaded identity is still the exact retained R1b."""
    assert candidate['candidate_files'] == c['Map_observer_bundle_private']
    assert candidate['candidate_binary_sha256'] == OBSERVER_BINARY
    assert candidate['candidate_image_uuid'] == c['Map_after_uuid_private']
    live = copy.deepcopy(candidate)
    live['candidate_image_uuid'] = c['Map_before_uuid_private']
    return live


def validate_native_and_jobs(c, scope):
    assert base.sha(scope / 'map-native-report-private.json') == NATIVE_REPORT_SHA
    native = json.loads((scope / 'map-native-report-private.json').read_text())
    assert native['status'] == 'built-private-map-observer-not-installed-or-hardware-accepted'
    assert native['observer_driver_sha256'] == DRIVER_SHA
    for role, key, uid in [('baseline', 'Map_control_bundle_private', 'Map_before_uuid_private'),
                           ('observer', 'Map_observer_bundle_private', 'Map_after_uuid_private')]:
        assert native['roles'][role]['bundle_files_private'] == c[key]
        assert canonical_uuid(native['roles'][role]['identity_private']['image_uuid_private']) == canonical_uuid(c[uid])
    assert set(c['Map_job_files']) == set(c['jobs'])
    for path, filename in c['Map_job_files'].items():
        assert c['sealed'][filename] == c['jobs'][path]
        role = 'startup' if Path(path).name == 'local.phxboot.plist' else 'guardian'
        job = plistlib.loads((scope / filename).read_bytes())
        assert job['ProgramArguments'] == [base.PYTHON, '-B', '-I', str(scope / 'owner-startup-private.py'), role]
        assert job.get('RunAtLoad') is True and not job.get('KeepAlive')
    assert c['sealed']['watcher-job.plist'] == c['watcher_job_sha256']
    watcher = plistlib.loads((scope / 'watcher-job.plist').read_bytes())
    assert watcher['ProgramArguments'] == [base.PYTHON, '-B', '-I', str(scope / 'owner-startup-private.py'), 'watch']
    assert watcher.get('RunAtLoad') is True and not watcher.get('KeepAlive')


def check_preparation(directory):
    """Validate an explicitly unauthorized inactive packet, never instantiate it."""
    h = MappingObserverHost.__new__(MappingObserverHost)
    h.scope = Path(directory)
    # Preserve all parent admission checks. Only the extra new grant remains
    # deliberately false; runtime construction still requires it to be true.
    c = parent.PresentCopyHost.contract(h)
    validate_delta(c, require_authorized=False)
    assert c['Map_trial_authorized'] is False
    validate_native_and_jobs(c, h.scope)
    assert not (h.scope / 'recovery-journal').exists() and not (h.scope / 'daily-recovery-journal').exists()
    assert not Path(c['watcher_job']).exists()
    for path, digest in c['Map_retained_jobs'].items():
        base.secure(path)
        assert base.sha(path) == digest
    actual_boot = subprocess.check_output(['/usr/sbin/sysctl', '-n', 'kern.bootsessionuuid'], text=True, timeout=10).strip()
    assert actual_boot == c['Map_prepared_boot']
    return dict(status='passed-inactive-unauthorized-map-observer-scope-preparation',
                kernel_build=34, native_pair_and_jobs_bound=True, journals_created=0,
                new_jobs_installed=0, trial_authorized=False, GPU_submissions=0, power_actions=0)


class MappingObserverHost(parent.PresentCopyHost):
    SCOPE_KIND = 'R3-map-observer-retained-R1b-R2a-startup-recovery'

    def validate_efi_contract(self, value):
        super().validate_efi_contract(value)
        validate_delta(value, require_authorized=False)

    def contract(self):
        value = super().contract()
        validate_delta(value)
        validate_native_and_jobs(value, self.scope)
        return value

    def __init__(self, directory):
        super().__init__(directory)
        c = self.config
        accepted = Path(c['Map_parent_scope'])
        base.secure(accepted / 'contract-private.json')
        assert base.sha(accepted / 'contract-private.json') == c['Map_parent_contract_sha256']
        accepted_config = json.loads((accepted / 'contract-private.json').read_text())
        assert accepted_config['scope_kind'] == parent.PresentCopyHost.SCOPE_KIND
        assert accepted_config['EFI_after_private'] == c['Map_before_EFI_private']
        assert accepted_config['jobs'] == c['Map_retained_jobs']
        # Reconstruct the extra independent parent only during recovery, not
        # on every ordinary startup worker's timed critical path.
        self.accepted_path = accepted
        previous = self.readonly.derive
        def derive(record, config, kind):
            result = derive_observer(previous(record, config, kind), config, kind)
            if kind == 'contract':
                self.require_new_boot()
                result = observed_geometry(result, self.collect_metadata())
            return result
        self.readonly.derive = derive
        self.readonly.full_static = self.full_static

    def collect_metadata(self):
        reader = load('MapObserver_passive_metadata', self.scope / 'build34_map_observation.py')
        return reader.collect()

    def require_new_boot(self):
        assert self.boot() != self.config['Map_prepared_boot'], 'mapping trial still in preparation boot'

    def note_failure(self, reason):
        self.require_new_boot()
        return super().note_failure(reason)

    def full_static(self):
        d, k, c = self.readonly.build()
        d.r.verify_disk('candidate')
        with d.r.efi(d.r.static()) as root:
            assert d.r.files(root) == c['Map_after_EFI_private']
            subprocess.run(['/usr/bin/codesign', '--verify', '--strict', str(root / d.r.ACTIVE)],
                           capture_output=True, check=True, timeout=20)
        assert d.plugin.files(d.plugin.LIVE) == k['plugin_after']
        cache = self.cache_check()
        self.acpi_check()
        for path in ['/Library/Extensions/PhxAccel.kext', str(d.plugin.LIVE)]:
            subprocess.run(['/usr/bin/codesign', '--verify', '--strict', path], capture_output=True, check=True, timeout=20)
        assert not d.r.support.report_names() - set(k['reports_before'])
        return d, k, c, cache

    def _read_admission(self):
        self.require_new_boot()
        result = super()._read_admission()
        if result is not True:
            return result
        metadata = self.collect_metadata()
        assert metadata['status'] == 'mapping-options-observed-not-reader-admitted'
        assert metadata['native_reader_admitted'] is False and metadata['effective_cache_proven'] is False
        record = dict(boot_private=self.boot(), candidate_binary_sha256=OBSERVER_BINARY, metadata=metadata)
        name = 'mapping-observation-' + self.boot() + '.json'
        if (self.scope / name).exists():
            base.secure(self.scope / name)
            assert json.loads((self.scope / name).read_text()) == record
        else:
            self.put(name, record)
        return True

    def check_restore_inputs(self):
        c = self.contract()
        route = load('MapObserver_exact_EFI_inputs', self.readonly.OLD / 'internal-route-private.py')
        with route.efi(route.static()) as root:
            assert route.files(root) in (c['Map_before_EFI_private'], c['Map_after_EFI_private'])
        expected = parent.physical_baseline(c)
        expected.update(parent.AFTER)  # Keep the accepted R2a, never its old VBL-only control.
        for path, digest in expected.items():
            if path not in c['jobs']:
                parent.require_protected_file(path, digest)
        for path, record in c['Map_recovery_jobs'].items():
            base.secure(path)
            assert base.sha(path) in (c['jobs'][path], record['sha256'])
            assert base.sha(self.scope / record['backup']) == record['sha256']
        watcher = Path(c['watcher_job'])
        if watcher.exists():
            base.secure(watcher)
            assert base.sha(watcher) == c['watcher_job_sha256']
        pending = Path('/var/db/phxboot.pending')
        if pending.exists():
            base.secure(pending)
            assert pending.read_bytes() == b''
        return c

    def restore_jobs(self):
        c = self.contract()
        for path, record in c['Map_recovery_jobs'].items():
            base.secure(path)
            assert base.sha(path) in (c['jobs'][path], record['sha256'])
            assert base.sha(self.scope / record['backup']) == record['sha256']
        for path, record in c['Map_recovery_jobs'].items():
            self.readonly.atomic_file(path, (self.scope / record['backup']).read_bytes(), [c['jobs'][path], record['sha256']])

    def restore(self):
        c = self.check_restore_inputs()
        route = load('MapObserver_exact_kernel_restore', self.readonly.OLD / 'internal-route-private.py')
        with route.efi(route.static(), writable=True) as root:
            assert route.files(root) in (c['Map_before_EFI_private'], c['Map_after_EFI_private'])
            self.readonly.atomic_file(root / KERNEL, (self.scope / 'map-control-kernel.bin').read_bytes(), [BASE_BINARY, OBSERVER_BINARY])
            assert route.files(root) == c['Map_before_EFI_private']
        self.restore_jobs()
        self.retire_watcher()
        pending = Path('/var/db/phxboot.pending')
        if pending.exists():
            base.secure(pending)
            assert pending.read_bytes() == b''
            pending.unlink()
        subprocess.run(['/usr/sbin/sysctl', '-w', 'debug.phxfb_hold=0'], capture_output=True, timeout=5)
        subprocess.run(['/bin/sync'], check=True, timeout=15)

    def verify_restore(self):
        accepted = parent.PresentCopyHost(self.accepted_path)
        d, k, c = accepted.readonly.build()
        d.r.verify_disk('candidate')
        with d.r.efi(d.r.static()) as root:
            assert d.r.files(root) == c['EFI_after_private'] == self.config['Map_before_EFI_private']
            subprocess.run(['/usr/bin/codesign', '--verify', '--strict', str(root / d.r.ACTIVE)], capture_output=True, check=True, timeout=20)
        assert d.plugin.files(d.plugin.LIVE) == k['plugin_after']
        accepted.cache_check()
        accepted.acpi_check()
        accepted.check_restore_inputs()
        assert d.r.support.security() == k['security']
        for path, digest in self.config['Map_retained_jobs'].items():
            base.secure(path)
            assert base.sha(path) == digest
        assert not Path(self.config['watcher_job']).exists()
        return True

    verify = verify_restore

    def watch(self):
        self.require_new_boot()
        return super().watch()

    def worker(self, role):
        self.require_new_boot()
        return super().worker(role)

    def supervise(self, role):
        self.require_new_boot()
        return super().supervise(role)

    def prepare_restart(self):
        self.require_new_boot()
        return super().prepare_restart()

    def request_restart(self):
        self.require_new_boot()
        subprocess.run(['/sbin/shutdown', '-r', 'now', 'Bounded build34 mapping-observer startup recovery'],
                       capture_output=True, check=True, timeout=15)


if __name__ == '__main__':
    os.umask(0o077)
    action = sys.argv[1]
    if action == 'check-preparation':
        print(json.dumps(check_preparation(Path(__file__).resolve().parent), sort_keys=True))
        raise SystemExit(0)
    host = MappingObserverHost(Path(__file__).resolve().parent)
    if action == 'watch': host.watch()
    elif action == 'recover': host.note_failure('protected-startup-failure')
    elif action == 'worker': host.worker(sys.argv[2])
    else: host.supervise(action)
