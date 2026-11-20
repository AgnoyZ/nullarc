#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Extract actual client/VMID bodies into finite CPU lifetime counterexamples.

No Kernel SDK build, IOKit service open, installation, GPU or power action.
The staged exact client intentionally retains resources forever; not deployable.
"""
import argparse
import difflib
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_client_lifetime import ENTRY_GUARD, LOCK_RECHECK, stage
from build34_exact_submit import once
from test_build34_exact_callbacks import PRIOR as CALLBACK_PRIOR
from test_build34_exact_ownership import DRIVER, PINNED, ROOT, method, sha

PRIOR = {
    **CALLBACK_PRIOR,
    'tools/build34_exact_callbacks.py': '3ebe7644a4b904f7fd335fc765028e2938c221991195e671e8caac65445e0ea0',
    'tools/build34_exact_callbacks.h': '0916cc3bdb346eb6cff922fb8d13f7aa8c85e1fabc3bf0a79f7d488db6af146d',
    'tools/test_build34_exact_callbacks.py': 'd9fa9d8288e7c33833ebae37272285a68d02ac300d50e0c4803f4ec26a34a65a',
}
FIXTURE = 'tests/test_build34_exact_client_lifetime.cpp'
TRANSFORM = 'tools/build34_exact_client_lifetime.py'
RUNNER = 'tools/test_build34_exact_client_lifetime.py'
SIGNATURES = [
    'static bool shape(', 'bool IOAccelPhxNativeClient::start(',
    'IOReturn IOAccelPhxNativeClient::clientClose(', 'void IOAccelPhxNativeClient::free(',
    'void IOAccelPhxNativeClient::freeAll(', 'void IOAccelPhxNativeClient::boRelease(',
    'IOAccelPhxNativeClient::Bo *IOAccelPhxNativeClient::findBo(',
    'IOReturn IOAccelPhxNativeClient::doBoFree(', 'IOReturn IOAccelPhxNativeClient::doGemVa(',
    'IOReturn IOAccelPhxNativeClient::doSubmit(', 'IOReturn IOAccelPhxNativeClient::doWaitSeq(',
    'IOReturn IOAccelPhxNativeClient::externalMethod(',
    'IOReturn IOAccelPhxNativeClient::clientMemoryForType(', 'void PhxBringup::vmidFree(',
]


def test(out):
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored worktree build path ending -private')
    subprocess.run(['git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    paths = [*PINNED, *PRIOR, FIXTURE, TRANSFORM, RUNNER,
             'LICENSE', 'LICENSES/MIT.txt', 'THIRD_PARTY_NOTICES.md']
    inputs = {name: (ROOT / name).read_bytes() for name in paths}
    for name, digest in {**PINNED, **PRIOR}.items():
        if sha(inputs[name]) != digest:
            raise ValueError('Production or prior experiment input drift: ' + name)
    protected_names = subprocess.check_output(
        ['git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'],
        cwd=ROOT, text=True, timeout=15).splitlines()
    protected = {name: sha((ROOT / name).read_bytes()) for name in protected_names}
    source = inputs[DRIVER].decode()
    staged = stage(source)
    if '#define PHX_KEXT_BUILD 34u\n' not in staged:
        raise ValueError('Only default build34 is admissible')
    for sig in ['IOReturn IOAccelPhxNativeClient::doWaitSeq(', 'void PhxBringup::vmidFree(',
                'uint64_t PhxBringup::queueFence(']:
        if method(source, sig) != method(staged, sig):
            raise ValueError('Unrelated wait/fence/VMID source drift')
    external = method(source, 'IOReturn IOAccelPhxNativeClient::externalMethod(')
    actual = {'doSubmit', 'doBoFree', 'doGemVa', 'doWaitSeq'}
    leaves = sorted(set(re.findall(r'(?:return|r =) (do\w+)\(a\)', external)) - actual)
    if not {'doTopology', 'doSurfGpuMark', 'doQueryInfo'} <= set(leaves):
        raise ValueError('Dispatcher leaf extraction drift')
    stubs = '\n'.join('    IOReturn ' + name + '(IOExternalMethodArguments *) { '
                      '++leafCalls; event("' + name + '"); return kIOReturnSuccess; }' for name in leaves)
    out.mkdir(parents=True, mode=0o700)
    frozen = out / 'frozen'
    for name, blob in inputs.items():
        path = frozen / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    stage_path = out / 'source' / DRIVER
    stage_path.parent.mkdir(parents=True)
    stage_path.write_text(staged)
    (out / 'source-experiment.diff').write_text(''.join(difflib.unified_diff(
        source.splitlines(True), staged.splitlines(True), fromfile='a/' + DRIVER, tofile='b/' + DRIVER)))
    cc = ['/usr/bin/xcrun', 'clang++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-Wno-unused-parameter', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer',
          '-I' + str(frozen / 'tools'), '-I' + str(frozen / 'src/phxbringup')]

    def run(args, label, broken=False):
        p = subprocess.run([str(arg) for arg in args], cwd=out, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=60)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if broken:
            if p.returncode == 0 or b'failed ' not in p.stderr:
                raise ValueError(label + ' failed to detect the intended defect')
        elif p.returncode or p.stderr:
            raise RuntimeError(label + ' failed; see private logs')
        return p.stdout.decode()

    def exercise(label, code, broken=False, sanitizer='address,undefined', baseline=False):
        target = out / (label + '.cpp')
        fixture = once(inputs[FIXTURE].decode(), '// PHX34_CLIENT_STUBS', stubs)
        target.write_text(once(fixture, '// PHX34_CLIENT_METHODS',
                               '\n'.join(method(code, sig) for sig in SIGNATURES)))
        binary, dep = out / (label + '-CPU-only'), out / (label + '.d')
        defines = ['-DPHX34_CLIENT_LEGACY_COUNTEREXAMPLE'] if baseline else []
        run([*cc, '-fsanitize=' + sanitizer, *defines, '-MMD', '-MF', dep, target, '-o', binary],
            label + '-compile')
        dependencies = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        allowed = {str((frozen / name).resolve()) for name in inputs} | {str(target.resolve())}
        if not dependencies or any(str(Path(name).resolve()) not in allowed for name in dependencies):
            raise ValueError('Unfrozen compilation dependency')
        linked = run(['/usr/bin/otool', '-L', binary], label + '-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linked, re.I):
            raise ValueError('Device runtime linked')
        return run([binary], label + '-test', broken)

    legacy = exercise('legacy-counterexamples', source, baseline=True)
    if legacy != ('PASS actual legacy cleanup counterexamples: BOs released before close wait; '
                  'timeout clears VM; free releases after timeout; GPU_executed=false\n'):
        raise ValueError('Legacy cleanup counterexamples incomplete')
    result = exercise('exact-client-retention', staged)
    pattern = (r'PASS actual staged exact client retention: (\d+) checks; (\d+) groups; '
               r'(\d+) threaded scenarios; GPU_executed=false\n')
    match = re.fullmatch(pattern, result)
    if not match or int(match[2]) != 17 or int(match[3]) != 8:
        raise ValueError('Incomplete exact client retention/thread suite')
    mutations = {}

    def mutate(label, sig, old, new):
        original = method(staged, sig)
        mutations[label] = once(staged, original, once(original, old, new))

    mutate('missing-start-client-pin', 'bool IOAccelPhxNativeClient::start(',
           '        retain(); // pin before exposing an exact-capable client\n', '')
    mutate('missing-start-provider-pin', 'bool IOAccelPhxNativeClient::start(',
           '        owner->retain(); // provider outlives every retained client resource\n', '')
    for name in ['externalMethod', 'clientMemoryForType', 'doSubmit']:
        mutate('unguarded-' + name, 'IOReturn IOAccelPhxNativeClient::' + name + '(', ENTRY_GUARD, '')
    for name in ['externalMethod', 'clientMemoryForType']:
        mutate('lock-ignores-close-' + name, 'IOReturn IOAccelPhxNativeClient::' + name + '(', LOCK_RECHECK, '')
    mutate('close-enters-legacy-teardown', 'IOReturn IOAccelPhxNativeClient::clientClose(',
           '        return kIOReturnSuccess; // quarantine; no drain/terminate/unpin\n', '')
    for name, old in [
            ('free', '    if (exactClientPinned) return; // no late retain/resurrection in free\n'),
            ('freeAll', '    if (exactClientPinned) return; // only a future proved drain may unpin\n'),
            ('boRelease', '    if (exactClientPinned && exactResourcesExposed) return;\n')]:
        mutate('unguarded-' + name, 'void IOAccelPhxNativeClient::' + name + '(', old, '')
    mutate('missing-sticky-resource-exposure', 'IOReturn IOAccelPhxNativeClient::doSubmit(',
           '        if (exactOwnership) exactResourcesExposed = true; // sticky BEFORE fallible GPU admission\n', '')
    for name in ['doBoFree', 'doGemVa']:
        mutate('unguarded-' + name, 'IOReturn IOAccelPhxNativeClient::' + name + '(',
               '    if (exactClientPinned && exactResourcesExposed) return kIOReturnBusy;\n', '')
    mutate('close-blocks-admitted-publication', 'IOReturn IOAccelPhxNativeClient::clientClose(',
           '        // Keep Registry writable for a submit admitted BEFORE close.\n',
           '        exactOwnership->close(); // incorrect: races already admitted submit\n')
    mutate('global-prefix-authorizes-VMID-release', 'IOReturn IOAccelPhxNativeClient::clientClose(',
           '        // Keep Registry writable for a submit admitted BEFORE close.\n',
           '        if (lastSeq && owner->gpuRetired() >= lastSeq) owner->vmidFree(vmid, lastSeq);\n')
    for label, code in mutations.items():
        exercise(label, code, broken=True)
    tsan = re.fullmatch(pattern, exercise('exact-client-retention-tsan', staged, sanitizer='thread'))
    if not tsan or int(tsan[2]) != 17 or int(tsan[3]) != 8:
        raise ValueError('Incomplete TSan client suite')
    if any((ROOT / name).read_bytes() != blob or (frozen / name).read_bytes() != blob for name, blob in inputs.items()):
        raise ValueError('Frozen input drift')
    if protected != {name: sha((ROOT / name).read_bytes()) for name in protected_names}:
        raise ValueError('Production input drift')
    report = dict(status='passed-CPU-only-staged-exact-client-retention', kernel_build=34,
                  checks=int(match[1]), groups=int(match[2]), threaded_scenarios=int(match[3]),
                  actual_methods_extracted=len(SIGNATURES), stubbed_dispatch_leaves=leaves,
                  legacy_cleanup_counterexamples_reproduced_with_pending_CPU_backend=True,
                  asan_ubsan=True, tsan=True, detected_callsite_mutations=list(mutations),
                  start_time_client_and_provider_pins=True, pre_start_immutable_fixture_binding_only=True,
                  close_admission_does_not_wait_take_client_lock_or_release_resources=True,
                  already_admitted_submit_can_publish_after_close=True,
                  exposed_BO_free_and_UNMAP_refused_before_accounting_changes=True,
                  global_prefix_and_metadata_forget_never_authorize_release=True,
                  deliberate_permanent_client_provider_and_resource_retention=True,
                  input_sha256={name: sha(blob) for name, blob in inputs.items()},
                  staged_driver_sha256=sha(staged.encode()), protected_production_file_count=len(protected),
                  production_inputs_ABI_runtime_recipes_unchanged=True,
                  native_IOKit_reference_counting_or_finalization_proven=False,
                  all_VM_mutations_or_all_native_entrypoints_audited=False,
                  original_legacy_client_BO_VMID_teardown_repaired=False,
                  native_GPU_drain_or_resource_reclamation_implemented=False,
                  native_exact_observer_allocator_capability_or_ack_implemented=False,
                  native_Kernel_SDK_compile=False, installed=False, loaded=False, GPU_executed=False,
                  R3_hardware_accepted=False, R4_R6_started=False, physical_FPS_measured=False,
                  public_binary_upload=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    test(parser.parse_args().out)
