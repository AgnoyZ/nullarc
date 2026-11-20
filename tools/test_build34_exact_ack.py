#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Test staged acknowledgement against wait-pinned receipts; CPU only."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_ack import stage, stage_header
from build34_exact_submit import once
from build34_exact_wait import stage as previous_stage, stage_header as previous_header
from test_build34_exact_binding import SIGNATURES as BINDING_SIGNATURES
from test_build34_exact_fence32 import PRIOR as FENCE_PRIOR
from test_build34_exact_ownership import DRIVER, PINNED, ROOT, method, sha

PRIOR = {
    **FENCE_PRIOR,
    'tools/build34_exact_fence32.h': '29eb9924e9fd2eda00bf5504faf6e921a8875d31a78f1dd330c2588b2a6aaec4',
    'tools/test_build34_exact_fence32.py': '49f9598d8d37956a34498786eec064aff671766620f97ba13885caa8df9d2e3f',
    'tests/test_build34_exact_fence32.cpp': '585893d763c8ba8808e1f8cfc6565b3b5834e6cc42e5f6e91792f37d4f4db1bf',
}
BASE = 'tests/test_build34_exact_binding.cpp'
WAIT_FIXTURE = 'tests/test_build34_exact_wait.cpp'
FIXTURE = 'tests/test_build34_exact_ack.cpp'
HEADER = 'tools/build34_exact_ownership.h'
TRANSFORM = 'tools/build34_exact_ack.py'
RUNNER = 'tools/test_build34_exact_ack.py'
WAIT = 'phx34_exact::Status IOAccelPhxNativeClient::waitExact('
ACK = 'phx34_exact::Status IOAccelPhxNativeClient::ackExact('


