#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual pinned Mesa completion/ACK lifetime with CPU adapters, never IOKit."""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_submit import once
from test_build34_exact_cs_shape import PATCHES as SHAPE_PATCHES, PRIOR as SHAPE_PRIOR
from test_build34_exact_multitarget import apply, stage
from test_build34_exact_ownership import PINNED, ROOT, sha
from upstream34_layout import radv_ib_tail

PREFIX = radv_ib_tail.PREFIX
KEXT, HEADER, DRM = (PREFIX + n for n in ['ac_darwin_kext.c', 'ac_darwin_kext.h', 'ac_darwin_drm.c'])
PATCH = 'mesa-patches-build34/0007-radv-exact-receipt-lifetime.patch'
FIXTURE = 'tests/test_build34_exact_transport.c'
RUNNER = 'tools/test_build34_exact_transport.py'
REGRESSIONS = {'tests/test_build34_exact_cs_shape.c': ('HAVE_EXACT_CS_SHAPE', 1901),
               'tests/test_build34_exact_cs_dependencies.c': ('HAVE_EXACT_CS_GUARD', 4552)}
PRIOR = {**SHAPE_PRIOR,
         SHAPE_PATCHES[3]: '3e3d171cb7a42715379b26110a2dc15c5d64633e5ae2c3ccb536e5d5b0c4022d'}


