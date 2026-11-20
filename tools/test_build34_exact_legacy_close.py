#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise actual staged legacy close/retention/reaping with CPU-only doubles."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_legacy_close import stage, stage_header
from build34_exact_bo_lifetime import stage as previous_stage
from build34_exact_submit import once
from test_build34_exact_binding import SIGNATURES
from test_build34_exact_ownership import DRIVER, ROOT, method, sha

HEADER = 'tools/build34_exact_ownership.h'
BASE = 'tests/test_build34_exact_vm_lifetime.cpp'
OLD_BO = 'tests/test_build34_exact_bo_lifetime.cpp'
FIXTURE = 'tests/test_build34_exact_legacy_close.cpp'
RUNNER = 'tools/test_build34_exact_legacy_close.py'
TRANSFORM = 'tools/build34_exact_legacy_close.py'
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
    prior = json.loads((ROOT / 'docs/validation/build34-r3-bo-lifetime-offline-20261121.json').read_text())
    pinned = prior['input_sha256']
    paths = {*pinned, BASE, OLD_BO, 'tools/build34_exact_vm_lifetime.py', 'tools/test_build34_exact_vm_lifetime.py',
             FIXTURE, RUNNER, TRANSFORM}
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
                'IOReturn IOAccelPhxNativeClient::doExactSubmit(']:
        if method(previous, sig) != method(staged, sig):
            raise ValueError('Unrelated/quarantine method drift: ' + sig)
    if re.search(r'exactDwordReader\s*=|exactFenceReader\s*=|exactRequested\s*=', staged):
        raise ValueError('No native reader or mode binding admitted')
    if '#define PHX_KEXT_BUILD 34u\n' not in staged:
        raise ValueError('Build34 only')
    service = staged[staged.index('class PhxBringup :'):staged.index('OSDefineMetaClassAndStructors(PhxBringup')]
    for name in ['vmBoSnapshot', 'registerLegacyClient', 'requestLegacyClose', 'detachLegacyClient']:
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
    (out / 'legacy-close.diff').write_text(''.join(difflib.unified_diff(
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

    def exercise(label, code, broken=False, sanitizer='address,undefined'):
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
                    '    IOReturn vmBoSnapshot(uint32_t,uint64_t,const void *,bool,uint64_t *);\n'
                    '    bool registerLegacyClient(OSObject *); bool requestLegacyClose(IOAccelPhxNativeClient *);\n'
                    '    bool detachLegacyClient(IOAccelPhxNativeClient *);')
        # Real source Bo/Map layouts and real PHXN_MAX_BOS-sized backing arrays.
        layout = code[code.index('    struct Bo {'):code.index('    IOReturn doHello(')]
        old = base[base.index('    struct Bo {'):base.index('    PhxBringup *owner=nullptr;')]
        base = once(base, old, layout + '\n'
                    '    std::vector<Bo> boStorage=std::vector<Bo>(PHXN_MAX_BOS); Bo *bos=boStorage.data();\n'
                    '    Map mapStorage[kMaxMaps]{}; Map *maps=mapStorage;\n'
                    '    uint64_t hostUsed=0,gttUsed=0,hiUsed=0,visUsed=0;\n'
                    '    bool hello=true,boCleanupFault=false;\n'
                    '    Bo *releasePermit=nullptr; Bo releaseHeld{};\n'
                    '    uint32_t legacyState=0,legacyReaping=0; bool legacyClientPinned=false,legacyProviderPinned=false,legacyReleaseAuthorized=false;\n'
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
                    '    IOReturn submitExactReceipt(const void *,uint32_t,Ticket &,Receipt &);')
        base = once(base, '    void freeAll() { ++frees; }', '    bool freeAll();\n    // PHX34_CLOSE_DISPATCH_STUBS')
        stubs = sorted(set(re.findall(r'\br = (do\w+)\(a\)', method(code, 'IOReturn IOAccelPhxNativeClient::externalMethod('))))
        stubs = [n for n in stubs if n not in {'doBoFree', 'doGemVa', 'doSubmit'}]
        stubs += ['doTopology', 'doSurfGpuMark', 'doExactSubmit']
        stubtext = '\n'.join('    IOReturn ' + n + '(IOExternalMethodArguments *) { event("dispatch"); return kIOReturnSuccess; }' for n in stubs)
        stubtext += '\n    IOReturn doExactReceipt(uint32_t,IOExternalMethodArguments *) { return kIOReturnUnsupported; }'
        base = once(base, '    // PHX34_CLOSE_DISPATCH_STUBS', stubtext)
        reference = code[code.index('class Phx34ScopedReference {'):code.index('static phx34_exact::OwnerEpochs gExactOwners;')]
        base = once(base, 'static OwnerEpochs gExactOwners;', reference + '\nstatic OwnerEpochs gExactOwners;')
        sigs = [*SIGNATURES, 'PhxBringup::VmCtx *PhxBringup::vmOwned(', 'bool PhxBringup::vmWorkCurrent(',
                'bool PhxBringup::vmFlushTlbChecked(', 'uint32_t PhxBringup::vmidAlloc(', 'bool PhxBringup::vmidFree(',
                'IOReturn PhxBringup::vmMap(', 'IOReturn PhxBringup::vmUnmap(', 'uint32_t PhxBringup::vmBind(',
                'bool PhxBringup::exactGlobalRetiredLocked(', 'bool PhxBringup::readExactFence32(', SNAPSHOT,
                'IOAccelPhxNativeClient::Bo *IOAccelPhxNativeClient::findBo(', BOFREE, GEMVA, RELEASE, FENCE, WAIT,
                'IOReturn IOAccelPhxNativeClient::submitExactReceipt(',
                'bool PhxBringup::registerLegacyClient(', 'bool PhxBringup::requestLegacyClose(',
                'bool PhxBringup::detachLegacyClient(', 'void PhxBringup::reapLegacyClients(',
                'IOReturn IOAccelPhxNativeClient::finishLegacyClose(', 'void IOAccelPhxNativeClient::free(',
                'bool IOAccelPhxNativeClient::freeAll(', 'void PhxBringup::hangTick(',
                'IOReturn IOAccelPhxNativeClient::externalMethod(', 'IOReturn IOAccelPhxNativeClient::clientMemoryForType(']
        base = once(base, '// PHX34_VM_METHODS', method(code, 'static bool shape(') + '\n' +
                    '\n'.join(method(code, sig) for sig in sigs))
        helpers = inputs[OLD_BO].decode().split('struct Pause {', 1)[1].split('static void happyBoFree()', 1)[0]
        helpers = 'struct Pause {' + helpers
        helpers = once(helpers, '    packetWrites=frees=terminations=sleepCalls=delays=lineFlushes=0;',
                       '    packetWrites=frees=terminations=sleepCalls=delays=lineFlushes=0;\n'
                       '    baseFrees=storageFrees=lockFrees=sessionReleases=hangChecks=hangArms=0; baseStartResult=true;')
        fixture = once(inputs[FIXTURE].decode(), '// PHX34_CLOSE_BASE', base + helpers)
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

    pattern = r'PASS staged legacy close and reaping: (\d+) checks; (\d+) groups; (\d+) threaded scenarios; GPU_executed=false\n'
    normal = re.fullmatch(pattern, exercise('legacy-close', staged))
    tsan = re.fullmatch(pattern, exercise('legacy-close-tsan', staged, sanitizer='thread'))
    if not normal or not tsan:
        raise ValueError('Incomplete actual BO suite')
    mutations = {}

    def mutant(label, sig, before, after):
        old = method(staged, sig)
        mutations[label] = once(staged, old, once(old, before, after))

    register = 'bool PhxBringup::registerLegacyClient('
    finish = 'IOReturn IOAccelPhxNativeClient::finishLegacyClose('
    close = 'IOReturn IOAccelPhxNativeClient::clientClose('
    reap = 'void PhxBringup::reapLegacyClients('
    all_bos = 'bool IOAccelPhxNativeClient::freeAll('
    mutant('client-registration-pin-omitted', register,
           '    client->retain(); // established', '    // established')
    mutant('provider-registration-pin-omitted', register,
           '    retain(); // provider identity/locks', '    // provider identity/locks')
    mutant('registry-published-before-both-pins', register,
           '    client->retain(); // established', '    legacyClients[slot].client = client;\n    client->retain(); // established')
    mutant('legacy-client-admitted-without-reaper-callback', register, ' || !hangCall || hangStop', '')
    mutant('close-does-not-close-admission', close,
           '    exactClientCallbacks.close(); // both modes', '    // both modes')
    mutant('close-takes-client-lock-before-CPU-drain', finish,
           '    if (!exactClientCallbacks.drained()) return kIOReturnBusy; // no client lock while draining', '')
    mutant('reentrant-cleanup-claim-ignored', finish, '    if (!claim) return kIOReturnBusy;', '')
    mutant('BO-release-before-checked-VM-release', finish,
           '    if (vmid && !owner->vmidFree(',
           '    if (bos && bos[1].md) { releasePermit = &bos[1]; boRelease(bos[1]); }\n'
           '    if (vmid && !owner->vmidFree(')
    mutant('VM-release-failure-ignored', finish,
           '    if (vmid && !owner->vmidFree(vmid, vmGeneration, this, lastSeq)) {',
           '    if (vmid && !owner->vmidFree(vmid, vmGeneration, this, lastSeq) && false) {')
    mutant('failed-VM-release-loses-tuple', finish,
           '        return kIOReturnNotReady; // retain tuple, BOs, pools, maps, session and both pins',
           '        vmid = 0; vmGeneration = 0;\n        return kIOReturnNotReady; // lost tuple')
    mutant('healthy-client-registration-pin-never-cleared', finish,
           '    legacyClientPinned = false;', '')
    mutant('provider-released-while-another-close-can-use-owner', finish,
           '    legacyClientPinned = false;',
           '    legacyProviderPinned = false; provider->release();\n    legacyClientPinned = false;')
    mutant('final-free-leaks-provider-reference', 'void IOAccelPhxNativeClient::free(',
           '    Phx34ScopedReference providerReference(legacyProviderPinned ? owner : nullptr, false);',
           '    Phx34ScopedReference providerReference(nullptr, false);')
    mutant('final-free-retains-instead-of-adopting-provider', 'void IOAccelPhxNativeClient::free(',
           '    Phx34ScopedReference providerReference(legacyProviderPinned ? owner : nullptr, false);',
           '    Phx34ScopedReference providerReference(legacyProviderPinned ? owner : nullptr, true);')
    mutant('client-registry-slot-not-detached', 'bool PhxBringup::detachLegacyClient(',
           '    if (slot >= 0) legacyClients[slot] = LegacyClientSlot{};', '')
    mutant('reaper-uses-client-without-transient-reference', reap,
           '            slot.client->retain(); // acquire while the registration pin still exists', '')
    mutant('reaper-holds-GPU-lock-during-client-cleanup', reap,
           '        const IOReturn result = client->finishLegacyClose();',
           '        IOLockLock(gpuLock);\n        const IOReturn result = client->finishLegacyClose();\n        IOLockUnlock(gpuLock);')
    mutant('reaper-batch-count-regression', reap, 'count < 4;', 'count < 3;')
    mutant('sparse-pending-clients-not-scanned', reap, 'scanned < kMaxCtx &&', 'scanned < 4 &&')
    mutant('actual-timer-does-not-call-reaper', 'void PhxBringup::hangTick(', '    me->reapLegacyClients();', '')
    mutant('pool-accounting-not-validated', all_bos,
           '    if (totals[0] != visUsed || totals[1] != hiUsed || totals[2] != gttUsed || totals[3] != hostUsed)',
           '    if (false && (totals[0] != visUsed || totals[1] != hiUsed || totals[2] != gttUsed || totals[3] != hostUsed))')
    mutant('descriptor-release-does-not-require-exact-Bo-permit', RELEASE, '        releasePermit != &b || ', '        ')
    mutant('host-complete-failure-ignored', RELEASE,
           '    if (releaseHeld.host && md->complete() != kIOReturnSuccess) {',
           '    if (releaseHeld.host && (md->complete(), false)) {')
    mutant('failed-host-complete-loses-retained-descriptor', RELEASE,
           '        boCleanupFault = true;', '        releaseHeld = Bo{};\n        boCleanupFault = true;')
    for label, sig in [('outer-entry-skips-close-recheck', 'IOReturn IOAccelPhxNativeClient::externalMethod('),
                       ('memory-entry-skips-close-recheck', 'IOReturn IOAccelPhxNativeClient::clientMemoryForType(')]:
        mutant(label, sig, '    if (exactClientCallbacks.closed() || boCleanupFault) {',
               '    if (false && (exactClientCallbacks.closed() || boCleanupFault)) {')
    mutant('legacy-entry-admitted-during-start', 'IOReturn IOAccelPhxNativeClient::externalMethod(',
           '(!(exactRequested || exactOwnership) &&\n        __atomic_load_n(&legacyState, __ATOMIC_ACQUIRE) != 2)',
           'false')
    mutant('legacy-entry-admitted-after-service-stop', 'IOReturn IOAccelPhxNativeClient::externalMethod(',
           ' || owner->exactAdmissionClosed()', '')
    # Every variant must compile then fail an assertion; timeouts and compile
    # failures do not count as detected runtime defects.
    for label, code in mutations.items():
        exercise(label, code, broken=True)
    if any((ROOT / n).read_bytes() != b or (frozen / n).read_bytes() != b for n, b in inputs.items()):
        raise ValueError('Frozen input drift')
    if protected != {n: sha((ROOT / n).read_bytes()) for n in names}:
        raise ValueError('Production input drift')
    report = dict(status='passed-CPU-only-staged-legacy-close-and-reaping', kernel_build=34,
                  checks=int(normal[1]), tsan_checks=int(tsan[1]), groups=int(normal[2]),
                  real_thread_scenarios=int(normal[3]), asan_ubsan=True, tsan=True,
                  detected_mutations=list(mutations), input_sha256={n: sha(b) for n, b in inputs.items()},
                  staged_driver_sha256=sha(staged.encode()), original_production_file_count=len(names),
                  production_prior_experiments_ABI_runtime_unchanged=True,
                  actual_staged_close_registration_reaper_outer_entries_BO_VM_and_descriptor_methods_tested=True,
                  late_CPU_fence_handle_reuse_counterexample_guarded=True,
                  uncertain_host_completion_retains_exact_descriptor=True,
                  CPU_double_only=True, actual_page_walker_tested=False, hardware_ACK_freshness_proved=False,
                  actual_mapping_coherency_proved=False, legacy_client_close_order_fixed_in_CPU_stage=True,
                  bounded_legacy_reaper_wired_to_actual_hangTick=True,
                  native_healthy_client_or_service_reclaimer_accepted=False,
                  permanent_exact_client_service_quarantine_removed=False,
                  native_reader_or_mode_bound=False, native_Kernel_SDK_compile=False,
                  installed=False, loaded=False, GPU_executed=False, physical_FPS_measured=False,
                  long_term_stability_accepted=False, R3_goal_complete=False, R4_R6_started=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    test(parser.parse_args().out)
