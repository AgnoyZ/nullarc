# SPDX-License-Identifier: MIT
"""Prepare a new, deliberately inactive PCI observer capsule on build34."""
import argparse
import copy
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys


TOOLS = Path(__file__).resolve().parent
# The privileged invocation uses Python isolated mode and explicit sibling paths.
sys.path.insert(0, str(TOOLS))
import build34_pci_irq_candidate as artifact
import build34_pci_irq_observer_host as host


DB = Path('/private/var/db')
ARCHIVE_ONLY = {'install.py', 'installed-readback.py', 'restart-private.py', 'watcher-job.plist'}
WATCHER_LABEL = 'dev.nullarc.build34.r3-pci-observer-once'


def run(*args, timeout=25):
    return subprocess.run([str(a) for a in args], check=True, capture_output=True,
                          stdin=subprocess.DEVNULL, timeout=timeout).stdout


def bundle(path):
    return {name: {'sha256': digest, 'bytes': (path / name).stat().st_size}
            for name, digest in artifact.common.tree_files(path).items()}


def protected_inputs():
    root = artifact.ROOT
    branch = run('/usr/bin/git', '-C', root, 'branch', '--show-current').strip()
    assert branch == b'upstream34/vram-layout-fix'
    files = run('/usr/bin/git', '-C', root, 'ls-files', '-z', *artifact.PROTECTED).rstrip(b'\0').decode().split('\0')
    assert len(files) == 172
    assert not run('/usr/bin/git', '-C', root, 'diff', '--name-only', host.SOURCE, '--', *artifact.PROTECTED)
    return {name: host.base.sha(root / name) for name in files}


def live_control(prior):
    accepted = host.mapping.MappingObserverHost(prior)
    d, k, c = accepted.readonly.build()
    assert accepted.policy.startup_accepted(accepted.boot()) and not accepted.daily_failed()
    assert not Path(c['watcher_job']).exists()
    d.live_identity(k, desktop=True)
    host.verify_disk(d, k, c['Map_after_EFI_private'])
    return accepted, c


def prepare(prior, out, pair):
    assert os.geteuid() == 0 and sys.executable == host.base.PYTHON
    assert out.is_absolute() and out.parent == DB and out.name.startswith('nullarc-build34-r3-pci-inactive-')
    assert prior.parent == DB and prior != out and not out.exists()
    assert not sys.flags.optimize
    prior_digest = host.base.sha(prior / 'contract-private.json')
    accepted, original = live_control(prior)
    boot = accepted.boot()
    production = protected_inputs()
    for key in ('restore', 'pci-observer'):
        path = pair / key / 'PhxBringup.kext'
        run('/usr/bin/codesign', '--verify', '--strict', path)
        run('/usr/bin/lipo', path / host.EXE, '-verify_arch', 'x86_64')
    restore = pair / 'restore' / 'PhxBringup.kext'
    observer = pair / 'pci-observer' / 'PhxBringup.kext'
    assert bundle(restore) == original['Map_observer_bundle_private']
    observed = bundle(observer)
    uuid = artifact.common.macho_identity((observer / host.EXE).read_bytes())['image_uuid_private']
    watcher = Path('/Library/LaunchDaemons') / (WATCHER_LABEL + '.plist')
    assert not watcher.exists()

    out.mkdir(mode=0o700)
    c = copy.deepcopy(original)
    c['sealed'] = {}

    def seal(name, data):
        path = out / name
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with path.open('xb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        c['sealed'][name] = host.base.sha(path)

    for name, digest in original['sealed'].items():
        if name not in ARCHIVE_ONLY | {'owner-startup-private.py', *original['Map_job_files'].values()}:
            data = (prior / name).read_bytes()
            assert artifact.common.sha(data) == digest
            seal(name, data)
    old_controller = (prior / 'owner-startup-private.py').read_bytes()
    assert artifact.common.sha(old_controller) == original['sealed']['owner-startup-private.py']
    seal('build34_map_observer_host.py', old_controller)
    seal('owner-startup-private.py', Path(host.__file__).read_bytes())
    seal('build34_pci_irq_observation.py', Path(host.irq.__file__).read_bytes())
    seal(host.REPORT, (pair / 'build-report-private.json').read_bytes())
    seal(host.RESTORE_FILE, (restore / host.EXE).read_bytes())
    seal(host.OBSERVER_FILE, (observer / host.EXE).read_bytes())
    c.update(scope_kind=host.PCIObserverHost.SCOPE_KIND, PCI_source_checkpoint=host.SOURCE,
             PCI_prior_scope=str(prior), PCI_prior_contract_sha256=prior_digest, PCI_prepared_boot=boot,
             PCI_trial_authorized=False, PCI_GPU_pressure_authorized=False, PCI_IRQ_registration_authorized=False,
             PCI_ordinary_restart_limit=1, PCI_before_EFI_private=original['Map_after_EFI_private'],
             PCI_observer_bundle_private=observed, PCI_after_uuid_private=uuid,
             PCI_retained_jobs=original['jobs'], PCI_recovery_jobs={}, jobs={}, watcher_job=str(watcher))
    c['PCI_after_EFI_private'] = {**c['PCI_before_EFI_private'], host.KERNEL: observed[host.EXE]}
    ctl = str(out / 'owner-startup-private.py')
    for i, (path, old_hash) in enumerate(original['jobs'].items()):
        data = Path(path).read_bytes()
        assert artifact.common.sha(data) == old_hash
        backup = 'pci-current-job-' + str(i) + '.plist'
        seal(backup, data)
        c['PCI_recovery_jobs'][path] = dict(backup=backup, sha256=old_hash)
        job = plistlib.loads(data)
        job['ProgramArguments'][3] = ctl
        filename = original['Map_job_files'][path]
        seal(filename, plistlib.dumps(job))
        c['jobs'][path] = c['sealed'][filename]
    seal(host.WATCHER, plistlib.dumps(dict(Label=WATCHER_LABEL, RunAtLoad=True,
        ProgramArguments=[host.base.PYTHON, '-B', '-I', ctl, 'watch'])))
    c['watcher_job_sha256'] = c['sealed'][host.WATCHER]
    host.validate_delta(c, require_authorized=False)
    with (out / 'contract-private.json').open('x') as f:
        json.dump(c, f, indent=2, sort_keys=True)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())

    proposed = out / 'owner-startup-private.py'
    result = json.loads(run(host.base.PYTHON, '-B', '-I', proposed, 'check-preparation'))
    refused = subprocess.run([host.base.PYTHON, '-B', '-I', proposed, 'watch'], capture_output=True, timeout=10)
    assert refused.returncode and b'fresh PCI observer trial authorization missing' in refused.stderr
    assert not Path(c['watcher_job']).exists() and protected_inputs() == production
    assert host.base.sha(prior / 'contract-private.json') == prior_digest
    assert accepted.boot() == boot
    return dict(result, private_files_sealed=len(c['sealed']), protected_production_inputs_unchanged=len(production),
                runtime_refused_inactive_scope=True, disk_control_checked=True, loaded_control_checked=True)


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prior', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--pair', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.prior, args.out, args.pair), sort_keys=True))
