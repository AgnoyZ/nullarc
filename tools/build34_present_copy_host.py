#!/usr/bin/env python3
"""One R2a accelerator/cache trial retaining the accepted R1b/VBL/AML stack.

Run only in a fresh sealed scope. This module does not install or dispatch an
ordinary restart; the finite inherited startup policy controls recovery.
"""
import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import sys


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


r1b = load('R2a_R1b_host', Path(__file__).with_name('build34_r1b_resume_host.py'))
base = r1b.base
SOURCE = 'cac3df37345d13c7686dc9188656c846ce01e10d'
ACCELERATOR = r1b.acpi.vbl.ACCELERATOR
CACHE = r1b.acpi.vbl.CACHE
BEFORE = dict(r1b.acpi.vbl.EXPECTED_CANDIDATES)
AFTER = {
    ACCELERATOR: 'e5e9148513180eedec29f550c74a2ec132c797189edbe1edee08ef89e33bfc13',
    CACHE: '42277808a822db259de905fc50e3902f2e5cbcaff8ada302c7bdc7e527300593',
}


def validate_delta(c):
    assert c['R2a_source_checkpoint'] == SOURCE
    assert c['R2a_sequential_trial_authorized'] is True
    assert c['R2a_parent_EFI_private'] == c['EFI_after_private']
    assert set(c['R2a_changes']) == set(AFTER)
    for path, change in c['R2a_changes'].items():
        assert change['before'] == BEFORE[path] and change['after'] == AFTER[path]
        assert c['R2a_before_protected'][path] == BEFORE[path]
        assert c['sealed'][change['backup']] == BEFORE[path]
        assert c['sealed'][change['candidate']] == AFTER[path]
    assert c['R2a_before_uuid_private'] != c['R2a_after_uuid_private']
    assert set(c['R2a_retained_jobs']) == set(c['jobs']) == set(c['recovery_jobs'])
    for path, record in c['recovery_jobs'].items():
        assert record['sha256'] == c['R2a_retained_jobs'][path]
        assert c['sealed'][record['backup']] == record['sha256']


def derive_present(record, c, kind):
    result = copy.deepcopy(record)
    assert kind in ('contract', 'stage')
    if kind == 'contract':
        assert result['protected'] == c['R2a_before_protected']
        for path in AFTER:
            assert result['protected'][path] == BEFORE[path]
            result['protected'][path] = AFTER[path]
        runtime = result['desktop_runtime']
        assert runtime['accel_image_uuid'] == c['R2a_before_uuid_private']
        runtime['accel_image_uuid'] = c['R2a_after_uuid_private']
    return result


def pre_restart_live_contract(candidate, c):
    result = copy.deepcopy(candidate)
    assert result['desktop_runtime']['accel_image_uuid'] == c['R2a_after_uuid_private']
    result['desktop_runtime']['accel_image_uuid'] = c['R2a_before_uuid_private']
    return result


def physical_baseline(c):
    expected = copy.deepcopy(c['R2a_before_protected'])
    choice = c['daily_configuration']
    assert expected[choice['protected_path']] == choice['original_sha256']
    expected[choice['protected_path']] = choice['configured_sha256']
    for path, digest in c['R2a_retained_jobs'].items():
        if path in expected:
            expected[path] = digest
    return expected


