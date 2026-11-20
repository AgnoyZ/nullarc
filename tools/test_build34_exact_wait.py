#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the staged precise-ticket wait on frozen CPU doubles only."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_binding import stage as previous_stage
from build34_exact_wait import stage, stage_header
from build34_exact_submit import once
from test_build34_exact_binding import PRIOR as BINDING_PRIOR, SIGNATURES as BINDING_SIGNATURES
from test_build34_exact_ownership import DRIVER, PINNED, ROOT, method, sha

PRIOR = {
    **BINDING_PRIOR,
    'tools/build34_exact_binding.py': '7df8a381c2ab8da8645d62a59c8bba7d72ca2ae799ce6625f3a1737cf6049836',
    'tools/test_build34_exact_binding.py': 'c20d4b580714ff711acefb0653c57e83e5bc96fa4dd4c994e1bb74803bf1bada',
    'tests/test_build34_exact_binding.cpp': '3d2ea9b62b672cf09e13e6403066f2ce5a7733be640619cea4367def4028a6c4',
}
HEADER = 'tools/build34_exact_ownership.h'
BASE = 'tests/test_build34_exact_binding.cpp'
FIXTURE = 'tests/test_build34_exact_wait.cpp'
TRANSFORM = 'tools/build34_exact_wait.py'
RUNNER = 'tools/test_build34_exact_wait.py'
WAIT = 'phx34_exact::Status IOAccelPhxNativeClient::waitExact('


