#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Test R3 multitarget waits on pinned actual Mesa, with CPU callbacks only.

Applies 0003 then isolated 0004 in fresh private sources, never runtime recipes.
No production backend enables the internal capability; no native/GPU execution,
installation, driver compilation, configuration, job or power operation occurs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess

from upstream34_layout import radv_ib_tail

ROOT = Path(__file__).resolve().parents[1]
SYNC = 'src/amd/common/darwin/ac_darwin_sync.c'
HEADER = 'src/amd/common/darwin/ac_darwin_drm.h'
PATCHES = [ROOT / 'mesa-patches-build34' / name for name in [
    '0003-radv-exact-completion-bookkeeping.patch',
    '0004-radv-exact-multitarget-wait-query.patch']]
FIXTURE = ROOT / 'tests/test_build34_exact_multitarget.c'
OLD_FIXTURE = ROOT / 'tests/test_build34_exact_completion.c'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(command, out, label, data=None):
    r = subprocess.run([str(x) for x in command], input=data, capture_output=True, timeout=90)
    (out / (label + '.stdout')).write_bytes(r.stdout)
    (out / (label + '.stderr')).write_bytes(r.stderr)
    if r.returncode:
        raise RuntimeError(label + ' failed; preserve private logs')
    return r.stdout.decode()


def stage(blobs, path):
    for name, data in blobs.items():
        p = path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def apply(patch, source, out, label):
    for check in [True, False]:
        run(['git', '-C', source, 'apply'] + (['--check'] if check else []) + ['-'],
            out, label + ('-check' if check else '-apply'), data=patch)