class PresentCopyHost(r1b.R1bHost):
    SCOPE_KIND = 'R2a-packed-copy-retained-R1b-VBL-AML-startup-recovery'

    def contract(self):
        value = super().contract()
        validate_delta(value)
        return value

    def __init__(self, directory):
        super().__init__(directory)
        c = self.config
        self.retained = r1b.R1bHost(Path(c['R2a_retained_scope']))
        assert base.sha(self.retained.scope / 'contract-private.json') == c['R2a_retained_contract_sha256']
        assert self.retained.config['EFI_after_private'] == c['R2a_parent_EFI_private']
        assert self.retained.config['jobs'] == c['R2a_retained_jobs']
        assert self.retained.policy.startup_accepted(c['prepared_boot'])
        assert not self.retained.daily_failed()
        original = self.readonly.derive
        self.readonly.derive = lambda record, config, kind: derive_present(
            original(record, config, kind), config, kind)
        self.readonly.cache_check = self.cache_check

    def cache_check(self):
        checker = load('R2a_complete_cache_metadata', self.scope / 'check_build34_cache_metadata.py')
        raw = subprocess.check_output(['/usr/bin/kmutil', 'inspect', '-a', 'x86_64',
            '-B', '/System/Library/KernelCollections/BootKernelExtensions.kc',
            '-S', '/System/Library/KernelCollections/SystemKernelExtensions.kc',
            '-A', CACHE, '--show-prelink-info'], timeout=60)
        return checker.compare_captures((self.scope / 'R2a-candidate-prelink-private.txt').read_bytes(), raw, [])

    def check_restore_inputs(self):
        c = self.contract()
        route = load('R2a_unchanged_EFI', self.readonly.OLD / 'internal-route-private.py')
        with route.efi(route.static()) as root:
            assert route.files(root) == c['R2a_parent_EFI_private']
        for path, digest in physical_baseline(c).items():
            if path in c['R2a_changes']:
                base.secure(path)
                assert base.sha(path) in (BEFORE[path], AFTER[path])
            elif path not in c['jobs']:
                assert not Path(path).is_symlink() and base.sha(path) == digest
        for path, change in c['R2a_changes'].items():
            for kind, digest in [('backup', BEFORE[path]), ('candidate', AFTER[path])]:
                base.secure(self.scope / change[kind])
                assert base.sha(self.scope / change[kind]) == digest
        for path, accepted in c['recovery_jobs'].items():
            base.secure(path)
            assert base.sha(path) in (c['jobs'][path], accepted['sha256'])
            assert base.sha(self.scope / accepted['backup']) == accepted['sha256']
        watcher = Path(c['watcher_job'])
        if watcher.exists():
            base.secure(watcher)
            assert base.sha(watcher) == c['watcher_job_sha256']
        pending = Path('/var/db/phxboot.pending')
        if pending.exists():
            base.secure(pending)
            assert pending.read_bytes() == b''
        return c

    def restore(self):
        c = self.check_restore_inputs()
        for path, change in c['R2a_changes'].items():
            r1b.acpi.vbl.atomic_image(path, self.scope / change['backup'], (BEFORE[path], AFTER[path]))
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
        # Disk verification deliberately does not require a failed candidate
        # accelerator to have started. The kernel/plugin/AML never change.
        d, k, c = self.retained.readonly.build()
        d.r.verify_disk('candidate')
        with d.r.efi(d.r.static()) as root:
            assert d.r.files(root) == c['EFI_after_private']
            subprocess.run(['/usr/bin/codesign', '--verify', '--strict', str(root / d.r.ACTIVE)],
                           capture_output=True, check=True, timeout=20)
        assert d.plugin.files(d.plugin.LIVE) == k['plugin_after']
        self.retained.cache_check()
        assert c['EFI_after_private'] == self.config['R2a_parent_EFI_private']
        self.retained.acpi_check()
        self.retained.check_restore_inputs()
        assert d.r.support.security() == k['security']
        for path, digest in self.config['R2a_retained_jobs'].items():
            base.secure(path)
            assert base.sha(path) == digest
        assert not Path(self.config['watcher_job']).exists()
        return True

    verify = verify_restore

    def request_restart(self):
        subprocess.run(['/sbin/shutdown', '-r', 'now', 'Bounded R2a startup recovery'],
                       capture_output=True, check=True, timeout=15)


if __name__ == '__main__':
    os.umask(0o077)
    host = PresentCopyHost(Path(__file__).resolve().parent)
    action = sys.argv[1]
    if action == 'watch': host.watch()
    elif action == 'recover': host.note_failure('protected-startup-failure')
    elif action == 'worker': host.worker(sys.argv[2])
    else: host.supervise(action)
