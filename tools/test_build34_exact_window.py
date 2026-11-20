#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise actual staged raw-dword/window callsites using CPU bytes only."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_submit import once
from build34_exact_submit_receipt import stage as previous_stage
from build34_exact_window import stage, stage_header
from test_build34_exact_binding import SIGNATURES as BINDING
from test_build34_exact_ownership import DRIVER, ROOT, method, sha

BASE = 'tests/test_build34_exact_binding.cpp'
HEADER = 'tools/build34_exact_ownership.h'
WINDOW = 'tools/build34_exact_fence32.h'
FIXTURE = 'tests/test_build34_exact_window.cpp'
RUNNER = 'tools/test_build34_exact_window.py'
TRANSFORM = 'tools/build34_exact_window.py'
READER = 'bool PhxBringup::readExactFence32('


def test(out):
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored worktree build directory ending -private')
    subprocess.run(['git','check-ignore','-q',str(out)],cwd=ROOT,check=True,timeout=15)
    prior = json.loads((ROOT/'docs/validation/build34-r3-submit-receipt-offline-20261121.json').read_text())
    pinned = prior['input_sha256']
    paths = {*pinned, BASE, HEADER, WINDOW, FIXTURE, RUNNER, TRANSFORM}
    inputs = {n:(ROOT/n).read_bytes() for n in sorted(paths)}
    for n,h in pinned.items():
        if sha(inputs[n]) != h: raise ValueError('Protected/prior input drift: '+n)
    names = subprocess.check_output(['git','ls-files','src','tools/phxctl','tools/build_kext.py'],cwd=ROOT,text=True).splitlines()
    protected = {n:sha((ROOT/n).read_bytes()) for n in names}
    original = inputs[DRIVER].decode()
    previous,staged = previous_stage(original),stage(original)
    header = stage_header(inputs[HEADER].decode())
    allowed_changes = {'IOReturn PhxBringup::gpuSubmit(','IOReturn PhxBringup::adoptQueue(',
                       'void PhxBringup::invalidateExactQueues(','phx34_exact::Status PhxBringup::observeExact('}
    unchanged = [*BINDING,'IOReturn IOAccelPhxNativeClient::doWaitSeq(',
        'IOReturn IOAccelPhxNativeClient::externalMethod(','IOReturn IOAccelPhxNativeClient::doExactReceipt(',
        'IOReturn IOAccelPhxNativeClient::doExactSubmit(','IOReturn IOAccelPhxNativeClient::submitExactReceipt(',
        'void PhxBringup::vmidFree(','void IOAccelPhxNativeClient::free(',
        'void IOAccelPhxNativeClient::freeAll(','void IOAccelPhxNativeClient::boRelease(']
    for sig in unchanged:
        if sig not in allowed_changes and method(previous,sig)!=method(staged,sig):
            raise ValueError('Unrelated method/legacy/quarantine changed: '+sig)
    if re.search(r'exactDwordReader\s*=|exactFenceReader\s*=|exactRequested\s*=',staged):
        raise ValueError('No native reader/mode may be bound')
    if '#define PHX_KEXT_BUILD 34u\n' not in staged:
        raise ValueError('Build34 only')
    out.mkdir(parents=True,mode=0o700)
    frozen,source = out/'frozen',out/'source/src/phxbringup'
    for n,b in inputs.items():
        p=frozen/n; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b)
    source.mkdir(parents=True)
    (source/'PhxBringup.cpp').write_text(staged)
    header_path=source/Path(HEADER).name; header_path.write_text(header)
    for n in [WINDOW,'tools/build34_exact_callbacks.h']:
        (source/Path(n).name).write_bytes(inputs[n])
    (out/'window-callsite.diff').write_text(''.join(difflib.unified_diff(
        previous.splitlines(True),staged.splitlines(True),fromfile='a/source',tofile='b/source')))
    cc=['/usr/bin/xcrun','clang++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror',
        '-Wno-unused-parameter','-Wno-unused-function','-fno-sanitize-recover=all','-fno-omit-frame-pointer',
        '-I'+str(source),'-I'+str(frozen/'src/phxbringup')]

    def run(args,label,broken=False):
        p=subprocess.run([str(a) for a in args],cwd=out,stdin=subprocess.DEVNULL,capture_output=True,timeout=90)
        (out/(label+'.stdout')).write_bytes(p.stdout); (out/(label+'.stderr')).write_bytes(p.stderr)
        if broken:
            if not p.returncode or b'failed ' not in p.stderr:
                raise ValueError(label+' did not detect intended runtime defect')
        elif p.returncode or p.stderr: raise RuntimeError(label+' failed; preserve private evidence')
        return p.stdout.decode()

    def exercise(label,code,broken=False,sanitizer='address,undefined'):
        base=once(inputs[BASE].decode(),'#include "build34_exact_ownership.h"\n',
                  '#include "build34_exact_ownership.h"\n#include "build34_exact_fence32.h"\n')
        base=once(base,'static bool baseStart=true;\n',
                  'static bool baseStart=true;\nstatic std::atomic<unsigned> vmBinds{0},sleepCalls{0};\n'
                  'static thread_local uint64_t testTicks=10000000;\n')
        base=once(base,'static uint64_t mach_absolute_time() { return 10000000; }',
                  'static uint64_t mach_absolute_time() { return testTicks; }')
        base=once(base,'static void IOSleep(unsigned ms) { CHECK(ms==1 && !gpuHeld); }',
                  'static void IOSleep(unsigned ms) { CHECK(ms==1 && !gpuHeld); CHECK(++sleepCalls<=2001); testTicks+=1000000; }')
        base=once(base,'struct Memory {\n',
                  'struct Memory {\n    bool overrideBase=false,overrideLength=false;\n'
                  '    uintptr_t customBase=0; uint64_t customLength=0;\n')
        base=once(base,'return reinterpret_cast<uintptr_t>(words);','return overrideBase ? customBase : reinterpret_cast<uintptr_t>(words);')
        base=once(base,'return sizeof words;','return overrideLength ? customLength : sizeof words;')
        base=once(base,'    ExactFenceReader exactFenceReader=nullptr;\n',
                  '    ExactFenceReader exactFenceReader=nullptr;\n'
                  '    FenceWindow32 exactFenceWindow[2];\n'
                  '    using ExactDwordReader=bool (*)(const volatile uint32_t *,uint32_t *);\n'
                  '    ExactDwordReader exactDwordReader=nullptr;\n'
                  '    bool readExactFence32(uint32_t,uint64_t *);\n')
        base=once(base,'uint32_t vmBind(uint32_t h) { CHECK(gpuHeld && h==7); return 8; }',
                  'uint32_t vmBind(uint32_t h) { CHECK(gpuHeld && h==7); ++vmBinds; return 8; }')
        base=once(base,'// PHX34_BINDING_METHODS','\n'.join(method(code,sig) for sig in BINDING))
        base=once(base,'int main() {\n','static void previous_binding_fixture_not_executed() {\n')
        base_path=out/'window-binding-CPU-only.h'; base_path.write_text(base)
        target,binary,dep=out/(label+'.cpp'),out/(label+'-CPU-only'),out/(label+'.d')
        target.write_text(once(inputs[FIXTURE].decode(),'// PHX34_WINDOW_METHODS',method(code,READER)))
        run([*cc,'-fsanitize='+sanitizer,'-MMD','-MF',dep,target,'-o',binary],label+'-compile')
        allowed={str((frozen/n).resolve()) for n in inputs}|{str(target),str(base_path),str(header_path)}
        allowed|={str(source/Path(n).name) for n in [WINDOW,'tools/build34_exact_callbacks.h']}
        deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
        if not deps or any(str(Path(n).resolve()) not in allowed for n in deps):
            raise ValueError('Unfrozen compilation dependency')
        linked=run(['/usr/bin/otool','-L',binary],label+'-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel',linked,re.I): raise ValueError('Device runtime linked')
        return run([binary],label+'-test',broken)

    pattern=r'PASS staged exact dword window: (\d+) checks; (\d+) groups; 4 threaded scenarios; actual shared-queue callsites; GPU_executed=false\n'
    normal=re.fullmatch(pattern,exercise('window',staged))
    tsan=re.fullmatch(pattern,exercise('window-tsan',staged,sanitizer='thread'))
    if not normal or not tsan: raise ValueError('Incomplete actual dword-window suite')
    mutations={}

    def mutant(label,sig,before,after):
        old=method(staged,sig); mutations[label]=once(staged,old,once(old,before,after))

    submit='IOReturn PhxBringup::gpuSubmit('
    mutant('legacy-submissions-not-counted',submit,
           'if (!exactFenceWindow[actualQueue].submit(', 'if (exact && !exactFenceWindow[actualQueue].submit(')
    mutant('can-submit-guard-skipped',submit,
           'if (!exactFenceWindow[actualQueue].canSubmit(exactQueueGeneration[actualQueue], gSeq + 1)) {',
           'if (false && !exactFenceWindow[actualQueue].canSubmit(exactQueueGeneration[actualQueue], gSeq + 1)) {')
    mutant('legacy-sequence-exhaustion-unchecked',submit,
           'if (gSeq >= UINT64_MAX - 1) { // every', 'if (exact && gSeq >= UINT64_MAX - 1) { // every')
    mutant('legacy-64bit-completion-used-for-ring-space',submit,
           '        uint64_t done;\n'
           '        if (!readExactFence32(qp == &gq[1] ? 1u : 0u, &done)) {\n'
           '            IOLockUnlock(gpuLock);\n            return kIOReturnNotReady;\n        }\n',
           '        const uint64_t done = queueFence(q);\n')
    mutant('window-not-invalidated','void PhxBringup::invalidateExactQueues(',
           '        exactFenceWindow[i].invalidate();\n','')
    mutant('seed-before-old-window-invalidation','IOReturn PhxBringup::adoptQueue(',
           '    exactFenceWindow[qi].invalidate();\n','')
    for label,before,after in [
        ('wrong-queue-decoded','exactFenceWindow[qi].observe(exactQueueGeneration[qi], raw, value)',
         'exactFenceWindow[qi ^ 1].observe(exactQueueGeneration[qi ^ 1], raw, value)'),
        ('raw-dword-used-as-full-sequence','if (!exactFenceWindow[qi].observe(exactQueueGeneration[qi], raw, value)) return false;',
         'value=raw;'),
        ('reader-error-ignored','if (!exactDwordReader(reinterpret_cast<const volatile uint32_t *>(base + offset), &raw) ||',
         'if ((exactDwordReader(reinterpret_cast<const volatile uint32_t *>(base + offset), &raw) && false) ||'),
        ('closure-after-read-unchecked','        exactCallbacks.closed()) return false;','        false) return false;'),
        ('mapping-length-unchecked','offset > length || length - offset < 4 ||','((void)length, false) ||'),
        ('logical-aperture-length-unchecked','offset > fbAperLen || fbAperLen - offset < 4 ||','false ||'),
        ('failed-output-overwritten','    uint32_t raw = 0;','    *completed = 0;\n    uint32_t raw = 0;'),
    ]: mutant(label,READER,before,after)
    for label,code in mutations.items(): exercise(label,code,broken=True)
    if any((ROOT/n).read_bytes()!=b or (frozen/n).read_bytes()!=b for n,b in inputs.items()):
        raise ValueError('Frozen input drift')
    if protected!={n:sha((ROOT/n).read_bytes()) for n in names}: raise ValueError('Production input drift')
    report=dict(status='passed-CPU-only-staged-shared-queue-dword-window',kernel_build=34,
        checks=int(normal[1]),tsan_checks=int(tsan[1]),groups=int(normal[2]),real_thread_scenarios=4,
        asan_ubsan=True,tsan=True,detected_mutations=list(mutations),
        input_sha256={n:sha(b) for n,b in inputs.items()},staged_driver_sha256=sha(staged.encode()),
        original_production_file_count=len(names),production_prior_experiments_ABI_runtime_unchanged=True,
        all_shared_queue_submissions_checked=True,decoder_seeded_before_queue_ready=True,
        submission_scope='All calls through the actual staged gpuSubmit, including exact and legacy clients; no assertion about external GPU/firmware writers.',
        ring_history_uses_bounded_dword=True,publication_refusal_preserves_decoder_upper_bound=True,
        R1b_timeout_uses_CPU_monotonic_clock=True,actual_native_vmBind_tested=False,
        raw_32bit_reader_native_binding=False,legacy_64bit_reader_used_for_exact_observation=False,
        old_global_retirement_or_release_paths_proved_safe=False,actual_mapping_coherency_proved=False,
        queue_ownership_or_old_writer_drain_proved=False,healthy_resource_drain=False,native_mode_or_capability=False,
        native_Kernel_SDK_compile=False,installed=False,loaded=False,GPU_executed=False,
        physical_FPS_measured=False,long_term_stability_accepted=False,R3_goal_complete=False,R4_R6_started=False)
    (out/'result-private.json').write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--out',required=True,type=Path)
    test(parser.parse_args().out)
