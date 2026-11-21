#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Test actual public timer methods in CPU models and compile the complete native source.

Never links/packages a kext, installs, opens IOKit, submits GPU work or changes power.
"""
import argparse
import json
from pathlib import Path
import platform
import plistlib
import re
import shlex
import struct
import subprocess

from build34_exact_public_timer import stage, previous_stage, stage_header
from build34_exact_submit import once
from test_build34_exact_ownership import DRIVER, ROOT, method, sha
from test_build34_exact_native_sdk import file_sha
from upstream34_layout.ring_padding_candidate import SDK_PIN, sdk_inputs
from build34_kpi_symbolset import interface_exports

PRIOR = 'docs/validation/build34-r3-native-sdk-offline-20261121.json'
TRANSFORM = 'tools/build34_exact_public_timer.py'
RUNNER = 'tools/test_build34_exact_public_timer.py'
BACKEND = 'tests/build34_exact_public_timer_backend.h'
FIXTURE = 'tests/test_build34_exact_public_timer.cpp'
SOURCES = 'docs/validation/build34-r3-public-timer-sources-20261121.json'
HEADERS = ('build34_exact_fence32.h', 'build34_exact_callbacks.h',
           'build34_exact_receipt_wire.h', 'build34_exact_submit_wire.h')
SIGNATURES = ['void PhxBringup::stop(', 'bool PhxBringup::startHangTimer(',
              'bool PhxBringup::abortHangTimerStart(', 'bool PhxBringup::armHangTimer(',
              'IOReturn PhxBringup::armHangTimerAction(', 'IOReturn PhxBringup::closeHangTimerAction(',
              'void PhxBringup::requestHangDrain(', 'void PhxBringup::sealStoppedQueues(',
              'void PhxBringup::hangDrainTick(', 'void PhxBringup::hangTick(']


def test(out, sdk, kdk):
    if platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        raise ValueError('Require native Intel macOS')
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored worktree build path ending -private')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    if subprocess.check_output(['/usr/bin/git', 'symbolic-ref', '--short', 'HEAD'], cwd=ROOT,
                               text=True, timeout=15).strip() != 'upstream34/vram-layout-fix':
        raise ValueError('Default build34 branch only')
    prior_blob = (ROOT / PRIOR).read_bytes()
    prior = json.loads(prior_blob)
    if prior['status'] != 'passed-native-translation-unit-check-KPI-admission-refused' or prior['GPU_executed']:
        raise ValueError('Require the frozen native compile/refusal prerequisite')
    inputs = {n: (ROOT / n).read_bytes() for n in prior['input_sha256']}
    if any(sha(b) != prior['input_sha256'][n] for n, b in inputs.items()):
        raise ValueError('Production/prior input drift')
    inputs.update({n: (ROOT / n).read_bytes() for n in [TRANSFORM, RUNNER, BACKEND, FIXTURE, SOURCES,
                                                     'tools/build34_kpi_symbolset.py']})
    inputs[PRIOR] = prior_blob
    names = subprocess.check_output(['/usr/bin/git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'],
                                    cwd=ROOT, text=True, timeout=15).splitlines()
    protected = {n: (ROOT / n).read_bytes() for n in names}
    original = inputs[DRIVER].decode()
    previous, proposed = previous_stage(original), stage(original)
    if sha(previous.encode()) != prior['staged_driver_sha256']:
        raise ValueError('Native predecessor drift')
    ownership = stage_header(inputs['tools/build34_exact_ownership.h'].decode())
    if sha(ownership.encode()) != prior['staged_header_sha256']:
        raise ValueError('Unrelated ownership header drift')
    for sig in ['bool PhxBringup::start(', 'IOReturn PhxBringup::gpuSubmit(',
                'bool PhxBringup::vmidFree(', 'IOReturn PhxBringup::vmMap(', 'IOReturn PhxBringup::vmUnmap(',
                'IOReturn IOAccelPhxNativeClient::externalMethod(', 'IOReturn IOAccelPhxNativeClient::doExactSubmit(',
                'IOReturn IOAccelPhxNativeClient::doExactReceipt(', 'void PhxBringup::requestHangDrain(',
                'void PhxBringup::sealStoppedQueues(', 'void PhxBringup::stop(']:
        if method(previous, sig) != method(proposed, sig):
            raise ValueError('Unrelated method or quarantine drift: ' + sig)
    if ('#define PHX_KEXT_BUILD 34u\n' not in proposed or 'thread_call_cancel_wait' in proposed or
            re.search(r'exactDwordReader\s*=|exactFenceReader\s*=|exactRequested\s*=', proposed)):
        raise ValueError('Build34 only, no private cancellation, reader or exact mode')
    sdk_blobs = sdk_inputs(sdk)
    source_review = json.loads(inputs[SOURCES])
    for name, h in source_review['local_SDK_header_sha256'].items():
        if sha(sdk_blobs['Headers/IOKit/' + name]) != h:
            raise ValueError('Reviewed public timer SDK interface drift')
    for name, h in source_review['local_SDK_symbol_interface_header_sha256'].items():
        if sha(sdk_blobs[name]) != h:
            raise ValueError('Reviewed kernel symbol-interface format drift')
    kdk = Path(kdk).resolve()
    metadata = kdk / 'System/Library/CoreServices/SystemVersion.plist'
    metadata_blob = metadata.read_bytes()
    version = plistlib.loads(metadata_blob)
    os_version = subprocess.check_output(['/usr/bin/sw_vers', '-productVersion'], text=True, timeout=15).strip()
    os_build = subprocess.check_output(['/usr/bin/sw_vers', '-buildVersion'], text=True, timeout=15).strip()
    if (version['ProductVersion'], version['ProductBuildVersion']) != (os_version, os_build):
        raise ValueError('KDK metadata must match current OS version/build')
    kernel = kdk / 'System/Library/Kernels/kernel'
    if kernel.is_symlink():
        raise ValueError('Unexpected KDK kernel link')
    kernel_sha256 = file_sha(kernel)
    system = 'System/Library/Extensions/System.kext/PlugIns/'
    provider_paths = {('com.apple.kpi.' + name.lower()): (system + file + '.kext/' + file,
                       system + file + '.kext/Info.plist') for name, file in
                      [('bsd', 'BSDKernel'), ('iokit', 'IOKit'), ('libkern', 'Libkern'),
                       ('mach', 'Mach'), ('unsupported', 'Unsupported')]}
    provider_paths['com.apple.iokit.IOPCIFamily'] = (
        'System/Library/Extensions/IOPCIFamily.kext/Contents/MacOS/IOPCIFamily',
        'System/Library/Extensions/IOPCIFamily.kext/Contents/Info.plist')
    libraries = plistlib.loads(protected['src/phxbringup/Info.plist'])['OSBundleLibraries']
    if set(libraries) != set(provider_paths) or 'com.apple.kpi.private' in libraries:
        raise ValueError('No dependency addition or private provider admitted')
    provider_blobs = {}
    for name, paths in provider_paths.items():
        for path in paths:
            if (kdk / path).is_symlink():
                raise ValueError('Unexpected KDK provider link')
            provider_blobs[path] = (kdk / path).read_bytes()
        if plistlib.loads(provider_blobs[paths[1]])['CFBundleIdentifier'] != name:
            raise ValueError('KDK declared-provider identity mismatch')
    compiler = Path(subprocess.check_output(['/usr/bin/xcrun', '--find', 'clang++'], text=True, timeout=15).strip()).resolve()
    nm = Path(subprocess.check_output(['/usr/bin/xcrun', '--find', 'nm'], text=True, timeout=15).strip()).resolve()
    otool = Path(subprocess.check_output(['/usr/bin/xcrun', '--find', 'otool'], text=True, timeout=15).strip()).resolve()
    host_sdk = Path(subprocess.check_output(['/usr/bin/xcrun', '--show-sdk-path'], text=True, timeout=15).strip()).resolve()
    tools = {p: file_sha(p) for p in [compiler, nm, otool, host_sdk / 'SDKSettings.json']}
    out.mkdir(parents=True, mode=0o700)
    for base, blobs in [('frozen', inputs), ('sdk', sdk_blobs), ('kdk', provider_blobs)]:
        for name, b in blobs.items():
            p = out / base / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)
    tmp = out / 'tmp-private'
    tmp.mkdir()
    env = {'PATH': str(compiler.parent) + ':/usr/bin:/bin:/usr/sbin:/sbin',
           'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': str(tmp)}

    def run(args, label, broken=False):
        p = subprocess.run([str(a) for a in args], cwd=out, env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if broken:
            if p.returncode != 86 or not p.stderr.startswith(b'failed '):
                raise ValueError(label + ' did not detect its intended runtime defect')
        elif p.returncode:
            raise RuntimeError(label + ' failed; preserve private evidence')
        return p

    def dependencies(dep, closure):
        paths = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        if not paths or any(Path(n).resolve() not in closure for n in paths):
            raise ValueError('Unfrozen compiler dependency')

    cpu = out / 'cpu'
    cpu.mkdir()
    for name in [BACKEND, 'tools/build34_exact_callbacks.h']:
        (cpu / Path(name).name).write_bytes(inputs[name])
    cc = [str(compiler), '--driver-mode=g++', '-isysroot', str(host_sdk), '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-Wno-unused-parameter', '-Wno-unused-function', '-fno-omit-frame-pointer',
          '-fno-sanitize-recover=all', '-I' + str(cpu)]

    def exercise(label, text, sanitizer='address,undefined', broken=False):
        fields = text[text.index('    // One-shot lifecycle: 0 fresh,'):text.index('    bool vmWorkCurrent(')]
        ref = text[text.index('class Phx34ScopedReference {'):text.index('class Phx34ReapClaim {')]
        fixture = once(inputs[FIXTURE].decode(), '// PHX34_REFERENCE', ref)
        fixture = once(fixture, '    // PHX34_FIELDS', fields)
        fixture = once(fixture, '// PHX34_METHODS', '\n'.join(method(text, s) for s in SIGNATURES))
        source, binary, dep = cpu / (label + '.cpp'), cpu / (label + '-CPU-only'), cpu / (label + '.d')
        source.write_text(fixture)
        compilation = run([*cc, '-fsanitize=' + sanitizer, '-MMD', '-MF', dep, source, '-o', binary], label + '-compile')
        if compilation.stderr:
            raise ValueError(label + ' has unexpected CPU compile diagnostics')
        allowed = {source.resolve(), (cpu / Path(BACKEND).name).resolve(), (cpu / 'build34_exact_callbacks.h').resolve()}
        dependencies(dep, allowed)
        linked = run([otool, '-L', binary], label + '-linkage').stdout.decode()
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linked, re.I):
            raise ValueError('CPU fixture links a device runtime')
        result = run([binary], label + '-test', broken)
        if not broken and result.stderr:
            raise ValueError('CPU sanitizer diagnostics')
        return result.stdout.decode()

    pattern = r'PASS public service timer: (\d+) checks; (\d+) groups; (\d+) threaded scenarios; GPU_executed=false\n'
    normal = re.fullmatch(pattern, exercise('public-timer', proposed))
    tsan = re.fullmatch(pattern, exercise('public-timer-tsan', proposed, sanitizer='thread'))
    if not normal or not tsan:
        raise ValueError('Incomplete public timer CPU suites')
    mutations = {}

    def mutant(name, sig, old, new):
        body = method(proposed, sig)
        mutations[name] = once(proposed, body, once(body, old, new))

    start, arm, action, close, drain = ('bool PhxBringup::startHangTimer(', 'bool PhxBringup::armHangTimer(',
                                     'IOReturn PhxBringup::armHangTimerAction(',
                                     'IOReturn PhxBringup::closeHangTimerAction(', 'void PhxBringup::hangDrainTick(')
    mutant('owner-pin-missing-before-publication', start, '    retain(); // persistent', '    // persistent')
    mutant('periodic-priority-reverts-to-shared-default', start, 'kIOTimerEventSourceOptionsPriorityKernel,',
           'kIOTimerEventSourceOptionsPriorityKernelHigh,')
    mutant('periodic-permits-reentrancy', start, 'kIOTimerEventSourceOptionsPriorityKernel,',
           'kIOTimerEventSourceOptionsPriorityKernel | kIOTimerEventSourceOptionsAllowReenter,')
    mutant('captured-loop-reference-missing', arm, '    if (loop) loop->retain();', '')
    mutant('captured-timer-reference-missing', arm, '    if (timer) timer->retain();', '')
    mutant('wait-for-workloop-with-timer-lock-held', arm, '    IOLockUnlock(timerLock);', '')
    mutant('queued-arm-ignores-closed-admission', action,
           ' && !me->exactCallbacks.closed() &&\n        !me->hangStopping()', '')
    mutant('worker-skips-gated-detachment', drain,
           'const bool detached = loop->runAction(closeHangTimerAction, me, timer, loop) == kIOReturnSuccess;',
           'const bool detached = true;')
    body = method(proposed, close)
    mutations['close-omits-both-cancellation-operations'] = once(proposed, body, once(body,
        '        timer->disable();\n        timer->cancelTimeout();', ''))
    mutant('remove-error-ignored-after-partial-detach', close,
           'loop->removeEventSource(timer) : kIOReturnSuccess;',
           '(loop->removeEventSource(timer), kIOReturnSuccess) : kIOReturnSuccess;')
    mutant('remove-success-does-not-recheck-attachment', close,
           '        if (result == kIOReturnSuccess && timer->getWorkLoop()) result = kIOReturnNotReady;', '')
    mutant('partial-cleanup-drops-registration-pin', drain, 'const bool releasePin = detached && freed;',
           'const bool releasePin = detached || freed;')
    mutant('failed-raw-free-forgets-handle', drain, 'const bool freed = thread_call_free(drain);',
           'const bool freed = (thread_call_free(drain), true);')
    mutant('worker-does-not-free-own-raw-handle', drain, 'const bool freed = thread_call_free(drain);',
           'const bool freed = ((void)drain, true);')
    mutant('timer-and-loop-owned-references-leak', drain, '    if (releasePin) { timer->release(); loop->release(); }', '')
    mutant('registration-pin-leaks-after-success', drain, '    if (releasePin) me->release();', '')
    mutant('repeated-stop-retains-again', 'void PhxBringup::stop(',
           '    if (!exactCallbacks.close()) return;', '    exactCallbacks.close();')
    mutant('rearm-error-does-not-close-admission', 'void PhxBringup::hangTick(',
           '    if (!me->armHangTimer() && !me->exactCallbacks.closed()) me->stop(nullptr);', '    (void)me->armHangTimer();')
    mutant('stale-timer-sender-is-accepted', 'void PhxBringup::hangTick(',
           ' ||\n        sender != __atomic_load_n(&me->hangEvent, __ATOMIC_ACQUIRE)', '')
    mutant('stop-does-not-publish-no-more-rearm', 'void PhxBringup::requestHangDrain(',
           '    __atomic_store_n(&hangStop, true, __ATOMIC_RELEASE);', '')
    mutations['timer-drain-claimed-before-worker-leaves'] = once(proposed, '== 5 && hangWorkers.drained();', '== 5;')
    for name, text in mutations.items():
        exercise(name, text, broken=True)

    flags = ['-arch', 'x86_64', '-mmacosx-version-min=11.0', '-mkernel', '-fno-builtin', '-fno-common',
             '-nostdinc', '-I' + str(out / 'sdk/Headers'), '-DKERNEL', '-DKERNEL_PRIVATE', '-DDRIVER_PRIVATE',
             '-DAPPLE', '-DNeXT', '-Os', '-Wall', '-std=c++17', '-fapple-kext', '-fno-rtti', '-fno-exceptions']
    imports, warnings, object_sha = {}, {}, {}
    for label, text in [('previous', previous), ('public', proposed)]:
        base = out / label
        closure = {DRIVER: text.encode(), 'src/phxbringup/PhxNativeABI.h': inputs['src/phxbringup/PhxNativeABI.h'],
                   'src/amd/phx_topology.h': inputs['src/amd/phx_topology.h'],
                   'src/phxbringup/build34_exact_ownership.h': ownership.encode()}
        closure.update({'src/phxbringup/' + n: inputs['tools/' + n] for n in HEADERS})
        for name, b in closure.items():
            path = base / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        result = run([compiler, *flags, '-MMD', '-MF', dep, '-c', base / DRIVER, '-o', obj], label + '-native-compile')
        warnings[label] = re.findall(r'warning: (.+)', result.stderr.decode())
        expected = ["declaration shadows a field of 'PhxBringup' [-Wshadow]"] * 3 + [
            "private field 'exactFenceReader' is not used [-Wunused-private-field]"]
        if sorted(warnings[label]) != sorted(expected):
            raise ValueError('Review unexpected native compiler diagnostics')
        allowed = {(base / n).resolve() for n in closure} | {(out / 'sdk' / n).resolve() for n in sdk_blobs}
        dependencies(dep, allowed)
        if any((base / n).read_bytes() != b for n, b in closure.items()):
            raise ValueError('Native source snapshot drift')
        data = obj.read_bytes()
        if struct.unpack_from('<4I', data) != (0xfeedfacf, 0x1000007, 3, 1):
            raise ValueError('Only x86_64 nonloadable MH_OBJECT is allowed')
        object_sha[label] = sha(data)
        imports[label] = set(run([nm, '-arch', 'x86_64', '-uj', obj], label + '-imports').stdout.decode().splitlines())
    kernel_definitions = set(run([nm, '-arch', 'x86_64', '-gUj', kernel],
                                 'KDK-kernel-defined-externals').stdout.decode().splitlines())
    exports, interface_aliases = {}, {}
    for name, paths in provider_paths.items():
        info = plistlib.loads(provider_blobs[paths[1]])
        if info.get('OSKernelResource') is True:
            if not name.startswith('com.apple.kpi.'):
                raise ValueError('Unreviewed kernel-resource provider')
            # These actual KPI files are symbol-only forwarder interfaces,
            # not implementation images. References and explicit N_INDR
            # aliases may be offered only after structural validation and
            # proof of each target's definition in this exact KDK kernel.
            targets = interface_exports(provider_blobs[paths[0]])
            if set(targets.values()) - kernel_definitions:
                raise ValueError('Unresolved kernel-interface target')
            exports[name] = set(targets)
            interface_aliases[name] = sum(n != target for n, target in targets.items())
        else:
            # Ordinary implementation binaries contribute defined externals
            # only; their own undefined imports are never offered exports.
            exports[name] = set(run([nm, '-arch', 'x86_64', '-gUj', out / 'kdk' / paths[0]],
                                    name + '-exports').stdout.decode().splitlines())
            try:
                interface_exports(provider_blobs[paths[0]])
            except ValueError:
                pass
            else:
                raise ValueError('Implementation mistaken for a kernel interface')
    available = set().union(*exports.values())
    previous_missing = sorted(imports['previous'] - available)
    if '_thread_call_cancel_wait' not in previous_missing:
        raise ValueError('Prior private-cancellation admission refusal did not reproduce')
    unresolved = sorted(imports['public'] - available)
    if unresolved or '_thread_call_cancel_wait' in imports['public']:
        raise ValueError('Public timer still has unavailable imports: ' + ', '.join(unresolved))
    if any((ROOT / n).read_bytes() != b or (out / 'frozen' / n).read_bytes() != b for n, b in inputs.items()):
        raise ValueError('Frozen input/recipe drift')
    if any((ROOT / n).read_bytes() != b for n, b in protected.items()):
        raise ValueError('Production input drift')
    if sdk_inputs(sdk) != sdk_blobs or any((out / 'sdk' / n).read_bytes() != b for n, b in sdk_blobs.items()):
        raise ValueError('SDK drift')
    if file_sha(kernel) != kernel_sha256 or metadata.read_bytes() != metadata_blob or any((kdk / n).read_bytes() != b or (out / 'kdk' / n).read_bytes() != b
                                                   for n, b in provider_blobs.items()):
        raise ValueError('KDK provider drift')
    if any(file_sha(p) != h for p, h in tools.items()):
        raise ValueError('Native toolchain drift')
    added = sorted(imports['public'] - imports['previous'])
    report = dict(status='passed-CPU-and-native-object-public-service-timer-prerequisite', kernel_build=34,
                  os_version=os_version, os_build=os_build, sdk_commit=SDK_PIN, sdk_file_count=len(sdk_blobs),
                  input_sha256={n: sha(b) for n, b in inputs.items()}, staged_driver_sha256=sha(proposed.encode()),
                  staged_header_sha256=sha(ownership.encode()), original_production_file_count=len(protected),
                  production_prior_ABI_dependencies_runtime_unchanged=True,
                  asan_ubsan=True, tsan=True, checks=int(normal[1]), tsan_checks=int(tsan[1]),
                  groups=int(normal[2]), threaded_scenarios=int(normal[3]), detected_mutations=list(mutations),
                  CPU_model_copies_no_Apple_implementation=True, actual_timer_method_bodies_tested=True,
                  actual_IOKit_execution=False, full_platform_start_unwind_tested=False,
                  callback_and_workloop_CPU_models_only=True, native_Kernel_SDK_compile=True,
                  actual_complete_native_translation_unit_compiled=True, native_object_only=True,
                  native_object_sha256=object_sha, compiler_warnings=warnings,
                  previous_import_count=len(imports['previous']), proposed_import_count=len(imports['public']),
                  added_imports=added, removed_imports=sorted(imports['previous'] - imports['public']),
                  previous_imports_missing_from_declared_KDK_providers=previous_missing,
                  all_proposed_imports_have_declared_KDK_provider=True, unresolved_proposed_imports=unresolved,
                  added_import_providers={s: [n for n, values in exports.items() if s in values] for s in added},
                  KDK_metadata_matches_current_OS_build=True, KDK_metadata_sha256=sha(metadata_blob),
                  KDK_kernel_sha256=kernel_sha256, KDK_kernel_defined_external_count=len(kernel_definitions),
                  kernel_resource_interfaces_structurally_symbol_only=True,
                  interface_reference_and_alias_targets_defined_in_KDK_kernel=True,
                  interface_alias_counts=interface_aliases, ordinary_implementation_undefineds_never_offered=True,
                  KDK_declared_provider_sha256={n: sha(provider_blobs[paths[0]]) for n, paths in provider_paths.items()},
                  dependency_addition_or_private_KPI_bypass=False, direct_private_cancellation_import_removed=True,
                  callback_gate_and_generation_cancellation_CPU_checks=True,
                  uncertain_detach_or_free_retains_objects_and_registration_pin=True,
                  native_lifecycle_or_module_unload_accepted=False, full_collection_inclusion_tested=False,
                  native_reader_or_mode_bound=False, service_permanent_quarantine_removed=False,
                  native_candidate_admitted=False, linked=False, kernel_bundle_created=False, signed=False,
                  installed=False, loaded=False, IOKit_opened=False, GPU_executed=False,
                  physical_FPS_measured=False, long_term_stability_accepted=False, R3_goal_complete=False, R4_R6_started=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['status', 'checks', 'tsan_checks', 'groups', 'threaded_scenarios',
                                           'all_proposed_imports_have_declared_KDK_provider', 'GPU_executed', 'R3_goal_complete']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--kdk', type=Path, required=True)
    args = parser.parse_args()
    test(args.out, args.sdk, args.kdk)
