# SPDX-License-Identifier: MIT
"""Build and verify the private build34 PCI observation pair; no deployment."""

import argparse
from collections import Counter
import json
from pathlib import Path
import platform
import subprocess

import build34_map_candidate as mapped
import build34_pci_irq_config as config
from upstream34_layout import ring_padding_candidate as common

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'e9ee265ce005693f2928b4f981dfd097ca53fb80'
EVIDENCE = 'docs/validation/build34-r3-pci-irq-config-offline-20261121.json'
REFERENCE = ROOT / 'build/build34-r3-map-candidate-attempt1-20261121-private/observer/PhxBringup.kext'
CONTROL_BINARY = '923182fab482d5c584f484520622283922f67a9caaa2d310e638cd71d1fb1dc7'
PROTECTED = ('src', 'tools/phxctl', 'tools/build_kext.py')
RECIPES = (EVIDENCE, 'tools/build34_pci_irq_config.py', 'tools/build34_map_observation.py',
           'tools/test_build34_pci_irq_config.py', 'tests/test_build34_pci_irq_config.cpp',
           'tools/build34_map_candidate.py', 'tools/upstream34_layout/ring_padding_candidate.py')


def git(*args):
    return subprocess.check_output(['/usr/bin/git', *args], cwd=ROOT, timeout=20)


def sources(baseline, evidence):
    if set(baseline) != set(common.SOURCE_INPUTS):
        raise ValueError('Incomplete reviewed source, recipe or license inputs')
    control, observer = dict(baseline), dict(baseline)
    control[common.DRIVER] = mapped.observation.stage_baseline(baseline[common.DRIVER].decode()).encode()
    observer[common.DRIVER] = config.stage(baseline[common.DRIVER].decode()).encode()
    mapped.verify_sources(baseline, control)
    a, b = control[common.DRIVER], observer[common.DRIVER]
    if (evidence['status'] != 'passed-offline-pci-irq-config-observer' or
            evidence['kernel_build'] != 34 or evidence['native_import_count'] != 375 or
            evidence['new_native_imports'] != 0 or evidence['sdk_commit'] != common.SDK_PIN or
            evidence['control_source_sha256'] != common.sha(a) or evidence['observer_source_sha256'] != common.sha(b) or
            b.replace(config.OBSERVER.encode(), b'', 1).replace(config.START_OBSERVER.encode(), b'', 1) != a):
        raise ValueError('Require the exact offline-verified PCI observation delta')
    return {'restore': control, 'pci-observer': observer}


def bundle_pair(reference, restore, observer):
    exe = mapped.EXE
    if (reference != restore or restore.get(exe) != CONTROL_BINARY or set(restore) != set(observer) or
            {n for n in restore if restore[n] != observer[n]} != {exe}):
        raise ValueError('Require exact restore bundle and a sole observer executable delta')


def private_output(out):
    out = out.resolve()
    if ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Use ignored, private output inside the build34 worktree')
    git('check-ignore', '-q', str(out))
    if git('branch', '--show-current').strip() != b'upstream34/vram-layout-fix':
        raise ValueError('Require default build34 branch')
    return out


def inspect(out, run):
    """Read the private artifact pair independently of the recorded build checks."""
    manifests, uuids, imports = {}, {}, {}
    for role in ('restore', 'pci-observer'):
        bundle = out / role / 'PhxBringup.kext'
        binary = bundle / mapped.EXE
        manifests[role] = common.tree_files(bundle)
        identity = common.macho_identity(binary.read_bytes())
        uuids[role] = identity['image_uuid_private']
        if manifests[role][mapped.EXE] != identity['binary_sha256']:
            raise ValueError('Bundle changed during image readback')
        run(role + '-signature', '/usr/bin/codesign', '--verify', '--strict', bundle)
        run(role + '-architecture', '/usr/bin/lipo', binary, '-verify_arch', 'x86_64')
        imports[role] = set(run(role + '-imports', '/usr/bin/nm', '-arch', 'x86_64', '-uj', binary).stdout.splitlines())
    bundle_pair(common.tree_files(REFERENCE), manifests['restore'], manifests['pci-observer'])
    if (uuids['restore'] == uuids['pci-observer'] or imports['restore'] != imports['pci-observer'] or
            len(imports['restore']) != 375 or b'_thread_call_cancel_wait' not in imports['restore']):
        raise ValueError('Require distinct images and exactly the inherited import set')
    return dict(restore_bundle_byte_exact=True, observer_executable_sha256=manifests['pci-observer'][mapped.EXE],
                restore_executable_sha256=CONTROL_BINARY, bundle_file_count=len(manifests['restore']),
                sole_bundle_delta=mapped.EXE, strict_signatures_passed=True, distinct_x86_64_images=True,
                native_import_count=len(imports['restore']), new_imports=0,
                inherited_private_import='_thread_call_cancel_wait', generic_AuxKC_admitted=False)


