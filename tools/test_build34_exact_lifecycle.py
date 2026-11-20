#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run actual staged native lifecycle methods with frozen CPU platform doubles."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_lifecycle import stage
from build34_exact_submit import once
from test_build34_exact_ownership import ROOT, DRIVER, PINNED, method, sha

FIXTURE = 'tests/test_build34_exact_lifecycle.cpp'
TRANSFORM = 'tools/build34_exact_lifecycle.py'
RUNNER = 'tools/test_build34_exact_lifecycle.py'
SUBMIT_FIXTURE = 'tests/test_build34_exact_submit.cpp'
PRIOR = {
    'tools/build34_exact_submit.py': 'da8d6eb6e908f789bb82bde9a56870ce1475e37a455dc388eb4adca8350fd4c0',
    SUBMIT_FIXTURE: '640480ce033aefecea39e71c2bf9c1f04682a20d00d104c93a3e0643a8e8a086',
    'tools/build34_exact_ownership.h': 'cba41878010a2698a87f56884da818a9965cd125b0c431239859b1cd1e2e149b',
}


def test(out):
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored build path ending -private')
    paths = [*PINNED, *PRIOR, FIXTURE, TRANSFORM, RUNNER, 'tools/test_build34_exact_ownership.py',
             'LICENSE', 'LICENSES/MIT.txt', 'THIRD_PARTY_NOTICES.md']
    inputs = {name: (ROOT / name).read_bytes() for name in paths}
    for name, digest in {**PINNED, **PRIOR}.items():
        if sha(inputs[name]) != digest:
            raise ValueError('Accepted production or earlier experiment input drift: ' + name)
    protected_names = subprocess.check_output(
        ['git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'],
        cwd=ROOT, text=True, timeout=15).splitlines()
    protected = {name: sha((ROOT / name).read_bytes()) for name in protected_names}
    source = inputs[DRIVER].decode()
    staged = stage(source)
    if '#define PHX_KEXT_BUILD 34u\n' not in staged:
        raise ValueError('Only default build34 source is admissible')
    for sig in ['uint64_t PhxBringup::gpuRetired(', 'uint64_t PhxBringup::queueFence(',
                'IOReturn IOAccelPhxNativeClient::doWaitSeq(', 'void PhxBringup::vmidFree(',
                'IOReturn IOAccelPhxNativeClient::clientClose(', 'void IOAccelPhxNativeClient::free(']:
        if method(source, sig) != method(staged, sig):
            raise ValueError('Legacy retirement/observation/teardown drift')
    # The new stop prefix invalidates metadata only; every old resource-release
    # operation remains as before and is deliberately NOT accepted as safe drain.
    if not method(staged, 'void PhxBringup::stop(').endswith(
            method(source, 'void PhxBringup::stop(').split('{', 1)[1]):
        raise ValueError('Existing stop release operations drifted')
    out.mkdir(parents=True, mode=0o700)
    frozen = out / 'frozen'
    for name, blob in inputs.items():
        path = frozen / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    stage_path = out / 'source' / DRIVER
    stage_path.parent.mkdir(parents=True)
    stage_path.write_text(staged)
    (stage_path.parent / 'build34_exact_ownership.h').write_bytes(inputs['tools/build34_exact_ownership.h'])
    (out / 'source-experiment.diff').write_text(''.join(difflib.unified_diff(
        source.splitlines(True), staged.splitlines(True), fromfile='a/' + DRIVER, tofile='b/' + DRIVER)))

    fixture = inputs[FIXTURE].decode()
    markers = ['// PHX34_LIFECYCLE_SUPPORT\n', '// PHX34_LIFECYCLE_MEMBERS\n', '// PHX34_LIFECYCLE_TESTS\n']
    if any(fixture.count(marker) != 1 for marker in markers):
        raise ValueError('Lifecycle fixture marker drift')
    _, fixture = fixture.split(markers[0])
    support, fixture = fixture.split(markers[1])
    members, tests = fixture.split(markers[2])
    template = inputs[SUBMIT_FIXTURE].decode()
    template = once(template, 'static void IOLog(const char *, ...) {}\n',
                    'static void IOLog(const char *, ...) {}\n' + support)
    template = once(template, 'struct PhxBringup {', 'struct PhxBringup : IOService {')
    template = once(template, '    size_t getLength() const { return sizeof words; }',
                    '    size_t getLength() const { return sizeof words; }\n'
                    '    void release() { releaseCheck(); }')
    template = once(template, '    void *mmio = this, *gpuLock = &gpuToken;',
                    '    Memory registers; Memory *mmio = &registers; void *gpuLock = &gpuToken;')
    template = once(template, '    struct { uint64_t lastSeq = 0; } hwv[8];',
                    '    struct HwVmid { uint64_t lastSeq = 0; }; HwVmid hwv[8];')
    template = once(template, '// PHX34_EXACT_SUBMIT_DECLARATION', members + '// PHX34_EXACT_SUBMIT_DECLARATION')
    template = once(template,
                    'observations[qi] = {exactQueueGeneration[qi],candidate,gSeq,true,false};',
                    'observations[qi] = {exactQueueGeneration[qi],candidate,gSeq,\n'
                    '                exactQueueLive[qi] && !exactStopped && !isSleeping,false};')
    template = once(template, 'int main() {', 'int runSubmitRegression() {')
    if not template.endswith('}\n'):
        raise ValueError('Submit fixture end drift')
    template = template[:-2] + '    return 0;\n}\n' + tests
    declarations = re.findall(r'^    IOReturn gpuSubmit\([^;]+;', staged, re.M)
    if len(declarations) != 1:
        raise ValueError('Native submit declaration drift')
    template = once(template, '// PHX34_EXACT_SUBMIT_DECLARATION', declarations[0])
    signatures = ['IOReturn PhxBringup::gpuSubmit(', 'IOReturn IOAccelPhxNativeClient::doSubmit(',
                  'IOReturn PhxBringup::adoptQueue(', 'uint64_t PhxBringup::queueFence(',
                  'uint64_t PhxBringup::gpuRetired(', 'IOReturn PhxBringup::setPowerState(',
                  'void PhxBringup::invalidateExactQueues(', 'void PhxBringup::killWaves(',
                  'void PhxBringup::stop(']
    cc = ['/usr/bin/xcrun', 'clang++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer',
          '-I' + str(frozen / 'src/phxbringup'), '-I' + str(frozen / 'tools')]

    def run(args, label, failure=False):
        result = subprocess.run([str(arg) for arg in args], cwd=out, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_bytes(result.stdout)
        (out / (label + '.stderr')).write_bytes(result.stderr)
        if failure:
            if result.returncode == 0 or b'failed ' not in result.stderr:
                raise ValueError(label + ' did not detect the intended lifecycle defect')
        elif result.returncode or result.stderr:
            raise RuntimeError(label + ' failed; see private logs')
        return result.stdout.decode()

    def exercise(label, code, failure=False):
        extracted = '\n'.join(method(code, sig) for sig in signatures)
        # Only the unchanged native power signature has an unused platform argument.
        extracted = '#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wunused-parameter"\n' + extracted
        extracted += '#pragma clang diagnostic pop\n'
        path = out / (label + '.cpp')
        path.write_text(once(template, '// PHX34_EXACT_SUBMIT_METHODS', extracted))
        binary, dep = out / (label + '-CPU-only'), out / (label + '.d')
        run([*cc, '-MMD', '-MF', dep, path, '-o', binary], label + '-compile')
        dependencies = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        allowed = {str((frozen / name).resolve()) for name in inputs} | {str(path.resolve())}
        if not dependencies or any(str(Path(name).resolve()) not in allowed for name in dependencies):
            raise ValueError('Unfrozen compilation dependency')
        linked = run(['/usr/bin/otool', '-L', binary], label + '-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linked, re.I):
            raise ValueError('CPU test linked a device runtime')
        return run([binary], label + '-test', failure)

    result = exercise('exact-lifecycle', staged)
    match = re.fullmatch(
        r'PASS actual staged native submit: (\d+) checks; (\d+) cases; CPU_only=true; GPU_executed=false\n'
        r'PASS actual staged lifecycle: (\d+) additional checks; (\d+) additional groups; '
        r'baseline_checks=(\d+); baseline_groups=(\d+); GPU_executed=false\n', result)
    if not match or int(match[2]) != 80 or match[1] != match[5] or match[2] != match[6]:
        raise ValueError('Incomplete actual lifecycle or inherited submit suite')
    mutants = {
        'sleep-not-invalidated': ('if (!isSleeping) invalidateExactQueues();', '/* missing sleep invalidation */'),
        'wake-reopens-queues': ('// Wake does not prove queue continuity; fresh adoption is required.',
                               'exactQueueLive[0] = exactQueueLive[1] = true;'),
        'fault-invalidated-too-late': ('    invalidateExactQueues();\n    wreg(kRegRlcSafeMode, 0x3);',
                                      '    wreg(kRegRlcSafeMode, 0x3);\n    invalidateExactQueues();'),
        'stop-not-terminal': ('    exactStopped = true;', '    exactStopped = false;'),
        'terminal-adoption-reopens': ('if (exactStopped || isSleeping) {', 'if (isSleeping) {'),
        'missing-submit-lifetime-gate': (
            'if (exact && (exactStopped || isSleeping || !exactQueueLive[qp == &gq[1] ? 1 : 0] ||',
            'if (false && exact && (exactStopped || isSleeping || !exactQueueLive[qp == &gq[1] ? 1 : 0] ||'),
        'waiting-request-crosses-invalidation': ('admissionEpoch != exactInvalidationEpoch)) {',
                                                '(admissionEpoch != exactInvalidationEpoch && false))) {'),
    }
    for label, (old, new) in mutants.items():
        exercise(label, once(staged, old, new), True)
    if any((ROOT / name).read_bytes() != blob or (frozen / name).read_bytes() != blob for name, blob in inputs.items()):
        raise ValueError('Frozen input drift')
    if protected != {name: sha((ROOT / name).read_bytes()) for name in protected_names}:
        raise ValueError('Protected production input drift')
    report = dict(status='passed-CPU-only-staged-lifecycle-invalidation', kernel_build=34,
                  actual_methods_extracted=len(signatures), inherited_submit_checks=int(match[1]),
                  inherited_submit_groups=int(match[2]), lifecycle_checks=int(match[3]), lifecycle_groups=int(match[4]),
                  asan_ubsan=True, detected_lifecycle_mutations=list(mutants),
                  invalidation_precedes_first_recovery_register_write=True,
                  invalidation_precedes_stop_release_callbacks=True, wake_does_not_reopen_queues=True,
                  blocked_exact_submit_rechecks_lifecycle=True, pending_or_lost_metadata_retained=True,
                  old_waiting_request_refused_after_invalidation_and_readoption=True,
                  generation_saturates_without_reuse=True,
                  legacy_client_VMID_and_stop_release_operations_unchanged=True,
                  native_ABI_and_legacy_WAITSEQ_unchanged=True, native_global_retirement_unchanged=True,
                  protected_production_file_count=len(protected), production_inputs_unchanged=True,
                  input_sha256={name: sha(blob) for name, blob in inputs.items()}, staged_driver_sha256=sha(staged.encode()),
                  native_observer_callback_lifetime_fencing_implemented=False,
                  coherent_hardware_fence_read_implemented=False, native_teardown_drain_implemented=False,
                  native_owner_allocation_and_capability_negotiation_implemented=False,
                  new_actual_thread_concurrency_or_TSan_testing=False, kernel_compiled=False,
                  installed=False, loaded=False, GPU_executed=False, R3_hardware_accepted=False,
                  R4_R6_started=False, physical_FPS_measured=False, public_binary_upload=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    test(parser.parse_args().out)
