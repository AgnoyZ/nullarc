#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Sealed PCI observation scope; no installation or ordinary restart entry."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mapping = load('PCI_mapping_host', Path(__file__).with_name('build34_map_observer_host.py'))
irq = load('PCI_passive_reader', Path(__file__).with_name('build34_pci_irq_observation.py'))
parent = mapping.parent.PresentCopyHost
base = mapping.base
KERNEL, EXE = mapping.KERNEL, mapping.EXE
RESTORE = mapping.OBSERVER_BINARY
OBSERVER = 'd2d6abe1e35a99c6a0f197d4a9a4726e0f8caedaf7942712aba851ab24bfef70'
SOURCE = '643fe8588a375908a3865d11d21f0dad2b676a1f'
REPORT = 'pci-build-report-private.json'
RESTORE_FILE, OBSERVER_FILE = 'pci-restore-kernel.bin', 'pci-observer-kernel.bin'
INTENT = 'pci-ordinary-restart.intent'
WATCHER = 'pci-watcher-job.plist'


def validate_delta(c, *, require_authorized=True):
    assert c['PCI_source_checkpoint'] == SOURCE and type(c['PCI_trial_authorized']) is bool
    if require_authorized:
        assert c['PCI_trial_authorized'] is True, 'fresh PCI observer trial authorization missing'
    assert c['PCI_GPU_pressure_authorized'] is False and c['PCI_IRQ_registration_authorized'] is False
    assert c['PCI_ordinary_restart_limit'] == 1 and c['daily_recovery_restart_limit'] == 0
    assert c['automatic_recovery_reboots'] == 1 and c['startup_limits_seconds'] == [45, 150, 300]
    assert c['resident_monitor_enabled'] is False and c['pressure_probe_enabled'] is False
    assert c['Map_trial_authorized'] is True
    retained = c['PCI_retained_jobs']
    mapping.validate_delta({**c, 'jobs': retained})
    assert c['PCI_prepared_boot'] and type(c['PCI_prepared_boot']) is str
    assert c['PCI_prepared_boot'] != c['Map_prepared_boot']
    before, after = c['PCI_before_EFI_private'], c['PCI_after_EFI_private']
    assert before == c['Map_after_EFI_private'] and len(before) == 358 and set(before) == set(after)
    assert {n for n in before if before[n] != after[n]} == {KERNEL}
    restore, observer = c['Map_observer_bundle_private'], c['PCI_observer_bundle_private']
    assert len(restore) == 3 and set(restore) == set(observer)
    assert {n for n in restore if restore[n] != observer[n]} == {EXE}
    assert before[KERNEL] == restore[EXE] and after[KERNEL] == observer[EXE]
    assert restore[EXE]['sha256'] == c['sealed'][RESTORE_FILE] == RESTORE
    assert observer[EXE]['sha256'] == c['sealed'][OBSERVER_FILE] == OBSERVER
    assert mapping.canonical_uuid(c['Map_after_uuid_private']) != mapping.canonical_uuid(c['PCI_after_uuid_private'])
    assert len(retained) == 2 and set(retained) == set(c['jobs']) == set(c['PCI_recovery_jobs'])
    assert all(retained[path] != c['jobs'][path] for path in retained)
    for path, record in c['PCI_recovery_jobs'].items():
        assert retained[path] == c['sealed'][record['backup']] == record['sha256']
    assert c['sealed'][WATCHER] == c['watcher_job_sha256']
    assert {REPORT, 'build34_map_observer_host.py', 'build34_pci_irq_observation.py',
            'owner-startup-private.py'} <= set(c['sealed'])


def validate_inputs(c, scope):
    previous = Path(c['PCI_prior_scope'])
    assert previous != scope and previous.is_absolute()
    path = previous / 'contract-private.json'
    base.secure(previous)
    base.secure(path)
    assert base.sha(path) == c['PCI_prior_contract_sha256']
    old = json.loads(path.read_bytes())
    assert old['scope_kind'] == mapping.MappingObserverHost.SCOPE_KIND
    mapping.validate_delta(old)
    assert old['jobs'] == c['PCI_retained_jobs']
    assert old['Map_after_EFI_private'] == c['PCI_before_EFI_private']
    assert old['Map_after_uuid_private'] == c['Map_after_uuid_private']
    assert old['sealed']['owner-startup-private.py'] == c['sealed']['build34_map_observer_host.py']
    assert old['watcher_job'] != c['watcher_job']
    report = json.loads((scope / REPORT).read_bytes())
    assert report['status'] == 'built-private-pci-observer-awaiting-trial-scope' and report['kernel_build'] == 34
    assert report['os_build'] == '25G332' and report['strict_signatures_passed'] is True
    assert report['restore_bundle_byte_exact'] is True and report['generic_AuxKC_admitted'] is False
    assert report['restore_executable_sha256'] == RESTORE and report['observer_executable_sha256'] == OBSERVER
    for filename, job_path, role, digest in [
        (c['Map_job_files'][p], p, 'startup' if Path(p).name == 'local.phxboot.plist' else 'guardian', h)
        for p, h in c['jobs'].items()
    ] + [(WATCHER, c['watcher_job'], 'watch', c['watcher_job_sha256'])]:
        assert c['sealed'][filename] == digest
        job = plistlib.loads((scope / filename).read_bytes())
        assert job['ProgramArguments'] == [base.PYTHON, '-B', '-I', str(scope / 'owner-startup-private.py'), role]
        assert job['Label'] == Path(job_path).stem and job['RunAtLoad'] is True and not job.get('KeepAlive')
    return old


