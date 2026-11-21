#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise actual staged multi-pending CPU fences without device execution."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_cpu_fences import stage, stage_header
from build34_exact_close import stage as previous_stage, stage_header as previous_header
from build34_exact_submit import once
from test_build34_exact_binding import SIGNATURES
from test_build34_exact_ownership import DRIVER, ROOT, method, sha

HEADER = 'tools/build34_exact_ownership.h'
BASE = 'tests/test_build34_exact_vm_lifetime.cpp'
OLD_BO = 'tests/test_build34_exact_bo_lifetime.cpp'
LEGACY = 'tests/test_build34_exact_legacy_close.cpp'
EXACT = 'tests/test_build34_exact_close.cpp'
FIXTURE = 'tests/test_build34_exact_cpu_fences.cpp'
RUNNER = 'tools/test_build34_exact_cpu_fences.py'
TRANSFORM = 'tools/build34_exact_cpu_fences.py'
SNAPSHOT = 'IOReturn PhxBringup::vmBoSnapshot('
BOFREE = 'IOReturn IOAccelPhxNativeClient::doBoFree('
GEMVA = 'IOReturn IOAccelPhxNativeClient::doGemVa('
RELEASE = 'bool IOAccelPhxNativeClient::boRelease('
FENCE = 'bool IOAccelPhxNativeClient::publishCpuFence('
WAIT = 'IOReturn IOAccelPhxNativeClient::doWaitSeq('