def test(out):
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored worktree build path ending -private')
    subprocess.run(['git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    paths = [*PINNED, *PRIOR, FIXTURE, TRANSFORM, RUNNER, 'LICENSE', 'LICENSES/MIT.txt', 'THIRD_PARTY_NOTICES.md']
    inputs = {name: (ROOT / name).read_bytes() for name in paths}
    for name, digest in {**PINNED, **PRIOR}.items():
        if sha(inputs[name]) != digest:
            raise ValueError('Production/prior experiment input drift: ' + name)
    names = subprocess.check_output(['git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'],
                                    cwd=ROOT, text=True, timeout=15).splitlines()
    protected = {name: sha((ROOT / name).read_bytes()) for name in names}
    source = inputs[DRIVER].decode()
    previous, staged = previous_stage(source), stage(source)
    header = stage_header(inputs[HEADER].decode())
    if '#define PHX_KEXT_BUILD 34u\n' not in staged:
        raise ValueError('Only default build34 is admitted')
    for sig in [*BINDING_SIGNATURES, 'IOReturn IOAccelPhxNativeClient::doWaitSeq(',
                'void PhxBringup::vmidFree(', 'void IOAccelPhxNativeClient::free(']:
        if method(previous, sig) != method(staged, sig):
            raise ValueError('Earlier callsite, legacy wait or permanent quarantine changed')
    wait = method(staged, WAIT)
    if wait.count('->lookup(') != 1 or wait.index('->lookup(') > wait.index('for (;;)'):
        raise ValueError('Wait must snapshot exactly one ticket before polling')
    if re.search(r'exactRequested\s*=|exactFenceReader\s*=', staged):
        raise ValueError('No native request or reader binding is admitted')
    out.mkdir(parents=True, mode=0o700)
    frozen = out / 'frozen'
    for name, blob in inputs.items():
        path = frozen / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    stage_path = out / 'source' / DRIVER
    stage_path.parent.mkdir(parents=True)
    stage_path.write_text(staged)
    header_path = stage_path.parent / Path(HEADER).name
    header_path.write_text(header)
    (stage_path.parent / 'build34_exact_callbacks.h').write_bytes(inputs['tools/build34_exact_callbacks.h'])
    (out / 'ticket-wait.diff').write_text(''.join(difflib.unified_diff(
        previous.splitlines(True), staged.splitlines(True), fromfile='a/source', tofile='b/source')))
    cc = ['/usr/bin/xcrun', 'clang++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-Wno-unused-parameter', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer',
          '-I' + str(stage_path.parent), '-I' + str(frozen / 'src/phxbringup')]

    def run(args, label, broken=False):
        p = subprocess.run([str(a) for a in args], cwd=out, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=60)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if broken:
            if not p.returncode or b'failed ' not in p.stderr:
                raise ValueError(label + ' did not detect intended defect')
        elif p.returncode or p.stderr:
            raise RuntimeError(label + ' failed; see private logs')
        return p.stdout.decode()

    def exercise(label, code, broken=False, sanitizer='address,undefined'):
        fixture = once(inputs[BASE].decode(), '// PHX34_BINDING_METHODS',
                       '\n'.join(method(code, sig) for sig in BINDING_SIGNATURES))
        fixture = once(fixture, 'static bool baseStart=true;\n',
                       'static bool baseStart=true;\n'
                       'static thread_local uint64_t testTicks=10000000,clockScale=1;\n'
                       'static std::atomic<unsigned> sleepCalls{0};\n')
        fixture = once(fixture, 'static uint64_t mach_absolute_time() { return 10000000; }',
                       'static uint64_t mach_absolute_time() { return testTicks; }')
        fixture = once(fixture, 'static void absolutetime_to_nanoseconds(uint64_t v,uint64_t *out) { *out=v; }',
                       'static void absolutetime_to_nanoseconds(uint64_t v,uint64_t *out) { *out=v*clockScale; }')
        fixture = once(fixture, 'static void IOSleep(unsigned ms) { CHECK(ms==1 && !gpuHeld); }',
                       'static void IOSleep(unsigned ms) { CHECK(ms==1 && !clientHeld && !gpuHeld); '
                       'CHECK(++sleepCalls<=2001); event("sleep"); testTicks+=1000000/clockScale; }')
        fixture = once(fixture, '    Status queryExact(uint64_t);\n',
                       '    Status queryExact(uint64_t);\n    Status waitExact(uint64_t,uint64_t);\n')
        fixture = once(fixture, 'int main() {\n', 'static void binding_regressions() {\n')
        base = out / 'binding-fixture-CPU-only.h'
        base.write_text(fixture)
        target = out / (label + '.cpp')
        target.write_text(once(inputs[FIXTURE].decode(), '// PHX34_EXACT_WAIT_METHOD', method(code, WAIT)))
        binary, dep = out / (label + '-CPU-only'), out / (label + '.d')
        run([*cc, '-fsanitize=' + sanitizer, '-MMD', '-MF', dep, target, '-o', binary], label + '-compile')
        allowed = {str((frozen / name).resolve()) for name in inputs} | {
            str(target.resolve()), str(base.resolve()), str(header_path.resolve()),
            str((stage_path.parent / 'build34_exact_callbacks.h').resolve())}
        dependencies = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        if not dependencies or any(str(Path(p).resolve()) not in allowed for p in dependencies):
            raise ValueError('Unfrozen compilation dependency')
        linkage = run(['/usr/bin/otool', '-L', binary], label + '-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linkage, re.I):
            raise ValueError('Device runtime linked')
        return run([binary], label + '-test', broken)

    pattern = (r'PASS staged exact embedded binding: (\d+) checks; 22 groups; 5 threaded scenarios; GPU_executed=false\n'
               r'PASS staged exact ticket wait: (\d+) additional checks; (\d+) additional groups; '
               r'(\d+) additional threaded scenarios; inherited binding passed; GPU_executed=false\n')
    result = re.fullmatch(pattern, exercise('ticket-wait', staged))
    if not result or int(result[3]) != 28 or int(result[4]) != 6:
        raise ValueError('Incomplete ticket wait suite')
    mutations = {}

    def mutate(label, old, new):
        mutations[label] = once(staged, wait, once(wait, old, new))

    mutate('missing-wait-client-lease', '    phx34_exact::CallbackGate<>::Lease callback(exactClientCallbacks);\n',
           '    const bool callback=true;\n')
    mutate('wait-accepts-foreign-registry', 'exactOwnership == &exactRegistry && ', '')
    mutate('wait-missing-pin', 'exactClientPinned && ', '')
    mutate('wait-no-budget-cap', '    if (timeout > PHXN_WAIT_CAP_NS) timeout = PHXN_WAIT_CAP_NS;\n', '')
    mutate('expired-budget-sleeps-again', 'if (elapsed >= timeout)', 'if (elapsed > timeout)')
    mutate('pending-reported-complete', '        if (result != phx34_exact::Status::Pending) return result;\n',
           '        if (result == phx34_exact::Status::Pending) return phx34_exact::Status::Complete;\n'
           '        if (result != phx34_exact::Status::Pending) return result;\n')
    mutate('wait-lock-held-during-sleep', '        IOSleep(1);\n',
           '        IOLockLock(lock); IOSleep(1); IOLockUnlock(lock);\n')
    mutate('zero-length-sleep-spin', '        IOSleep(1);\n', '        IOSleep(0);\n')
    mutate('clock-conversion-omitted',
           '        absolutetime_to_nanoseconds(mach_absolute_time() - start, &elapsed);\n',
           '        elapsed = mach_absolute_time() - start;\n')
    mutate('start-reset-after-queued-lock', '    if (result != phx34_exact::Status::Ok) return result;\n',
           '    if (result != phx34_exact::Status::Ok) return result;\n'
           '    start = mach_absolute_time();\n')
    # The broken version must remain well-defined CPU code: use a mutable start.
    mutations['start-reset-after-queued-lock'] = once(mutations['start-reset-after-queued-lock'],
           '    const uint64_t start = mach_absolute_time(); // include queued lock and reader time\n',
           '    uint64_t start = mach_absolute_time(); // broken budget reset\n')
    mutate('close-ignored-at-poll',
           '        result = exactClientCallbacks.closed() ? phx34_exact::Status::Closed :\n'
           '                 owner->observeExact(*exactOwnership, ticket, exactClientCallbacks, this);\n',
           '        result = owner->observeExact(*exactOwnership, ticket, exactClientCallbacks, this);\n')
    mutate('global-prefix-substituted-for-target',
           '                 owner->observeExact(*exactOwnership, ticket, exactClientCallbacks, this);\n',
           '                 (owner->gpuRetired() >= sequence ? phx34_exact::Status::Complete : phx34_exact::Status::Pending);\n')
    slept = once(wait, '    phx34_exact::Ticket ticket;\n', '    uint64_t slept=0;\n    phx34_exact::Ticket ticket;\n')
    slept = once(slept, '        absolutetime_to_nanoseconds(mach_absolute_time() - start, &elapsed);\n',
                 '        elapsed = slept + (start - start);\n')
    slept = once(slept, '        IOSleep(1);\n', '        IOSleep(1); slept+=1000000;\n')
    mutations['requested-sleep-budget-instead-of-real-time'] = once(staged, wait, slept)
    for label, code in mutations.items():
        exercise(label, code, broken=True)
    tsan = re.fullmatch(pattern, exercise('ticket-wait-tsan', staged, sanitizer='thread'))
    if not tsan or int(tsan[3]) != 28 or int(tsan[4]) != 6:
        raise ValueError('Incomplete wait TSan suite')
    if stage_path.read_text() != staged or header_path.read_text() != header:
        raise ValueError('Staged source/header drift')
    if any((ROOT / name).read_bytes() != blob or (frozen / name).read_bytes() != blob for name, blob in inputs.items()):
        raise ValueError('Frozen input drift')
    if protected != {name: sha((ROOT / name).read_bytes()) for name in names}:
        raise ValueError('Production drift')
    report = dict(status='passed-CPU-only-staged-ticket-wait', kernel_build=34,
                  additional_checks=int(result[2]), additional_groups=int(result[3]),
                  additional_threaded_scenarios=int(result[4]), additional_tsan_checks=int(tsan[2]),
                  inherited_binding_checks=int(result[1]), inherited_binding_groups=22, inherited_binding_threaded_scenarios=5,
                  staged_methods_extracted=len(BINDING_SIGNATURES)+1, asan_ubsan=True, tsan=True,
                  detected_wait_mutations=list(mutations), ticket_captured_once_before_polling=True,
                  real_elapsed_budget_counts_lock_reader_scheduler_delay=True,
                  budget_capped_to_legacy_two_seconds=True, locks_released_during_sleep=True,
                  whole_wait_client_lease=True, zero_budget_final_poll=True,
                  exact_GFX_completion_does_not_advance_safe_global_prefix=True,
                  no_flush_CPU_fence_ack_or_reclamation_added=True,
                  native_request_reader_interrupt_event_or_per_wait_cancel_selector_implemented=False,
                  fallback_one_millisecond_rounding_not_hard_return_bound=True,
                  deliberate_client_service_quarantine_preserved=True,
                  input_sha256={name: sha(blob) for name, blob in inputs.items()},
                  staged_driver_sha256=sha(staged.encode()), staged_registry_header_sha256=sha(header.encode()),
                  protected_production_file_count=len(names), production_inputs_ABI_runtime_recipes_unchanged=True,
                  native_Kernel_SDK_compile=False, installed=False, loaded=False, GPU_executed=False,
                  R3_hardware_accepted=False, R4_R6_started=False, physical_FPS_measured=False, public_binary_upload=False)
    (out / 'result-private.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    test(parser.parse_args().out)