def intent_record(c, scope):
    return dict(scope=str(scope), prepared_boot_private=c['PCI_prepared_boot'],
                observer_sha256=OBSERVER, restore_sha256=RESTORE, ordinary_requests=1)


def classification(sample):
    mode = sample['start_time_config_classification']
    assert sample['status'] == 'start-time-pci-config-classification' and mode in irq.START_CLASSES
    assert sample['pci'] == '1002:1900' and sample['PhxBringup_build'] == 34 and sample['os_build'] == '25G332'
    assert sample['direct_pci_provider_matched'] is True
    for key in ('device_opened', 'raw_registry_saved', 'active_interrupt_mode_proved', 'active_isr_proved',
                'eop_delivery_proved', 'ih_consumer_ownership_proved', 'fence_visibility_proved'):
        assert sample[key] is False
    return mode


def derive(record, c, kind, map_sample=None, pci_sample=None):
    result = mapping.derive_observer(record, c, kind)
    if kind == 'contract':
        result['candidate_files'] = copy.deepcopy(c['PCI_observer_bundle_private'])
        result['candidate_binary_sha256'] = OBSERVER
        result['candidate_image_uuid'] = c['PCI_after_uuid_private']
        result = mapping.observed_geometry(result, map_sample)
        geometry = result['baseline_node_geometry']
        assert irq.START_CONFIG not in geometry
        geometry[irq.START_CONFIG] = classification(pci_sample)
    return result


def verify_disk(d, k, manifest):
    d.r.verify_disk('candidate')
    with d.r.efi(d.r.static()) as root:
        assert d.r.files(root) == manifest
        subprocess.run(['/usr/bin/codesign', '--verify', '--strict', str(root / d.r.ACTIVE)],
                       capture_output=True, check=True, timeout=20)
    assert d.plugin.files(d.plugin.LIVE) == k['plugin_after']
    assert d.r.support.security() == k['security']


class MappingRestoreView(parent):
    """Independent control contract; disk-only derivation needs no live properties."""
    SCOPE_KIND = mapping.MappingObserverHost.SCOPE_KIND

    def contract(self):
        c = super().contract()
        mapping.validate_delta(c)
        mapping.validate_native_and_jobs(c, self.scope)
        return c

    def __init__(self, scope):
        super().__init__(scope)
        previous = self.readonly.derive
        self.readonly.derive = lambda record, config, kind: mapping.derive_observer(
            previous(record, config, kind), config, kind)


