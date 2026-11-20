#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Freeze actual build34 callback methods and run finite CPU thread interleavings."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_callbacks import GUARDS, guard, stage
from build34_exact_submit import once
from test_build34_exact_ownership import DRIVER, PINNED, ROOT, method, sha

PRIOR = {
    'tools/build34_exact_lifecycle.py': '0bb30218ef3305bcd5433d38e8ca09390faaccc2d0287927fe88f8da177d2eb8',
    'tools/build34_exact_submit.py': 'da8d6eb6e908f789bb82bde9a56870ce1475e37a455dc388eb4adca8350fd4c0',
    'tools/build34_exact_ownership.h': 'cba41878010a2698a87f56884da818a9965cd125b0c431239859b1cd1e2e149b',
    'tools/test_build34_exact_ownership.py': 'c7c66f35af6d9570a4f6277533c3011f5d5ca43455ae03b60a1d3d77276d2ccb',
}
HEADER = 'tools/build34_exact_callbacks.h'
FIXTURE = 'tests/test_build34_exact_callbacks.cpp'
TRANSFORM = 'tools/build34_exact_callbacks.py'
RUNNER = 'tools/test_build34_exact_callbacks.py'


def test(out):
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored worktree build path ending -private')
    paths = [*PINNED, *PRIOR, HEADER, FIXTURE, TRANSFORM, RUNNER,
             'LICENSE', 'LICENSES/MIT.txt', 'THIRD_PARTY_NOTICES.md']
    inputs = {name: (ROOT / name).read_bytes() for name in paths}
    for name, digest in {**PINNED, **PRIOR}.items():
        if sha(inputs[name]) != digest:
            raise ValueError('Production or earlier experiment input drift: ' + name)
    names = subprocess.check_output(['git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'],
                                    cwd=ROOT, text=True, timeout=15).splitlines()
    protected = {name: sha((ROOT / name).read_bytes()) for name in names}
    source = inputs[DRIVER].decode()
    staged = stage(source)
    if '#define PHX_KEXT_BUILD 34u\n' not in staged:
        raise ValueError('Only default build34 is admissible')
    for sig in ['uint64_t PhxBringup::queueFence(', 'IOReturn IOAccelPhxNativeClient::doWaitSeq(',
                'void PhxBringup::vmidFree(', 'IOReturn IOAccelPhxNativeClient::clientClose(',
                'void IOAccelPhxNativeClient::free(']:
        if method(source, sig) != method(staged, sig):
            raise ValueError('Unrelated observation or client/VMID teardown drift')
    out.mkdir(parents=True, mode=0o700)
    frozen = out / 'frozen'
    for name, blob in inputs.items():
        path = frozen / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    stage_path = out / 'source' / DRIVER
    stage_path.parent.mkdir(parents=True)
    stage_path.write_text(staged)
    for name in [HEADER, 'tools/build34_exact_ownership.h']:
        (stage_path.parent / Path(name).name).write_bytes(inputs[name])
    (out / 'source-experiment.diff').write_text(''.join(difflib.unified_diff(
        source.splitlines(True), staged.splitlines(True), fromfile='a/' + DRIVER, tofile='b/' + DRIVER)))
    signatures = [*GUARDS, 'void PhxBringup::hangTick(', 'void PhxBringup::stop(',
                  'void PhxBringup::invalidateExactQueues(', 'uint64_t PhxBringup::queueFence(']
    cc = ['/usr/bin/xcrun', 'clang++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-Wno-unused-parameter', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer',
          '-I' + str(frozen / 'tools')]

    def run(args, label, broken=False):
        result = subprocess.run([str(arg) for arg in args], cwd=out, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=45)
        (out / (label + '.stdout')).write_bytes(result.stdout)
        (out / (label + '.stderr')).write_bytes(result.stderr)
        if broken:
            if result.returncode == 0 or b'failed ' not in result.stderr:
                raise ValueError(label + ' did not detect the intended defect')
        elif result.returncode or result.stderr:
            raise RuntimeError(label + ' failed; see private logs')
        return result.stdout.decode()

    def exercise(label, code, broken=False, sanitizer='address,undefined'):
        target = out / (label + '.cpp')
        target.write_text(once(inputs[FIXTURE].decode(), '// PHX34_CALLBACK_METHODS',
                               '\n'.join(method(code, sig) for sig in signatures)))
        binary, dep = out / (label + '-CPU-only'), out / (label + '.d')
        run([*cc, '-fsanitize=' + sanitizer, '-MMD', '-MF', dep, target, '-o', binary], label + '-compile')
        dependencies = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        allowed = {str((frozen / name).resolve()) for name in inputs} | {str(target.resolve())}
        if not dependencies or any(str(Path(name).resolve()) not in allowed for name in dependencies):
            raise ValueError('Unfrozen compilation dependency')
        linked = run(['/usr/bin/otool', '-L', binary], label + '-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linked, re.I):
            raise ValueError('Device runtime linked')
        return run([binary], label + '-test', broken)

    result = exercise('callback-leases', staged)
    match = re.fullmatch(r'PASS actual staged callback leases: (\d+) checks; (\d+) groups; '
                         r'(\d+) threaded scenarios; GPU_executed=false\n', result)
    if not match or int(match[2]) != 92 or int(match[3]) != 76:
        raise ValueError('Incomplete actual callback/thread suite')
    mutations = {}
    for sig, denial in GUARDS.items():
        old = method(staged, sig)
        mutations['unguarded-' + sig.split('::')[1].split('(')[0]] = once(
            staged, old, once(old, guard(sig, denial), ''))
    tick = method(staged, 'void PhxBringup::hangTick(')
    mutations['unguarded-hangTick'] = once(staged, tick, once(tick,
        '    phx34_exact::CallbackGate<>::Lease callback(me->exactCallbacks);\n    if (!callback) return;\n', ''))
    mutations['retry-ignores-close'] = once(staged,
        '        if (exactCallbacks.closed()) {\n', '        if (false && exactCallbacks.closed()) {\n')
    mutations['stop-forgets-service-pin'] = once(staged,
        '    retain(); // quarantine service object as well as its mappings and locks\n', '')
    mutations['CPU-drain-authorizes-GPU-release'] = once(staged,
        '    // CPU drain is NOT GPU drain: no release, PMstop, base stop or retry here.',
        '    fbAper->release(); // incorrect CPU-only retirement shortcut')
    mutations['busy-stop-releases-aperture'] = once(staged,
        '    if (!exactCallbacks.drained()) return;',
        '    if (!exactCallbacks.drained()) { fbAper->release(); return; }')
    for label, code in mutations.items():
        exercise(label, code, True)
    tsan_result = exercise('callback-leases-tsan', staged, sanitizer='thread')
    if not re.fullmatch(r'PASS actual staged callback leases: \d+ checks; 92 groups; '
                        r'76 threaded scenarios; GPU_executed=false\n', tsan_result):
        raise ValueError('Incomplete TSan callback suite')
    subset = out / 'header-subset.cpp'
    subset.write_text('#include "build34_exact_callbacks.h"\n'
                      'bool example() { phx34_exact::CallbackGate<> g; '
                      'phx34_exact::CallbackGate<>::Lease lease(g); return bool(lease); }\n')
    obj = out / 'header-subset.o'
    run(['/usr/bin/xcrun', 'clang++', '-std=c++14', '-Wall', '-Wextra', '-Werror',
         '-fno-exceptions', '-fno-rtti', '-I' + str(frozen / 'tools'), '-c', subset, '-o', obj],
        'header-subset-compile')
    imports = run(['/usr/bin/nm', '-u', obj], 'header-subset-imports')
    if re.search(r'atomic|malloc|IOLock', imports, re.I):
        raise ValueError('Lifetime gate needs an allocated lock or atomic runtime')
    if any((ROOT / name).read_bytes() != blob or (frozen / name).read_bytes() != blob for name, blob in inputs.items()):
        raise ValueError('Frozen source input drift')
    if protected != {name: sha((ROOT / name).read_bytes()) for name in names}:
        raise ValueError('Production input drift')
    report = dict(status='passed-CPU-only-staged-callback-leases-and-quarantine', kernel_build=34,
                  checks=int(match[1]), groups=int(match[2]), threaded_scenarios=int(match[3]),
                  check_count_can_vary_with_actual_thread_schedule=True,
                  actual_methods_extracted=len(signatures), asan_ubsan=True, tsan=True,
                  detected_callsite_mutations=list(mutations), embedded_lock_free_admission=True,
                  lease_covers_unlocked_submit_retry=True, submit_rechecks_close_before_dispatch=True,
                  post_dispatch_stop_preserves_receipt_and_resources=True,
                  busy_stop_takes_no_GPU_lock_and_waits_for_no_callback=True,
                  CPU_drain_never_authorizes_GPU_resource_release=True,
                  staged_stop_deliberately_leaks_service_and_resources=True,
                  one_post_close_tick_can_be_queued_but_cannot_rearm_itself=True,
                  CXX14_no_exceptions_no_RTTI_no_out_of_line_atomics=True,
                  input_sha256={name: sha(blob) for name, blob in inputs.items()},
                  staged_driver_sha256=sha(staged.encode()), protected_production_file_count=len(names),
                  production_inputs_ABI_runtime_recipes_unchanged=True,
                  complete_native_callback_and_object_lifetime_proven=False,
                  broader_watchdog_queue_selection_adoption_races_proven=False,
                  original_client_BO_VMID_teardown_certified_safe=False,
                  native_GPU_drain_or_resource_reclamation_implemented=False,
                  coherent_hardware_observer_or_capability_negotiation_implemented=False,
                  native_Kernel_SDK_compile=False, installed=False, loaded=False, GPU_executed=False,
                  R3_hardware_accepted=False, R4_R6_started=False, physical_FPS_measured=False,
                  public_binary_upload=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    test(parser.parse_args().out)
