#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Freeze and exercise staged target-observer methods, CPU readers only."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_client_lifetime import stage as stage_client
from build34_exact_observer import stage, stage_header
from build34_exact_submit import once
from test_build34_exact_client_lifetime import PRIOR as CLIENT_PRIOR
from test_build34_exact_ownership import DRIVER, PINNED, ROOT, method, sha

PRIOR = {
    **CLIENT_PRIOR,
    'tools/build34_exact_client_lifetime.py': '98e486d380c69be3ed5086354e2e5adae5b9b9de8f94d94b1d77dcfc09ba9a7e',
    'tools/test_build34_exact_client_lifetime.py': 'f08e816b2cc2d8f22a9c26961347e60acfb3f8c95a775a0eea07b8e360648b42',
}
HEADER = 'tools/build34_exact_ownership.h'
FIXTURE = 'tests/test_build34_exact_observer.cpp'
TRANSFORM = 'tools/build34_exact_observer.py'
RUNNER = 'tools/test_build34_exact_observer.py'
SIGNATURES = [
    'phx34_exact::Status PhxBringup::observeExact(', 'phx34_exact::Status IOAccelPhxNativeClient::queryExact(',
    'IOReturn PhxBringup::gpuSubmit(', 'IOReturn PhxBringup::adoptQueue(',
    'IOReturn PhxBringup::setPowerState(', 'void PhxBringup::invalidateExactQueues(',
    'void PhxBringup::stop(', 'void PhxBringup::killWaves(',
    'uint64_t PhxBringup::queueFence(', 'uint64_t PhxBringup::gpuRetired(',
]