class PCIObserverHost(mapping.MappingObserverHost):
    SCOPE_KIND = 'R3-pci-start-observer-retained-map-R2a-startup-recovery'

    def validate_efi_contract(self, c):
        parent.validate_efi_contract(self, c)
        validate_delta(c, require_authorized=False)

    def contract(self):
        c = parent.contract(self)
        validate_delta(c)
        validate_inputs(c, self.scope)
        base.secure(self.scope / INTENT)
        assert json.loads((self.scope / INTENT).read_bytes()) == intent_record(c, self.scope)
        return c

    def __init__(self, directory):
        parent.__init__(self, directory)
        previous = self.readonly.derive
        self.admission_mode = None

        def scoped_record(record, config, kind):
            result = previous(record, config, kind)
            if kind == 'stage':
                return derive(result, config, kind)
            self.require_new_boot()
            sample = irq.collect()
            mode = classification(sample)
            assert self.admission_mode in (None, mode)
            self.admission_mode = mode
            return derive(result, config, kind, self.collect_metadata(), sample)

        self.readonly.derive = scoped_record
        self.readonly.full_static = self.full_static

    def require_new_boot(self):
        assert self.boot() != self.config['PCI_prepared_boot'], 'PCI trial still in preparation boot'

    def full_static(self):
        d, k, c = self.readonly.build()
        verify_disk(d, k, c['PCI_after_EFI_private'])
        cache = self.cache_check()
        self.acpi_check()
        for path in ['/Library/Extensions/PhxAccel.kext', str(d.plugin.LIVE)]:
            subprocess.run(['/usr/bin/codesign', '--verify', '--strict', path],
                           capture_output=True, check=True, timeout=20)
        assert not d.r.support.report_names() - set(k['reports_before'])
        return d, k, c, cache

    def _read_admission(self):
        self.require_new_boot()
        result = base.Host._read_admission(self)
        if result is True:
            sample = irq.collect()
            mode = classification(sample)
            assert self.admission_mode == mode
            name = 'pci-observation-' + self.boot() + '.json'
            receipt = dict(boot_private=self.boot(), candidate_binary_sha256=OBSERVER, classification=mode)
            if (self.scope / name).exists():
                base.secure(self.scope / name)
                assert json.loads((self.scope / name).read_bytes()) == receipt
            else:
                self.put(name, receipt)
        return result

    def route(self):
        return load('PCI_exact_EFI_route', self.readonly.OLD / 'internal-route-private.py')

    def check_restore_inputs(self):
        self.require_new_boot()
        c = self.contract()
        route = self.route()
        with route.efi(route.static()) as root:
            assert route.files(root) in (c['PCI_before_EFI_private'], c['PCI_after_EFI_private'])
        expected = mapping.parent.physical_baseline(c)
        expected.update(mapping.parent.AFTER)
        for path, digest in expected.items():
            if path not in c['jobs']:
                mapping.parent.require_protected_file(path, digest)
        for path, record in c['PCI_recovery_jobs'].items():
            base.secure(path)
            assert base.sha(path) in (c['jobs'][path], record['sha256'])
            assert base.sha(self.scope / record['backup']) == record['sha256']
        for path, digest in ((Path(c['watcher_job']), c['watcher_job_sha256']),
                             (Path('/var/db/phxboot.pending'), mapping.parent.EMPTY_SHA256)):
            if path.exists():
                base.secure(path)
                assert base.sha(path) == digest
        return c

    def restore(self):
        c = self.check_restore_inputs()
        route = self.route()
        with route.efi(route.static(), writable=True) as root:
            assert route.files(root) in (c['PCI_before_EFI_private'], c['PCI_after_EFI_private'])
            self.readonly.atomic_file(root / KERNEL, (self.scope / RESTORE_FILE).read_bytes(), [RESTORE, OBSERVER])
            assert route.files(root) == c['PCI_before_EFI_private']
        for path, record in c['PCI_recovery_jobs'].items():
            self.readonly.atomic_file(path, (self.scope / record['backup']).read_bytes(), [c['jobs'][path], record['sha256']])
        self.retire_watcher()
        pending = Path('/var/db/phxboot.pending')
        if pending.exists():
            base.secure(pending)
            assert pending.read_bytes() == b''
            pending.unlink()
        subprocess.run(['/usr/sbin/sysctl', '-w', 'debug.phxfb_hold=0'], capture_output=True, timeout=5)
        subprocess.run(['/bin/sync'], check=True, timeout=15)

    def verify_restore(self):
        self.require_new_boot()
        c = self.contract()
        old = MappingRestoreView(Path(c['PCI_prior_scope']))
        d, k, previous = old.readonly.build()
        assert previous['Map_after_EFI_private'] == c['PCI_before_EFI_private']
        verify_disk(d, k, c['PCI_before_EFI_private'])
        old.cache_check()
        old.acpi_check()
        assert not Path(c['watcher_job']).exists()
        return True

    verify = verify_restore

    def request_restart(self):
        self.require_new_boot()
        intent = Path(self.policy.journal) / 'recovery-restart.intent'
        base.secure(intent)
        assert json.loads(intent.read_bytes()) == {'boot': self.boot(), 'requests': 1}
        subprocess.run(['/sbin/shutdown', '-r', 'now', 'Bounded build34 PCI observer recovery'],
                       capture_output=True, check=True, timeout=15)


def check_preparation(scope):
    host = PCIObserverHost.__new__(PCIObserverHost)
    host.scope = scope
    c = parent.contract(host)
    validate_delta(c, require_authorized=False)
    assert c['PCI_trial_authorized'] is False
    validate_inputs(c, scope)
    assert not Path(c['watcher_job']).exists()
    for name in (INTENT, 'recovery-journal', 'daily-recovery-journal'):
        assert not (scope / name).exists()
    for path, digest in c['PCI_retained_jobs'].items():
        base.secure(path)
        assert base.sha(path) == digest
    actual_boot = subprocess.check_output(['/usr/sbin/sysctl', '-n', 'kern.bootsessionuuid'], text=True, timeout=10).strip()
    assert actual_boot == c['PCI_prepared_boot']
    return dict(status='passed-inactive-pci-observer-scope', authorization=False, EFI_files=len(c['PCI_before_EFI_private']),
                executable_deltas=1, live_jobs_unchanged=True, recovery_journals_created=0, power_actions=0)


if __name__ == '__main__':
    os.umask(0o077)
    scope = Path(__file__).resolve().parent
    action = sys.argv[1]
    if action == 'check-preparation':
        print(json.dumps(check_preparation(scope), sort_keys=True))
    else:
        host = PCIObserverHost(scope)
        if action == 'watch': host.watch()
        elif action == 'recover': host.note_failure('protected-startup-failure')
        elif action == 'worker': host.worker(sys.argv[2])
        else: host.supervise(action)
