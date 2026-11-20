#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Test the exact-mode CS shape boundary on actual pinned Mesa, CPU only."""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_submit import once
from test_build34_exact_ack import PRIOR as ACK_PRIOR
from test_build34_exact_multitarget import apply, stage
from test_build34_exact_ownership import PINNED, ROOT, sha
from upstream34_layout import radv_ib_tail

PREFIX = radv_ib_tail.PREFIX
DRM = PREFIX + 'ac_darwin_drm.c'
PATCHES = ['mesa-patches-build34/' + name for name in [
    '0003-radv-exact-completion-bookkeeping.patch', '0004-radv-exact-multitarget-wait-query.patch',
    '0005-radv-exact-cs-dependency-guard.patch', '0006-radv-exact-cs-shape-guard.patch']]
FIXTURE = 'tests/test_build34_exact_cs_shape.c'
REGRESSION = 'tests/test_build34_exact_cs_dependencies.c'
RUNNER = 'tools/test_build34_exact_cs_shape.py'
PRIOR = {
    **ACK_PRIOR,
    'tools/build34_exact_ack.py': 'fba06abb2dac5e97225d6bf490dc6ac48477959870ca6132ddba8011b9f78833',
    'tools/test_build34_exact_ack.py': '40694d5f740473639e05597bd636298f66251246001e35b3b381f4a938a16d2c',
    'tests/test_build34_exact_ack.cpp': 'c946cb912fdb30e382b6be513c0a0c29105c7c09b3f25514d278b38212d6e9ff',
    PATCHES[0]: '5f65def0db78e048fb64434d50061d80f551c92dc09dff872d0551acd28805e7',
    PATCHES[1]: '266a22f7784a6823226333c9fbec5fb115fdf713812dedd9a57acf967b275806',
    PATCHES[2]: 'c5b403d4336bb517071838a76bbb03c47a85cc19337c90d2bb38f574472ac61d',
}


