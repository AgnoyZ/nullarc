#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise actual staged full-token dispatch, CPU C peer only; never a kext."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_ack import stage as previous_stage, stage_header as previous_header
from build34_exact_receipt import stage, stage_header
from build34_exact_submit import once
from test_build34_exact_ack import ACK, WAIT, BASE, WAIT_FIXTURE, FIXTURE as ACK_FIXTURE
from test_build34_exact_binding import SIGNATURES as BINDING_SIGNATURES
from test_build34_exact_cs_shape import PRIOR as SHAPE_PRIOR
from test_build34_exact_ownership import DRIVER, PINNED, ROOT, method, sha

HEADER = 'tools/build34_exact_ownership.h'
WIRE = 'tools/build34_exact_receipt_wire.h'
TRANSFORM = 'tools/build34_exact_receipt.py'
RUNNER = 'tools/test_build34_exact_receipt.py'
FIXTURE = 'tests/test_build34_exact_receipt.cpp'
PEER = 'tests/test_build34_exact_receipt_peer.c'
SIGNATURES = ['phx34_exact::Status IOAccelPhxNativeClient::waitExactReceipt(',
              'phx34_exact::Status IOAccelPhxNativeClient::ackExactReceipt(',
              'bool PhxBringup::exactAdmissionClosed(',
              'IOReturn IOAccelPhxNativeClient::doExactReceipt(',
              'IOReturn IOAccelPhxNativeClient::externalMethod(']
PRIOR = {**SHAPE_PRIOR,
         'tests/test_build34_exact_ack.cpp': 'c946cb912fdb30e382b6be513c0a0c29105c7c09b3f25514d278b38212d6e9ff'}