def test(out):
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored worktree build path ending -private')
    subprocess.run(['git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    paths = [*PINNED, *PRIOR, FIXTURE, TRANSFORM, RUNNER, 'LICENSE', 'LICENSES/MIT.txt', 'THIRD_PARTY_NOTICES.md']
    inputs = {name: (ROOT / name).read_bytes() for name in paths}
    for name, digest in {**PINNED, **PRIOR}.items():
        if sha(inputs[name]) != digest:
            raise ValueError('Production/prior input drift: ' + name)
    names = subprocess.check_output(['git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'],
                                    cwd=ROOT, text=True, timeout=15).splitlines()
    protected = {name: sha((ROOT / name).read_bytes()) for name in names}
    source = inputs[DRIVER].decode()
    previous, staged = previous_stage(source), stage(source)
    header = stage_header(inputs[HEADER].decode())
    if '#define PHX_KEXT_BUILD 34u\n' not in staged:
        raise ValueError('Only default build34 is admitted')
    for sig in [*BINDING_SIGNATURES, 'IOReturn IOAccelPhxNativeClient::doWaitSeq(',
                'void PhxBringup::vmidFree(', 'void IOAccelPhxNativeClient::free(',
                'void IOAccelPhxNativeClient::freeAll(', 'void IOAccelPhxNativeClient::boRelease(']:
        if method(previous, sig) != method(staged, sig):
            raise ValueError('Previous callsite, legacy path or permanent quarantine changed')
    if re.search(r'exactRequested\s*=|exactFenceReader\s*=', staged):
        raise ValueError('Native exact requests and readers remain unbound')
    out.mkdir(parents=True, mode=0o700)
    frozen = out / 'frozen'
    for name, blob in inputs.items():
        p = frozen / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)
    stage_path = out / 'source' / DRIVER
    stage_path.parent.mkdir(parents=True)
    stage_path.write_text(staged)
    header_path = stage_path.parent / Path(HEADER).name
    header_path.write_text(header)
    (stage_path.parent / 'build34_exact_callbacks.h').write_bytes(inputs['tools/build34_exact_callbacks.h'])
    for label, before, after in [('receipt-ack', previous, staged),
                                  ('wait-pins', previous_header(inputs[HEADER].decode()), header)]:
        (out / (label + '.diff')).write_text(''.join(difflib.unified_diff(
            before.splitlines(True), after.splitlines(True), fromfile='a/source', tofile='b/source')))
    cc = ['/usr/bin/xcrun', 'clang++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-Wno-unused-parameter', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer',
          '-I' + str(stage_path.parent), '-I' + str(frozen / 'src/phxbringup')]

    def run(args, label, broken=False):
        p = subprocess.run([str(a) for a in args], cwd=out, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=60)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if broken:
            if p.returncode == 0 or b'failed ' not in p.stderr:
                raise ValueError(label + ' did not detect intended defect')
        elif p.returncode or p.stderr:
            raise RuntimeError(label + ' failed; see private logs')
        return p.stdout.decode()

    def exercise(label, code, proposed_header=header, broken=False, sanitizer='address,undefined'):
        header_path.write_text(proposed_header)
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
                       '    Status queryExact(uint64_t);\n    Status waitExact(uint64_t,uint64_t);\n'
                       '    Status ackExact(uint64_t);\n')
        fixture = once(fixture, 'int main() {\n', 'static void binding_regressions() {\n')
        base = out / 'ack-base-CPU-only.h'
        base.write_text(fixture)
        # Re-run the frozen earlier deadline/identity/close tests on the NEW
        # actual wait, adapting only deliberate forget attempts: a live wait
        # now pins the complete record, so eviction refuses Busy, not Unknown.
        waits = once(inputs[WAIT_FIXTURE].decode(), '#include "binding-fixture-CPU-only.h"\n', '')
        waits = once(waits, '// PHX34_EXACT_WAIT_METHOD', '')
        waits = once(waits, 'int main() {\n    binding_regressions();\n',
                     'static void wait_regressions() {\n')
        waits = once(waits, 'if(mode==ForgetAndReuse || mode==ForgetUnknown) expected=Status::Unknown;',
                     'if(mode==ForgetAndReuse || mode==ForgetUnknown) expected=Status::Complete;')
        waits = once(waits,
                     '                CHECK(c.exactRegistry.forget(old)==Status::Ok); IOLockUnlock(c.lock);\n'
                     '                if(mode==ForgetAndReuse) { auto next=submit(c); CHECK(next>seq); d.setFence(1,next); }\n',
                     '                CHECK(c.exactRegistry.forget(old)==Status::Busy); IOLockUnlock(c.lock);\n')
        wait_tests = out / 'wait-regressions-CPU-only.h'
        wait_tests.write_text(waits)
        target = out / (label + '.cpp')
        target.write_text(once(inputs[FIXTURE].decode(), '// PHX34_EXACT_ACK_METHODS',
                               method(code, WAIT) + '\n' + method(code, ACK)))
        binary, dep = out / (label + '-CPU-only'), out / (label + '.d')
        run([*cc, '-fsanitize=' + sanitizer, '-MMD', '-MF', dep, target, '-o', binary], label + '-compile')
        allowed = {str((frozen / n).resolve()) for n in inputs} | {
            str(target), str(base), str(wait_tests), str(header_path), str(stage_path.parent / 'build34_exact_callbacks.h')}
        deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        if not deps or any(str(Path(p).resolve()) not in allowed for p in deps):
            raise ValueError('Unfrozen compilation dependency')
        linked = run(['/usr/bin/otool', '-L', binary], label + '-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linked, re.I):
            raise ValueError('Device runtime linked')
        return run([binary], label + '-test', broken)

    pattern = (r'PASS staged exact embedded binding: (\d+) checks; 22 groups; 5 threaded scenarios; GPU_executed=false\n'
               r'PASS staged exact ticket wait: (\d+) additional checks; 28 additional groups; '
               r'6 additional threaded scenarios; inherited binding passed; GPU_executed=false\n'
               r'PASS staged exact receipt acknowledgement: (\d+) additional checks; (\d+) additional groups; '
               r'(\d+) additional threaded scenarios; inherited binding passed; GPU_executed=false\n')
    result = re.fullmatch(pattern, exercise('ack', staged))
    if not result or int(result[4]) != 19 or int(result[5]) != 5:
        raise ValueError('Incomplete acknowledgement suite')
    mutations = {}

    def source_mutant(label, sig, old, new):
        original = method(staged, sig)
        mutations[label] = once(staged, original, once(original, old, new)), header

    source_mutant('wait-never-pins-receipt', WAIT,
                  '    if (result == phx34_exact::Status::Ok) result = exactOwnership->pinWait(ticket);\n', '')
    source_mutant('wait-forgets-to-unpin', WAIT,
                  '        const auto released = exactOwnership->unpinWait(ticket);\n',
                  '        const auto released = phx34_exact::Status::Ok;\n')
    source_mutant('wait-unpins-outside-client-lock', WAIT,
                  '        IOLockLock(lock);\n        const auto released = exactOwnership->unpinWait(ticket);\n'
                  '        IOLockUnlock(lock);\n',
                  '        const auto released = exactOwnership->unpinWait(ticket);\n')
    source_mutant('ack-without-client-lease', ACK,
                  '    phx34_exact::CallbackGate<>::Lease callback(exactClientCallbacks);\n',
                  '    const bool callback=true;\n')
    source_mutant('ack-accepts-foreign-registry', ACK, 'exactOwnership == &exactRegistry && ', '')
    source_mutant('ack-missing-client-pin', ACK, 'exactClientPinned && ', '')
    source_mutant('ack-accepts-pending-as-complete', ACK,
                  '        result = owner->observeExact(*exactOwnership, ticket, exactClientCallbacks, this);\n',
                  '        result = phx34_exact::Status::Complete;\n')
    source_mutant('ack-forgets-pending-without-observing', ACK,
                  '        result = owner->observeExact(*exactOwnership, ticket, exactClientCallbacks, this);\n',
                  '        result = exactOwnership->forget(ticket);\n')
    header_changes = {
        'forget-ignores-active-waits': ('        if (e->waiters) return Status::Busy;\n', ''),
        'waiter-counter-wraps': ('        if (e->waiters == UINT16_MAX) return Status::Exhausted;\n', ''),
        'waiter-counter-underflows': ('        if (!e->waiters) return Status::Invalid;\n', ''),
        'close-prevents-admitted-wait-release': ('    Status unpinWait(Ticket ticket) {\n',
                                                '    Status unpinWait(Ticket ticket) {\n        if (closed_) return Status::Closed;\n'),
    }
    for label, (old, new) in header_changes.items():
        mutations[label] = staged, once(header, old, new)
    for label, (code, proposed) in mutations.items():
        exercise(label, code, proposed, broken=True)
    tsan = re.fullmatch(pattern, exercise('ack-tsan', staged, sanitizer='thread'))
    if not tsan or int(tsan[4]) != 19 or int(tsan[5]) != 5:
        raise ValueError('Incomplete acknowledgement TSan suite')
    if header_path.read_text() != header or stage_path.read_text() != staged:
        raise ValueError('Staged header/source drift')
    if any((ROOT / n).read_bytes() != b or (frozen / n).read_bytes() != b for n, b in inputs.items()):
        raise ValueError('Frozen input drift')
    if protected != {n: sha((ROOT / n).read_bytes()) for n in names}:
        raise ValueError('Production drift')
    report = dict(status='passed-CPU-only-staged-receipt-acknowledgement', kernel_build=34,
                  additional_checks=int(result[3]), additional_groups=int(result[4]),
                  additional_threaded_scenarios=int(result[5]), additional_tsan_checks=int(tsan[3]),
                  inherited_binding_checks=int(result[1]), asan_ubsan=True, tsan=True,
                  previous_wait_checks_on_new_staged_wait=int(result[2]),
                  previous_wait_tsan_checks_on_new_staged_wait=int(tsan[2]),
                  previous_wait_groups=28, previous_wait_threaded_scenarios=6,
                  previous_wait_forget_cases_require_Busy_instead_of_eviction=True,
                  staged_methods_extracted=len(BINDING_SIGNATURES)+2, detected_mutations=list(mutations),
                  completed_metadata_ack_blocked_until_all_admitted_waits_leave=True,
                  pending_lost_unknown_or_closed_receipts_not_forgotten=True,
                  completed_receipt_slots_reused_for_2000_submissions=True,
                  full_64_receipt_admission_refused_before_packets=True,
                  waiter_counter_saturation_and_underflow_checked=True,
                  all_terminal_wait_paths_unpin_under_client_lock=True,
                  forget_does_not_free_BO_VMID_client_provider_or_publish_CPU_fence=True,
                  exact_GFX_completion_does_not_advance_safe_global_prefix=True,
                  native_selector_negotiation_Mesa_ack_or_healthy_resource_drain_implemented=False,
                  deliberate_permanent_quarantine_preserved=True,
                  input_sha256={n: sha(b) for n, b in inputs.items()},
                  staged_driver_sha256=sha(staged.encode()), staged_registry_header_sha256=sha(header.encode()),
                  protected_production_file_count=len(names), production_ABI_prior_transforms_runtime_unchanged=True,
                  native_Kernel_SDK_compile=False, installed=False, loaded=False, GPU_executed=False,
                  R3_hardware_accepted=False, R4_R6_started=False, physical_FPS_measured=False,
                  long_term_stability_accepted=False, public_binary_upload=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    test(parser.parse_args().out)
