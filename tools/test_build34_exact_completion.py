#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage/test one pinned Mesa sync prerequisite offline; never install or load.

The legacy kernel/transport are unchanged. This is not a complete exact-wait
candidate: native capability negotiation, dependency ordering and AMD events
still need separate work before a paired deployment can be admitted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from upstream34_layout import radv_ib_tail

ROOT = Path(__file__).resolve().parents[1]
SYNC = 'src/amd/common/darwin/ac_darwin_sync.c'
PATCH = ROOT / 'mesa-patches-build34/0003-radv-exact-completion-bookkeeping.patch'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(command, destination, name):
    result = subprocess.run([str(x) for x in command], stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=90)
    (destination / (name + '.stdout')).write_bytes(result.stdout)
    (destination / (name + '.stderr')).write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError(name + ' failed; preserve the private logs')
    return result.stdout.decode()


def test(mesa, destination):
    mesa, destination = Path(mesa).resolve(), Path(destination).resolve()
    if destination.exists() or ROOT / 'build' not in destination.parents:
        raise ValueError('Fresh private output inside the active worktree build is required')
    blobs = radv_ib_tail.verified_source(mesa)
    # This source-only test must not change any production driver/ABI/tool.
    protected_names = subprocess.check_output([
        'git', 'ls-files', 'src/phxbringup', 'src/phxaccel', 'src/nmplugin', 'tools/phxctl',
    ], cwd=ROOT, text=True, timeout=15).splitlines()
    protected = {n: sha((ROOT / n).read_bytes()) for n in protected_names}
    assert b'#define PHX_KEXT_BUILD 34u\n' in (ROOT / 'src/phxbringup/PhxBringup.cpp').read_bytes()
    patch = PATCH.read_bytes()
    fixture = ROOT / 'tests/test_build34_exact_completion.c'
    fixture_sha = sha(fixture.read_bytes())
    destination.mkdir(parents=True, mode=0o700)
    for role in ['baseline', 'candidate']:
        stage = destination / role
        for name, data in blobs.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    candidate = destination / 'candidate'
    run(['git', 'init', '-q', candidate], destination, 'init-isolated-stage')
    for check in [True, False]:
        command = ['git', '-C', str(candidate), 'apply'] + (['--check'] if check else []) + ['-']
        result = subprocess.run(command, input=patch, capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError('Exact-completion patch refused: ' + result.stderr.decode())
    patched = {name: (candidate / name).read_bytes() for name in blobs}
    if {name for name in blobs if patched[name] != blobs[name]} != {SYNC}:
        raise ValueError('Require a change to only the reviewed sync provider')
    if not patched[SYNC].startswith(blobs[SYNC].split(b'#include', 1)[0]):
        raise ValueError('Original sync-provider notice changed')
    outputs = {}
    for role in ['baseline', 'candidate']:
        stage = destination / role
        binary = destination / (role + '-CPU-only')
        cc = ['/usr/bin/xcrun', 'clang', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
              '-Wno-unused-parameter', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
              '-fno-omit-frame-pointer']
        cc += ['-I' + str(stage / name) for name in ['include', 'include/darwin', 'src',
                                                   radv_ib_tail.PREFIX]]
        if role == 'baseline':
            cc += ['-DEXPECT_LEGACY_PREFIX=1']
        run(cc + [fixture, stage / SYNC, '-o', binary], destination, role + '-compile')
        linkage = run(['/usr/bin/otool', '-L', binary], destination, role + '-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linkage, re.I):
            raise ValueError('CPU fixture unexpectedly links a device runtime')
        outputs[role] = run([binary], destination, role + '-test')
        if (destination / (role + '-test.stderr')).read_bytes():
            raise ValueError('CPU fixture emitted diagnostics')
    if outputs['baseline'] != ('PASS baseline counterexample: exact 20 falsely completes pending 10; '
                               'GPU_executed=false\n'):
        raise ValueError('Baseline counterexample not reproduced')
    match = re.fullmatch(r'PASS actual Mesa exact-completion prerequisite: (\d+) checks; 128 gaps, '
                         r'clones, timelines, transfers, reset/destroy races; GPU_executed=false\n',
                         outputs['candidate'])
    if not match:
        raise ValueError('Incomplete candidate framing')
    if radv_ib_tail.verified_source(mesa) != blobs or PATCH.read_bytes() != patch:
        raise ValueError('Input drift during test')
    if sha(fixture.read_bytes()) != fixture_sha:
        raise ValueError('Fixture changed during test')
    if {n: sha((ROOT / n).read_bytes()) for n in protected_names} != protected:
        raise ValueError('Production driver/tool/ABI changed during test')
    if any((candidate / n).read_bytes() != data for n, data in patched.items()):
        raise ValueError('Staged source changed during test')
    report = dict(status='passed-CPU-only-exact-completion-bookkeeping-prerequisite',
                  pinned_input_files=len(blobs), baseline_counterexample_reproduced=True,
                  candidate_checks=int(match[1]), gap_cases=128, asan_ubsan=True,
                  actual_Mesa_sync_provider=True, original_notice_preserved=True,
                  base_sync_sha256=sha(blobs[SYNC]), candidate_sync_sha256=sha(patched[SYNC]),
                  patch_sha256=sha(patch), fixture_sha256=fixture_sha,
                  production_driver_ABI_tool_inputs_unchanged=True,
                  installed=False, loaded=False, GPU_executed=False,
                  kernel_exact_wait_implemented=False, transport_opt_in_implemented=False,
                  R3_hardware_accepted=False, public_binary_upload=False)
    (destination / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesa-source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    test(args.mesa_source, args.out)
