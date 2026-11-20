#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Test staged exact-submit/wait/ACK end to end against CPU objects only."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_receipt import stage as previous_stage
from build34_exact_submit_receipt import stage, stage_header
from build34_exact_submit import once
from test_build34_exact_binding import SIGNATURES as BINDING
from test_build34_exact_receipt import PRIOR, BASE, HEADER, SIGNATURES as RECEIPT
from test_build34_exact_ownership import DRIVER, PINNED, ROOT, method, sha

FIXTURE = 'tests/test_build34_exact_submit_receipt.cpp'
PEER = 'tests/test_build34_exact_submit_peer.c'
WIRE = 'tools/build34_exact_submit_wire.h'
NEW = ['IOReturn IOAccelPhxNativeClient::submitExactReceipt(', 'IOReturn IOAccelPhxNativeClient::doExactSubmit(']


def test(out):
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored build directory ending -private')
    subprocess.run(['git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    evidence = json.loads((ROOT / 'docs/validation/build34-r3-receipt-offline-20261121.json').read_text())
    paths = {*PINNED, *PRIOR, *evidence['input_sha256'], BASE, HEADER, WIRE, FIXTURE, PEER,
             'tools/build34_exact_submit_receipt.py', 'tools/test_build34_exact_submit_receipt.py'}
    inputs = {n: (ROOT / n).read_bytes() for n in sorted(paths)}
    for name, digest in {**PINNED, **PRIOR, **evidence['input_sha256']}.items():
        if sha(inputs[name]) != digest:
            raise ValueError('Production or previous experiment drift: ' + name)
    names = subprocess.check_output(['git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'],
                                    cwd=ROOT, text=True, timeout=15).splitlines()
    protected = {n: sha((ROOT / n).read_bytes()) for n in names}
    original = inputs[DRIVER].decode()
    previous, staged = previous_stage(original), stage(original)
    header = stage_header(inputs[HEADER].decode())
    for sig in [*BINDING, *RECEIPT[:-1], 'phx34_exact::Status IOAccelPhxNativeClient::waitExact(',
                'phx34_exact::Status IOAccelPhxNativeClient::ackExact(', 'IOReturn IOAccelPhxNativeClient::doWaitSeq(',
                'void PhxBringup::vmidFree(', 'void IOAccelPhxNativeClient::free(',
                'void IOAccelPhxNativeClient::freeAll(', 'void IOAccelPhxNativeClient::boRelease(']:
        if method(previous, sig) != method(staged, sig):
            raise ValueError('Prior method/legacy/quarantine changed: ' + sig)
    route = ('    if (selector == PHX34_R3_SEL_SUBMIT_RECEIPT)\n'
             '        return doExactSubmit(a); // this handler owns its client lock\n')
    if once(method(staged, RECEIPT[-1]), route, '') != method(previous, RECEIPT[-1]):
        raise ValueError('Dispatch changed beyond exact-submit route')
    selectors = set(map(int, re.findall(r'PHXN_SEL_\w+\s*=\s*(\d+)', inputs['src/phxbringup/PhxNativeABI.h'].decode())))
    if selectors & {64, 65, 66} or '#define PHX_KEXT_BUILD 34u\n' not in staged:
        raise ValueError('Build34 or experimental selector collision')
    if re.search(r'exactRequested\s*=|exactFenceReader\s*=', staged):
        raise ValueError('No native exact-mode or hardware-reader admission')
    out.mkdir(parents=True, mode=0o700)
    frozen, source = out / 'frozen', out / 'source/src/phxbringup'
    for name, data in inputs.items():
        path = frozen / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    source.mkdir(parents=True)
    (source / 'PhxBringup.cpp').write_text(staged)
    header_path = source / Path(HEADER).name
    for name in [WIRE, 'tools/build34_exact_receipt_wire.h', 'tools/build34_exact_callbacks.h']:
        (source / Path(name).name).write_bytes(inputs[name])
    (out / 'submit-receipt.diff').write_text(''.join(difflib.unified_diff(
        previous.splitlines(True), staged.splitlines(True), fromfile='a/source', tofile='b/source')))
    cc = ['/usr/bin/xcrun', 'clang++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-Wno-unused-parameter', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer',
          '-I' + str(source), '-I' + str(frozen / 'src/phxbringup')]

    def run(args, label, broken=False):
        p = subprocess.run([str(a) for a in args], cwd=out, stdin=subprocess.DEVNULL, capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if broken:
            if not p.returncode or b'failed ' not in p.stderr:
                raise ValueError(label + ' did not detect its defect at runtime')
        elif p.returncode or p.stderr:
            raise RuntimeError(label + ' failed; preserve private evidence')
        return p.stdout.decode()

    def exercise(label, code, proposed=header, broken=False, sanitizer='address,undefined'):
        header_path.write_text(proposed)
        base = once(inputs[BASE].decode(), '// PHX34_BINDING_METHODS', '\n'.join(method(code, sig) for sig in BINDING))
        base = once(base, 'static bool baseStart=true;\n',
                    'static bool baseStart=true;\nstatic thread_local uint64_t testTicks=10000000;\n')
        base = once(base, 'static uint64_t mach_absolute_time() { return 10000000; }',
                    'static uint64_t mach_absolute_time() { return testTicks; }')
        base = once(base, 'static void IOSleep(unsigned ms) { CHECK(ms==1 && !gpuHeld); }',
                    'static void IOSleep(unsigned ms) { CHECK(ms==1 && !gpuHeld); testTicks+=1000000; }')
        base = once(base, 'if(p->client) CHECK(!gpuHeld);', 'if(p->client) CHECK(!gpuHeld && !clientHeld);')
        base = once(base, '    p->mutex.unlock();\n',
                    '    p->mutex.unlock();\n    if(p->client) event("client-unlocked");\n')
        base = once(base, 'struct IOExternalMethodArguments {\n',
                    'struct IOExternalMethodDispatch {};\nstatic constexpr unsigned kIOExternalMethodArgumentsCurrentVersion=2;\n'
                    'struct IOExternalMethodArguments {\n'
                    '    uint32_t version=2,selector=0,asyncWakePort=0,asyncReferenceCount=0,structureOutputDescriptorSize=0;\n'
                    '    void *structureOutput=nullptr,*structureOutputDescriptor=nullptr,*structureVariableOutputData=nullptr,*asyncReference=nullptr;\n')
        base = once(base, '    bool bindExactClient(Registry &,OSObject *);\n',
                    '    bool bindExactClient(Registry &,OSObject *);\n    bool exactAdmissionClosed() const;\n')
        base = once(base, '++packetWrites; }', '++packetWrites; event("packet"); }')
        base = once(base, '    bool gpuReady() const { return true; }',
                    '    bool deviceReady=true;\n    bool gpuReady() const { return deviceReady; }')
        base = once(base, '    bool ensureVmid() { vmid=7; return true; }',
                    '    bool vmidAvailable=true;\n    bool ensureVmid() { if(!vmidAvailable) return false; vmid=7; return true; }')
        declarations = ('    bool hello=false;\n'
            '    Status waitExactReceipt(Ticket,const Receipt &,uint64_t,uint64_t);\n'
            '    Status ackExactReceipt(Ticket,const Receipt &);\n'
            '    IOReturn doExactReceipt(uint32_t,IOExternalMethodArguments *);\n'
            '    IOReturn doExactSubmit(IOExternalMethodArguments *);\n'
            '    IOReturn submitExactReceipt(const void *,uint32_t,Ticket &,Receipt &);\n'
            '    IOReturn externalMethod(uint32_t,IOExternalMethodArguments *,IOExternalMethodDispatch *,OSObject *,void *);\n')
        for name in sorted(set(re.findall(r'\b(do\w+)\(a\)', method(code, RECEIPT[-1]))) - {'doSubmit', 'doExactSubmit'}):
            declarations += '    IOReturn ' + name + '(IOExternalMethodArguments *) { return 123; }\n'
        base = once(base, '    Status queryExact(uint64_t);\n', '    Status queryExact(uint64_t);\n' + declarations)
        base = once(base, 'int main() {\n', 'static void binding_regressions() {\n')
        base_path = out / 'submit-binding-CPU-only.h'; base_path.write_text(base)
        target, binary, dep = out / (label + '.cpp'), out / (label + '-CPU-only'), out / (label + '.d')
        target.write_text(once(inputs[FIXTURE].decode(), '// PHX34_SUBMIT_RECEIPT_METHODS',
                               '\n'.join(method(code, sig) for sig in [*RECEIPT, *NEW])))
        peers = []
        for n, name in enumerate([PEER, 'tests/test_build34_exact_receipt_peer.c']):
            peer = out / (label + '-peer' + str(n) + '.o'); peers.append(peer)
            run(['/usr/bin/xcrun', 'clang', '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                 '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all', '-fno-omit-frame-pointer',
                 '-I' + str(source), '-I' + str(frozen / 'src/phxbringup'), '-c', frozen / name, '-o', peer], label + '-peer' + str(n))
        run([*cc, '-fsanitize=' + sanitizer, '-MMD', '-MF', dep, target, *peers, '-o', binary], label + '-compile')
        allowed = {str((frozen / n).resolve()) for n in inputs} | {str(target), str(base_path), str(header_path)}
        allowed |= {str(source / Path(n).name) for n in [WIRE, 'tools/build34_exact_receipt_wire.h', 'tools/build34_exact_callbacks.h']}
        deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        if not deps or any(str(Path(p).resolve()) not in allowed for p in deps):
            raise ValueError('Unfrozen compilation dependency')
        linked = run(['/usr/bin/otool', '-L', binary], label + '-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linked, re.I):
            raise ValueError('Device runtime linked')
        return run([binary], label + '-test', broken)

    pattern = (r'PASS staged exact embedded binding: (\d+) checks; 22 groups; 5 threaded scenarios; GPU_executed=false\n'
               r'PASS staged exact submit receipt: (\d+) additional checks; (\d+) groups; (\d+) threaded scenarios; inherited binding passed; GPU_executed=false\n')
    normal = re.fullmatch(pattern, exercise('submit-receipt', staged))
    tsan = re.fullmatch(pattern, exercise('submit-receipt-tsan', staged, sanitizer='thread'))
    if not normal or not tsan or int(normal[4]) != 7 or int(tsan[4]) != 7:
        raise ValueError('Incomplete exact submit receipt suite')
    mutations = {}

    def mutant(label, sig, before, after):
        mutations[label] = once(staged, method(staged, sig), once(method(staged, sig), before, after))

    for label, before, after in [
        ('owner-not-authenticated', '!exactRegistry.hasOwner(request.owner)', 'false'),
        ('input-length-unchecked', 'a->structureInputSize != sizeof(phx34_r3_submit_request) ||', 'false ||'),
        ('output-length-unchecked', 'a->structureOutputSize != sizeof(phx34_r3_reply) ||', 'false ||'),
        ('request-reserved-unchecked', ' || request.reserved[0] || request.reserved[1]', ''),
        ('unused-IB-not-zero', 'if (memcmp(&request.ibs[i], &zero, sizeof(zero)))', 'if (memcmp(&request.ibs[i], &zero, sizeof(zero)) && false)'),
        ('submit-input-reread', '    IOLockLock(lock);\n', '    IOLockLock(lock);\n    memcpy(&request,a->structureInput,sizeof(request));\n'),
        ('output-before-success', '    const phxn_cs_ib zero{};', '    memset(a->structureOutput,0,sizeof(phx34_r3_reply));\n    const phxn_cs_ib zero{};'),
        ('client-final-gate-omitted', 'if (exactClientCallbacks.closed() || owner->exactAdmissionClosed()) return kIOReturnNotReady;', 'if (owner->exactAdmissionClosed()) return kIOReturnNotReady;'),
        ('service-final-gate-omitted', 'if (exactClientCallbacks.closed() || owner->exactAdmissionClosed()) return kIOReturnNotReady;', 'if (exactClientCallbacks.closed()) return kIOReturnNotReady;'),
        ('sequence-truncated', 'reply.sequence = receipt.sequence;', 'reply.sequence = uint32_t(receipt.sequence);'),
        ('generation-truncated', 'reply.generation = receipt.generation;', 'reply.generation = uint32_t(receipt.generation);'),
        ('requested-queue-echoed', 'reply.queue = receipt.queue;', 'reply.queue = request.ibs[0].ip_type == PHX_AMDGPU_HW_IP_GFX ? 1 : 0;'),
    ]:
        mutant(label, NEW[1], before, after)
    mutant('mixed-engines-admitted', NEW[0], 'if (ib.ip_type != first.ip_type) return kIOReturnUnsupported;',
           'if (ib.ip_type != first.ip_type && false) return kIOReturnUnsupported;')
    mutant('CPU-user-fence-admitted', NEW[0], 'if (h.flags) return kIOReturnUnsupported;', 'if (h.flags && false) return kIOReturnUnsupported;')
    external = method(staged, RECEIPT[-1]); late = once(external, route, '')
    late = once(late, '    IOLockLock(lock);\n', '    IOLockLock(lock);\n' + route)
    mutations['submit-routed-under-client-lock'] = once(staged, external, late)
    for label, code in mutations.items():
        exercise(label, code, broken=True)
    header_path.write_text(header)
    if any((ROOT / n).read_bytes() != b or (frozen / n).read_bytes() != b for n, b in inputs.items()):
        raise ValueError('Frozen input changed')
    if protected != {n: sha((ROOT / n).read_bytes()) for n in names}:
        raise ValueError('Production input changed')
    report = dict(status='passed-CPU-only-staged-submit-receipt', kernel_build=34, checks=int(normal[2]),
        tsan_checks=int(tsan[2]), groups=int(normal[3]), real_thread_scenarios=int(normal[4]),
        inherited_binding_checks=int(normal[1]), asan_ubsan=True, tsan=True, detected_mutations=list(mutations),
        input_sha256={n: sha(b) for n, b in inputs.items()}, staged_driver_sha256=sha(staged.encode()),
        staged_ownership_sha256=sha(header.encode()), original_production_file_count=len(names),
        prior_methods_production_ABI_runtime_unchanged=True, experimental_selectors=[64,65,66],
        submit_wait_ACK_full_token_CPU_roundtrip=True, actual_queue_fallback_preserved=True,
        mixed_engines_and_CPU_user_fences_refused=True, uncertain_dispatched_receipts_retained=True,
        native_mode_or_capability=False, hardware_reader_assigned=False, Mesa_wire_binding=False,
        global_prefix_visibility_or_CPU_fence_publication=False, healthy_resource_drain=False,
        native_Kernel_SDK_compile=False, installed=False, loaded=False, GPU_executed=False,
        physical_FPS_measured=False, long_term_stability_accepted=False, R3_goal_complete=False,
        R4_R6_started=False, public_binary_upload=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    test(parser.parse_args().out)