def test(mesa, out):
    mesa, out = Path(mesa).resolve(), Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored worktree build path ending -private')
    subprocess.run(['git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    blobs = radv_ib_tail.verified_source(mesa)
    paths = [*PINNED, *PRIOR, PATCHES[3], FIXTURE, REGRESSION, RUNNER,
             'tools/test_build34_exact_multitarget.py', 'tools/upstream34_layout/radv_ib_tail.py',
             str(radv_ib_tail.MANIFEST.relative_to(ROOT)), 'LICENSE', 'LICENSES/MIT.txt', 'THIRD_PARTY_NOTICES.md']
    inputs = {n: (ROOT / n).read_bytes() for n in paths}
    for n, digest in {**PINNED, **PRIOR}.items():
        if sha(inputs[n]) != digest:
            raise ValueError('Production/prior input drift: ' + n)
    names = subprocess.check_output(['git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'],
                                    cwd=ROOT, text=True, timeout=15).splitlines()
    protected = {n: sha((ROOT / n).read_bytes()) for n in names}
    if b'#define PHX_KEXT_BUILD 34u\n' not in inputs['src/phxbringup/PhxBringup.cpp']:
        raise ValueError('Only default build34 is admitted')
    out.mkdir(parents=True, mode=0o700)
    frozen = out / 'frozen'
    for n, blob in inputs.items():
        p = frozen / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)

    def run(args, label, broken=False):
        p = subprocess.run([str(a) for a in args], cwd=out, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if broken:
            if not p.returncode or b'check failed' not in p.stderr:
                raise ValueError(label + ' did not detect intended defect')
        elif p.returncode or p.stderr:
            raise RuntimeError(label + ' failed; preserve private logs')
        return p.stdout.decode()

    baseline, candidate = out / '0005-only', out / 'candidate'
    stage(blobs, baseline)
    run(['git', 'init', '-q', baseline], 'baseline-init')
    for i, patch in enumerate(PATCHES[:3], 3):
        apply(inputs[patch], baseline, out, '000' + str(i))
    prerequisite = {n: (baseline / n).read_bytes() for n in blobs}
    if sha(prerequisite[DRM]) != '0bfa9204101e21fbc5399aefad52c6b0f878076528fd0383ec1e10a87434197b':
        raise ValueError('Earlier CS guard source drift')
    stage(prerequisite, candidate)
    run(['git', 'init', '-q', candidate], 'candidate-init')
    apply(inputs[PATCHES[3]], candidate, out, '0006')
    patched = {n: (candidate / n).read_bytes() for n in blobs}
    if {n for n in blobs if patched[n] != prerequisite[n]} != {DRM}:
        raise ValueError('Only the exact-mode CS wrapper may change')
    if not patched[DRM].startswith(blobs[DRM].split(b'#include', 1)[0]):
        raise ValueError('Original MIT notice changed')
    if b'const struct acd_sync_backend be = {.wait_seq = acd_backend_wait_seq, .ctx = c->kext};' not in patched[DRM]:
        raise ValueError('Production exact capability must remain default false')
    cc = ['/usr/bin/xcrun', 'clang', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-Wno-unused-parameter', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']

    def compile_object(source, closure, obj, extra=()):
        includes = ['-I' + str(closure / n) for n in ['include', 'include/darwin', 'src', 'src/amd', PREFIX]]
        dep = obj.with_suffix('.d')
        run([*cc, *includes, *extra, '-MMD', '-MF', dep, '-c', source, '-o', obj], obj.stem + '-compile')
        deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        allowed = {str((closure / n).resolve()) for n in blobs} | {str(source.resolve())}
        if not deps or any(str(Path(n).resolve()) not in allowed for n in deps):
            raise ValueError('Unfrozen compilation dependency')

    def common_objects(closure, label):
        objects = []
        for n in [PREFIX + 'ac_darwin_sync.c', PREFIX + 'ac_darwin_kext.c',
                  PREFIX + 'amdgpu_vamgr.c', 'src/amd/common/amdgpu_devices.c']:
            obj = out / (label + '-' + Path(n).stem + '.o')
            # Same CPU-only offsetof substitution as the prior checked suite;
            # retain UBSan and do not alter the frozen vendored list macro.
            extra = ['-Dlibdrm_container_of(ptr,sample,member)=((void *)((char *)(ptr) - __builtin_offsetof(__typeof__(*(sample)), member)))'] if n.endswith('amdgpu_vamgr.c') else []
            compile_object(closure / n, closure, obj, extra)
            objects.append(obj)
        return objects

    def execute(closure, label, common, extra=(), broken=False, fixture=FIXTURE):
        obj, binary = out / (label + '-fixture.o'), out / (label + '-CPU-only')
        compile_object(frozen / fixture, closure, obj, extra)
        run([*cc, '-Wl,-dead_strip', obj, *common, '-o', binary], label + '-link')
        linked = run(['/usr/bin/otool', '-L', binary], label + '-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linked, re.I):
            raise ValueError('Device runtime linked')
        return run([binary], label + '-test', broken)

    base_objects = common_objects(baseline, '0005-only')
    before = execute(baseline, '0005-only', base_objects)
    if before != ('PASS 0005-only CS shape counterexamples: mixed plans reach single-queue packets; '
                  'split result omits earlier pending sequence; GPU_executed=false\n'):
        raise ValueError('Expected prospective exact-CS counterexamples not reproduced')
    objects = common_objects(candidate, 'candidate')
    pattern = r'PASS actual Mesa exact CS shape: (\d+) checks; 8 accepted and 80 refused shapes; empty and legacy; GPU_executed=false\n'
    result = re.fullmatch(pattern, execute(candidate, 'candidate', objects, ['-DHAVE_EXACT_CS_SHAPE=1']))
    if not result:
        raise ValueError('Incomplete exact-CS shape suite')
    current = patched[DRM].decode()
    changes = {
        'split-plan-admitted': ('bool supported = plan.n_ibs <= N48N_MAX_IBS;', 'bool supported = true;'),
        'sixty-fifth-IB-admitted': ('plan.n_ibs <= N48N_MAX_IBS;', 'plan.n_ibs <= N48N_MAX_IBS + 1;'),
        'mixed-queues-admitted': ('ib->ip_type != plan.ibs[0].ip_type || ', ''),
        'unknown-engine-admitted': ('(ib->ip_type != AMDGPU_HW_IP_GFX && ib->ip_type != AMDGPU_HW_IP_COMPUTE)', 'false'),
        'unsupported-instance-admitted': ('|| ib->ip_instance || ib->ring)', '|| ib->ring)'),
        'unsupported-ring-admitted': ('|| ib->ip_instance || ib->ring)', '|| ib->ip_instance)'),
        'legacy-mode-changed': ('if (acd_sync_has_exact_completion(dev->sync)) {', 'if (true) {'),
        'output-touched-before-refusal': ('      if (!supported) {\n', '      if (!supported) {\n         cs->out.handle = 0;\n'),
    }
    mutations = {label: once(current, old, new) for label, (old, new) in changes.items()}
    start = current.index('      /* One exact receipt represents')
    end = current.index('      /* The parser historically', start)
    guard = current[start:end]
    late = once(current, guard, '')
    mutations['shape-validated-after-dependency-waits'] = once(late, '   uint64_t seq = 0;\n   if (!r)\n',
        '   if (acd_sync_has_exact_completion(dev->sync)) {\n' + guard + '   }\n\n'
        '   uint64_t seq = 0;\n   if (!r)\n')
    for label, code in mutations.items():
        (candidate / DRM).write_text(code)
        execute(candidate, label, objects, ['-DHAVE_EXACT_CS_SHAPE=1'], broken=True)
    (candidate / DRM).write_bytes(patched[DRM])

    # Re-test the actual changed CS function with all preceding dependency
    # scenarios. Its provider clock redirects are the same prior CPU doubles.
    provider = out / 'cs-dependency-provider.o'
    compile_object(candidate / (PREFIX + 'ac_darwin_sync.c'), candidate, provider,
                   ['-Dclock_gettime=fixture_clock_gettime', '-Dpthread_cond_timedwait=fixture_cond_timedwait'])
    regression = execute(candidate, 'cs-dependency-regression', [provider, *objects[1:]],
                         ['-DHAVE_EXACT_CS_GUARD=1'], fixture=REGRESSION)
    found = re.fullmatch(r'PASS actual Mesa CS dependency guard: (\d+) checks; 64 ordering cases, six multi-dependency cases, '
                         r'errors, budgets, chunk refusal, CPU attach, reset/destroy/reuse; GPU_executed=false\n', regression)
    if not found or int(found[1]) != 4552:
        raise ValueError('Earlier actual-CS dependency regression changed')
    if radv_ib_tail.verified_source(mesa) != blobs:
        raise ValueError('Mesa input drift')
    if any((ROOT / n).read_bytes() != b or (frozen / n).read_bytes() != b for n, b in inputs.items()):
        raise ValueError('Frozen repository input drift')
    for closure, expected in [(baseline, prerequisite), (candidate, patched)]:
        if any((closure / n).read_bytes() != b for n, b in expected.items()):
            raise ValueError('Staged Mesa source drift')
    if protected != {n: sha((ROOT / n).read_bytes()) for n in names}:
        raise ValueError('Production drift')
    report = dict(status='passed-CPU-only-actual-Mesa-exact-CS-shape-guard', kernel_build=34,
                  checks=int(result[1]), accepted_shapes=8, refused_shapes=80, asan_ubsan=True,
                  baseline_future_exact_backend_counterexamples_reproduced=2,
                  baseline_installed_driver_failure_reproduced=False,
                  actual_ioctl_planner_marshaller_provider=True, detected_mutations=list(mutations),
                  preflight_precedes_dependencies_submission_and_output_attach=True,
                  fragmented_mixed_unknown_engine_nonzero_instance_or_ring_refused=True,
                  unchanged_CS_dependency_checks=int(found[1]), legacy_call_behavior_preserved=True,
                  production_exact_capability_enabled=False, original_MIT_notice_preserved=True,
                  changed_Mesa_files=[DRM], pinned_Mesa_input_files=len(blobs),
                  Mesa_input_sha256={n: sha(b) for n, b in blobs.items()},
                  staged_Mesa_sha256={n: sha(b) for n, b in patched.items() if b != blobs[n]},
                  input_sha256={n: sha(b) for n, b in inputs.items()},
                  protected_production_file_count=len(names), production_ABI_prior_patches_runtime_unchanged=True,
                  native_protocol_or_userspace_ACK_cache_implemented=False,
                  native_Kernel_SDK_compile=False, installed=False, loaded=False, GPU_executed=False,
                  R3_hardware_accepted=False, R4_R6_started=False, physical_FPS_measured=False,
                  long_term_stability_accepted=False, public_binary_upload=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesa-source', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    test(args.mesa_source, args.out)