def test(mesa, out):
    mesa, out = Path(mesa).resolve(), Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh private output under the active worktree build')
    blobs = radv_ib_tail.verified_source(mesa)
    inputs = {p: p.read_bytes() for p in [*PATCHES, FIXTURE, OLD_FIXTURE, Path(__file__),
              radv_ib_tail.MANIFEST, ROOT / 'LICENSE', ROOT / 'LICENSES/MIT.txt',
              ROOT / 'THIRD_PARTY_NOTICES.md']}
    names = subprocess.check_output(['git', 'ls-files', 'src/phxbringup', 'src/phxaccel',
                                     'src/nmplugin', 'tools/phxctl'], cwd=ROOT,
                                    text=True, timeout=15).splitlines()
    protected = {name: sha((ROOT / name).read_bytes()) for name in names}
    if b'#define PHX_KEXT_BUILD 34u\n' not in (ROOT / 'src/phxbringup/PhxBringup.cpp').read_bytes():
        raise ValueError('Build34 source required')
    out.mkdir(parents=True, mode=0o700)
    baseline = out / 'bookkeeping-only'
    stage(blobs, baseline)
    run(['git', 'init', '-q', baseline], out, 'baseline-init')
    apply(inputs[PATCHES[0]], baseline, out, '0003')
    prerequisite = {name: (baseline / name).read_bytes() for name in blobs}
    if {name for name in blobs if prerequisite[name] != blobs[name]} != {SYNC}:
        raise ValueError('0003 must change only the reviewed sync provider')
    if sha(prerequisite[SYNC]) != '9e93e1ed15e2e817179d86698a0699ae824e3ff04b298a8179df11132abca844':
        raise ValueError('0003 output differs from previously tested prerequisite')
    candidate = out / 'candidate'
    stage(prerequisite, candidate)
    run(['git', 'init', '-q', candidate], out, 'candidate-init')
    apply(inputs[PATCHES[1]], candidate, out, '0004')
    patched = {name: (candidate / name).read_bytes() for name in blobs}
    if {name for name in blobs if patched[name] != prerequisite[name]} != {SYNC, HEADER}:
        raise ValueError('0004 must change only sync provider and internal backend header')
    for name in [SYNC, HEADER]:
        if not patched[name].startswith(blobs[name].split(b'#include', 1)[0]):
            raise ValueError('Original MIT notice changed')
    # Header-only userspace capability defaults false in the unchanged production
    # initializer. No ABI ioctl, transport selector or runtime opt-in is added.
    drm = 'src/amd/common/darwin/ac_darwin_drm.c'
    initializer = b'const struct acd_sync_backend be = {.wait_seq = acd_backend_wait_seq, .ctx = c->kext};'
    if patched[drm] != blobs[drm] or initializer not in patched[drm]:
        raise ValueError('Production backend initializer changed')

    cc = ['/usr/bin/xcrun', 'clang', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-Wno-unused-parameter', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
          '-fno-omit-frame-pointer']

    def compile_object(source, closure, obj, extra=()):
        flags = ['-I' + str(closure / name) for name in
                 ['include', 'include/darwin', 'src', radv_ib_tail.PREFIX]]
        dep = obj.with_suffix('.d')
        run(cc + flags + list(extra) + ['-MMD', '-MF', dep, '-c', source, '-o', obj],
            out, obj.stem + '-compile')
        deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        allowed = {str((closure / name).resolve()) for name in blobs} | {str(source.resolve())}
        if not deps or any(str(Path(name).resolve()) not in allowed for name in deps):
            raise ValueError('Compilation used an unfrozen non-system dependency')

    def executable(role, closure, fixture, extra=(), redirects=False):
        fixture_obj, provider_obj = out / (role + '-fixture.o'), out / (role + '-provider.o')
        compile_object(fixture, closure, fixture_obj, extra)
        compile_object(closure / SYNC, closure, provider_obj,
                       ['-Drealloc=fixture_realloc', '-Dclock_gettime=fixture_clock_gettime',
                        '-Dpthread_mutex_unlock=fixture_mutex_unlock',
                        '-Dpthread_cond_timedwait=fixture_cond_timedwait'] if redirects else [])
        binary = out / (role + '-CPU-only')
        run(cc + [fixture_obj, provider_obj, '-o', binary], out, role + '-link')
        linkage = run(['/usr/bin/otool', '-L', binary], out, role + '-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linkage, re.I):
            raise ValueError('Fixture unexpectedly links a device runtime')
        output = run([binary], out, role + '-test')
        if (out / (role + '-test.stderr')).read_bytes():
            raise ValueError('Sanitizer or test emitted diagnostics')
        return output

    before = executable('0003-only', baseline, FIXTURE, redirects=True)
    if before != ('PASS 0003-only counterexamples: wait-any, multi-query, higher-timeline; '
                  'GPU_executed=false\n'):
        raise ValueError('Three transition counterexamples were not reproduced')
    after = executable('candidate', candidate, FIXTURE, ['-DHAVE_EXACT_MULTITARGET=1'], True)
    match = re.fullmatch(r'PASS actual Mesa exact multitarget: (\d+) checks; 128 gaps, wait-any/all, '
                         r'query, deadlines, rotation, mutation, allocation, legacy; GPU_executed=false\n', after)
    if not match:
        raise ValueError('Incomplete multitarget candidate test')
    old = executable('bookkeeping-regression', candidate, OLD_FIXTURE)
    if not re.fullmatch(r'PASS actual Mesa exact-completion prerequisite: 4741 checks; 128 gaps, '
                       r'clones, timelines, transfers, reset/destroy races; GPU_executed=false\n', old):
        raise ValueError('Existing 4741-check prerequisite regressed')
    if radv_ib_tail.verified_source(mesa) != blobs or any(p.read_bytes() != data for p, data in inputs.items()):
        raise ValueError('Input drift during test')
    if protected != {name: sha((ROOT / name).read_bytes()) for name in names}:
        raise ValueError('Production driver/plugin/ABI/tool changed')
    for closure, expected in [(baseline, prerequisite), (candidate, patched)]:
        if any((closure / name).read_bytes() != data for name, data in expected.items()):
            raise ValueError('Frozen source drift')
    report = dict(status='passed-CPU-only-exact-multitarget-prerequisite', pinned_input_files=len(blobs),
                  three_0003_only_counterexamples_reproduced=True,
                  candidate_checks=int(match[1]), existing_bookkeeping_regression_checks=4741,
                  gap_cases=128, asan_ubsan=True, actual_Mesa_sync_provider=True,
                  deterministic_deadline_clock_fixture=True, allocation_failure_checks=True,
                  concurrent_reset_destroy_reuse_query_wait_races=True,
                  empty_snapshot_attach_before_sleep_regression_passed=True,
                  legacy_default_call_shape_preserved=True, production_capability_enabled=False,
                  source_sha256={n: sha(patched[n]) for n in [SYNC, HEADER]},
                  patch_sha256={p.name: sha(inputs[p]) for p in PATCHES},
                  fixture_sha256=sha(inputs[FIXTURE]), runner_sha256=sha(inputs[Path(__file__)]),
                  production_driver_plugin_ABI_tool_unchanged=True, original_MIT_notices_preserved=True,
                  installed=False, loaded=False, GPU_executed=False,
                  kernel_exact_wait_implemented=False, cross_queue_dependencies_resolved=False,
                  AMD_completion_events_implemented=False, R3_hardware_accepted=False,
                  public_binary_upload=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesa-source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    test(args.mesa_source, args.out)
