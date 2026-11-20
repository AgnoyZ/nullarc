#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise actual staged BO handlers with frozen CPU-only VM/IOKit doubles."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_bo_lifetime import stage, stage_header
from build34_exact_vm_lifetime import stage as previous_stage
from build34_exact_submit import once
from test_build34_exact_binding import SIGNATURES
from test_build34_exact_ownership import DRIVER, ROOT, method, sha

HEADER = 'tools/build34_exact_ownership.h'
BASE = 'tests/test_build34_exact_vm_lifetime.cpp'
FIXTURE = 'tests/test_build34_exact_bo_lifetime.cpp'
RUNNER = 'tools/test_build34_exact_bo_lifetime.py'
TRANSFORM = 'tools/build34_exact_bo_lifetime.py'
SNAPSHOT = 'IOReturn PhxBringup::vmBoSnapshot('
BOFREE = 'IOReturn IOAccelPhxNativeClient::doBoFree('
GEMVA = 'IOReturn IOAccelPhxNativeClient::doGemVa('
RELEASE = 'void IOAccelPhxNativeClient::boRelease('
FENCE = 'bool IOAccelPhxNativeClient::publishCpuFence('
WAIT = 'IOReturn IOAccelPhxNativeClient::doWaitSeq('


def test(out):
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored worktree build path ending -private')
    subprocess.run(['git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    prior = json.loads((ROOT / 'docs/validation/build34-r3-vm-lifetime-offline-20261121.json').read_text())
    pinned = prior['input_sha256']
    paths = {*pinned, BASE, 'tools/build34_exact_vm_lifetime.py', 'tools/test_build34_exact_vm_lifetime.py',
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
    for sig in ['void PhxBringup::stop(', 'IOReturn IOAccelPhxNativeClient::clientClose(',
                'void IOAccelPhxNativeClient::free(', 'void IOAccelPhxNativeClient::freeAll(',
                'IOReturn PhxBringup::gpuSubmit(', 'bool PhxBringup::vmidFree(',
                'IOReturn PhxBringup::vmMap(', 'IOReturn PhxBringup::vmUnmap(',
                'IOReturn IOAccelPhxNativeClient::doExactSubmit(']:
        if method(previous, sig) != method(staged, sig):
            raise ValueError('Unrelated/quarantine method drift: ' + sig)
    if re.search(r'exactDwordReader\s*=|exactFenceReader\s*=|exactRequested\s*=', staged):
        raise ValueError('No native reader or mode binding admitted')
    if '#define PHX_KEXT_BUILD 34u\n' not in staged:
        raise ValueError('Build34 only')
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
    extras = ['tools/build34_exact_fence32.h', 'tools/build34_exact_callbacks.h']
    for n in extras:
        (source / Path(n).name).write_bytes(inputs[n])
    (out / 'bo-lifetime.diff').write_text(''.join(difflib.unified_diff(
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
        constants = original[original.index('static constexpr uint32_t kFirstUserVmid ='):
                             original.index('static inline void flushLine(')]
        base = once(base, '// PHX34_VM_CONSTANTS', constants)
        base = once(base, 'static constexpr int kMaxMaps=2;', 'static constexpr int kMaxMaps=4;')
        base = once(base, '    uint64_t scalarOutput[1]{sentinel};',
                    '    const void *structureOutputDescriptor=nullptr;\n'
                    '    const uint64_t *scalarInput=nullptr;\n'
                    '    uint64_t storage[3]{sentinel,sentinel,sentinel}; uint64_t *scalarOutput=storage;')
        base = once(base, 'struct IOMemoryDescriptor {', 'struct IOMemoryDescriptor {\n'
                    '    bool alive=true,prepared=true; unsigned completes=0,releases=0;\n'
                    '    void complete() { CHECK(alive && prepared && !gpuHeld); ++completes; prepared=false; event("md-complete"); }\n'
                    '    void release() { CHECK(alive && !gpuHeld); ++releases; alive=false; event("md-release"); }')
        base = once(base, 'CHECK(n==1 && gpuHeld==1 && ++delays<=1000);',
                    'CHECK(((n==1 && gpuHeld==1) || (n==50 && !gpuHeld)) && ++delays<=1000);')
        base = once(base, 'testTicks+=delayStep;', 'testTicks+=delayStep*n;')
        fields = code[code.index('    static constexpr uint32_t kPtChunkBytes ='):code.index('    uint64_t *ptTable(')]
        base = once(base, '    // PHX34_VM_FIELDS', fields)
        base = once(base, '    bool debugEnabled() const { return false; }',
                    '    bool debugEnabled() const { return false; }\n'
                    '    bool exactAdmissionClosed() const { return exactCallbacks.closed() || exactStopped; }')
        # Real source Bo/Map layouts and real PHXN_MAX_BOS-sized backing arrays.
        layout = code[code.index('    struct Bo {'):code.index('    IOReturn doHello(')]
        old = base[base.index('    struct Bo {'):base.index('    PhxBringup *owner=nullptr;')]
        base = once(base, old, layout + '\n'
                    '    std::vector<Bo> boStorage=std::vector<Bo>(PHXN_MAX_BOS); Bo *bos=boStorage.data();\n'
                    '    Map mapStorage[kMaxMaps]{}; Map *maps=mapStorage;\n'
                    '    uint64_t hostUsed=0,gttUsed=0,hiUsed=0,visUsed=0;\n'
                    '    bool hello=true,boCleanupFault=false;\n')
        ensure = re.findall(r'    bool ensureVmid\(\) \{[^\n]*\}', code)
        if len(ensure) != 1:
            raise ValueError('Require actual ensureVmid')
        base = once(base, '    // PHX34_VM_ENSURE', ensure[0])
        base = once(base, '    void flushBos() { CHECK(clientHeld); } Bo *findBo(uint32_t) { return nullptr; }',
                    '    void flushBos() { CHECK(clientHeld); event("cpu-flush"); }\n'
                    '    Bo *findBo(uint32_t); void boRelease(Bo &); bool publishCpuFence(uint64_t);\n'
                    '    IOReturn doBoFree(IOExternalMethodArguments *); IOReturn doGemVa(IOExternalMethodArguments *);\n'
                    '    IOReturn doWaitSeq(IOExternalMethodArguments *);\n'
                    '    IOReturn submitExactReceipt(const void *,uint32_t,Ticket &,Receipt &);')
        sigs = [*SIGNATURES, 'PhxBringup::VmCtx *PhxBringup::vmOwned(', 'bool PhxBringup::vmWorkCurrent(',
                'bool PhxBringup::vmFlushTlbChecked(', 'uint32_t PhxBringup::vmidAlloc(', 'bool PhxBringup::vmidFree(',
                'IOReturn PhxBringup::vmMap(', 'IOReturn PhxBringup::vmUnmap(', 'uint32_t PhxBringup::vmBind(',
                'bool PhxBringup::exactGlobalRetiredLocked(', 'bool PhxBringup::readExactFence32(', SNAPSHOT,
                'IOAccelPhxNativeClient::Bo *IOAccelPhxNativeClient::findBo(', BOFREE, GEMVA, RELEASE, FENCE, WAIT,
                'IOReturn IOAccelPhxNativeClient::submitExactReceipt(']
        base = once(base, '// PHX34_VM_METHODS', method(code, 'static bool shape(') + '\n' +
                    '\n'.join(method(code, sig) for sig in sigs))
        fixture = once(inputs[FIXTURE].decode(), '// PHX34_BO_BASE', base)
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

    pattern = r'PASS staged transactional BO cleanup: (\d+) checks; (\d+) groups; (\d+) threaded scenarios; GPU_executed=false\n'
    normal = re.fullmatch(pattern, exercise('bo-lifetime', staged))
    tsan = re.fullmatch(pattern, exercise('bo-lifetime-tsan', staged, sanitizer='thread'))
    if not normal or not tsan:
        raise ValueError('Incomplete actual BO suite')
    mutations = {}

    def mutant(label, sig, before, after):
        old = method(staged, sig)
        mutations[label] = once(staged, old, once(old, before, after))

    mutant('bo-free-truncates-handle', BOFREE, ' || a->scalarInput[0] > UINT32_MAX', '')
    mutant('bo-free-accounting-underflow', BOFREE, ' || *used < b->size', '')
    mutant('bo-free-no-drain-proof', BOFREE, '    if (proof != kIOReturnSuccess) return proof;',
           '    if (proof != kIOReturnSuccess) retired = lastSeq;')
    mutant('bo-free-ignores-unmap-failure', BOFREE, '        if (r != kIOReturnSuccess) {',
           '        if (false && r != kIOReturnSuccess) {')
    mutant('bo-free-no-partial-poison', BOFREE, 'if (mutated || r != kIOReturnBusy)', 'if (false && (mutated || r != kIOReturnBusy))')
    mutant('bo-free-releases-before-unmap', BOFREE, '    bool mutated = false;',
           '    boRelease(*b);\n    bool mutated = false;')
    mutant('bo-free-does-not-publish-pending-fence', BOFREE,
           '    if (!publishCpuFence(retired)) return kIOReturnNotReady;', '')
    mutant('unmap-metadata-cleared-on-error', GEMVA, '                    return r;',
           '                    maps[i] = Map{}; return r;')
    mutant('unmap-failure-reported-success', GEMVA, '                    return r;',
           '                    return kIOReturnSuccess;')
    mutant('map-metadata-published-before-backend', GEMVA, '        if (vmid || owner->gpuReady()) {',
           '        maps[freei] = Map{true, v->handle, va, v->map_size, v->offset_in_bo, v->flags};\n'
           '        if (vmid || owner->gpuReady()) {')
    mutant('unmap-no-sticky-poison', GEMVA, 'if (r != kIOReturnBusy) boCleanupFault = true;',
           'if (false && r != kIOReturnBusy) boCleanupFault = true;')
    mutant('map-range-addition-overflow', GEMVA,
           'v->offset_in_bo > b->size || v->map_size > b->size - v->offset_in_bo',
           'v->offset_in_bo + v->map_size > b->size')
    mutant('mapping-rereads-caller-input', GEMVA, 'const phxn_gem_va *v = &request;',
           'const phxn_gem_va *v = static_cast<const phxn_gem_va *>(a->structureInput);')
    mutant('descriptor-consumed-after-callback', RELEASE, '    b = Bo{};', '    /* late consumption */')
    mutant('host-release-before-complete', RELEASE,
           '    if (host) md->complete();\n    md->release();',
           '    md->release();\n    if (host) md->complete();')
    mutant('completed-fence-not-cleared', FENCE, '        pendFenceSeq = 0;', '')
    mutant('fence-store-before-cache-flush', FENCE, '    flushBos();\n    if (fb) {',
           '    if (fb) {\n        bcopy(&pendFenceSeq, fb->kva + pendFenceOffset, 8);\n        flushBos();')
    mutant('pending-global-work-accepted', SNAPSHOT, '    if (idle && retired < c->newest) {',
           '    if (false && idle && retired < c->newest) {')
    mutant('snapshot-old-generation-accepted', SNAPSHOT,
           'VmCtx *c = vmOwned(handle, generation, client);', 'VmCtx *c = vmCtx(handle);')
    mutant('snapshot-overwrites-output-on-error', SNAPSHOT,
           '    IOLockLock(gpuLock);', '    *out = 0;\n    IOLockLock(gpuLock);')
    for label, sig in [('legacy-submit-ignores-client-fault', 'IOReturn IOAccelPhxNativeClient::doSubmit('),
                       ('typed-submit-ignores-client-fault', 'IOReturn IOAccelPhxNativeClient::submitExactReceipt(')]:
        mutant(label, sig, '    if (boCleanupFault) return kIOReturnNotReady;', '')
    for label, code in mutations.items():
        exercise(label, code, broken=True)
    if any((ROOT / n).read_bytes() != b or (frozen / n).read_bytes() != b for n, b in inputs.items()):
        raise ValueError('Frozen input drift')
    if protected != {n: sha((ROOT / n).read_bytes()) for n in names}:
        raise ValueError('Production input drift')
    report = dict(status='passed-CPU-only-staged-transactional-BO-cleanup', kernel_build=34,
                  checks=int(normal[1]), tsan_checks=int(tsan[1]), groups=int(normal[2]),
                  real_thread_scenarios=int(normal[3]), asan_ubsan=True, tsan=True,
                  detected_mutations=list(mutations), input_sha256={n: sha(b) for n, b in inputs.items()},
                  staged_driver_sha256=sha(staged.encode()), original_production_file_count=len(names),
                  production_prior_experiments_ABI_runtime_unchanged=True,
                  actual_staged_BO_VM_wait_and_descriptor_methods_tested=True,
                  late_CPU_fence_handle_reuse_counterexample_guarded=True,
                  partial_unmap_retains_BO_metadata_and_closes_client_dispatch=True,
                  CPU_double_only=True, actual_page_walker_tested=False, hardware_ACK_freshness_proved=False,
                  actual_mapping_coherency_proved=False, legacy_client_close_order_fixed=False,
                  healthy_client_or_service_reclaimer=False, permanent_quarantine_removed=False,
                  native_reader_or_mode_bound=False, native_Kernel_SDK_compile=False,
                  installed=False, loaded=False, GPU_executed=False, physical_FPS_measured=False,
                  long_term_stability_accepted=False, R3_goal_complete=False, R4_R6_started=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    test(parser.parse_args().out)