def test(out):
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored worktree build path ending -private')
    subprocess.run(['git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    prior = json.loads((ROOT / 'docs/validation/build34-r3-exact-close-offline-20261121.json').read_text())
    pinned = prior['input_sha256']
    paths = {*pinned, BASE, OLD_BO, 'tools/build34_exact_vm_lifetime.py', 'tools/test_build34_exact_vm_lifetime.py',
             FIXTURE, RUNNER, TRANSFORM, LEGACY, EXACT, 'tools/build34_exact_legacy_close.py',
             'tools/test_build34_exact_legacy_close.py', 'tools/build34_exact_close.py', 'tools/test_build34_exact_close.py'}
    inputs = {n: (ROOT / n).read_bytes() for n in sorted(paths)}
    for n, h in pinned.items():
        if sha(inputs[n]) != h:
            raise ValueError('Production/prior input drift: ' + n)
    names = subprocess.check_output(['git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'],
                                    cwd=ROOT, text=True).splitlines()
    protected = {n: sha((ROOT / n).read_bytes()) for n in names}
    original = inputs[DRIVER].decode()
    previous, staged = previous_stage(original), stage(original)
    for sig in ['void PhxBringup::stop(',
                'IOReturn PhxBringup::gpuSubmit(', 'bool PhxBringup::vmidFree(',
                'IOReturn PhxBringup::vmMap(', 'IOReturn PhxBringup::vmUnmap(',
                'IOReturn IOAccelPhxNativeClient::doExactSubmit(',
                'IOReturn IOAccelPhxNativeClient::doExactReceipt(']:
        if method(previous, sig) != method(staged, sig):
            raise ValueError('Unrelated/quarantine method drift: ' + sig)
    if re.search(r'exactDwordReader\s*=|exactFenceReader\s*=|exactRequested\s*=', staged):
        raise ValueError('No native reader or mode binding admitted')
    if '#define PHX_KEXT_BUILD 34u\n' not in staged:
        raise ValueError('Build34 only')
    service = staged[staged.index('class PhxBringup :'):staged.index('OSDefineMetaClassAndStructors(PhxBringup')]
    for name in ['vmBoSnapshot', 'registerLegacyClient', 'requestLegacyClose', 'detachLegacyClient', 'exactCloseSnapshot']:
        pos = service.index(name + '(')
        if service.rfind('\npublic:', 0, pos) < service.rfind('\nprivate:', 0, pos):
            raise ValueError('Native service helper inaccessible to client: ' + name)
    out.mkdir(parents=True, mode=0o700)
    frozen, source = out / 'frozen', out / 'source/src/phxbringup'
    for n, b in inputs.items():
        p = frozen / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
    source.mkdir(parents=True)
    (source / 'PhxBringup.cpp').write_text(staged)
    header_path = source / Path(HEADER).name
    header_path.write_text(stage_header(inputs[HEADER].decode()))
    extras = ['tools/build34_exact_fence32.h', 'tools/build34_exact_callbacks.h',
              'tools/build34_exact_receipt_wire.h', 'tools/build34_exact_submit_wire.h']
    for n in extras:
        (source / Path(n).name).write_bytes(inputs[n])
    (out / 'cpu-fences.diff').write_text(''.join(difflib.unified_diff(
        previous.splitlines(True), staged.splitlines(True), fromfile='a/source', tofile='b/source')))
    cc = ['/usr/bin/xcrun', 'clang++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-Wno-unused-parameter', '-Wno-unused-function', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer',
          '-I' + str(source), '-I' + str(frozen / 'src/phxbringup')]

    def run(args, label, broken=False):
        p = subprocess.run([str(a) for a in args], cwd=out, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if broken:
            if not p.returncode or b'failed ' not in p.stderr:
                raise ValueError(label + ' did not detect intended runtime defect')
        elif p.returncode or p.stderr:
            raise RuntimeError(label + ' failed; preserve private evidence')
        return p.stdout.decode()

    def exercise(label, code, proposed_header=None, broken=False, sanitizer='address,undefined', baseline=False):
        header_path.write_text(proposed_header if proposed_header is not None else stage_header(inputs[HEADER].decode()))
        # Reuse ONLY the frozen CPU double prefix. No old scenarios/counts are
        # executed or added to this suite's independently reported coverage.
        base = inputs[BASE].decode().split('struct Pause {', 1)[0]
        # Assertion failures in deliberately broken CPU children are ordinary
        # nonzero exits, not intentional process crashes or OS crash reports.
        base = once(base, 'std::abort();', 'std::_Exit(86);')
        base = once(base, '#include "PhxNativeABI.h"',
                    '#include "PhxNativeABI.h"\n#include "build34_exact_submit_wire.h"')
        base = once(base, 'using IOReturn=int;',
                    'using IOReturn=int; using UInt32=uint32_t; using IOOptionBits=unsigned;\n'
                    'using thread_call_param_t=void *; struct IOExternalMethodDispatch {};\n'
                    'static std::atomic<unsigned> baseFrees{0},storageFrees{0},lockFrees{0},sessionReleases{0},hangChecks{0},hangArms{0};\n'
                    'static std::atomic<bool> baseStartResult{true};\n'
                    'static constexpr unsigned kMillisecondScale=1;')
        constants = original[original.index('static constexpr uint32_t kFirstUserVmid ='):
                             original.index('static inline void flushLine(')]
        base = once(base, '// PHX34_VM_CONSTANTS', constants)
        base = once(base, 'static constexpr int kMaxMaps=2;', 'static constexpr int kMaxMaps=4;')
        base = once(base, 'struct Lock { std::mutex mutex; bool client=false; };',
                    'struct Lock { std::mutex mutex; bool client=false,freed=false; };')
        base = once(base, '    CHECK(p); event(p->client', '    CHECK(p && !p->freed); event(p->client')
        base = once(base, '    CHECK(!gpuHeld);', '    CHECK(!gpuHeld && (!p->client || !clientHeld));')
        base = once(base, 'static uint64_t mach_absolute_time()',
                    'static void IOLockFree(Lock *p) { CHECK(p && !p->freed && !clientHeld && !gpuHeld); p->freed=true; ++lockFrees; }\n'
                    'static void IOFree(void *p,size_t) { CHECK(p && !clientHeld && !gpuHeld); ++storageFrees; }\n'
                    'static void clock_interval_to_deadline(unsigned n,unsigned,uint64_t *d) { CHECK(n==500); *d=500; }\n'
                    'static void thread_call_enter_delayed(void *p,uint64_t d) { CHECK(p && d==500); ++hangArms; }\n'
                    'static uint64_t mach_absolute_time()')
        base = once(base, 'struct OSObject { std::atomic<unsigned> retained{0}; virtual ~OSObject()=default; void retain() { ++retained; event("retain"); } };',
                    'struct OSObject { std::atomic<unsigned> refs{1}; std::atomic<bool> finalized{false};\n'
                    '    virtual ~OSObject()=default;\n'
                    '    virtual void free() { CHECK(!refs && !finalized); finalized=true; }\n'
                    '    void retain() { CHECK(!finalized && refs.fetch_add(1)>0); event("retain"); }\n'
                    '    void release() { event("object-release"); auto old=refs.fetch_sub(1); CHECK(old>0); if(old==1) free(); } };')
        base = once(base, 'struct IOUserClient : IOService { bool start(IOService *) { return true; } void terminate() { ++terminations; } };',
                    'struct IOUserClient : IOService { bool start(IOService *) { return baseStartResult; }\n'
                    '    void terminate() { ++terminations; event("terminate"); }\n'
                    '    void free() override { ++baseFrees; OSObject::free(); } };')
        base = once(base, '    uint64_t scalarOutput[1]{sentinel};',
                    '    const void *structureOutputDescriptor=nullptr;\n'
                    '    const uint64_t *scalarInput=nullptr;\n'
                    '    uint64_t storage[3]{sentinel,sentinel,sentinel}; uint64_t *scalarOutput=storage;')
        base = once(base, 'struct IOExternalMethodArguments {\n',
                    'static constexpr unsigned kIOExternalMethodArgumentsCurrentVersion=2;\n'
                    'struct IOExternalMethodArguments {\n'
                    '    uint32_t version=2,selector=0,asyncWakePort=0,asyncReferenceCount=0,structureOutputDescriptorSize=0;\n'
                    '    void *structureOutput=nullptr,*structureVariableOutputData=nullptr,*asyncReference=nullptr;\n')
        base = once(base, 'struct IOMemoryDescriptor {', 'struct IOMemoryDescriptor {\n'
                    '    bool alive=true,prepared=true,failComplete=false; unsigned completes=0,releases=0,retains=0;\n'
                    '    IOReturn complete() { CHECK(alive && prepared && !gpuHeld); ++completes; event("md-complete");\n'
                    '        if(failComplete) return kIOReturnVMError; prepared=false; return kIOReturnSuccess; }\n'
                    '    void retain() { CHECK(alive); ++retains; }\n'
                    '    void release() { CHECK(alive && !gpuHeld); ++releases; alive=false; event("md-release"); }')
        base = once(base, 'CHECK(n==1 && gpuHeld==1 && ++delays<=1000);',
                    'CHECK(((n==1 && gpuHeld==1) || (n==50 && !gpuHeld)) && ++delays<=1000);')
        base = once(base, 'testTicks+=delayStep;', 'testTicks+=delayStep*n;')
        fields = code[code.index('    static constexpr uint32_t kPtChunkBytes ='):code.index('    uint64_t *ptTable(')]
        base = once(base, '    // PHX34_VM_FIELDS', fields)
        base = once(base, '    bool debugEnabled() const { return false; }',
                    '    bool debugEnabled() const { return false; }\n'
                    '    bool exactAdmissionClosed() const { return exactCallbacks.closed() || exactStopped; }\n'
                    '    bool hangStop=false; void *hangCall=this;\n'
                    '    static void hangTick(thread_call_param_t,thread_call_param_t);\n'
                    '    void hangCheck() { ++hangChecks; }')
        base = once(base, '    bool claimSession() { return true; } void releaseSession() {}',
                    '    std::atomic<unsigned> sessionOpen{0};\n'
                    '    bool claimSession() { unsigned v=0; return sessionOpen.compare_exchange_strong(v,1); }\n'
                    '    void releaseSession() { unsigned v=1; if(sessionOpen.compare_exchange_strong(v,0)) ++sessionReleases; }')
        base = once(base, '    bool bindExactClient(Registry &,OSObject *);',
                    '    bool bindExactClient(Registry &,OSObject *);\n'
                    '    IOReturn exactCloseSnapshot(Registry &,IOAccelPhxNativeClient *,uint32_t,uint64_t,uint64_t,uint64_t *);\n'
                    '    IOReturn vmBoSnapshot(uint32_t,uint64_t,const void *,bool,uint64_t *);\n'
                    '    bool registerLegacyClient(OSObject *); bool requestLegacyClose(IOAccelPhxNativeClient *);\n'
                    '    bool detachLegacyClient(IOAccelPhxNativeClient *);')
        # Real source Bo/Map layouts and real PHXN_MAX_BOS-sized backing arrays.
        cpu_fields = '' if baseline else code[code.index('    static constexpr uint32_t kMaxCpuFences ='):code.index('    bool publishCpuFence(')]
        layout = code[code.index('    struct Bo {'):code.index('    IOReturn doHello(')]
        old = base[base.index('    struct Bo {'):base.index('    PhxBringup *owner=nullptr;')]
        base = once(base, old, layout + '\n' + cpu_fields + '\n'
                    '    std::vector<Bo> boStorage=std::vector<Bo>(PHXN_MAX_BOS); Bo *bos=boStorage.data();\n'
                    '    Map mapStorage[kMaxMaps]{}; Map *maps=mapStorage;\n'
                    '    uint64_t hostUsed=0,gttUsed=0,hiUsed=0,visUsed=0;\n'
                    '    bool hello=true,boCleanupFault=false;\n'
                    '    Bo *releasePermit=nullptr; Bo releaseHeld{};\n'
                    '    uint32_t legacyState=0,legacyReaping=0; bool legacyClientPinned=false,legacyProviderPinned=false,legacyReleaseAuthorized=false;\n'
                    '    bool exactReleaseAuthorized=false; IOReturn finishExactClose();\n'
                    '    IOReturn finishLegacyClose(); void free() override;\n'
                    '    IOReturn externalMethod(uint32_t,IOExternalMethodArguments *,IOExternalMethodDispatch *,OSObject *,void *);\n'
                    '    IOReturn clientMemoryForType(UInt32,IOOptionBits *,IOMemoryDescriptor **);\n')
        ensure = re.findall(r'    bool ensureVmid\(\) \{[^\n]*\}', code)
        if len(ensure) != 1:
            raise ValueError('Require actual ensureVmid')
        base = once(base, '    // PHX34_VM_ENSURE', ensure[0])
        base = once(base, '    void flushBos() { CHECK(clientHeld); } Bo *findBo(uint32_t) { return nullptr; }',
                    '    void flushBos() { CHECK(clientHeld); event("cpu-flush"); }\n'
                    '    Bo *findBo(uint32_t); bool boRelease(Bo &); bool publishCpuFence(uint64_t);\n'
                    '    IOReturn doBoFree(IOExternalMethodArguments *); IOReturn doGemVa(IOExternalMethodArguments *);\n'
                    '    IOReturn doWaitSeq(IOExternalMethodArguments *);\n'
                    '    IOReturn submitExactReceipt(const void *,uint32_t,Ticket &,Receipt &);\n'
                    '    Status waitExact(uint64_t,uint64_t); Status ackExact(uint64_t);\n'
                    '    Status waitExactReceipt(Ticket,const Receipt &,uint64_t,uint64_t);\n'
                    '    Status ackExactReceipt(Ticket,const Receipt &);\n'
                    '    IOReturn doExactReceipt(uint32_t,IOExternalMethodArguments *);\n'
                    '    IOReturn doExactSubmit(IOExternalMethodArguments *);')
        base = once(base, '    void freeAll() { ++frees; }', '    bool freeAll();\n    // PHX34_CLOSE_DISPATCH_STUBS')
        stubs = sorted(set(re.findall(r'\br = (do\w+)\(a\)', method(code, 'IOReturn IOAccelPhxNativeClient::externalMethod('))))
        stubs = [n for n in stubs if n not in {'doBoFree', 'doGemVa', 'doSubmit'}]
        stubs += ['doTopology', 'doSurfGpuMark']
        stubtext = '\n'.join('    IOReturn ' + n + '(IOExternalMethodArguments *) { event("dispatch"); return kIOReturnSuccess; }' for n in stubs)
        base = once(base, '    // PHX34_CLOSE_DISPATCH_STUBS', stubtext)
        reference = code[code.index('class Phx34ScopedReference {'):code.index('static phx34_exact::OwnerEpochs gExactOwners;')]
        base = once(base, 'static OwnerEpochs gExactOwners;', reference + '\nstatic OwnerEpochs gExactOwners;')
        sigs = [*SIGNATURES, 'PhxBringup::VmCtx *PhxBringup::vmOwned(', 'bool PhxBringup::vmWorkCurrent(',
                'bool PhxBringup::vmFlushTlbChecked(', 'uint32_t PhxBringup::vmidAlloc(', 'bool PhxBringup::vmidFree(',
                'IOReturn PhxBringup::vmMap(', 'IOReturn PhxBringup::vmUnmap(', 'uint32_t PhxBringup::vmBind(',
                'bool PhxBringup::exactGlobalRetiredLocked(', 'bool PhxBringup::readExactFence32(', SNAPSHOT,
                'IOAccelPhxNativeClient::Bo *IOAccelPhxNativeClient::findBo(', BOFREE, GEMVA, RELEASE, FENCE, WAIT,
                'bool IOAccelPhxNativeClient::checkCpuFences(', 'bool IOAccelPhxNativeClient::appendCpuFence(',
                'IOReturn IOAccelPhxNativeClient::prepareCpuFence(',
                'IOReturn IOAccelPhxNativeClient::submitExactReceipt(',
                'IOReturn PhxBringup::exactCloseSnapshot(',
                'IOReturn IOAccelPhxNativeClient::finishExactClose(',
                'phx34_exact::Status IOAccelPhxNativeClient::waitExact(',
                'phx34_exact::Status IOAccelPhxNativeClient::ackExact(',
                'phx34_exact::Status IOAccelPhxNativeClient::waitExactReceipt(',
                'phx34_exact::Status IOAccelPhxNativeClient::ackExactReceipt(',
                'IOReturn IOAccelPhxNativeClient::doExactReceipt(',
                'IOReturn IOAccelPhxNativeClient::doExactSubmit(',
                'bool PhxBringup::registerLegacyClient(', 'bool PhxBringup::requestLegacyClose(',
                'bool PhxBringup::detachLegacyClient(', 'void PhxBringup::reapLegacyClients(',
                'IOReturn IOAccelPhxNativeClient::finishLegacyClose(', 'void IOAccelPhxNativeClient::free(',
                'bool IOAccelPhxNativeClient::freeAll(', 'void PhxBringup::hangTick(',
                'IOReturn IOAccelPhxNativeClient::externalMethod(', 'IOReturn IOAccelPhxNativeClient::clientMemoryForType(']
        if baseline:
            sigs = [sig for sig in sigs if not any(n in sig for n in ['checkCpuFences(', 'appendCpuFence(', 'prepareCpuFence('])]
        base = once(base, '// PHX34_VM_METHODS', method(code, 'static bool shape(') + '\n' +
                    '\n'.join(method(code, sig) for sig in sigs))
        helpers = inputs[OLD_BO].decode().split('struct Pause {', 1)[1].split('static void happyBoFree()', 1)[0]
        helpers = 'struct Pause {' + helpers
        helpers = once(helpers, '    packetWrites=frees=terminations=sleepCalls=delays=lineFlushes=0;',
                       '    packetWrites=frees=terminations=sleepCalls=delays=lineFlushes=0;\n'
                       '    baseFrees=storageFrees=lockFrees=sessionReleases=hangChecks=hangArms=0; baseStartResult=true;')
        legacy = inputs[LEGACY].decode()
        legacy = once(legacy, 'int main() {', 'static void legacy_regressions() {')
        old_exact = legacy[legacy.index('static void exactStillQuarantined() {'):legacy.index('static void callbackDrainWithoutLockWait() {')]
        legacy = once(legacy, old_exact, '''static void exactStillQuarantined() {
    // Derived regression: healthy exact close is now conditionally reclaimable.
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,true);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
    CHECK(registered(d)==1 && c.exactClientPinned && c.refs==2 && d.refs==2);
    CHECK(c.clientClose()==kIOReturnSuccess && terminations==1); c.release();
    CHECK(!md.alive && c.finalized && !c.refs && !c.exactClientPinned && d.refs==1);
}
''')
        legacy = once(legacy, 'c.pendFenceHandle=1; c.pendFenceSeq=seq;', 'CHECK(c.appendCpuFence(1,0,seq));')
        legacy = once(legacy, 'c.pendFenceHandle=1; c.pendFenceOffset=8; c.pendFenceSeq=seq;', 'CHECK(c.appendCpuFence(1,8,seq));')
        fixture = once(legacy, '// PHX34_CLOSE_BASE', base + helpers)
        fixture += '\n' + once(inputs[EXACT].decode(), 'int main() {', 'static void exact_close_regressions() {')
        fixture += '\n' + inputs[FIXTURE].decode()
        # Keep large CPU service doubles in their scenario's own stack frame.
        # Only zero-argument static fixture functions are affected; actual native
        # methods retain the compiler's ordinary O1 inlining and source bodies.
        fixture = re.sub(r'^static void (\w+)\(\) \{',
                         r'static __attribute__((noinline)) void \1() {', fixture, flags=re.M)
        if baseline:
            fixture = base + helpers + '''
int main() {
    reset(); CHECK(!threaded); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
    Request a,b; a.h.flags=b.h.flags=PHXN_CS_HAS_FENCE;
    a.h.fence_handle=b.h.fence_handle=1; a.h.fence_offset=0; b.h.fence_offset=8;
    IOLockLock(c.lock); CHECK(c.doSubmit(&a.a)==kIOReturnSuccess && c.doSubmit(&b.a)==kIOReturnSuccess); IOLockUnlock(c.lock);
    const auto first=a.a.scalarOutput[0],last=b.a.scalarOutput[0]; CHECK(first<last);
    d.setFence(1,last); CHECK(wait(c,last,0)==kIOReturnSuccess);
    CHECK(!read64(bytes) && read64(bytes,8)==last); // first accepted fence was overwritten
    CHECK(c.clientClose()==kIOReturnSuccess); c.release(); CHECK(c.finalized);
    std::puts("REPRODUCED previous actual submit/WAITSEQ losing the earlier CPU fence; GPU_executed=false");
}
'''

        target, binary, dep = out / (label + '.cpp'), out / (label + '-CPU-only'), out / (label + '.d')
        target.write_text(fixture)
        run([*cc, '-fsanitize=' + sanitizer, '-MMD', '-MF', dep, target, '-o', binary], label + '-compile')
        allowed = {str((frozen / n).resolve()) for n in inputs} | {str(target), str(header_path)}
        allowed |= {str(source / Path(n).name) for n in extras}
        deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        if not deps or any(str(Path(n).resolve()) not in allowed for n in deps):
            raise ValueError('Unfrozen dependency')
        linked = run(['/usr/bin/otool', '-L', binary], label + '-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linked, re.I):
            raise ValueError('Device runtime linked')
        return run([binary], label + '-test', broken)

    baseline = exercise('previous-single-fence-counterexample', previous, baseline=True)
    if baseline != 'REPRODUCED previous actual submit/WAITSEQ losing the earlier CPU fence; GPU_executed=false\n':
        raise ValueError('Prior actual-method counterexample did not reproduce')
    pattern = (r'PASS staged legacy close and reaping: (\d+) checks; (\d+) groups; (\d+) threaded scenarios; GPU_executed=false\n'
               r'PASS staged exact close and reaping: (\d+) additional checks; (\d+) groups; (\d+) threaded scenarios; GPU_executed=false\n'
               r'PASS staged multiple CPU fences: (\d+) additional checks; (\d+) groups; (\d+) threaded scenarios; GPU_executed=false\n')
    normal = re.fullmatch(pattern, exercise('cpu-fences', staged))
    tsan = re.fullmatch(pattern, exercise('cpu-fences-tsan', staged, sanitizer='thread'))
    if not normal or not tsan:
        raise ValueError('Incomplete multi-pending fence and inherited close suites')
    mutations = {}

    def mutant(label, sig, before, after):
        old = method(staged, sig)
        mutations[label] = once(staged, old, once(old, before, after))

    check = 'bool IOAccelPhxNativeClient::checkCpuFences('
    append = 'bool IOAccelPhxNativeClient::appendCpuFence('
    prepare = 'IOReturn IOAccelPhxNativeClient::prepareCpuFence('
    submit = 'IOReturn IOAccelPhxNativeClient::doSubmit('
    for label, before, after in [
        ('descriptor', 'b->md != f.md || ', ''),
        ('KVA', 'b->kva != f.kva || ', ''),
        ('size', ' || b->size != f.size', ''),
        ('offset-alignment', '(f.offset & 7) || ', ''),
        ('sequence-order', 'f.sequence <= previous || ', '(false && f.sequence <= previous) || '),
        ('authoritative-last-sequence', ' || f.sequence > lastSeq', ''),
        ('unused-slot', 'if (f.sequence || f.md || f.kva || f.size || f.handle || f.offset) valid = false;', ''),
    ]:
        mutant('ledger-ignores-' + label, check, before, after)
    mutant('full-ledger-admitted-before-GPU-dispatch', prepare,
           '    if (cpuFenceCount < kMaxCpuFences) return kIOReturnSuccess;',
           '    if (cpuFenceCount <= kMaxCpuFences) return kIOReturnSuccess;')
    mutant('full-ledger-collection-promotes-own-last-to-global', prepare,
           '    if (!publishCpuFence(retired))', '    retired = lastSeq;\n    if (!publishCpuFence(retired))')
    mutant('full-ledger-ignores-unknown-reader', prepare, '    if (proof != kIOReturnSuccess) return proof;', '    (void)proof;')
    mutant('publication-ignores-entire-ledger-preflight', FENCE,
           '    if (!checkCpuFences() || retired == UINT64_MAX)', '    if (retired == UINT64_MAX)')
    mutant('publication-signals-pending-fences', FENCE, '        if (f.sequence > retired) break;', '')
    mutant('publication-drops-target-offset', FENCE, 'f.kva + f.offset, 8', 'f.kva, 8')
    mutant('publication-leaves-reused-slot-stale', FENCE, '        f = CpuFence{};', '        // stale slot retained')
    mutant('publication-never-clears-newest-mirrors', FENCE,
           '    if (!cpuFenceCount) pendFenceSeq = pendFenceHandle = pendFenceOffset = 0;', '')
    mutant('wait-defers-all-older-fences-until-newest-target', WAIT,
           '(retired >= target ||\n                (cpuFenceCount && cpuFences[cpuFenceHead].sequence <= retired))', 'retired >= target')
    mutant('accepted-submit-forgets-to-record-CPU-fence', submit,
           '        if (fb && !appendCpuFence(h.fence_handle, h.fence_offset, seq)) return kIOReturnNotReady;', '')
    mutant('exact-mode-silently-accepts-unsupported-CPU-fence', submit,
           '    if (exactOwnership && (h.flags & PHXN_CS_HAS_FENCE)) return kIOReturnUnsupported;', '')
    mutant('lost-real-GPU-work-enters-synthetic-CPU-success', submit,
           '    if (vmid || vmGeneration || lastSeq || cpuFenceCount) return kIOReturnNotReady;', '')
    mutant('synthetic-counter-wrap-accepted', submit,
           '    if (emitted >= UINT64_MAX - 1) return kIOReturnNoResources;', '')
    mutant('descriptor-release-ignores-pending-CPU-fences', RELEASE,
           'boCleanupFault || cpuFenceCount || ', 'boCleanupFault || ')
    mutant('post-dispatch-record-failure-does-not-quarantine', append,
           '        boCleanupFault = true; // unexpected', '        // unexpected')
    for label, code in mutations.items():
        exercise(label, code, broken=True)
    if any((ROOT / n).read_bytes() != b or (frozen / n).read_bytes() != b for n, b in inputs.items()):
        raise ValueError('Frozen input drift')
    if protected != {n: sha((ROOT / n).read_bytes()) for n in names}:
        raise ValueError('Production input drift')
    report = dict(status='passed-CPU-only-multiple-pending-user-fences', kernel_build=34,
                  prior_actual_submit_WAITSEQ_loss_reproduced=True,
                  additional_checks=int(normal[7]), tsan_additional_checks=int(tsan[7]),
                  additional_groups=int(normal[8]), additional_real_thread_scenarios=int(normal[9]),
                  inherited_derived_legacy_checks=int(normal[1]), inherited_derived_legacy_groups=int(normal[2]),
                  inherited_derived_legacy_threads=int(normal[3]),
                  inherited_exact_close_checks=int(normal[4]), inherited_exact_close_groups=int(normal[5]),
                  inherited_exact_close_threads=int(normal[6]),
                  asan_ubsan=True, tsan=True, detected_mutations=list(mutations),
                  input_sha256={n: sha(b) for n, b in inputs.items()}, staged_driver_sha256=sha(staged.encode()),
                  staged_header_sha256=sha(stage_header(inputs[HEADER].decode()).encode()),
                  original_production_file_count=len(names), production_prior_experiments_ABI_runtime_unchanged=True,
                  actual_staged_submit_WAITSEQ_BO_close_reaper_and_VM_methods_tested=True,
                  ledger_capacity=128, last_fence_fields_are_checked_newest_record_mirrors=True,
                  records_preflight_all_pending_BO_descriptor_KVA_size_ranges_and_order=True,
                  full_ledger_backpressure_precedes_GPU_dispatch=True,
                  partial_checked_global_prefix_publishes_completed_records_before_newer_target_timeout=True,
                  CPU_double_only=True, actual_page_walker_tested=False,
                  hardware_ACK_freshness_proved=False, actual_mapping_coherency_proved=False,
                  native_protocol_or_exact_CPU_fences_admitted=False, native_reader_or_mode_bound=False,
                  native_Kernel_SDK_compile=False, native_completion_event_route=False,
                  service_permanent_quarantine_removed=False, native_resource_reclaimer_accepted=False,
                  installed=False, loaded=False, GPU_executed=False, physical_FPS_measured=False,
                  long_term_stability_accepted=False, R3_goal_complete=False, R4_R6_started=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    test(parser.parse_args().out)
