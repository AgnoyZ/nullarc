#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""CPU-only actual staged context identity, VM cleanup and TLB callsite tests."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_vm_lifetime import stage, stage_header
from build34_exact_global import stage as previous_stage
from build34_exact_submit import once
from test_build34_exact_binding import SIGNATURES
from test_build34_exact_ownership import DRIVER, ROOT, method, sha

HEADER='tools/build34_exact_ownership.h'
FIXTURE='tests/test_build34_exact_vm_lifetime.cpp'
RUNNER='tools/test_build34_exact_vm_lifetime.py'
TRANSFORM='tools/build34_exact_vm_lifetime.py'
OWNED='PhxBringup::VmCtx *PhxBringup::vmOwned('
FLUSH='bool PhxBringup::vmFlushTlbChecked('
FREE='bool PhxBringup::vmidFree('
BIND='uint32_t PhxBringup::vmBind('
MAP='IOReturn PhxBringup::vmMap('
UNMAP='IOReturn PhxBringup::vmUnmap('
SUBMIT='IOReturn PhxBringup::gpuSubmit('


def test(out):
    out=Path(out).resolve()
    if out.exists() or ROOT/'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored worktree build path ending -private')
    subprocess.run(['git','check-ignore','-q',str(out)],cwd=ROOT,check=True,timeout=15)
    prior=json.loads((ROOT/'docs/validation/build34-r3-global-vmid-offline-20261121.json').read_text())
    pinned=prior['input_sha256']
    inputs={n:(ROOT/n).read_bytes() for n in sorted({*pinned,HEADER,FIXTURE,RUNNER,TRANSFORM})}
    for n,h in pinned.items():
        if sha(inputs[n])!=h: raise ValueError('Protected/prior input drift: '+n)
    names=subprocess.check_output(['git','ls-files','src','tools/phxctl','tools/build_kext.py'],cwd=ROOT,text=True).splitlines()
    protected={n:sha((ROOT/n).read_bytes()) for n in names}
    original=inputs[DRIVER].decode(); previous,staged=previous_stage(original),stage(original)
    for sig in ['void PhxBringup::vmFlushTlb(', 'void PhxBringup::stop(',
        'void IOAccelPhxNativeClient::freeAll(', 'void IOAccelPhxNativeClient::boRelease(',
        'IOReturn IOAccelPhxNativeClient::doWaitSeq(', 'IOReturn IOAccelPhxNativeClient::doExactReceipt(',
        'IOReturn IOAccelPhxNativeClient::doExactSubmit(', 'phx34_exact::Status PhxBringup::observeExact(',
        'IOReturn PhxBringup::adoptQueue(', 'void PhxBringup::invalidateExactQueues(']:
        if method(previous,sig)!=method(staged,sig): raise ValueError('Unrelated/quarantine method drift: '+sig)
    # Client BO cleanup is deliberately not advertised as fixed. Only VM-token
    # arguments differ in its old paths; the exact quarantine remains identical.
    for sig in ['IOReturn IOAccelPhxNativeClient::clientClose(', 'void IOAccelPhxNativeClient::free(']:
        normalized=method(staged,sig).replace('vmidFree(vmid, vmGeneration, this, lastSeq)', 'vmidFree(vmid, lastSeq)')
        if normalized!=method(previous,sig): raise ValueError('Client retention/legacy teardown drift')
    if re.search(r'exactDwordReader\s*=|exactFenceReader\s*=|exactRequested\s*=',staged):
        raise ValueError('No native reader or mode binding is admitted')
    if '#define PHX_KEXT_BUILD 34u\n' not in staged: raise ValueError('Build34 only')
    if staged.count('vmFlushTlb(')!=2:
        raise ValueError('Old unchecked void TLB helper must have declaration/definition only')
    out.mkdir(parents=True,mode=0o700); frozen,source=out/'frozen',out/'source/src/phxbringup'
    for n,b in inputs.items():
        p=frozen/n; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b)
    source.mkdir(parents=True); (source/'PhxBringup.cpp').write_text(staged)
    header_path=source/Path(HEADER).name; header_path.write_text(stage_header(inputs[HEADER].decode()))
    extras=['tools/build34_exact_fence32.h','tools/build34_exact_callbacks.h']
    for n in extras: (source/Path(n).name).write_bytes(inputs[n])
    (out/'vm-lifetime.diff').write_text(''.join(difflib.unified_diff(previous.splitlines(True),staged.splitlines(True),
        fromfile='a/source',tofile='b/source')))
    cc=['/usr/bin/xcrun','clang++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror',
        '-Wno-unused-parameter','-Wno-unused-function','-fno-sanitize-recover=all','-fno-omit-frame-pointer',
        '-I'+str(source),'-I'+str(frozen/'src/phxbringup')]

    def run(args,label,broken=False):
        p=subprocess.run([str(a) for a in args],cwd=out,stdin=subprocess.DEVNULL,capture_output=True,timeout=90)
        (out/(label+'.stdout')).write_bytes(p.stdout); (out/(label+'.stderr')).write_bytes(p.stderr)
        if broken:
            if not p.returncode or b'failed ' not in p.stderr: raise ValueError(label+' did not detect intended runtime defect')
        elif p.returncode or p.stderr: raise RuntimeError(label+' failed; preserve private evidence')
        return p.stdout.decode()

    def exercise(label,code,broken=False,sanitizer='address,undefined'):
        fixture=inputs[FIXTURE].decode()
        constants=original[original.index('static constexpr uint32_t kFirstUserVmid ='):original.index('static inline void flushLine(')]
        fixture=once(fixture,'// PHX34_VM_CONSTANTS',constants)
        fields=code[code.index('    static constexpr uint32_t kPtChunkBytes ='):code.index('    uint64_t *ptTable(')]
        # The field slice ends before the existing page-walker declarations.
        fixture=once(fixture,'    // PHX34_VM_FIELDS',fields)
        ensure=re.findall(r'    bool ensureVmid\(\) \{[^\n]*\}',code)
        if len(ensure)!=1: raise ValueError('Require actual native ensureVmid body')
        fixture=once(fixture,'    // PHX34_VM_ENSURE',ensure[0])
        sigs=[*SIGNATURES,OWNED,'bool PhxBringup::vmWorkCurrent(',FLUSH,'uint32_t PhxBringup::vmidAlloc(',FREE,MAP,UNMAP,BIND,
              'bool PhxBringup::exactGlobalRetiredLocked(', 'bool PhxBringup::readExactFence32(']
        fixture=once(fixture,'// PHX34_VM_METHODS','\n'.join(method(code,sig) for sig in sigs))
        target,binary,dep=out/(label+'.cpp'),out/(label+'-CPU-only'),out/(label+'.d')
        target.write_text(fixture)
        run([*cc,'-fsanitize='+sanitizer,'-MMD','-MF',dep,target,'-o',binary],label+'-compile')
        allowed={str((frozen/n).resolve()) for n in inputs}|{str(target),str(header_path)}
        allowed|={str(source/Path(n).name) for n in extras}
        deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
        if not deps or any(str(Path(n).resolve()) not in allowed for n in deps): raise ValueError('Unfrozen dependency')
        linked=run(['/usr/bin/otool','-L',binary],label+'-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel',linked,re.I): raise ValueError('Device runtime linked')
        return run([binary],label+'-test',broken)

    pattern=r'PASS staged VM identities and checked cleanup: (\d+) checks; (\d+) groups; (\d+) threaded scenarios; GPU_executed=false\n'
    normal=re.fullmatch(pattern,exercise('vm-lifetime',staged))
    tsan=re.fullmatch(pattern,exercise('vm-lifetime-tsan',staged,sanitizer='thread'))
    if not normal or not tsan: raise ValueError('Incomplete actual VM lifecycle suite')
    mutations={}

    def mutant(label,sig,before,after):
        old=method(staged,sig); mutations[label]=once(staged,old,once(old,before,after))

    mutant('old-generation-token-accepted',OWNED,'c->generation == generation && ','')
    mutant('foreign-client-token-accepted',OWNED,'c->client == client &&','true &&')
    mutant('closing-context-mutation-accepted',OWNED,'(closing || !c->closing)', '(closing || true)')
    mutant('allocation-generation-reset-on-free',FREE,'        c.busy = false;', '        c.generation = 0;\n        c.busy = false;')
    mutant('client-lastSeq-trusted-instead-of-actual-submit',FREE,
        'const uint64_t target = c.newest > lastSeq ? c.newest : lastSeq;', 'const uint64_t target = lastSeq;')
    mutant('actual-context-newest-not-recorded',SUBMIT,
        '    vm[handle - 1].newest = seq;', '    (void)handle;')
    mutant('cleanup-after-wait-timeout',FREE,
        '            if (elapsed >= 2000000000ull) return false;\n            IOSleep(1);\n            continue;',
        '            if (elapsed < 2000000000ull) { IOSleep(1); continue; }\n            IOLockLock(gpuLock);')
    mutant('free-ignores-TLB-failure',FREE,'            if (!vmFlushTlbChecked(c.hw)) {',
        '            if (false && !vmFlushTlbChecked(c.hw)) {')
    mutant('tables-cleared-before-TLB-acceptance',FREE,
        '            // Do not clear a byte or free metadata if invalidation is uncertain.',
        '            bzero(c.chunk[0]->getBytesNoCopy(),4096);\n'
        '            // Do not clear a byte or free metadata if invalidation is uncertain.')
    mutant('binding-published-before-TLB-acceptance',BIND,'    if (!vmFlushTlbChecked(vmid)) {',
        '    h.ctx = handle; h.generation = generation; c.hw = vmid;\n    if (!vmFlushTlbChecked(vmid)) {')
    mutant('map-partial-failure-not-quarantined',MAP,
        '    if (r != kIOReturnSuccess) exactVMFault = true;', '    if (false && r != kIOReturnSuccess) exactVMFault = true;')
    mutant('map-ignores-pending-context',MAP,'    if (retired < c.newest) {','    if (false && retired < c.newest) {')
    mutant('unmap-ignores-pending-context',UNMAP,'    if (retired < c.newest) {','    if (false && retired < c.newest) {')
    mutant('wrong-ACK-bit-accepted',FLUSH,'        if (ack & (1u << vmid)) return true;', '        if (ack) return true;')
    mutant('TLB-wall-clock-budget-ignored',FLUSH,'elapsed >= 1000000ull || ', 'false || ')
    mutant('TLB-delay-after-final-attempt',FLUSH,' || attempt == 1000', '')
    mutant('TLB-post-read-stop-unchecked',FLUSH,
        '        if (exactCallbacks.closed() || exactStopped || isSleeping) return false;\n        if (ack &',
        '        if (ack &')
    for label,sig in [('map-identity-cached-before-lock',MAP),('unmap-identity-cached-before-lock',UNMAP)]:
        mutant(label,sig,
            '    IOLockLock(gpuLock);\n    VmCtx *context = vmOwned(handle, generation, client);',
            '    VmCtx *context = vmOwned(handle, generation, client);\n    IOLockLock(gpuLock);')
    mutant('cached-hardware-generation-unchecked',BIND,
        '            hwv[c.hw - kFirstUserVmid].generation != generation', '            false')
    mutant('victim-hardware-generation-unchecked',BIND,'old->generation != h.generation ||', 'false ||')
    mutant('partial-physical-page-accepted',MAP,' && segLen >= 4096','')
    mutant('old-queue-generation-treated-as-complete','bool PhxBringup::vmWorkCurrent(',
        'generation != exactQueueGeneration[qi] || ', '')
    mutant('older-other-queue-context-work-discarded',SUBMIT,
        '    vm[handle - 1].queueSequence[actualQueue] = seq;',
        '    vm[handle - 1].queueSequence[actualQueue ^ 1] = 0;\n'
        '    vm[handle - 1].queueGeneration[actualQueue ^ 1] = 0;\n'
        '    vm[handle - 1].queueSequence[actualQueue] = seq;')
    mutant('queued-allocation-output-not-rechecked','uint32_t PhxBringup::vmidAlloc(',
        '    if (*generation || exactCallbacks.closed()', '    if (exactCallbacks.closed()')
    mutant('invalid-cached-root-admitted','uint32_t PhxBringup::vmidAlloc(',
        '        if (!c.phys || (c.phys & ~kPtAddrMask) || c.chunkPhys[0] != c.phys ||\n'
        '            c.pages != kPtChunks * kPtChunkPages || !c.chunk[0]->getBytesNoCopy()) continue;', '')
    for label,code in mutations.items(): exercise(label,code,broken=True)
    if any((ROOT/n).read_bytes()!=b or (frozen/n).read_bytes()!=b for n,b in inputs.items()): raise ValueError('Frozen input drift')
    if protected!={n:sha((ROOT/n).read_bytes()) for n in names}: raise ValueError('Production input drift')
    report=dict(status='passed-CPU-only-staged-context-identity-VM-cleanup',kernel_build=34,
        checks=int(normal[1]),tsan_checks=int(tsan[1]),groups=int(normal[2]),real_thread_scenarios=int(normal[3]),
        asan_ubsan=True,tsan=True,detected_mutations=list(mutations),input_sha256={n:sha(b) for n,b in inputs.items()},
        staged_driver_sha256=sha(staged.encode()),original_production_file_count=len(names),
        production_prior_experiments_ABI_runtime_unchanged=True,actual_staged_VM_methods_tested=True,
        actual_native_ensureVmid_body_tested=True,owner_generation_rechecked_under_GPU_lock=True,
        authoritative_context_newest_recorded_by_submit=True,VM_service_timeout_does_not_clear_tables=True,
        checked_TLB_failure_propagated_and_sticky_quarantine=True,
        page_walker_allocator_IOKit_register_clock_doubles_only=True,actual_page_walker_tested=False,
        legacy_client_BO_cleanup_order_fixed=False,healthy_client_or_service_reclaimer=False,
        permanent_client_service_quarantine_removed=False,hardware_ACK_freshness_proved=False,
        actual_mapping_coherency_proved=False,queue_ownership_or_old_writer_drain_proved=False,
        native_reader_or_mode_bound=False,native_Kernel_SDK_compile=False,installed=False,loaded=False,
        GPU_executed=False,physical_FPS_measured=False,long_term_stability_accepted=False,
        R3_goal_complete=False,R4_R6_started=False)
    (out/'result-private.json').write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--out',required=True,type=Path)
    test(parser.parse_args().out)