def build(sdk, out):
    out = private_output(out)
    if out.exists() or platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        raise ValueError('Require Intel macOS and fresh private output')
    pinned = {n: (ROOT / n).read_bytes() for n in set(RECIPES) | set(common.SOURCE_INPUTS)}
    if any(git('show', SOURCE + ':' + n) != data for n, data in pinned.items()):
        raise ValueError('Prerequisite inputs differ from reviewed default commit')
    baseline = {n: pinned[n] for n in common.SOURCE_INPUTS}
    if any(git('show', mapped.observation.BASE_COMMIT + ':' + n) != data for n, data in baseline.items()):
        raise ValueError('Accepted build34 kernel/source/license inputs changed')
    evidence = json.loads(pinned[EVIDENCE])
    version = subprocess.check_output(['/usr/bin/sw_vers', '-productVersion'], timeout=10).decode().strip()
    os_build = subprocess.check_output(['/usr/bin/sw_vers', '-buildVersion'], timeout=10).decode().strip()
    if (version, os_build) != (evidence['os_version'], evidence['os_build']):
        raise ValueError('OS differs from the reviewed native compile host')
    pairs = sources(baseline, evidence)
    production = git('ls-files', '-z', *PROTECTED).rstrip(b'\0').decode().split('\0')
    if len(production) != 172 or git('diff', '--name-only', SOURCE, '--', *PROTECTED):
        raise ValueError('Production inputs differ from the reviewed checkpoint')
    production = {n: common.file_sha(ROOT / n) for n in production}
    ref = common.tree_files(REFERENCE)
    if ref.get(mapped.EXE) != CONTROL_BINARY:
        raise ValueError('Previous hardware-verified rollback reference changed')
    sdk_blobs = common.sdk_inputs(sdk)
    compiler = Path(subprocess.check_output(['/usr/bin/xcrun', '--find', 'clang++'], timeout=15).decode().strip()).resolve()
    tools = {p: common.file_sha(p) for p in (compiler, Path('/usr/bin/codesign'), Path('/usr/bin/nm'), Path('/usr/bin/lipo'))}
    out.mkdir(mode=0o700)
    tmp, sdk_copy = out / 'tmp-private', out / 'MacKernelSDK-pinned-private'
    tmp.mkdir()
    env = {'PATH': str(compiler.parent) + ':/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': str(tmp)}

    def materialize(dest, blobs):
        for n, blob in blobs.items():
            p = dest / n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(blob)

    def run(label, *args):
        p = subprocess.run([str(a) for a in args], cwd=out, env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=120)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if p.returncode:
            raise RuntimeError(label + ' failed; preserve private output')
        return p

    materialize(sdk_copy, sdk_blobs)
    for role, blobs in pairs.items():
        source = out / role / 'source'
        materialize(source, blobs)
        proc = run(role + '-build', '/bin/sh', source / 'src/phxbringup/build.sh', sdk_copy)
        warnings = Counter(line.split('warning:', 1)[1].strip() for line in proc.stderr.decode().splitlines() if 'warning:' in line)
        if warnings != mapped.WARNINGS:
            raise ValueError('Native compiler diagnostics changed')
        built = source / 'src/phxbringup/build/PhxBringup.kext'
        bundle = out / role / 'PhxBringup.kext'
        built.rename(bundle)
        plist = 'Contents/Info.plist'
        (bundle / plist).write_bytes(common.control_metadata(blobs['src/phxbringup/Info.plist']))
        before = common.macho_identity((bundle / mapped.EXE).read_bytes())
        run(role + '-sign', '/usr/bin/codesign', '--force', '--sign', '-', bundle)
        after = common.macho_identity((bundle / mapped.EXE).read_bytes())
        if before['image_uuid_private'] != after['image_uuid_private']:
            raise ValueError('Signing changed the image identity')
        if any((source / n).read_bytes() != data for n, data in blobs.items()):
            raise ValueError('Private source snapshot drift')
        if role == 'restore' and common.tree_files(bundle) != ref:
            raise ValueError('Stop before observer build: rollback bundle not byte-exact')
    checks = inspect(out, run)
    if (any((ROOT / n).read_bytes() != data for n, data in pinned.items()) or
            any(common.file_sha(ROOT / n) != h for n, h in production.items()) or
            any(common.file_sha(p) != h for p, h in tools.items()) or
            common.tree_files(REFERENCE) != ref or common.sdk_inputs(sdk) != sdk_blobs or
            common.tree_files(sdk_copy) != {n: common.sha(blob) for n, blob in sdk_blobs.items()}):
        raise ValueError('Source, toolchain, SDK or restore reference drift')
    report = dict(status='built-private-pci-observer-awaiting-trial-scope', kernel_build=34, source_checkpoint=SOURCE,
                  os_version=version, os_build=os_build, sdk_commit=common.SDK_PIN,
                  control_source_sha256=evidence['control_source_sha256'], observer_source_sha256=evidence['observer_source_sha256'],
                  recipe_sha256=common.file_sha(Path(__file__)), offline_evidence_sha256=common.sha(pinned[EVIDENCE]),
                  protected_production_inputs_unchanged=len(production), activation_scope_prepared=False,
                  installed=False, loaded=False, live_config_read=False, GPU_executed=False, power_actions=0, R3_complete=False,
                  **checks)
    (out / 'build-report-private.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def verify(out):
    out = private_output(out)

    def read(label, *args):
        return subprocess.run([str(a) for a in args], cwd=out, stdin=subprocess.DEVNULL, capture_output=True,
                              timeout=15, check=True)

    result = inspect(out, read)
    recorded = json.loads((out / 'build-report-private.json').read_bytes())
    if any(recorded.get(k) != value for k, value in result.items()):
        raise ValueError('Independent artifact readback does not match successful build evidence')
    return dict(status='passed-independent-private-artifact-readback', **result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--sdk', type=Path, help='Build using the pinned SDK checkout')
    mode.add_argument('--verify', action='store_true', help='Independently read back the built pair')
    args = parser.parse_args()
    print(json.dumps(verify(args.out) if args.verify else build(args.sdk.resolve(), args.out), indent=2))