def test(mesa, out):
    mesa, out = Path(mesa).resolve(), Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored worktree build path ending -private')
    subprocess.run(['git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    blobs = radv_ib_tail.verified_source(mesa)
    paths = [*PINNED, *PRIOR, PATCH, FIXTURE, RUNNER, *REGRESSIONS,
             'tools/test_build34_exact_cs_shape.py', 'tools/test_build34_exact_multitarget.py',
             'tools/upstream34_layout/radv_ib_tail.py', str(radv_ib_tail.MANIFEST.relative_to(ROOT)),
             'LICENSE', 'LICENSES/MIT.txt', 'THIRD_PARTY_NOTICES.md']
    inputs = {n: (ROOT / n).read_bytes() for n in paths}
    for n, digest in {**PINNED, **PRIOR}.items():
        if sha(inputs[n]) != digest:
            raise ValueError('Production/prior input drift: ' + n)
    names = subprocess.check_output(['git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'],
                                    cwd=ROOT, text=True, timeout=15).splitlines()
    protected = {n: sha((ROOT / n).read_bytes()) for n in names}
    if b'#define PHX_KEXT_BUILD 34u\n' not in inputs['src/phxbringup/PhxBringup.cpp']:
        raise ValueError('Only accepted default build34 is admitted')
    out.mkdir(parents=True, mode=0o700)
    frozen = out / 'frozen'
    for n, data in inputs.items():
        p = frozen / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def run(args, label, broken=False):
        p = subprocess.run([str(a) for a in args], cwd=out, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if broken:
            if not p.returncode or b'check failed' not in p.stderr:
                raise ValueError(label + ' did not detect its intended defect')
        elif p.returncode or p.stderr:
            raise RuntimeError(label + ' failed; preserve private logs')
        return p.stdout.decode()

    baseline, candidate = out / '0006-only', out / 'candidate'
    stage(blobs, baseline)
    run(['git', 'init', '-q', baseline], 'baseline-init')
    for i, patch in enumerate(SHAPE_PATCHES, 3):
        apply(inputs[patch], baseline, out, '000' + str(i))
    prerequisite = {n: (baseline / n).read_bytes() for n in blobs}
    if sha(prerequisite[DRM]) != '3eb2e86758cf060920deb8e2c97faadf655a784a206bfb99d8be71ad0da9ec1c':
        raise ValueError('Prior exact-CS guard source drift')
    stage(prerequisite, candidate)
    run(['git', 'init', '-q', candidate], 'candidate-init')
    apply(inputs[PATCH], candidate, out, '0007')
    patched = {n: (candidate / n).read_bytes() for n in blobs}
    if {n for n in blobs if patched[n] != prerequisite[n]} != {KEXT, HEADER}:
        raise ValueError('Only actual transport and its header may change')
    for n in [KEXT, HEADER]:
        if not patched[n].startswith(prerequisite[n].split(b'#include', 1)[0]):
            raise ValueError('Original MIT notice changed')
    if b'const struct acd_sync_backend be = {.wait_seq = acd_backend_wait_seq, .ctx = c->kext};' not in patched[DRM]:
        raise ValueError('Production exact capability must remain false')
    if b'#define ACD_EXACT_RECORDS 4096u\n' not in patched[HEADER]:
        raise ValueError('Completion ledger size changed without review')
    cc = ['/usr/bin/xcrun', 'clang', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-Wno-unused-parameter', '-fno-omit-frame-pointer']

    def compile_object(source, closure, obj, sanitizer, extra=()):
        includes = ['-I' + str(closure / n) for n in ['include', 'include/darwin', 'src', 'src/amd', PREFIX]]
        dep = obj.with_suffix('.d')
        run([*cc, '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all', *includes, *extra,
             '-MMD', '-MF', dep, '-c', source, '-o', obj], obj.stem + '-compile')
        deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        allowed = {str((closure / n).resolve()) for n in blobs} | {str(source.resolve())}
        if not deps or any(str(Path(n).resolve()) not in allowed for n in deps):
            raise ValueError('Unfrozen compilation dependency')

    def common_objects(closure, label, sanitizer):
        objects = []
        for n in [PREFIX + 'ac_darwin_sync.c', KEXT, PREFIX + 'amdgpu_vamgr.c', 'src/amd/common/amdgpu_devices.c']:
            obj = out / (label + '-' + Path(n).stem + '.o')
            extra = ['-Dlibdrm_container_of(ptr,sample,member)=((void *)((char *)(ptr) - __builtin_offsetof(__typeof__(*(sample)), member)))'] if n.endswith('amdgpu_vamgr.c') else []
            compile_object(closure / n, closure, obj, sanitizer, extra)
            objects.append(obj)
        return objects

    def execute(closure, label, common, sanitizer='address,undefined', extra=(), broken=False, fixture=FIXTURE):
        obj, binary = out / (label + '-fixture.o'), out / (label + '-CPU-only')
        compile_object(frozen / fixture, closure, obj, sanitizer, extra)
        run([*cc, '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all', '-Wl,-dead_strip',
             obj, *common, '-o', binary], label + '-link')
        linked = run(['/usr/bin/otool', '-L', binary], label + '-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linked, re.I):
            raise ValueError('Device runtime linked')
        return run([binary], label + '-test', broken)

    base_objects = common_objects(baseline, '0006-only', 'address,undefined')
    before = execute(baseline, '0006-only', base_objects)
    if before != ('PASS 0006-only prospective auto-ACK counterexample: late provider attach and raw WaitCS '
                  'lose completion; GPU_executed=false\n'):
        raise ValueError('Expected prospective late-completion failure was not reproduced')
    objects = common_objects(candidate, 'candidate', 'address,undefined')
    flags = ['-DHAVE_EXACT_RECEIPT_LIFETIME=1']
    pattern = (r'PASS actual Mesa exact receipt lifetime: (\d+) checks; bounded cache, ACK, prefix, raw WaitCS, '
               r'late attach, errors and four threaded scenarios; GPU_executed=false\n')
    result = re.fullmatch(pattern, execute(candidate, 'candidate', objects, extra=flags))
    if not result:
        raise ValueError('Incomplete exact transport suite')
    tsan = common_objects(candidate, 'tsan', 'thread')
    threaded = re.fullmatch(pattern, execute(candidate, 'tsan', tsan, 'thread', flags))
    if not threaded:
        raise ValueError('Incomplete TSan transport suite')
    current = patched[KEXT].decode()
    changes = {
        'ACK-drops-completed-record': ('         r->acked = true;', '         memset(r, 0, sizeof(*r));'),
        'ACK-busy-treated-as-success': ('      if (!result)\n         r->acked', '      if (!result || result == -EBUSY)\n         r->acked'),
        'completed-cache-pruned-before-global-prefix': ('!r->waiters && r->receipt.sequence <= e->retired)', '!r->waiters)'),
        'ACK-before-native-waiters-leave': (' || r->waiters)\n         continue;', ')\n         continue;'),
        'prefix-prunes-unacknowledged-receipt': (' && r->acked && !r->acknowledging', ' && !r->acknowledging'),
        'uncertain-dispatch-reuses-reservation': ('            e->poisoned = true; /* uncertain dispatch keeps the reservation */',
                                                '            memset(r, 0, sizeof(*r));'),
        'foreign-receipt-owner-admitted': ('receipt.owner != e->be.owner || ', ''),
        'bad-native-slot-admitted': ('receipt.slot >= 64 || ', ''),
        'bad-generation-admitted': ('!receipt.generation || receipt.generation == UINT64_MAX ||', ''),
        'reused-native-ticket-serial-admitted': ('receipt.serial <= e->native_serial ||', 'false ||'),
        'wrong-snapshot-session-admitted': ('s->owner != e->be.owner || ', ''),
        'direct-mixed-shape-admitted': ('ib->ip_type != plan->ibs[0].ip_type || ', ''),
        'configuration-after-legacy-traffic': ('k->sequence_traffic || k->exact', 'k->exact'),
        'observation-loss-masked-by-cache': ('return result && result != -EINTR && result != -EAGAIN;', 'return 0;'),
        'older-global-prefix-replaces-newer': ('if (s->retired > e->retired)', 'if (true)'),
        'LAST-waits-only-last-exact-target': ('return acd_exact_prefix(k, e, target, rel_ns, busy, st);',
                                            'return acd_exact_wait(k, e, target, rel_ns, busy, st);'),
        'deadline-chases-newer-submissions': ('acd_exact_prefix(k, e, seq, slice, busy, NULL)',
                                             'acd_exact_prefix(k, e, e->emitted, slice, busy, NULL)'),
        'local-CS-number-replaces-raw-sequence': ('*seq = receipt.sequence; /* raw native ABI, also the CPU fence value */',
                                                '*seq = receipt.serial;'),
    }
    mutations = {label: once(current, old, new) for label, (old, new) in changes.items()}
    mutations['pending-reply-undoes-completion'] = once(current,
        '         r->phase = ACD_EXACT_COMPLETE;\n      r->waiters--;',
        '         r->phase = ACD_EXACT_COMPLETE;\n      if (!result && pending) r->phase = ACD_EXACT_PENDING;\n      r->waiters--;')
    mutations['exact-completion-promotes-global-prefix'] = once(current,
        'if (!result && acd_exact_snapshot(e, &s) && !pending)\n         r->phase = ACD_EXACT_COMPLETE;',
        'if (!result && acd_exact_snapshot(e, &s) && !pending) {\n         r->phase = ACD_EXACT_COMPLETE;\n         e->retired = receipt.sequence;\n      }')
    mutations['full-cache-evicts-oldest-pending'] = once(current,
        '   if (!result && !r)\n      result = -EAGAIN;',
        '   if (!result && !r) { r = &e->records[0]; r->phase = ACD_EXACT_RESERVED; }')
    for label, source in mutations.items():
        (candidate / KEXT).write_text(source)
        mutant = out / (label + '-kext.o')
        compile_object(candidate / KEXT, candidate, mutant, 'address,undefined')
        execute(candidate, label, [objects[0], mutant, *objects[2:]], extra=flags, broken=True)
    (candidate / KEXT).write_bytes(patched[KEXT])

    regression_results = {}
    for fixture, (flag, expected) in REGRESSIONS.items():
        common = objects
        if fixture.endswith('cs_dependencies.c'):
            provider = out / 'dependency-provider.o'
            compile_object(candidate / (PREFIX + 'ac_darwin_sync.c'), candidate, provider, 'address,undefined',
                           ['-Dclock_gettime=fixture_clock_gettime', '-Dpthread_cond_timedwait=fixture_cond_timedwait'])
            common = [provider, *objects[1:]]
        output = execute(candidate, Path(fixture).stem, common, extra=['-D' + flag + '=1'], fixture=fixture)
        found = re.search(r': (\d+) checks;', output)
        if not found or int(found[1]) != expected:
            raise ValueError('Earlier actual-CS regression changed: ' + fixture)
        regression_results[fixture] = expected
    if radv_ib_tail.verified_source(mesa) != blobs:
        raise ValueError('Mesa input drift')
    if any((ROOT / n).read_bytes() != data or (frozen / n).read_bytes() != data for n, data in inputs.items()):
        raise ValueError('Frozen repository input drift')
    for closure, expected in [(baseline, prerequisite), (candidate, patched)]:
        if any((closure / n).read_bytes() != data for n, data in expected.items()):
            raise ValueError('Staged Mesa source drift')
    if protected != {n: sha((ROOT / n).read_bytes()) for n in names}:
        raise ValueError('Production drift')
    report = dict(status='passed-CPU-only-actual-Mesa-exact-receipt-lifetime', kernel_build=34,
                  checks=int(result[1]), tsan_checks=int(threaded[1]), asan_ubsan=True, tsan=True,
                  cache_capacity=4096, native_receipt_capacity_in_fixture=64, real_thread_scenarios=4,
                  prospective_naive_ACK_counterexamples_reproduced=1, installed_driver_failure_reproduced=False,
                  actual_ioctl_provider_transport=True, detected_mutations=list(mutations),
                  conservative_global_prefix_preserved=True, legacy_WAITSEQ_zero_used_for_snapshot=False,
                  raw_sequence_ABI_preserved=True, production_exact_capability_enabled=False,
                  adapter_native_wire_or_capability_implemented=False, caller_quiescent_destroy_still_required=True,
                  callbacks_outside_cache_mutex=True, transport_local_submit_mutex=True,
                  original_MIT_notices_preserved=True, prior_actual_CS_regressions=regression_results,
                  changed_Mesa_files=[KEXT, HEADER], pinned_Mesa_input_files=len(blobs),
                  Mesa_input_sha256={n: sha(data) for n, data in blobs.items()},
                  staged_Mesa_sha256={n: sha(data) for n, data in patched.items() if data != blobs[n]},
                  input_sha256={n: sha(data) for n, data in inputs.items()},
                  protected_production_file_count=len(names), production_ABI_prior_patches_runtime_unchanged=True,
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
