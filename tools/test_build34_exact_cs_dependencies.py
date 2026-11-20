#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""CPU-test the R3 CS dependency guard on the pinned real Mesa call chain.

Applies only the separate 0003/0004/0005 prerequisites in fresh private sources.
Never enables a production backend, compiles a driver, installs or submits GPU
work, changes a job/configuration or requests power. Native exact ownership,
negotiation, teardown and AMD events remain separate admission requirements.
"""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess

from upstream34_layout import radv_ib_tail
from test_build34_exact_multitarget import apply, run, sha, stage

ROOT = Path(__file__).resolve().parents[1]
PREFIX = radv_ib_tail.PREFIX
SYNC = PREFIX + 'ac_darwin_sync.c'
HEADER = PREFIX + 'ac_darwin_drm.h'
DRM = PREFIX + 'ac_darwin_drm.c'
PATCHES = [ROOT / 'mesa-patches-build34' / name for name in [
    '0003-radv-exact-completion-bookkeeping.patch',
    '0004-radv-exact-multitarget-wait-query.patch',
    '0005-radv-exact-cs-dependency-guard.patch']]
FIXTURE = ROOT / 'tests/test_build34_exact_cs_dependencies.c'
MULTI_FIXTURE = ROOT / 'tests/test_build34_exact_multitarget.c'
BOOK_FIXTURE = ROOT / 'tests/test_build34_exact_completion.c'


def test(mesa, out):
    mesa, out = Path(mesa).resolve(), Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh private output under the active worktree build')
    blobs = radv_ib_tail.verified_source(mesa)
    inputs = {p: p.read_bytes() for p in [*PATCHES, FIXTURE, MULTI_FIXTURE, BOOK_FIXTURE,
              Path(__file__), ROOT / 'tools/test_build34_exact_multitarget.py',
              radv_ib_tail.MANIFEST, ROOT / 'LICENSE', ROOT / 'LICENSES/MIT.txt',
              ROOT / 'THIRD_PARTY_NOTICES.md']}
    names = subprocess.check_output(['git', 'ls-files', 'src/phxbringup', 'src/phxaccel',
                                    'src/nmplugin', 'tools/phxctl'], cwd=ROOT,
                                   text=True, timeout=15).splitlines()
    protected = {name: sha((ROOT / name).read_bytes()) for name in names}
    if b'#define PHX_KEXT_BUILD 34u\n' not in (ROOT / 'src/phxbringup/PhxBringup.cpp').read_bytes():
        raise ValueError('Build34 source required')
    out.mkdir(parents=True, mode=0o700)
    baseline, candidate = out / '0004-only', out / 'candidate'
    stage(blobs, baseline)
    run(['git', 'init', '-q', baseline], out, 'baseline-init')
    for i, patch in enumerate(PATCHES[:2], 3):
        apply(inputs[patch], baseline, out, '000' + str(i))
    prerequisite = {name: (baseline / name).read_bytes() for name in blobs}
    if {n for n in blobs if prerequisite[n] != blobs[n]} != {SYNC, HEADER}:
        raise ValueError('Prerequisite source closure changed unexpectedly')
    expected = {SYNC: 'f1f44273011f0a30c9472cf1006397fbf6439d71d3555fffdcb1c877a93353ca',
                HEADER: 'd15198229acc7e17acfa4f16c28c526a9125d7af0e5bf30ede721bbe9c12e38d'}
    if any(sha(prerequisite[n]) != digest for n, digest in expected.items()):
        raise ValueError('0003/0004 differ from the reviewed passing prerequisite')
    stage(prerequisite, candidate)
    run(['git', 'init', '-q', candidate], out, 'candidate-init')
    apply(inputs[PATCHES[2]], candidate, out, '0005')
    patched = {name: (candidate / name).read_bytes() for name in blobs}
    if {n for n in blobs if patched[n] != prerequisite[n]} != {SYNC, HEADER, DRM}:
        raise ValueError('0005 must change only provider, internal header and CS wrapper')
    for name in [SYNC, HEADER, DRM]:
        if not patched[name].startswith(blobs[name].split(b'#include', 1)[0]):
            raise ValueError('Original MIT notice changed')
    initializer = b'const struct acd_sync_backend be = {.wait_seq = acd_backend_wait_seq, .ctx = c->kext};'
    if initializer not in patched[DRM]:
        raise ValueError('Production exact capability must remain default false')

    cc = ['/usr/bin/xcrun', 'clang', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-Wno-unused-parameter', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
          '-fno-omit-frame-pointer']

    def compile_object(source, closure, obj, extra=()):
        includes = ['-I' + str(closure / name) for name in
                    ['include', 'include/darwin', 'src', 'src/amd', PREFIX]]
        dep = obj.with_suffix('.d')
        run(cc + includes + list(extra) + ['-MMD', '-MF', dep, '-c', source, '-o', obj],
            out, obj.stem + '-compile')
        deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        allowed = {str((closure / name).resolve()) for name in blobs} | {str(source.resolve())}
        if not deps or any(str(Path(name).resolve()) not in allowed for name in deps):
            raise ValueError('Compilation used an unfrozen non-system dependency')

    def execute(objects, label):
        binary = out / (label + '-CPU-only')
        run(cc + ['-Wl,-dead_strip', *objects, '-o', binary], out, label + '-link')
        linkage = run(['/usr/bin/otool', '-L', binary], out, label + '-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linkage, re.I):
            raise ValueError('Fixture unexpectedly links a device runtime')
        text = run([binary], out, label + '-test')
        if (out / (label + '-test.stderr')).read_bytes():
            raise ValueError('Sanitizer or test emitted diagnostics')
        return text

    results = {}
    for label, closure, enabled in [('0004-only', baseline, False), ('candidate', candidate, True)]:
        fixture_obj, provider_obj = out / (label + '-fixture.o'), out / (label + '-provider.o')
        compile_object(FIXTURE, closure, fixture_obj, ['-DHAVE_EXACT_CS_GUARD=1'] if enabled else [])
        compile_object(closure / SYNC, closure, provider_obj,
                       ['-Dclock_gettime=fixture_clock_gettime',
                        '-Dpthread_cond_timedwait=fixture_cond_timedwait'])
        objects = [fixture_obj, provider_obj]
        for name in [PREFIX + 'ac_darwin_kext.c', PREFIX + 'amdgpu_vamgr.c',
                     'src/amd/common/amdgpu_devices.c']:
            obj = out / (label + '-' + Path(name).stem + '.o')
            # Preserve UBSan: the vendored list macro uses null-pointer member
            # arithmetic; use the equivalent compiler offsetof in this CPU TU.
            extra = ['-Dlibdrm_container_of(ptr,sample,member)=((void *)((char *)(ptr) - __builtin_offsetof(__typeof__(*(sample)), member)))'] if name.endswith('amdgpu_vamgr.c') else []
            compile_object(closure / name, closure, obj, extra)
            objects.append(obj)
        results[label] = execute(objects, label)
    if results['0004-only'] != ('PASS 0004-only CS counterexamples: compute/GFX consumers overtake '
                                'pending dependencies; legacy chunks ignored; GPU_executed=false\n'):
        raise ValueError('Expected actual-CS baseline counterexamples were not reproduced')
    match = re.fullmatch(r'PASS actual Mesa CS dependency guard: (\d+) checks; 64 ordering cases, six multi-dependency cases, '
                         r'errors, budgets, chunk refusal, CPU attach, reset/destroy/reuse; '
                         r'GPU_executed=false\n', results['candidate'])
    if not match:
        raise ValueError('Incomplete CS dependency guard test')

    regressions = {}
    for label, fixture, extra, redirects, expression in [
        ('multitarget-regression', MULTI_FIXTURE, ['-DHAVE_EXACT_MULTITARGET=1'],
         ['-Drealloc=fixture_realloc', '-Dclock_gettime=fixture_clock_gettime',
          '-Dpthread_mutex_unlock=fixture_mutex_unlock', '-Dpthread_cond_timedwait=fixture_cond_timedwait'],
         r'PASS actual Mesa exact multitarget: (\d+) checks; 128 gaps, wait-any/all, query, deadlines, '
         r'rotation, mutation, allocation, legacy; GPU_executed=false\n'),
        ('bookkeeping-regression', BOOK_FIXTURE, [], [],
         r'PASS actual Mesa exact-completion prerequisite: (\d+) checks; 128 gaps, clones, '
         r'timelines, transfers, reset/destroy races; GPU_executed=false\n')]:
        fobj, pobj = out / (label + '-fixture.o'), out / (label + '-provider.o')
        compile_object(fixture, candidate, fobj, extra)
        compile_object(candidate / SYNC, candidate, pobj, redirects)
        found = re.fullmatch(expression, execute([fobj, pobj], label))
        if not found:
            raise ValueError('Existing prerequisite test did not complete')
        regressions[label] = int(found[1])
    if regressions != {'multitarget-regression': 3768, 'bookkeeping-regression': 4741}:
        raise ValueError('Existing prerequisite coverage changed')
    if radv_ib_tail.verified_source(mesa) != blobs or any(p.read_bytes() != data for p, data in inputs.items()):
        raise ValueError('Input drift during test')
    if protected != {name: sha((ROOT / name).read_bytes()) for name in names}:
        raise ValueError('Production driver/plugin/native ABI/tool changed')
    for closure, expected in [(baseline, prerequisite), (candidate, patched)]:
        if any((closure / n).read_bytes() != data for n, data in expected.items()):
            raise ValueError('Frozen source drift')
    report = dict(status='passed-CPU-only-exact-CS-dependency-guard', pinned_input_files=len(blobs),
                  actual_Mesa_ioctl_planner_sync_marshaller=True,
                  two_direction_CS_overtake_and_two_ignored_dependency_chunk_counterexamples=True,
                  ordering_cases=64, multi_dependency_cases=6, candidate_checks=int(match[1]), asan_ubsan=True,
                  refused_CS_outputs_proven_unattached_by_actual_transfer=True,
                  regressions=regressions, deterministic_deadline_clock_fixture=True,
                  CPU_signal_attach_and_reset_destroy_reuse_races=True,
                  exact_mode_unsupported_nonempty_dependency_chunks_refused=True,
                  relative_budget_saturation_and_device_loss_mapping_passed=True,
                  legacy_dependency_behavior_preserved=True, production_capability_enabled=False,
                  source_sha256={n: sha(patched[n]) for n in [SYNC, HEADER, DRM]},
                  patch_sha256={p.name: sha(inputs[p]) for p in PATCHES},
                  fixture_sha256=sha(inputs[FIXTURE]), runner_sha256=sha(inputs[Path(__file__)]),
                  production_driver_plugin_native_ABI_tool_unchanged=True,
                  original_MIT_notices_preserved=True, installed=False, loaded=False,
                  GPU_executed=False, kernel_exact_wait_implemented=False,
                  native_GPU_queue_dependencies_implemented=False, native_submission_ownership_resolved=False,
                  AMD_completion_events_implemented=False, R3_hardware_accepted=False,
                  physical_FPS_measured=False, public_binary_upload=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesa-source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    test(args.mesa_source, args.out)