def test(out):
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored worktree build path ending -private')
    subprocess.run(['git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    paths = [*PINNED, *PRIOR, FIXTURE, TRANSFORM, RUNNER,
             'LICENSE', 'LICENSES/MIT.txt', 'THIRD_PARTY_NOTICES.md']
    inputs = {name: (ROOT / name).read_bytes() for name in paths}
    for name, digest in {**PINNED, **PRIOR}.items():
        if sha(inputs[name]) != digest:
            raise ValueError('Production or prior experiment input drift: ' + name)
    names = subprocess.check_output(['git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'],
                                    cwd=ROOT, text=True, timeout=15).splitlines()
    protected = {name: sha((ROOT / name).read_bytes()) for name in names}
    original = inputs[DRIVER].decode()
    previous = stage_client(original)
    staged, header = stage(original), stage_header(inputs[HEADER].decode())
    if '#define PHX_KEXT_BUILD 34u\n' not in staged:
        raise ValueError('Only default build34 is admissible')
    for sig in ['uint64_t PhxBringup::queueFence(', 'uint64_t PhxBringup::gpuRetired(',
                'IOReturn IOAccelPhxNativeClient::doWaitSeq(', 'void PhxBringup::vmidFree(',
                'IOReturn IOAccelPhxNativeClient::clientClose(', 'void IOAccelPhxNativeClient::free(']:
        if method(previous, sig) != method(staged, sig):
            raise ValueError('Legacy observation or accepted client quarantine drift')
    if staged.count('exactFenceReader{nullptr}') != 1 or re.search(r'exactFenceReader\s*=', staged):
        raise ValueError('No source binding of a native hardware reader is admitted')
    out.mkdir(parents=True, mode=0o700)
    frozen = out / 'frozen'
    for name, blob in inputs.items():
        path = frozen / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    stage_path = out / 'source' / DRIVER
    stage_path.parent.mkdir(parents=True)
    stage_path.write_text(staged)
    stage_header_path = stage_path.parent / Path(HEADER).name
    stage_header_path.write_text(header)
    (stage_path.parent / 'build34_exact_callbacks.h').write_bytes(inputs['tools/build34_exact_callbacks.h'])
    for label, before, after in [('source-experiment', previous, staged), ('registry-inspect', inputs[HEADER].decode(), header)]:
        (out / (label + '.diff')).write_text(''.join(difflib.unified_diff(
            before.splitlines(True), after.splitlines(True), fromfile='a/source', tofile='b/source')))
    cc = ['/usr/bin/xcrun', 'clang++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-Wno-unused-parameter', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer',
          '-I' + str(stage_path.parent), '-I' + str(frozen / 'tools')]

    def run(args, label, broken=False):
        p = subprocess.run([str(a) for a in args], cwd=out, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=60)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if broken:
            if p.returncode == 0 or b'failed ' not in p.stderr:
                raise ValueError(label + ' failed to detect intended defect')
        elif p.returncode or p.stderr:
            raise RuntimeError(label + ' failed; see private logs')
        return p.stdout.decode()

    def exercise(label, code, broken=False, sanitizer='address,undefined'):
        target = out / (label + '.cpp')
        target.write_text(once(inputs[FIXTURE].decode(), '// PHX34_OBSERVER_METHODS',
                               '\n'.join(method(code, sig) for sig in SIGNATURES)))
        binary, dep = out / (label + '-CPU-only'), out / (label + '.d')
        run([*cc, '-fsanitize=' + sanitizer, '-MMD', '-MF', dep, target, '-o', binary], label + '-compile')
        dependencies = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        allowed = {str((frozen / name).resolve()) for name in inputs} | {
            str(target.resolve()), str(stage_header_path.resolve()),
            str((stage_path.parent / 'build34_exact_callbacks.h').resolve())}
        if not dependencies or any(str(Path(name).resolve()) not in allowed for name in dependencies):
            raise ValueError('Unfrozen compilation dependency')
        linked = run(['/usr/bin/otool', '-L', binary], label + '-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linked, re.I):
            raise ValueError('Device runtime linked')
        return run([binary], label + '-test', broken)

    result = exercise('target-observer', staged)
    pattern = (r'PASS staged exact target observer: (\d+) checks; (\d+) groups; (\d+) threaded scenarios; '
               r'128 model rounds; hardware_reader=false; GPU_executed=false\n')
    match = re.fullmatch(pattern, result)
    if not match or int(match[2]) != 162 or int(match[3]) != 10:
        raise ValueError('Incomplete target-observer suite')
    mutations = {}

    def mutate(label, sig, old, new):
        body = method(staged, sig)
        mutations[label] = once(staged, body, once(body, old, new))

    observe = SIGNATURES[0]
    query = SIGNATURES[1]
    mutate('missing-service-lease', observe,
           '    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);\n',
           '    const bool callback = true; // broken admission\n')
    mutate('missing-client-lease', query,
           '    phx34_exact::CallbackGate<>::Lease callback(exactClientCallbacks);\n',
           '    const bool callback = true; // broken admission\n')
    mutate('query-skips-lock-held-close', query,
           '    if (exactClientCallbacks.closed()) {\n', '    if (false && exactClientCallbacks.closed()) {\n')
    mutate('query-missing-start-pin', query,
           '    if (!exactOwnership || !exactClientPinned)', '    if (!exactOwnership)')
    mutate('global-upper-bound-for-target', observe,
           '    observed.submitted = exactQueueSubmitted[receipt.queue];\n', '    observed.submitted = gSeq;\n')
    mutate('target-generation-forgery', observe,
           '    observed.generation = exactQueueGeneration[receipt.queue];\n', '    observed.generation = receipt.generation;\n')
    mutate('wrong-queue-fence', observe,
           'base + q.fenceOff);\n', 'base + gq[receipt.queue ^ 1].fenceOff);\n')
    mutate('service-close-during-reader-ignored', observe,
           '    const bool stillLive = live && !exactCallbacks.closed() && !clientAdmission.closed();\n',
           '    const bool stillLive = live && !clientAdmission.closed();\n')
    mutate('client-close-during-reader-ignored', observe,
           '    const bool stillLive = live && !exactCallbacks.closed() && !clientAdmission.closed();\n',
           '    const bool stillLive = live && !exactCallbacks.closed();\n')
    unlocked = method(staged, observe)
    unlocked = once(unlocked, '    IOLockLock(gpuLock); // same client -> GPU lock order as submit\n', '')
    unlocked = once(unlocked, '    IOLockUnlock(gpuLock);\n', '')
    mutations['snapshot-without-GPU-lock'] = once(staged, method(staged, observe), unlocked)
    mutate('legacy-read-without-admitted-reader', observe,
           '    bool sampled = false;\n',
           '    bool sampled = !exactFenceReader;\n'
           '    if (!exactFenceReader) observed.completed = queueFence(q);\n')
    mutate('submit-missing-queue-upper-bound', SIGNATURES[2],
           '    exactQueueSubmitted[actualQueue] = seq; // never substitute the global gSeq in an observation\n', '')
    mutate('adoption-missing-upper-seed', SIGNATURES[3],
           '    exactQueueSubmitted[qi] = gSeq; // matches the adoption seed in this new generation\n', '')
    mutate('lost-queue-observed-ready', observe,
           '    observed.ready = q.ready && exactQueueLive[receipt.queue];\n', '    observed.ready = true;\n')
    mutate('cached-range-ignored', observe,
           'q.fenceOff <= fbAperLen && fbAperLen - q.fenceOff >= 8', 'true')
    mutate('mapped-range-ignored', observe,
           'q.fenceOff <= length && length - q.fenceOff >= 8', '(void(length), true)')
    for label, code in mutations.items():
        exercise(label, code, broken=True)
    tsan = re.fullmatch(pattern, exercise('target-observer-tsan', staged, sanitizer='thread'))
    if not tsan or int(tsan[2]) != 162 or int(tsan[3]) != 10:
        raise ValueError('Incomplete target-observer TSan suite')
    subset = out / 'registry-subset.cpp'
    subset.write_text('#include "build34_exact_ownership.h"\n'
                      'phx34_exact::Status example(phx34_exact::Registry &r, phx34_exact::Ticket t) { '
                      'phx34_exact::Receipt v; return r.inspect(t, v); }\n')
    run(['/usr/bin/xcrun', 'clang++', '-std=c++14', '-Wall', '-Wextra', '-Werror',
         '-fno-exceptions', '-fno-rtti', '-I' + str(stage_path.parent), '-c', subset,
         '-o', out / 'registry-subset.o'], 'registry-subset-compile')
    if stage_path.read_text() != staged or stage_header_path.read_text() != header:
        raise ValueError('Staged source/header drift')
    if any((ROOT / name).read_bytes() != blob or (frozen / name).read_bytes() != blob for name, blob in inputs.items()):
        raise ValueError('Frozen input drift')
    if protected != {name: sha((ROOT / name).read_bytes()) for name in names}:
        raise ValueError('Production input drift')
    report = dict(status='passed-CPU-only-staged-target-observer', kernel_build=34,
                  checks=int(match[1]), groups=int(match[2]), threaded_scenarios=int(match[3]), model_rounds=128,
                  actual_and_new_staged_methods_extracted=len(SIGNATURES), asan_ubsan=True, tsan=True,
                  detected_callsite_mutations=list(mutations),
                  exact_GFX_can_complete_while_earlier_compute_pending_in_CPU_backend=True,
                  owned_target_queue_only_sampled=True, per_queue_submitted_bound_includes_legacy=True,
                  receipt_identity_copied_under_client_lock=True,
                  snapshot_and_classification_hold_client_then_GPU_lock=True,
                  closure_rechecked_after_reader=True, completion_does_not_authorize_resource_release=True,
                  no_reader_or_failed_reader_refuses_completion=True,
                  no_native_hardware_reader_binding_or_fallback=True,
                  coherent_device_fence_observation_proven=False, blocking_native_wait_implemented=False,
                  native_selector_allocator_capability_ack_or_GPU_drain_implemented=False,
                  native_IOKit_lifetime_proven=False, deliberate_client_service_quarantine_preserved=True,
                  staged_registry_inspect_CXX14_no_exceptions_no_RTTI_compile=True,
                  registry_to_provider_authentication_still_fixture_only=True,
                  input_sha256={name: sha(blob) for name, blob in inputs.items()},
                  staged_driver_sha256=sha(staged.encode()), staged_registry_header_sha256=sha(header.encode()),
                  protected_production_file_count=len(names), production_inputs_ABI_runtime_recipes_unchanged=True,
                  native_Kernel_SDK_compile=False, installed=False, loaded=False, GPU_executed=False,
                  R3_hardware_accepted=False, R4_R6_started=False, physical_FPS_measured=False,
                  public_binary_upload=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    test(parser.parse_args().out)
