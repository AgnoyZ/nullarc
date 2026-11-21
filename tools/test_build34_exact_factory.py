#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run actual factory/readiness CPU tests and complete native object checks.

No installation, load, IOKit open, GPU work, publication experiment or power action.
"""
import argparse
import json
from pathlib import Path
import platform
import re
import shlex
import subprocess

from build34_exact_factory import stage, previous_stage, stage_header, stage_bootstrap
from build34_exact_submit import once
from test_build34_exact_ownership import ROOT, DRIVER, method, sha
from test_build34_exact_native_sdk import file_sha
from test_build34_exact_raw_handoff import SIGNATURES as RAW_SIGNATURES, PUBLIC as RAW_PUBLIC
from build34_native_object_check import check as native_check

PRIOR = 'docs/validation/build34-r3-raw-handoff-offline-20261121.json'
TRANSFORM = 'tools/build34_exact_factory.py'
RUNNER = 'tools/test_build34_exact_factory.py'
HELPER = 'tools/build34_native_object_check.py'
FIXTURE = 'tests/test_build34_exact_factory.cpp'
SIGNATURES = ['IOReturn PhxBringup::newUserClient(', 'bool IOAccelPhxNativeClient::start(',
              'bool PhxBringup::registerLegacyClient(', 'bool PhxBringup::requestLegacyClose(',
              'IOReturn PhxBringup::adoptQueue(', 'void PhxBringup::stop(', 'void PhxBringup::sealStoppedQueues(',
              'void PhxBringup::invalidateExactQueues(', 'IOReturn PhxBringup::setPowerState(']


def getter(text):
    return next(line for line in text.splitlines(True) if line.startswith('    bool gpuReady() const {'))


def test(out, sdk, kdk):
    if platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        raise ValueError('Native x86_64 macOS only')
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require fresh ignored worktree build path ending -private')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    if subprocess.check_output(['/usr/bin/git', 'symbolic-ref', '--short', 'HEAD'], cwd=ROOT, text=True, timeout=15).strip() != 'upstream34/vram-layout-fix':
        raise ValueError('Default build34 only')
    prior_blob = (ROOT / PRIOR).read_bytes()
    prior = json.loads(prior_blob)
    if prior['status'] != 'passed-CPU-and-native-object-one-way-raw-handoff-prerequisite' or prior['GPU_executed']:
        raise ValueError('Require frozen preceding source/CPU/native-object evidence')
    inputs = {n: (ROOT / n).read_bytes() for n in prior['input_sha256']}
    if any(sha(b) != prior['input_sha256'][n] for n, b in inputs.items()):
        raise ValueError('Production/prior input drift')
    inputs.update({n: (ROOT / n).read_bytes() for n in [PRIOR, TRANSFORM, RUNNER, HELPER, FIXTURE]})
    protected = {n: (ROOT / n).read_bytes() for n in subprocess.check_output(
        ['/usr/bin/git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'], cwd=ROOT, text=True, timeout=15).splitlines()}
    # The new shared verifier also needs the declared dependency plist, which
    # older runners protected but did not include in their public hash map.
    inputs['src/phxbringup/Info.plist'] = protected['src/phxbringup/Info.plist']
    original = inputs[DRIVER].decode()
    previous, proposed = previous_stage(original), stage(original)
    ownership = stage_header(inputs['tools/build34_exact_ownership.h'].decode())
    if sha(previous.encode()) != prior['staged_driver_sha256'] or sha(ownership.encode()) != prior['staged_header_sha256']:
        raise ValueError('Preceding stage/header drift')
    if sha(stage_bootstrap(inputs['tools/phxctl/mesboot.c'].decode()).encode()) != prior['staged_bootstrap_sha256']:
        raise ValueError('Paired bootstrap must stay unchanged')
    stripped = proposed
    for sig in ['IOReturn PhxBringup::newUserClient(', 'IOReturn PhxBringup::adoptQueue(']:
        stripped = once(stripped, method(proposed, sig), method(previous, sig))
    stripped = once(stripped, '    // Configured-queue discovery only, NOT current completion/health/drain.\n', '')
    stripped = once(stripped, getter(proposed), getter(previous))
    stripped = once(stripped, '    uint32_t exactConfiguredQueues{0}; // atomic, monotonic; lost real work must never fall into E1 mock\n', '')
    if (stripped != previous or '#define PHX_KEXT_BUILD 34u\n' not in proposed or
            re.search(r'exactDwordReader\s*=|exactFenceReader\s*=|exactRequested\s*=', proposed)):
        raise ValueError('Unrelated source/build/reader/mode drift')
    # In this frozen stage actual queue.ready writes are only bzero of the
    # never-before-adopted queue and its single successful true publication.
    if proposed.count('    q.ready = true;\n') != 1 or re.search(r'\.ready\s*=\s*false', proposed):
        raise ValueError('Review changed queue readiness writer contract')
    out.mkdir(parents=True, mode=0o700)
    for n, b in inputs.items():
        p = out / 'frozen' / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
    compiler, otool = [Path(subprocess.check_output(['/usr/bin/xcrun', '--find', t], text=True, timeout=15).strip()).resolve()
                       for t in ['clang++', 'otool']]
    host_sdk = Path(subprocess.check_output(['/usr/bin/xcrun', '--show-sdk-path'], text=True, timeout=15).strip()).resolve()
    tools = {p: file_sha(p) for p in [compiler, otool, host_sdk / 'SDKSettings.json']}
    tmp = out / 'tmp-private'
    tmp.mkdir()
    env = {'PATH': str(compiler.parent) + ':/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': str(tmp),
           'TSAN_OPTIONS': 'halt_on_error=1:abort_on_error=0:exitcode=66'}

    def run(args, label, broken=False, race=False):
        p = subprocess.run([str(a) for a in args], cwd=out, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if race:
            if p.returncode != 66 or b'ThreadSanitizer: data race' not in p.stderr:
                raise ValueError(label + ' did not reproduce the intended CPU data race')
        elif broken:
            if p.returncode != 86 or not p.stderr.startswith(b'failed '):
                raise ValueError(label + ' did not detect its intended runtime defect')
        elif p.returncode:
            raise RuntimeError(label + ' failed; preserve private evidence')
        return p

    cpu = out / 'cpu'
    cpu.mkdir()
    start = proposed.index('    mutable phx34_exact::CallbackGate<> exactCallbacks;\n')
    fields = proposed[start:proposed.index('    uint64_t exactQueueSubmitted[2]', start)]
    start = proposed.index('    struct GpuQueue {')
    queue = proposed[start:proposed.index('    uint64_t gSeq{', start)]
    cc = [compiler, '--driver-mode=g++', '-isysroot', host_sdk, '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-Wno-unused-parameter', '-Wno-unused-function', '-fno-omit-frame-pointer', '-fno-sanitize-recover=all',
          '-I' + str(out / 'frozen/tools'), '-I' + str(out / 'frozen/src/phxbringup')]

    def execute_fixture(label, fixture, sanitizer='address,undefined', broken=False, race=False, mode=None):
        source, binary, dep = cpu / (label + '.cpp'), cpu / (label + '-CPU-only'), cpu / (label + '.d')
        source.write_text(fixture)
        compiled = run([*cc, '-fsanitize=' + sanitizer, '-MMD', '-MF', dep, source, '-o', binary], label + '-compile')
        if compiled.stderr:
            raise ValueError('Unexpected CPU compiler diagnostics')
        deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        allowed = {source.resolve()} | {(out / 'frozen' / n).resolve() for n in inputs}
        if not deps or any(Path(n).resolve() not in allowed for n in deps):
            raise ValueError('Unfrozen CPU compiler dependency')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', run([otool, '-L', binary], label + '-linkage').stdout.decode(), re.I):
            raise ValueError('CPU fixture links device runtime')
        result = run([binary, *([mode] if mode else [])], label + '-test', broken=broken, race=race)
        if not broken and not race and result.stderr:
            raise ValueError('Unexpected sanitizer diagnostics')
        return result.stdout.decode()

    def exercise(label, text, sanitizer='address,undefined', broken=False, race=False, mode=None):
        fixture = once(inputs[FIXTURE].decode(), '    // PHX34_FIELDS', fields)
        fixture = once(fixture, '    // PHX34_QUEUE', queue)
        fixture = once(fixture, '    // PHX34_GETTER', getter(text))
        fixture = once(fixture, '// PHX34_METHODS', '\n'.join(method(text, s) for s in SIGNATURES))
        return execute_fixture(label, fixture, sanitizer, broken, race, mode)

    if exercise('prior-factory-counterexamples', previous, mode='prior') != 'PASS prior factory CPU counterexamples: post-close allocation/attach and late handler; GPU_executed=false\n':
        raise ValueError('Previous factory behavior not reproduced')
    exercise('prior-configured-readiness-race', previous, sanitizer='thread', race=True, mode='readiness-race')
    pattern = r'PASS native factory: (\d+) checks; (\d+) groups; (\d+) threaded scenarios; GPU_executed=false\n'
    normal = re.fullmatch(pattern, exercise('factory', proposed))
    tsan = re.fullmatch(pattern, exercise('factory-tsan', proposed, sanitizer='thread'))
    if not normal or not tsan or normal.group(2, 3) != tsan.group(2, 3):
        raise ValueError('Incomplete factory/readiness suites')
    mutations = {}

    def mutant(name, sig, old, new):
        body = method(proposed, sig)
        mutations[name] = once(proposed, body, once(body, old, new))

    sig = 'IOReturn PhxBringup::newUserClient('
    mutant('factory-lease-missing', sig,
           '    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);\n    if (!callback || !hangTimerReady()) return kIOReturnNotReady;\n',
           '    if (!hangTimerReady()) return kIOReturnNotReady;\n')
    mutant('factory-does-not-clear-output', sig, '    *handler = nullptr;\n', '')
    mutant('factory-ignores-timer-readiness', sig, 'if (!callback || !hangTimerReady())', 'if (!callback)')
    mutant('factory-accepts-wrong-client-type', sig, '    if (type != PHXN_UC_TYPE) return kIOReturnBadArgument;\n', '')
    mutant('factory-does-not-recheck-before-start', sig,
           '    if (exactCallbacks.closed()) {\n        client->detach(this);\n        client->release();\n        return kIOReturnNotReady;\n    }\n', '')
    mutant('factory-hides-closure-as-exclusive-access', sig,
           'return exactCallbacks.closed() ? kIOReturnNotReady : kIOReturnExclusiveAccess;', 'return kIOReturnExclusiveAccess;')
    mutant('factory-does-not-recheck-after-start', sig,
           '    if (exactCallbacks.closed()) {\n        // No handler escaped.',
           '    if (false && exactCallbacks.closed()) {\n        // No handler escaped.')
    mutant('unexposed-client-admission-remains-open', sig, '        (void)client->clientClose();\n', '')
    mutant('unexposed-client-initial-reference-leaks', sig,
           '        (void)client->clientClose();\n        client->detach(this);\n        client->release();\n',
           '        (void)client->clientClose();\n        client->detach(this);\n')
    mutant('unexposed-client-remains-attached', sig,
           '        (void)client->clientClose();\n        client->detach(this);\n', '        (void)client->clientClose();\n')
    sig = 'IOReturn PhxBringup::adoptQueue('
    mutant('configured-queue-not-published', sig, '    __atomic_fetch_or(&exactConfiguredQueues, 1u << qi, __ATOMIC_RELEASE);\n', '')
    mutant('second-queue-loses-first-configured-bit', sig,
           '__atomic_fetch_or(&exactConfiguredQueues, 1u << qi, __ATOMIC_RELEASE);',
           '__atomic_store_n(&exactConfiguredQueues, 1u << qi, __ATOMIC_RELEASE);')
    body = method(proposed, sig)
    moved = once(body, '    __atomic_fetch_or(&exactConfiguredQueues, 1u << qi, __ATOMIC_RELEASE);\n', '')
    moved = once(moved, '    hdpFlush();\n',
                 '    __atomic_fetch_or(&exactConfiguredQueues, 1u << qi, __ATOMIC_RELEASE);\n    hdpFlush();\n')
    mutations['configured-bit-published-before-seeding-completes'] = once(proposed, body, moved)
    sig = 'void PhxBringup::invalidateExactQueues('
    body = method(proposed, sig)
    mutations['invalidation-reopens-E1-mock-fallback'] = once(proposed, body,
        body.replace('{\n', '{\n    __atomic_store_n(&exactConfiguredQueues, 0u, __ATOMIC_RELEASE);\n', 1))
    for name, text in mutations.items():
        exercise(name, text, broken=True)
    race_mutations = {
        'ready-getter-reverts-to-plain-queue-flags': once(proposed, getter(proposed), getter(previous)),
        'sysctl-once-reverts-to-plain-precheck': once(proposed, '    if (OSCompareAndSwap(0, 1, &gSysctlUp)) {\n',
                                                   '    if (!gSysctlUp && OSCompareAndSwap(0, 1, &gSysctlUp)) {\n'),
    }
    for name, text in race_mutations.items():
        exercise(name, text, sanitizer='thread', race=True, mode='readiness-race' if name.startswith('ready-') else 'sysctl-race')
    # Run the unchanged preceding 75-group raw-handoff suite on the actual new
    # adoption body. Its field marker naturally includes the new atomic mask;
    # no prior fixture, assertions or test expectations are rewritten.
    raw_fixture = once(inputs['tests/test_build34_exact_raw_handoff.cpp'].decode(), '    // PHX34_GATES', fields)
    raw_fixture = once(raw_fixture, '    // PHX34_QUEUE', queue)
    declarations = '\n'.join(method(proposed, s).split('{', 1)[0].replace('PhxBringup::', '').rstrip() + ';' for s in RAW_PUBLIC)
    raw_fixture = once(raw_fixture, '    // PHX34_DECLARATIONS', declarations)
    raw_fixture = once(raw_fixture, '// PHX34_METHODS', '\n'.join(method(proposed, s) for s in RAW_SIGNATURES))
    raw_pattern = r'PASS raw handoff: (\d+) checks; (\d+) groups; (\d+) threaded scenarios; GPU_executed=false\n'
    raw_asan = re.fullmatch(raw_pattern, execute_fixture('raw-handoff-regression', raw_fixture))
    raw_tsan = re.fullmatch(raw_pattern, execute_fixture('raw-handoff-regression-tsan', raw_fixture, sanitizer='thread'))
    if (not raw_asan or not raw_tsan or
            tuple(map(int, raw_asan.groups())) != (prior['checks'], prior['groups'], prior['threaded_scenarios']) or
            tuple(map(int, raw_tsan.groups())) != (prior['tsan_checks'], prior['groups'], prior['threaded_scenarios'])):
        raise ValueError('Incomplete actual new-source raw handoff regressions')
    native = native_check(out / 'native', inputs, previous, proposed, ownership, sdk, kdk, prior['native_import_count'],
                          prior['compiler_warnings']['handoff'],
                          json.loads(inputs['docs/validation/build34-r3-public-timer-offline-20261121.json']), compiler)
    if any((ROOT / n).read_bytes() != b or (out / 'frozen' / n).read_bytes() != b for n, b in inputs.items()):
        raise ValueError('Frozen input drift')
    if any((ROOT / n).read_bytes() != b for n, b in protected.items()) or any(file_sha(p) != h for p, h in tools.items()):
        raise ValueError('Production/toolchain drift')
    report = dict(status='passed-CPU-and-native-object-leased-factory-atomic-configured-discovery-prerequisite', kernel_build=34,
        input_sha256={n: sha(b) for n, b in inputs.items()}, staged_driver_sha256=sha(proposed.encode()),
        staged_header_sha256=sha(ownership.encode()), staged_bootstrap_sha256=prior['staged_bootstrap_sha256'],
        production_file_count=len(protected), production_prior_ABI_dependencies_runtime_unchanged=True,
        checks=int(normal[1]), tsan_checks=int(tsan[1]), groups=int(normal[2]), threaded_scenarios=int(normal[3]),
        asan_ubsan=True, tsan=True, prior_factory_CPU_counterexamples_reproduced=True,
        prior_actual_getter_adoption_CPU_data_race_reproduced_by_TSan=True,
        detected_assertion_mutations=list(mutations), detected_TSan_mutations=list(race_mutations),
        raw_handoff_regression_checks=int(raw_asan[1]), raw_handoff_regression_tsan_checks=int(raw_tsan[1]),
        raw_handoff_regression_groups=int(raw_asan[2]), raw_handoff_regression_threaded_scenarios=int(raw_asan[3]),
        actual_factory_start_registration_adoption_stop_power_methods_tested=True,
        factory_lease_covers_construction_and_observed_closed_start_refuses_handler=True,
        failed_unexposed_client_uses_existing_close_and_retains_uncertain_registration_pins=True,
        configured_discovery_atomic_monotonic_not_live_health_or_GPU_drain=True,
        raw_writer_guards_paired_bootstrap_VM_BO_watchdog_timer_protocol_methods_unchanged=True,
        adoption_changes_only_add_configured_mask_publication=True,
        OSObject_attach_sysctl_timer_and_close_finalization_are_CPU_models=True,
        native_reader_or_mode_bound=False, platform_start_unwind_or_PCI_publication_accepted=False,
        service_permanent_quarantine_removed=False, native_lifecycle_accepted=False, native_candidate_admitted=False,
        linked=False, kernel_bundle_created=False, installed=False, loaded=False, IOKit_opened=False, GPU_executed=False,
        physical_FPS_measured=False, long_term_stability_accepted=False, R3_goal_complete=False, R4_R6_started=False, **native)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['status', 'checks', 'tsan_checks', 'groups', 'threaded_scenarios',
                                           'native_import_count', 'GPU_executed', 'R3_goal_complete']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--kdk', type=Path, required=True)
    args = parser.parse_args()
    test(args.out, args.sdk, args.kdk)