def test(out):
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored worktree build path ending -private')
    subprocess.run(['git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    paths = [*PINNED, *PRIOR, BASE, WAIT_FIXTURE, ACK_FIXTURE, HEADER, WIRE, TRANSFORM, RUNNER, FIXTURE, PEER,
             'LICENSE', 'LICENSES/MIT.txt', 'THIRD_PARTY_NOTICES.md']
    inputs = {n: (ROOT / n).read_bytes() for n in paths}
    for n, digest in {**PINNED, **PRIOR}.items():
        if sha(inputs[n]) != digest:
            raise ValueError('Production/prior input drift: ' + n)
    names = subprocess.check_output(['git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'],
                                    cwd=ROOT, text=True, timeout=15).splitlines()
    protected = {n: sha((ROOT / n).read_bytes()) for n in names}
    original = inputs[DRIVER].decode()
    previous, staged = previous_stage(original), stage(original)
    header = stage_header(inputs[HEADER].decode())
    for sig in [*BINDING_SIGNATURES, WAIT, ACK, 'IOReturn IOAccelPhxNativeClient::doWaitSeq(',
                'void PhxBringup::vmidFree(', 'void IOAccelPhxNativeClient::free(',
                'void IOAccelPhxNativeClient::freeAll(', 'void IOAccelPhxNativeClient::boRelease(']:
        if method(previous, sig) != method(staged, sig):
            raise ValueError('Existing method/quarantine/legacy behavior changed: ' + sig)
    route = ('    if (selector == PHX34_R3_SEL_WAIT_RECEIPT || selector == PHX34_R3_SEL_ACK_RECEIPT)\n'
             '        return doExactReceipt(selector, a); // new waits must not inherit the legacy client lock\n')
    if once(method(staged, SIGNATURES[-1]), route, '') != method(previous, SIGNATURES[-1]):
        raise ValueError('Legacy dispatch changed beyond the new pre-lock route')
    selectors = {int(n) for n in re.findall(r'PHXN_SEL_\w+\s*=\s*(\d+)', inputs['src/phxbringup/PhxNativeABI.h'].decode())}
    if selectors & {64, 65}:
        raise ValueError('Experimental selector collision')
    if '#define PHX_KEXT_BUILD 34u\n' not in staged or re.search(r'exactRequested\s*=|exactFenceReader\s*=', staged):
        raise ValueError('Build34 only, no new native mode or hardware reader admission')
    out.mkdir(parents=True, mode=0o700)
    frozen, source_dir = out / 'frozen', out / 'source/src/phxbringup'
    for n, data in inputs.items():
        p = frozen / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    source_dir.mkdir(parents=True)
    (source_dir / 'PhxBringup.cpp').write_text(staged)
    header_path = source_dir / Path(HEADER).name
    for n in [WIRE, 'tools/build34_exact_callbacks.h']:
        (source_dir / Path(n).name).write_bytes(inputs[n])
    for name, before, after in [('receipt-entry', previous, staged),
                                ('receipt-identity', previous_header(inputs[HEADER].decode()), header)]:
        (out / (name + '.diff')).write_text(''.join(difflib.unified_diff(
            before.splitlines(True), after.splitlines(True), fromfile='a/source', tofile='b/source')))
    cc = ['/usr/bin/xcrun', 'clang++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-Wno-unused-parameter', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer',
          '-I' + str(source_dir), '-I' + str(frozen / 'src/phxbringup')]

    def run(args, label, broken=False):
        p = subprocess.run([str(a) for a in args], cwd=out, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if broken:
            if not p.returncode or b'failed ' not in p.stderr:
                raise ValueError(label + ' did not detect the intended defect')
        elif p.returncode or p.stderr:
            raise RuntimeError(label + ' failed; preserve private logs')
        return p.stdout.decode()

    def exercise(label, code, proposed_header=header, broken=False, sanitizer='address,undefined'):
        header_path.write_text(proposed_header)
        fixture = once(inputs[BASE].decode(), '// PHX34_BINDING_METHODS',
                       '\n'.join(method(code, sig) for sig in BINDING_SIGNATURES))
        fixture = once(fixture, 'static bool baseStart=true;\n',
                       'static bool baseStart=true;\nstatic thread_local uint64_t testTicks=10000000,clockScale=1;\n'
                       'static std::atomic<unsigned> sleepCalls{0};\n')
        fixture = once(fixture, 'static uint64_t mach_absolute_time() { return 10000000; }',
                       'static uint64_t mach_absolute_time() { return testTicks; }')
        fixture = once(fixture, '*out=v; }', '*out=v*clockScale; }')
        fixture = once(fixture, 'static void IOSleep(unsigned ms) { CHECK(ms==1 && !gpuHeld); }',
                       'static void IOSleep(unsigned ms) { CHECK(ms==1 && !clientHeld && !gpuHeld); '
                       'CHECK(++sleepCalls<=2001); event("sleep"); testTicks+=1000000/clockScale; }')
        fixture = once(fixture, 'if(p->client) CHECK(!gpuHeld);', 'if(p->client) CHECK(!gpuHeld && !clientHeld);')
        fixture = once(fixture, '    p->mutex.unlock();\n',
                       '    p->mutex.unlock();\n    if(p->client) event("client-unlocked");\n')
        fixture = once(fixture, 'struct IOExternalMethodArguments {\n',
                       'struct IOExternalMethodDispatch {};\nstatic constexpr unsigned kIOExternalMethodArgumentsCurrentVersion=2;\n'
                       'struct IOExternalMethodArguments {\n'
                       '    uint32_t version=2,selector=0,asyncWakePort=0,asyncReferenceCount=0,structureOutputDescriptorSize=0;\n'
                       '    void *structureOutput=nullptr,*structureOutputDescriptor=nullptr,*structureVariableOutputData=nullptr,*asyncReference=nullptr;\n')
        fixture = once(fixture, '    bool bindExactClient(Registry &,OSObject *);\n',
                       '    bool bindExactClient(Registry &,OSObject *);\n    bool exactAdmissionClosed() const;\n')
        declarations = ('    Status waitExact(uint64_t,uint64_t);\n    Status ackExact(uint64_t);\n'
                        '    Status waitExactReceipt(Ticket,const Receipt &,uint64_t,uint64_t);\n'
                        '    Status ackExactReceipt(Ticket,const Receipt &);\n'
                        '    bool hello=false;\n    IOReturn doExactReceipt(uint32_t,IOExternalMethodArguments *);\n'
                        '    IOReturn externalMethod(uint32_t,IOExternalMethodArguments *,IOExternalMethodDispatch *,OSObject *,void *);\n')
        for name in sorted(set(re.findall(r'\b(do\w+)\(a\)', method(code, SIGNATURES[-1]))) - {'doSubmit'}):
            declarations += '    IOReturn ' + name + '(IOExternalMethodArguments *) { return 123; }\n'
        fixture = once(fixture, '    Status queryExact(uint64_t);\n', '    Status queryExact(uint64_t);\n' + declarations)
        fixture = once(fixture, 'int main() {\n', 'static void binding_regressions() {\n')
        base = out / 'ack-base-CPU-only.h'; base.write_text(fixture)
        waits = once(inputs[WAIT_FIXTURE].decode(), '#include "binding-fixture-CPU-only.h"\n', '')
        waits = once(waits, '// PHX34_EXACT_WAIT_METHOD', '')
        waits = once(waits, 'int main() {\n    binding_regressions();\n', 'static void wait_regressions() {\n')
        waits = once(waits, 'if(mode==ForgetAndReuse || mode==ForgetUnknown) expected=Status::Unknown;',
                     'if(mode==ForgetAndReuse || mode==ForgetUnknown) expected=Status::Complete;')
        waits = once(waits,
                     '                CHECK(c.exactRegistry.forget(old)==Status::Ok); IOLockUnlock(c.lock);\n'
                     '                if(mode==ForgetAndReuse) { auto next=submit(c); CHECK(next>seq); d.setFence(1,next); }\n',
                     '                CHECK(c.exactRegistry.forget(old)==Status::Busy); IOLockUnlock(c.lock);\n')
        wait_tests = out / 'wait-regressions-CPU-only.h'; wait_tests.write_text(waits)
        ack_tests = once(inputs[ACK_FIXTURE].decode(), '// PHX34_EXACT_ACK_METHODS',
                         method(code, WAIT) + '\n' + method(code, ACK))
        ack_tests = once(ack_tests, 'int main() {\n', 'static void ack_regressions() {\n')
        ack_path = out / 'receipt-ack-regressions-CPU-only.h'; ack_path.write_text(ack_tests)
        target, binary, dep = out / (label + '.cpp'), out / (label + '-CPU-only'), out / (label + '.d')
        target.write_text(once(inputs[FIXTURE].decode(), '// PHX34_RECEIPT_METHODS',
                               '\n'.join(method(code, sig) for sig in SIGNATURES)))
        peer = out / (label + '-peer.o')
        run(['/usr/bin/xcrun', 'clang', '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
             '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all', '-fno-omit-frame-pointer',
             '-I' + str(source_dir), '-c', frozen / PEER, '-o', peer], label + '-peer-compile')
        run([*cc, '-fsanitize=' + sanitizer, '-MMD', '-MF', dep, target, peer, '-o', binary], label + '-compile')
        allowed = {str((frozen / n).resolve()) for n in inputs} | {str(target), str(base), str(wait_tests), str(ack_path),
                   str(header_path), str(source_dir / Path(WIRE).name), str(source_dir / 'build34_exact_callbacks.h')}
        deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        if not deps or any(str(Path(p).resolve()) not in allowed for p in deps):
            raise ValueError('Unfrozen compilation dependency')
        linked = run(['/usr/bin/otool', '-L', binary], label + '-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linked, re.I):
            raise ValueError('Device runtime linked')
        return run([binary], label + '-test', broken)

    pattern = (r'PASS staged exact embedded binding: (\d+) checks; 22 groups; 5 threaded scenarios; GPU_executed=false\n'
               r'PASS staged exact ticket wait: (\d+) additional checks; 28 additional groups; 6 additional threaded scenarios; inherited binding passed; GPU_executed=false\n'
               r'PASS staged exact receipt acknowledgement: (\d+) additional checks; 19 additional groups; 5 additional threaded scenarios; inherited binding passed; GPU_executed=false\n'
               r'PASS staged complete-token receipt wire: (\d+) additional checks; (\d+) groups; 5 threaded scenarios; C peer and inherited ACK regressions; GPU_executed=false\n')
    result = re.fullmatch(pattern, exercise('receipt', staged))
    if not result:
        raise ValueError('Incomplete complete-token receipt suite')
    tsan = re.fullmatch(pattern, exercise('receipt-tsan', staged, sanitizer='thread'))
    if not tsan:
        raise ValueError('Incomplete TSan receipt suite')
    mutations = {}

    def source_mutant(label, sig, old, new):
        original = method(staged, sig)
        mutations[label] = once(staged, original, once(original, old, new)), header

    for label, old in [('sequence', 'actual.sequence == expected.sequence && '),
                       ('generation', 'actual.generation == expected.generation &&\n               '),
                       ('queue', 'actual.queue == expected.queue')]:
        mutations['receipt-' + label + '-not-authenticated'] = staged, once(header, old, 'true' if label == 'queue' else '')
    for label, sig in [('wait', SIGNATURES[0]), ('ACK', SIGNATURES[1])]:
        source_mutant(label + '-bypasses-full-token', sig,
                      'exactOwnership->authenticate(ticket, receipt);', 'phx34_exact::Status::Ok;')
    wire_sig = SIGNATURES[3]
    for label, old, new in [
        ('input-length-not-checked', 'a->structureInputSize != sizeof(phx34_r3_request) ||', 'false ||'),
        ('output-length-not-checked', 'a->structureOutputSize != sizeof(phx34_r3_reply) ||', 'false ||'),
        ('wire-version-not-checked', 'request.version != PHX34_R3_WIRE_VERSION || ', ''),
        ('wire-reserved-not-checked', ' || request.reserved ||', ' || false ||'),
        ('async-request-admitted', ' || a->asyncWakePort || a->asyncReference || a->asyncReferenceCount', ''),
        ('ACK-nonzero-timeout-admitted', ' || (ack && request.timeout_ns)', ''),
        ('client-closure-misses-final-check', 'exactClientCallbacks.closed() || owner->exactAdmissionClosed()', 'owner->exactAdmissionClosed()'),
        ('service-closure-misses-final-check', 'exactClientCallbacks.closed() || owner->exactAdmissionClosed()', 'exactClientCallbacks.closed()'),
        ('input-reread-after-wait', '    phx34_r3_reply reply{};', '    memcpy(&request,a->structureInput,sizeof(request));\n    phx34_r3_reply reply{};'),
        ('output-written-before-error', '    const bool ack = selector', '    memset(a->structureOutput,0,sizeof(phx34_r3_reply));\n    const bool ack = selector'),
        ('wire-budget-restarts-after-handshake-lock', 'request.timeout_ns, start);', 'request.timeout_ns, ((void)start, mach_absolute_time()));'),
        ('reply-sequence-truncated-to-32-bit', 'reply.sequence = request.sequence;', 'reply.sequence = uint32_t(request.sequence);'),
        ('reply-generation-truncated-to-32-bit', 'reply.generation = request.generation;', 'reply.generation = uint32_t(request.generation);'),
    ]:
        source_mutant(label, wire_sig, old, new)
    old_external = method(staged, SIGNATURES[-1])
    late = once(old_external, route, '')
    late = once(late, '    IOLockLock(lock);\n', '    IOLockLock(lock);\n' + route)
    mutations['receipt-dispatch-under-client-lock'] = once(staged, old_external, late), header
    source_mutant('wire-wait-not-pinned', SIGNATURES[0],
                  'if (result == phx34_exact::Status::Ok) result = exactOwnership->pinWait(ticket);', '')
    for label, (code, proposed) in mutations.items():
        exercise(label, code, proposed, broken=True)
    header_path.write_text(header)
    if any((ROOT / n).read_bytes() != data or (frozen / n).read_bytes() != data for n, data in inputs.items()):
        raise ValueError('Frozen input drift')
    if protected != {n: sha((ROOT / n).read_bytes()) for n in names}:
        raise ValueError('Production input drift')
    report = dict(status='passed-CPU-only-staged-complete-token-receipt-wire', kernel_build=34,
                  checks=int(result[4]), tsan_checks=int(tsan[4]), groups=int(result[5]), real_thread_scenarios=5,
                  inherited_binding_checks=int(result[1]), inherited_wait_checks=int(result[2]),
                  inherited_ACK_checks=int(result[3]), asan_ubsan=True, tsan=True, detected_mutations=list(mutations),
                  C_peer_fixed_offset_little_endian=True, native_full_source_dispatch_extracted=True,
                  request_copied_once_and_output_preserved_on_error=True, complete_owner_slot_serial_queue_generation_sequence_checked=True,
                  experimental_selectors=[64, 65], native_capability_or_mode_requested=False, hardware_reader_assigned=False,
                  strict_wire_operations_implemented=True, paired_Mesa_adapter_bound=False,
                  global_prefix_visibility_or_CPU_fence_publication_implemented=False, healthy_resource_drain_implemented=False,
                  original_production_file_count=len(names), production_prior_experiments_ABI_runtime_unchanged=True,
                  input_sha256={n: sha(data) for n, data in inputs.items()}, staged_driver_sha256=sha(staged.encode()),
                  staged_ownership_sha256=sha(header.encode()), native_Kernel_SDK_compile=False,
                  installed=False, loaded=False, GPU_executed=False, physical_FPS_measured=False,
                  long_term_stability_accepted=False, R3_hardware_accepted=False, R3_goal_complete=False,
                  R4_R6_started=False, public_binary_upload=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    test(parser.parse_args().out)
