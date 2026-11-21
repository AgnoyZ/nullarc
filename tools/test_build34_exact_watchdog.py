#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise actual checked watchdog recovery with frozen CPU-only doubles."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_watchdog import stage, stage_header
from build34_exact_cpu_fences import stage as previous_stage
from build34_exact_submit import once
from test_build34_exact_binding import SIGNATURES
from test_build34_exact_ownership import DRIVER, ROOT, method, sha

HEADER = 'tools/build34_exact_ownership.h'
BASE = 'tests/test_build34_exact_vm_lifetime.cpp'
OLD_BO = 'tests/test_build34_exact_bo_lifetime.cpp'
LEGACY = 'tests/test_build34_exact_legacy_close.cpp'
EXACT = 'tests/test_build34_exact_close.cpp'
CPU_FENCES = 'tests/test_build34_exact_cpu_fences.cpp'
FIXTURE = 'tests/test_build34_exact_watchdog.cpp'
RUNNER = 'tools/test_build34_exact_watchdog.py'
TRANSFORM = 'tools/build34_exact_watchdog.py'
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
    prior = json.loads((ROOT / 'docs/validation/build34-r3-cpu-fences-offline-20261121.json').read_text())
    pinned = prior['input_sha256']
    paths = {*pinned, BASE, OLD_BO, 'tools/build34_exact_vm_lifetime.py', 'tools/test_build34_exact_vm_lifetime.py',
             FIXTURE, RUNNER, TRANSFORM, CPU_FENCES, LEGACY, EXACT, 'tools/build34_exact_legacy_close.py',
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
                'bool PhxBringup::vmidFree(',
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
    (out / 'watchdog.diff').write_text(''.join(difflib.unified_diff(
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
                    'static constexpr unsigned kMillisecondScale=1;\n'
                    'static int gHangMs=0; static std::atomic<int> gHangKills{0};\n'
                    'static void OSIncrementAtomic(std::atomic<int> *p) { ++*p; }\n'
                    'static void nanoseconds_to_absolutetime(uint64_t n,uint64_t *p) { *p=n; }\n'
                    'static constexpr uint32_t kRegSqCmd=0x1260+0x111b,kRegRlcSafeMode=0xa000+0x0980;')
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
        # Compile the actual native queue layout, rather than silently omitting
        # its new context-allocation tags in an all-public CPU double.
        actual_queue = code[code.index('    struct GpuQueue {'):code.index('    uint64_t gSeq{0};')]
        old_queue = base[base.index('    struct GpuQueue {'):base.index('    Memory aperture,bells;')]
        base = once(base, old_queue, actual_queue)
        base = once(base, '    PhxBringup() {', '    PhxBringup() {\n'
                    '        for(auto &q:gq) { q.ready=true; q.ringDw=1024; q.wbOff=8192; q.fenceOff=9000; q.wptr=q.doneEnd=8; q.lastDone=99; }\n'
                    '        mmioStorage.length=1u<<20;')
        base = once(base, 'Memory aperture,bells; Memory *fbAper=&aperture,*doorbellMap=&bells,*mmio=&aperture;',
                    'Memory aperture,bells,mmioStorage; Memory *fbAper=&aperture,*doorbellMap=&bells,*mmio=&mmioStorage;')
        base = once(base, 'struct Memory { alignas(16) uint64_t words[2048]{};',
                    'struct Memory { alignas(16) uint64_t words[2048]{}; uint64_t length=sizeof words; uintptr_t addressOverride=0;')
        base = once(base, 'uintptr_t getVirtualAddress() const { return reinterpret_cast<uintptr_t>(words); }',
                    'uintptr_t getVirtualAddress() const { event("map-address"); return addressOverride ? addressOverride : reinterpret_cast<uintptr_t>(words); }')
        base = once(base, 'uint64_t getLength() const { return sizeof words; }',
                    'uint64_t getLength() const { event("map-length"); return length; }')
        base = once(base, '    void wreg(uint32_t r,uint32_t v) { CHECK(gpuHeld==1); registers.emplace_back(r,v); event("register-write"); }',
                    '    unsigned rlcReads=0,rlcAfter=0,rlcEnters=0,rlcExits=0; bool rlcEntered=false;\n'
                    '    void wreg(uint32_t r,uint32_t v) { CHECK(gpuHeld==1); registers.emplace_back(r,v); event("register-write");\n'
                    '        if(r==kRegRlcSafeMode && v==3) { CHECK(!rlcEntered); rlcEntered=true; ++rlcEnters; event("rlc-enter"); }\n'
                    '        if(r==kRegRlcSafeMode && v==1) { CHECK(rlcEntered); rlcEntered=false; ++rlcExits; event("rlc-exit"); }\n'
                    '        if(r==kRegSqCmd) { CHECK(rlcEntered); event("sq-write"); } }')
        base = once(base, '    uint32_t rreg(uint32_t r) { CHECK(gpuHeld==1 && r==kRegInvEng17Ack); ++ackReads; event("ack-read"); return ackReads>ackAfter ? ackBits : 0; }',
                    '    uint32_t rreg(uint32_t r) { CHECK(gpuHeld==1);\n'
                    '        if(r==kRegInvEng17Ack) { ++ackReads; event("ack-read"); return ackReads>ackAfter ? ackBits : 0; }\n'
                    '        CHECK(r==kRegRlcSafeMode && rlcEntered); ++rlcReads; event("rlc-ack"); return rlcReads>rlcAfter ? 0 : 1; }')
        fields = code[code.index('    static constexpr uint32_t kPtChunkBytes ='):code.index('    uint64_t *ptTable(')]
        base = once(base, '    // PHX34_VM_FIELDS', fields)
        base = once(base, '    bool debugEnabled() const { return false; }',
                    '    bool debugEnabled() const { return false; }\n'
                    '    bool exactAdmissionClosed() const { return exactCallbacks.closed() || exactStopped; }\n'
                    '    bool hangStop=false; void *hangCall=this;\n'
                    '    static void hangTick(thread_call_param_t,thread_call_param_t);\n'
                    '    void hangCheck(); void killWaves(uint32_t,bool);')
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
        cpu_fields = code[code.index('    static constexpr uint32_t kMaxCpuFences ='):code.index('    bool publishCpuFence(')]
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
        sigs += ['void PhxBringup::hangCheck(']
        if baseline:
            sigs += ['void PhxBringup::killWaves(']
        else:
            sigs += ['bool PhxBringup::watchdogQueueLocked(', 'bool PhxBringup::captureWatchdogLocked(',
                     'bool PhxBringup::watchdogRecoveryCurrentLocked(', 'bool PhxBringup::readWatchdogRecoveryLocked(',
                     'bool PhxBringup::killWavesLocked(']
        base = once(base, '// PHX34_VM_METHODS', method(code, 'static bool shape(') + '\n' +
                    '\n'.join(method(code, sig) for sig in sigs))
        helpers = inputs[OLD_BO].decode().split('struct Pause {', 1)[1].split('static void happyBoFree()', 1)[0]
        helpers = 'struct Pause {' + helpers
        helpers = once(helpers, '    packetWrites=frees=terminations=sleepCalls=delays=lineFlushes=0;',
                       '    packetWrites=frees=terminations=sleepCalls=delays=lineFlushes=0;\n'
                       '    baseFrees=storageFrees=lockFrees=sessionReleases=hangChecks=hangArms=0; baseStartResult=true; gHangMs=0; gHangKills=0;')
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
        legacy = once(legacy, ' && hangChecks==2', '') # prior stub counter only, not native instrumentation
        fixture = once(legacy, '// PHX34_CLOSE_BASE', base + helpers)
        fixture += '\n' + once(inputs[EXACT].decode(), 'int main() {', 'static void exact_close_regressions() {')
        fixture += '\n' + once(inputs[CPU_FENCES].decode(), 'int main() {', 'static void cpu_fence_regressions() {')
        fixture += '\n' + inputs[FIXTURE].decode()
        # Keep large CPU service doubles in their scenario's own stack frame.
        # Only zero-argument static fixture functions are affected; actual native
        # methods retain the compiler's ordinary O1 inlining and source bodies.
        fixture = re.sub(r'^static void (\w+)\(\) \{',
                         r'static __attribute__((noinline)) void \1() {', fixture, flags=re.M)
        if baseline:
            fixture = base + helpers + r'''
int main() {
    reset(); CHECK(!threaded); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); const auto sequence=accepted(c);
    gHangMs=1; d.rlcAfter=UINT32_MAX; d.gq[1].lastDone=99; d.gq[1].lastProgress=testTicks-2000000;
    unsigned unlocked=0;
    eventHook=[&](const char *e) { if(!std::strcmp(e,"map-address") && !gpuHeld) ++unlocked; };
    d.hangCheck(); eventHook={};
    CHECK(unlocked && gHangKills==1 && d.rlcReads==1000 && d.rlcEnters==1 && d.rlcExits==1);
    CHECK(d.gq[1].killedSeq==sequence && !d.exactVMFault);
    std::puts("REPRODUCED previous actual watchdog reading unlocked and issuing SQ after RLC timeout; GPU_executed=false");
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

    baseline = exercise('previous-watchdog-counterexample', previous, baseline=True)
    if baseline != 'REPRODUCED previous actual watchdog reading unlocked and issuing SQ after RLC timeout; GPU_executed=false\n':
        raise ValueError('Prior actual-method watchdog counterexample did not reproduce')
    pattern = (r'PASS staged legacy close and reaping: (\d+) checks; (\d+) groups; (\d+) threaded scenarios; GPU_executed=false\n'
               r'PASS staged exact close and reaping: (\d+) additional checks; (\d+) groups; (\d+) threaded scenarios; GPU_executed=false\n'
               r'PASS staged multiple CPU fences: (\d+) additional checks; (\d+) groups; (\d+) threaded scenarios; GPU_executed=false\n'
               r'PASS staged checked watchdog: (\d+) additional checks; (\d+) groups; (\d+) threaded scenarios; GPU_executed=false\n')
    normal = re.fullmatch(pattern, exercise('watchdog', staged))
    tsan = re.fullmatch(pattern, exercise('watchdog-tsan', staged, sanitizer='thread'))
    if not normal or not tsan:
        raise ValueError('Incomplete watchdog and inherited regression suites')
    mutations = {}

    def mutant(label, sig, before, after):
        old = method(staged, sig)
        mutations[label] = once(staged, old, once(old, before, after))

    # Runtime mutations are inserted after the positive CPU suites are complete.
    queue = 'bool PhxBringup::watchdogQueueLocked('
    current = 'bool PhxBringup::watchdogRecoveryCurrentLocked('
    kill = 'bool PhxBringup::killWavesLocked('
    hang = 'void PhxBringup::hangCheck('
    capture = 'bool PhxBringup::captureWatchdogLocked('
    for label, before in [
        ('allocation-tag', 'q.fallocation[slot] != c.generation || '),
        ('reciprocal-hardware-context', 'v.ctx != h || '),
        ('reciprocal-hardware-generation', 'v.generation != c.generation || '),
        ('hardware-last-sequence', 'v.lastSeq != c.newest || '),
        ('client-identity', '!c.client || '),
    ]:
        mutant('pending-history-ignores-' + label, queue, before, '')
    for label, before in [
        ('epoch', 'exactInvalidationEpoch != w.epoch || '),
        ('post-recovery-generation', 'exactQueueGeneration[i] != w.postGeneration[i] ||\n            '),
        ('ordinary-live-state', 'exactQueueLive[i] || '),
        ('reader-identity', 'exactDwordReader != w.reader ||\n        '),
        ('mapping-identity', 'fbAper != w.mapping || '),
        ('register-mapping-length', 'mmio->getLength() != w.registerLength ||\n        '),
        ('target-slot-sequence', 'q.fseq[w.slot] != w.sequence || '),
        ('context-owner', 'c.client != w.client || '),
        ('context-generation', 'c.generation != w.allocation || '),
    ]:
        mutant('recovery-ignores-' + label, current, before, '')
    mutant('adoption-erases-faulted-history', 'IOReturn PhxBringup::adoptQueue(',
           'exactStopped || isSleeping || exactVMFault', 'exactStopped || isSleeping')
    mutant('submit-omits-allocation-tag', 'IOReturn PhxBringup::gpuSubmit(',
           '    q.fallocation[q.tail & 63] = generation;\n', '')
    mutant('submit-counts-old-idle-time-against-new-work', 'IOReturn PhxBringup::gpuSubmit(',
           '    if (startsPending) q.lastProgress = mach_absolute_time();', '    (void)startsPending;')
    mutant('submit-starts-new-pending-clock-before-doorbell', 'IOReturn PhxBringup::gpuSubmit(',
           '                    q.lastDone = done; startsPending = true;',
           '                    q.lastDone = done; q.lastProgress = mach_absolute_time(); startsPending = false;')
    mutant('diagnostic-reader-ignores-post-read-close-or-identity-loss', 'bool PhxBringup::readWatchdogRecoveryLocked(',
           ' ||\n        !watchdogRecoveryCurrentLocked()) return false; // close', ') return false; // close')
    mutant('recovery-does-not-close-VM-dispatch', capture,
           '    exactVMFault = true;', '    // exactVMFault deliberately not set;')
    mutant('recovery-does-not-invalidate-ordinary-queues', capture,
           '    invalidateExactQueues();', '')
    mutant('RLC-timeout-still-issues-SQ', kill, 'const bool ready = !(rreg(kRegRlcSafeMode) & 1);',
           'const bool ready = (rreg(kRegRlcSafeMode), true);')
    old = method(staged, kill)
    mutations['RLC-ignores-actual-elapsed-time'] = once(staged, old,
        old.replace('elapsed >= 1000000ull', '(false && elapsed >= 1000000ull)'))
    mutant('RLC-exceeds-fixed-read-bound', kill, 'attempt < 1000', 'attempt < 1001')
    mutant('RLC-forgets-paired-exit', kill, '    wreg(kRegRlcSafeMode, 0x1);', '')
    mutant('RLC-failure-retries-indefinitely', kill,
           'if (!issued || !watchdogRecoveryCurrentLocked()) w.terminal = true;', '(void)issued;')
    mutant('global-kill-after-half-threshold', hang, 'elapsed < w.limitNs || ', 'elapsed < w.limitNs / 2 || ')
    mutant('diagnostic-completion-promotes-health', hang,
           '                w.terminal = true;\n                return; // completion stops escalation',
           '                exactVMFault = false; w.terminal = true;\n                return; // completion stops escalation')
    mutant('global-kill-repeats-after-terminal-episode', hang, '            if (w.terminal) return;',
           '            w.terminal = false; w.globalAttempted = false;')
    mutant('disabling-watchdog-leaves-old-escalation-armed', hang,
           '            if (w.active) w.terminal = true;\n            return;\n        }\n        if (w.active)',
           '            return;\n        }\n        if (w.active)')
    mutant('RLC-sends-SQ-even-after-target-completed-at-ACK', kill,
           '            if (!readWatchdogRecoveryLocked(&done) || done >= w.sequence) break;', '')
    for label, code in mutations.items():
        exercise(label, code, broken=True)
    if any((ROOT / n).read_bytes() != b or (frozen / n).read_bytes() != b for n, b in inputs.items()):
        raise ValueError('Frozen input drift')
    if protected != {n: sha((ROOT / n).read_bytes()) for n in names}:
        raise ValueError('Production input drift')
    report = dict(status='passed-CPU-only-checked-watchdog-recovery', kernel_build=34,
                  prior_actual_unlocked_read_and_RLC_timeout_command_reproduced=True,
                  additional_checks=int(normal[10]), tsan_additional_checks=int(tsan[10]),
                  additional_groups=int(normal[11]), additional_real_thread_scenarios=int(normal[12]),
                  inherited_derived_legacy_checks=int(normal[1]), inherited_derived_legacy_groups=int(normal[2]),
                  inherited_derived_legacy_threads=int(normal[3]),
                  inherited_exact_close_checks=int(normal[4]), inherited_exact_close_groups=int(normal[5]),
                  inherited_exact_close_threads=int(normal[6]),
                  inherited_CPU_fence_checks=int(normal[7]), inherited_CPU_fence_groups=int(normal[8]),
                  inherited_CPU_fence_threads=int(normal[9]),
                  asan_ubsan=True, tsan=True, detected_mutations=list(mutations),
                  input_sha256={n: sha(b) for n, b in inputs.items()}, staged_driver_sha256=sha(staged.encode()),
                  staged_header_sha256=sha(stage_header(inputs[HEADER].decode()).encode()),
                  original_production_file_count=len(names), production_prior_experiments_ABI_runtime_unchanged=True,
                  actual_staged_watchdog_submit_wait_close_reaper_VM_methods_tested=True,
                  same_lock_selection_and_recovery=True, context_allocation_tags_precede_tail_publication=True,
                  new_pending_watchdog_clock_starts_after_doorbell=True,
                  sticky_fault_and_queue_invalidation_precede_recovery_MMIO=True,
                  RLC_ACK_required_with_monotonic_1ms_and_1000_reads_bounds=True,
                  paired_safe_mode_exit_on_observed_close_or_timeout=True,
                  at_most_one_targeted_then_one_global_attempt=True,
                  global_escalation_requires_second_full_threshold_and_current_pending_target=True,
                  diagnostic_old_generation_completion_never_retires_resources=True,
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
