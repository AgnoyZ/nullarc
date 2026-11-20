#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Test actual staged global snapshot/VM bind/submit using CPU doubles only."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_global import stage, stage_header
from build34_exact_window import stage as previous_stage
from build34_exact_submit import once
from test_build34_exact_binding import SIGNATURES
from test_build34_exact_ownership import DRIVER, ROOT, method, sha

BASE = 'tests/test_build34_exact_binding.cpp'
HEADER = 'tools/build34_exact_ownership.h'
FIXTURE = 'tests/test_build34_exact_global.cpp'
RUNNER = 'tools/test_build34_exact_global.py'
TRANSFORM = 'tools/build34_exact_global.py'
GLOBAL = 'bool PhxBringup::exactGlobalRetiredLocked('
BIND = 'uint32_t PhxBringup::vmBind('
SUBMIT = 'IOReturn PhxBringup::gpuSubmit('
READ = 'bool PhxBringup::readExactFence32('


def test(out):
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored worktree build directory ending -private')
    subprocess.run(['git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    prior = json.loads((ROOT/'docs/validation/build34-r3-window-callsites-offline-20261121.json').read_text())
    pinned = prior['input_sha256']
    inputs = {n:(ROOT/n).read_bytes() for n in sorted({*pinned, BASE, HEADER, FIXTURE, RUNNER, TRANSFORM})}
    for name, digest in pinned.items():
        if sha(inputs[name]) != digest:
            raise ValueError('Production/prior experiment input drift: '+name)
    names = subprocess.check_output(['git','ls-files','src','tools/phxctl','tools/build_kext.py'], cwd=ROOT, text=True).splitlines()
    protected = {n:sha((ROOT/n).read_bytes()) for n in names}
    original = inputs[DRIVER].decode()
    previous, staged = previous_stage(original), stage(original)
    unchanged = [*SIGNATURES, 'IOReturn IOAccelPhxNativeClient::doWaitSeq(',
        'IOReturn IOAccelPhxNativeClient::externalMethod(', 'IOReturn IOAccelPhxNativeClient::doExactReceipt(',
        'IOReturn IOAccelPhxNativeClient::doExactSubmit(', 'IOReturn IOAccelPhxNativeClient::submitExactReceipt(',
        'void PhxBringup::vmidFree(', 'void IOAccelPhxNativeClient::free(',
        'void IOAccelPhxNativeClient::freeAll(', 'void IOAccelPhxNativeClient::boRelease(',
        'IOReturn PhxBringup::vmMap(', 'IOReturn PhxBringup::vmUnmap(', READ]
    for sig in unchanged:
        if sig not in {SUBMIT, 'uint64_t PhxBringup::gpuRetired('} and method(previous,sig) != method(staged,sig):
            raise ValueError('Unrelated or permanent quarantine method drift: '+sig)
    if re.search(r'exactDwordReader\s*=|exactFenceReader\s*=|exactRequested\s*=',staged):
        raise ValueError('No native reader or mode binding is admitted')
    if '#define PHX_KEXT_BUILD 34u\n' not in staged:
        raise ValueError('Build34 only')
    out.mkdir(parents=True,mode=0o700)
    frozen, source = out/'frozen', out/'source/src/phxbringup'
    for name,blob in inputs.items():
        path=frozen/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(blob)
    source.mkdir(parents=True)
    (source/'PhxBringup.cpp').write_text(staged)
    header_path=source/Path(HEADER).name; header_path.write_text(stage_header(inputs[HEADER].decode()))
    for name in ['tools/build34_exact_fence32.h','tools/build34_exact_callbacks.h']:
        (source/Path(name).name).write_bytes(inputs[name])
    (out/'global-vmid.diff').write_text(''.join(difflib.unified_diff(previous.splitlines(True),staged.splitlines(True),
        fromfile='a/source',tofile='b/source')))
    cc=['/usr/bin/xcrun','clang++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror',
        '-Wno-unused-parameter','-Wno-unused-function','-fno-sanitize-recover=all','-fno-omit-frame-pointer',
        '-I'+str(source),'-I'+str(frozen/'src/phxbringup')]

    def run(args,label,broken=False):
        p=subprocess.run([str(x) for x in args],cwd=out,stdin=subprocess.DEVNULL,capture_output=True,timeout=90)
        (out/(label+'.stdout')).write_bytes(p.stdout); (out/(label+'.stderr')).write_bytes(p.stderr)
        if broken:
            if not p.returncode or b'failed ' not in p.stderr:
                raise ValueError(label+' did not detect intended runtime defect')
        elif p.returncode or p.stderr:
            raise RuntimeError(label+' failed; preserve private evidence')
        return p.stdout.decode()

    def exercise(label,code,broken=False,sanitizer='address,undefined'):
        base=once(inputs[BASE].decode(),'#include "build34_exact_ownership.h"\n',
            '#include "build34_exact_ownership.h"\n#include "build34_exact_fence32.h"\n')
        base=once(base,'static bool baseStart=true;\n',
            'static bool baseStart=true;\nstatic thread_local uint64_t testTicks=10000000;\n'
            'static std::atomic<unsigned> sleepCalls{0};\n')
        base=once(base,'    if(p->client) CHECK(!gpuHeld);\n',
            '    if(p->client) CHECK(!gpuHeld); else CHECK(!gpuHeld); // reject recursive gpu locking\n')
        base=once(base,'static uint64_t mach_absolute_time() { return 10000000; }',
            'static uint64_t mach_absolute_time() { event("clock"); return testTicks; }')
        base=once(base,'static void IOSleep(unsigned ms) { CHECK(ms==1 && !gpuHeld); }',
            'static void IOSleep(unsigned ms) { CHECK(ms==1 && !gpuHeld); CHECK(++sleepCalls<=2000); '
            'event("sleep"); testTicks+=1000000; }')
        base=once(base,'    ExactFenceReader exactFenceReader=nullptr;\n',
            '    ExactFenceReader exactFenceReader=nullptr;\n'
            '    FenceWindow32 exactFenceWindow[2];\n'
            '    using ExactDwordReader=bool (*)(const volatile uint32_t *,uint32_t *);\n'
            '    ExactDwordReader exactDwordReader=nullptr;\n'
            '    bool readExactFence32(uint32_t,uint64_t *);\n'
            '    bool exactGlobalRetiredLocked(uint64_t &);\n')
        # Actual field layout and actual context lookup expression, not the old vmBind stub.
        fields=original[original.index('    static constexpr uint32_t kPtChunkBytes ='):original.index('    uint64_t *ptTable(')]
        fields=once(fields,'    uint32_t vmBind(uint32_t handle);',
            '    uint32_t vmBind(uint32_t handle, uint64_t retired);')
        base=once(base,'    struct { uint64_t lastSeq=0; } hwv[8];',fields)
        base=once(base,'struct IOAccelPhxNativeClient;\n','struct IOBufferMemoryDescriptor; // opaque CPU layout pointer only\nstruct IOAccelPhxNativeClient;\n')
        base=once(base,'static constexpr uint32_t kFirstUserVmid=8;\n',
            'static constexpr uint32_t kFirstUserVmid=8,kNumUserVmids=8;\n'
            'static constexpr uint32_t kRegCtx0Cntl=0x28E8,kRegCtx0BaseLo=0x2953,kRegCtx0StartLo=0x2973,kRegCtx0EndLo=0x2993;\n')
        base=once(base,'    void *vmCtx(uint32_t h) { CHECK(gpuHeld); return h==7 ? this : nullptr; }\n'
            '    uint32_t vmBind(uint32_t h) { CHECK(gpuHeld && h==7); return 8; }\n',
            '    std::vector<std::pair<uint32_t,uint32_t>> registers;\n'
            '    unsigned tlbCalls=0;\n'
            '    void wreg(uint32_t r,uint32_t v) { CHECK(gpuHeld==1); registers.emplace_back(r,v); event("register-write"); }\n'
            '    void vmFlushTlb(uint32_t v) { CHECK(gpuHeld==1 && v>=8 && v<16); ++tlbCalls; event("tlb-double"); }\n')
        base=once(base,'    bool ensureVmid() { vmid=7; return true; }',
            '    uint32_t contextID=7;\n    bool ensureVmid() { vmid=contextID; return true; }')
        sigs=[*SIGNATURES,READ,GLOBAL,BIND]
        base=once(base,'// PHX34_BINDING_METHODS','\n'.join(method(code,sig) for sig in sigs))
        base=once(base,'int main() {\n','static void previous_binding_fixture_not_executed() {\n')
        base_path=out/'global-binding-CPU-only.h'; base_path.write_text(base)
        target,binary,dep=out/(label+'.cpp'),out/(label+'-CPU-only'),out/(label+'.d')
        target.write_bytes(inputs[FIXTURE])
        run([*cc,'-fsanitize='+sanitizer,'-MMD','-MF',dep,target,'-o',binary],label+'-compile')
        allowed={str((frozen/n).resolve()) for n in inputs}|{str(target),str(base_path),str(header_path)}
        allowed|={str(source/n) for n in ['build34_exact_callbacks.h','build34_exact_fence32.h']}
        deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
        if not deps or any(str(Path(n).resolve()) not in allowed for n in deps):
            raise ValueError('Unfrozen compilation dependency')
        linked=run(['/usr/bin/otool','-L',binary],label+'-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel',linked,re.I): raise ValueError('Device runtime linked')
        return run([binary],label+'-test',broken)

    pattern=r'PASS staged checked global and actual VMID: (\d+) checks; (\d+) groups; (\d+) threaded scenarios; GPU_executed=false\n'
    normal=re.fullmatch(pattern,exercise('global',staged))
    tsan=re.fullmatch(pattern,exercise('global-tsan',staged,sanitizer='thread'))
    if not normal or not tsan: raise ValueError('Incomplete actual-global/VMID suite')
    mutations={}

    def mutant(label,sig,before,after):
        old=method(staged,sig); mutations[label]=once(staged,old,once(old,before,after))

    mutant('exact-target-promoted-to-global',GLOBAL,
        '        if (pending && pending - 1 < retired) retired = pending - 1;',
        '        if (pending && qi == 1 && pending - 1 < retired) retired = pending - 1;')
    mutant('lost-queue-skipped',GLOBAL,'        uint64_t done;','        if (!exactQueueLive[qi]) continue;\n        uint64_t done;')
    mutant('oversized-history-accepted',GLOBAL,'        if (tail - head > 63u) return false;','')
    mutant('missing-history-accepted',GLOBAL,'            if (done != exactQueueSubmitted[qi]) return false;',
        '            if (false && done != exactQueueSubmitted[qi]) return false;')
    mutant('unordered-history-accepted',GLOBAL,'seq <= previous || ','')
    mutant('last-history-entry-unchecked',GLOBAL,'        } else if (previous != exactQueueSubmitted[qi]) return false;',
        '        } else if (false && previous != exactQueueSubmitted[qi]) return false;')
    mutant('failed-global-output-overwritten',GLOBAL,'    uint64_t retired = gSeq;',
        '    out = 0;\n    uint64_t retired = gSeq;')
    mutant('end-of-snapshot-stop-unchecked',GLOBAL,
        '    if (exactCallbacks.closed() || exactStopped || isSleeping) return false;\n    out = retired;',
        '    out = retired;')
    mutant('pending-VMID-evicted',BIND,'hwv[i].lastSeq <= retired && ', '')
    mutant('cached-reciprocal-unchecked',BIND,
        '            hwv[c.hw - kFirstUserVmid].ctx != handle','            false')
    mutant('victim-reciprocal-unchecked',BIND,
        '        if (!old || old->hw != kFirstUserVmid + static_cast<uint32_t>(pick)) return 0;',
        '        if (!old) return 0;')
    mutant('recursive-public-global-in-bind',BIND,'    VmCtx *context = vmCtx(handle);',
        '    (void)gpuRetired();\n    VmCtx *context = vmCtx(handle);')
    mutant('VMID-sleep-holds-global-lock',SUBMIT,
        '        IOLockUnlock(gpuLock);\n        IOSleep(1);',
        '        IOSleep(1);\n        IOLockUnlock(gpuLock);')
    mutant('VMID-admission-uses-target-not-global',SUBMIT,
        '            vmid = vmBind(handle, retired);','            vmid = vmBind(handle, done);')
    mutant('delayed-first-VMID-refusal-sleeps-after-expiry',SUBMIT,
        '        if (elapsed >= 2000000000ull) {\n            IOLockUnlock(gpuLock);\n            return kIOReturnBusy;\n        }\n        IOLockUnlock(gpuLock);',
        '        if (false && elapsed >= 2000000000ull) {\n            IOLockUnlock(gpuLock);\n            return kIOReturnBusy;\n        }\n        IOLockUnlock(gpuLock);')
    for label,code in mutations.items(): exercise(label,code,broken=True)
    if any((ROOT/n).read_bytes()!=b or (frozen/n).read_bytes()!=b for n,b in inputs.items()):
        raise ValueError('Frozen input drift')
    if protected != {n:sha((ROOT/n).read_bytes()) for n in names}: raise ValueError('Production input drift')
    report=dict(status='passed-CPU-only-checked-global-and-actual-VMID',kernel_build=34,
        checks=int(normal[1]),tsan_checks=int(tsan[1]),groups=int(normal[2]),real_thread_scenarios=int(normal[3]),
        asan_ubsan=True,tsan=True,detected_mutations=list(mutations),
        input_sha256={n:sha(b) for n,b in inputs.items()},staged_driver_sha256=sha(staged.encode()),
        original_production_file_count=len(names),production_prior_experiments_ABI_runtime_unchanged=True,
        actual_staged_vmBind_and_vmCtx_tested=True,actual_staged_submit_unlocked_VM_admission_tested=True,
        global_snapshot_checks_both_queues=True,global_snapshot_failure_preserves_output=True,
        CPU_IOKit_register_and_TLB_doubles_only=True,prior_fixture_functions_compiled_but_not_executed=True,
        raw_32bit_reader_native_binding=False,actual_mapping_coherency_proved=False,
        queue_ownership_or_old_writer_drain_proved=False,vmidFree_timeout_cleanup_fixed=False,
        TLB_ack_timeout_propagated=False,context_generation_or_ABA_audit_complete=False,
        healthy_resource_drain=False,permanent_quarantine_removed=False,native_mode_or_capability=False,
        native_global_prefix_visibility_wire=False,native_Kernel_SDK_compile=False,installed=False,loaded=False,
        GPU_executed=False,physical_FPS_measured=False,long_term_stability_accepted=False,
        R3_goal_complete=False,R4_R6_started=False)
    (out/'result-private.json').write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--out',required=True,type=Path)
    test(parser.parse_args().out)
