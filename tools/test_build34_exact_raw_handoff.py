#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise actual raw entrypoints and compile complete source to nonloadable objects.

No installation, driver loading, IOKit open, GPU execution or power action.
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

from build34_exact_raw_handoff import stage, previous_stage, stage_header, stage_bootstrap, WRITERS, READERS, SERVICE_LEASE, WRITER_LEASE, BOOTSTRAP
from build34_exact_submit import once
from test_build34_exact_ownership import ROOT, DRIVER, method, sha
from test_build34_exact_native_sdk import file_sha
from upstream34_layout.ring_padding_candidate import SDK_PIN, sdk_inputs
from build34_kpi_symbolset import interface_exports

PRIOR = 'docs/validation/build34-r3-public-timer-offline-20261121.json'
TRANSFORM = 'tools/build34_exact_raw_handoff.py'
RUNNER = 'tools/test_build34_exact_raw_handoff.py'
FIXTURE = 'tests/test_build34_exact_raw_handoff.cpp'
BOOT_FIXTURE = 'tests/test_build34_exact_raw_bootstrap.c'
BOOT_DRIVER = 'tools/phxctl/mesboot.c'
BOOT_HEADERS = ('mes_v11_api_def.h', 'PhxUpstream34Layout.h', 'csb_gfx11.h')
HEADERS = ('build34_exact_fence32.h', 'build34_exact_callbacks.h', 'build34_exact_receipt_wire.h', 'build34_exact_submit_wire.h')
PUBLIC = ['IOReturn PhxBringup::' + n + '(' for n in WRITERS + READERS]
SIGNATURES = PUBLIC + ['IOReturn PhxBringup::adoptQueue(', 'uint32_t PhxBringup::rreg(', 'void PhxBringup::wreg(',
    'void PhxBringup::hdpFlush(', 'void PhxBringup::clearRing(', 'bool PhxBringup::readExactFence32(',
    'void PhxBringup::stop(', 'void PhxBringup::sealStoppedQueues(', 'void PhxBringup::invalidateExactQueues(']


def test(out, sdk, kdk):
    if platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        raise ValueError('Native x86_64 macOS only')
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require fresh ignored worktree build directory ending -private')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    if subprocess.check_output(['/usr/bin/git', 'symbolic-ref', '--short', 'HEAD'], cwd=ROOT, text=True, timeout=15).strip() != 'upstream34/vram-layout-fix':
        raise ValueError('Only default build34 branch')
    prior_blob = (ROOT / PRIOR).read_bytes()
    prior = json.loads(prior_blob)
    if prior['status'] != 'passed-CPU-and-native-object-public-service-timer-prerequisite' or prior['GPU_executed']:
        raise ValueError('Require preceding frozen source/CPU/native-object evidence')
    inputs = {n: (ROOT / n).read_bytes() for n in prior['input_sha256']}
    if any(sha(b) != prior['input_sha256'][n] for n, b in inputs.items()):
        raise ValueError('Production/prior source drift')
    inputs.update({n: (ROOT / n).read_bytes() for n in [PRIOR, TRANSFORM, RUNNER, FIXTURE, BOOT_FIXTURE, BOOT_DRIVER,
                                                    *['tools/phxctl/' + n for n in BOOT_HEADERS]]})
    protected = {n: (ROOT / n).read_bytes() for n in subprocess.check_output(
        ['/usr/bin/git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'], cwd=ROOT, text=True, timeout=15).splitlines()}
    original = inputs[DRIVER].decode()
    previous, proposed = previous_stage(original), stage(original)
    boot_original = inputs[BOOT_DRIVER].decode()
    boot_proposed = stage_bootstrap(boot_original)
    if sha(previous.encode()) != prior['staged_driver_sha256']:
        raise ValueError('Public timer predecessor drift')
    ownership = stage_header(inputs['tools/build34_exact_ownership.h'].decode())
    if sha(ownership.encode()) != prior['staged_header_sha256']:
        raise ValueError('Ownership header drift')
    # Prove every other method/field stays byte-identical, including timer/stop,
    # global retirement, VM/BO ownership, watchdog, client and receipt protocol.
    stripped = proposed
    for sig in PUBLIC + ['IOReturn PhxBringup::adoptQueue(']:
        stripped = once(stripped, method(proposed, sig), method(previous, sig))
    gates_start = proposed.index('    mutable phx34_exact::CallbackGate<> exactCallbacks;\n')
    gates_end = proposed.index('    uint64_t exactQueueSubmitted[2]', gates_start)
    gates = proposed[gates_start:gates_end]
    stripped = once(stripped, gates, '    mutable phx34_exact::CallbackGate<> exactCallbacks;\n')
    if stripped != previous or '#define PHX_KEXT_BUILD 34u\n' not in proposed or re.search(r'exactDwordReader\s*=|exactFenceReader\s*=|exactRequested\s*=', proposed):
        raise ValueError('Unrelated source, build, reader or mode drift')
    sdk_blobs = sdk_inputs(sdk)
    compiler = Path(subprocess.check_output(['/usr/bin/xcrun', '--find', 'clang++'], text=True, timeout=15).strip()).resolve()
    nm = Path(subprocess.check_output(['/usr/bin/xcrun', '--find', 'nm'], text=True, timeout=15).strip()).resolve()
    otool = Path(subprocess.check_output(['/usr/bin/xcrun', '--find', 'otool'], text=True, timeout=15).strip()).resolve()
    host_sdk = Path(subprocess.check_output(['/usr/bin/xcrun', '--show-sdk-path'], text=True, timeout=15).strip()).resolve()
    tools = {p: file_sha(p) for p in [compiler, nm, otool, host_sdk / 'SDKSettings.json']}
    kdk = Path(kdk).resolve()
    metadata = kdk / 'System/Library/CoreServices/SystemVersion.plist'
    metadata_blob = metadata.read_bytes()
    version = plistlib.loads(metadata_blob)
    os_version = subprocess.check_output(['/usr/bin/sw_vers', '-productVersion'], text=True, timeout=15).strip()
    os_build = subprocess.check_output(['/usr/bin/sw_vers', '-buildVersion'], text=True, timeout=15).strip()
    kernel = kdk / 'System/Library/Kernels/kernel'
    kernel_hash = file_sha(kernel)
    if ((version['ProductVersion'], version['ProductBuildVersion']) != (os_version, os_build) or
            sha(metadata_blob) != prior['KDK_metadata_sha256'] or kernel_hash != prior['KDK_kernel_sha256']):
        raise ValueError('Require matching current-OS KDK and preceding kernel identity')
    base = 'System/Library/Extensions/System.kext/PlugIns/'
    providers = {'com.apple.kpi.' + n: (base + f + '.kext/' + f, base + f + '.kext/Info.plist') for n, f in
                 [('bsd', 'BSDKernel'), ('iokit', 'IOKit'), ('libkern', 'Libkern'), ('mach', 'Mach'), ('unsupported', 'Unsupported')]}
    providers['com.apple.iokit.IOPCIFamily'] = ('System/Library/Extensions/IOPCIFamily.kext/Contents/MacOS/IOPCIFamily',
                                             'System/Library/Extensions/IOPCIFamily.kext/Contents/Info.plist')
    if set(plistlib.loads(protected['src/phxbringup/Info.plist'])['OSBundleLibraries']) != set(providers):
        raise ValueError('Declared provider drift')
    provider_blobs = {p: (kdk / p).read_bytes() for paths in providers.values() for p in paths}
    for n, paths in providers.items():
        if sha(provider_blobs[paths[0]]) != prior['KDK_declared_provider_sha256'][n] or plistlib.loads(provider_blobs[paths[1]])['CFBundleIdentifier'] != n:
            raise ValueError('Provider identity drift')
    out.mkdir(parents=True, mode=0o700)
    for category, blobs in [('frozen', inputs), ('sdk', sdk_blobs), ('kdk', provider_blobs)]:
        for n, b in blobs.items():
            p = out / category / n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)
    tmp = out / 'tmp-private'
    tmp.mkdir()
    env = {'PATH': str(compiler.parent) + ':/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': str(tmp)}

    def run(args, label, broken=False):
        result = subprocess.run([str(a) for a in args], cwd=out, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_bytes(result.stdout)
        (out / (label + '.stderr')).write_bytes(result.stderr)
        if broken:
            if result.returncode != 86 or not result.stderr.startswith(b'failed '):
                raise ValueError(label + ' did not detect its intended runtime defect')
        elif result.returncode:
            raise RuntimeError(label + ' failed; preserve private evidence')
        return result

    def dependencies(dep, allowed):
        paths = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        if not paths or any(Path(n).resolve() not in allowed for n in paths):
            raise ValueError('Unfrozen compiler dependency')

    cpu = out / 'cpu'
    cpu.mkdir()
    queue_start = proposed.index('    struct GpuQueue {')
    queue_end = proposed.index('    uint64_t gSeq{', queue_start)
    queue = proposed[queue_start:queue_end]
    declarations = '\n'.join(method(proposed, s).split('{', 1)[0].replace('PhxBringup::', '').rstrip() + ';' for s in PUBLIC)
    cc = [compiler, '--driver-mode=g++', '-isysroot', host_sdk, '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-Wno-unused-parameter', '-Wno-unused-function', '-fno-omit-frame-pointer', '-fno-sanitize-recover=all',
          '-I' + str(out / 'frozen/tools'), '-I' + str(out / 'frozen/src/phxbringup')]

    def exercise(label, text, sanitizer='address,undefined', broken=False, control=False):
        local_gates = gates
        if '    bool exactQueueAdopted[2]{};' in text:
            start = text.index('    mutable phx34_exact::CallbackGate<> exactCallbacks;\n')
            local_gates = text[start:text.index('    uint64_t exactQueueSubmitted[2]', start)]
        fixture = once(inputs[FIXTURE].decode(), '    // PHX34_GATES', local_gates)
        fixture = once(fixture, '    // PHX34_QUEUE', queue)
        fixture = once(fixture, '    // PHX34_DECLARATIONS', declarations)
        fixture = once(fixture, '// PHX34_METHODS', '\n'.join(method(text, s) for s in SIGNATURES))
        source, binary, dep = cpu / (label + '.cpp'), cpu / (label + '-CPU-only'), cpu / (label + '.d')
        source.write_text(fixture)
        compiled = run([*cc, '-fsanitize=' + sanitizer, '-MMD', '-MF', dep, source, '-o', binary], label + '-compile')
        if compiled.stderr:
            raise ValueError(label + ' has unexpected CPU compiler diagnostics')
        dependencies(dep, {source.resolve()} | {(out / 'frozen' / n).resolve() for n in inputs})
        linked = run([otool, '-L', binary], label + '-linkage').stdout.decode()
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linked, re.I):
            raise ValueError('CPU test links device runtime')
        result = run([binary, *(['control'] if control else [])], label + '-test', broken)
        if not broken and result.stderr:
            raise ValueError('CPU sanitizer diagnostics')
        return result.stdout.decode()

    control = exercise('prior-counterexamples', previous, control=True)
    if control != 'PASS prior raw-write/closed-service/readoption/alias CPU counterexamples; GPU_executed=false\n':
        raise ValueError('Previous behavior not reproduced')
    pattern = r'PASS raw handoff: (\d+) checks; (\d+) groups; (\d+) threaded scenarios; GPU_executed=false\n'
    normal = re.fullmatch(pattern, exercise('handoff', proposed))
    tsan = re.fullmatch(pattern, exercise('handoff-tsan', proposed, sanitizer='thread'))
    if not normal or not tsan or normal.group(2, 3) != tsan.group(2, 3):
        raise ValueError('Incomplete actual-method CPU handoff suites')
    mutations = {}

    def mutant(name, sig, old, new):
        body = method(proposed, sig)
        mutations[name] = once(proposed, body, once(body, old, new))

    for name in WRITERS:
        sig = 'IOReturn PhxBringup::' + name + '('
        mutant('unguarded-raw-' + name, sig, WRITER_LEASE, SERVICE_LEASE)
        mutant('untracked-service-' + name, sig, SERVICE_LEASE, '')
    for name in READERS:
        mutant('untracked-service-' + name, 'IOReturn PhxBringup::' + name + '(', SERVICE_LEASE, '')
    sig = 'IOReturn PhxBringup::adoptQueue('
    mutant('adoption-does-not-close-raw-writers', sig, '    exactRawWriters.close();', '    // no close;')
    mutant('adoption-forgets-writer-drain', sig, '    if (!exactRawWriters.drained()) {', '    if (false && !exactRawWriters.drained()) {')
    mutant('readoption-resets-live-history', sig, '    if (exactQueueAdopted[qi]) {', '    if (false && exactQueueAdopted[qi]) {')
    mutant('ready-false-mistaken-for-old-writer-drain', sig, '    if (exactQueueAdopted[qi]) {', '    if (gq[qi].ready) {')
    mutant('queue-handoff-not-latched', sig, '    exactQueueAdopted[qi] = true;', '    // no latch;')
    mutant('adoption-allows-wrapped-ring-offset', sig, 'ringOff > fbAperLen || ringDw * 4 > fbAperLen - ringOff',
           'ringOff + ringDw * 4 > fbAperLen')
    mutant('same-queue-regions-may-overlap', sig,
           'if (overlaps(starts[i], sizes[i], starts[j], sizes[j]))',
           'if (false && overlaps(starts[i], sizes[i], starts[j], sizes[j]))')
    mutant('peer-regions-may-overlap', sig, '    if (exactQueueAdopted[qi ^ 1u]) {',
           '    if (false && exactQueueAdopted[qi ^ 1u]) {')
    mutant('peer-reservations-forgotten-when-not-ready', sig, '    if (exactQueueAdopted[qi ^ 1u]) {',
           '    if (gq[qi ^ 1u].ready) {')
    mutant('two-queues-share-doorbell', sig, 'bool alias = dbByte == peer.dbByte;', 'bool alias = false;')
    # A reentrant per-client lock cannot protect this service-wide state.
    mutations['raw-transactions-not-exclusive'] = proposed.replace('CallbackGate<1>', 'CallbackGate<>')
    for name, text in mutations.items():
        exercise(name, text, broken=True)

    def exercise_boot(label, text, broken=False, control=False):
        fixture = once(inputs[BOOT_FIXTURE].decode(), '// PHX34_BOOTSTRAP_HELPERS', BOOTSTRAP if control else
                       text[text.index('// R3: finish every raw setup operation'):text.index('static int open_kext(')])
        compute = method(text, 'static void compute_via_mes(void)\n')
        compute = compute[compute.index('   if (env_on("ADOPT"))'):compute.index('   if (env_on("VM8"))')]
        gfx = method(text, 'static void gfx_via_mes(void)\n')
        gfx = gfx[gfx.index('   if (env_on("ADOPT_GFX"))'):gfx.rindex('\n}')]
        sched = method(text, 'static void sched_test(void)\n')
        sched = sched[sched.index('   if (env_on("MESBOOT_CS"))'):sched.rindex('\n}')]
        fixture = once(fixture, '// PHX34_COMPUTE_ADOPTION', compute)
        fixture = once(fixture, '// PHX34_GFX_ADOPTION', gfx)
        fixture = once(fixture, '// PHX34_SCHED_TAIL', sched)
        fixture = once(fixture, '// PHX34_MAIN', method(text, 'int main(int argc, char **argv)\n').replace('int main(', 'int mesboot_main(', 1))
        source, binary, dep = cpu / (label + '.c'), cpu / (label + '-CPU-only'), cpu / (label + '.d')
        source.write_text(fixture)
        compiled = run([compiler, '--driver-mode=gcc', '-isysroot', host_sdk, '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                        '-Wno-unused-function', '-Wno-unused-parameter', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                        '-MMD', '-MF', dep, source, '-o', binary], label + '-compile')
        if compiled.stderr:
            raise ValueError('Unexpected bootstrap fixture compiler diagnostics')
        dependencies(dep, {source.resolve()})
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', run([otool, '-L', binary], label + '-linkage').stdout.decode(), re.I):
            raise ValueError('Bootstrap CPU test links device runtime')
        result = run([binary, *(['control'] if control else [])], label + '-test', broken)
        if not broken and result.stderr:
            raise ValueError('Bootstrap CPU sanitizer diagnostics')
        return result.stdout.decode()

    if exercise_boot('prior-bootstrap-order', boot_original, control=True) != 'PASS prior bootstrap has raw GFX setup after compute adoption; GPU_executed=false\n':
        raise ValueError('Prior bootstrap ordering not reproduced')
    boot_match = re.fullmatch(r'PASS deferred bootstrap: (\d+) checks; actual main and adoption blocks; GPU_executed=false\n',
                             exercise_boot('deferred-bootstrap', boot_proposed))
    if not boot_match:
        raise ValueError('Incomplete deferred bootstrap tests')
    boot_mutations = {
        'bootstrap-does-not-commit': once(boot_proposed, '   return phx34CommitAdoptions();\n', '   return 0;\n'),
        'bootstrap-ignores-adoption-error': once(boot_proposed, '      if (kr) {\n', '      if (false && kr) {\n'),
        'bootstrap-duplicate-not-refused': once(boot_proposed,
            'phx34AdoptionFault || (phx34AdoptionPending & (1u << qi))', 'phx34AdoptionFault'),
        'bootstrap-loses-request-copy': once(boot_proposed, '   memcpy(phx34Adoption[qi], in, sizeof(phx34Adoption[qi]));\n', ''),
        'bootstrap-commits-before-GFX-setup': boot_proposed.replace('      phx34DeferAdoption(in);\n',
            '      phx34DeferAdoption(in);\n      (void)phx34CommitAdoptions();\n', 1),
    }
    for name, text in boot_mutations.items():
        exercise_boot(name, text, broken=True)

    flags = ['-arch', 'x86_64', '-mmacosx-version-min=11.0', '-mkernel', '-fno-builtin', '-fno-common', '-nostdinc',
             '-I' + str(out / 'sdk/Headers'), '-DKERNEL', '-DKERNEL_PRIVATE', '-DDRIVER_PRIVATE', '-DAPPLE', '-DNeXT',
             '-Os', '-Wall', '-std=c++17', '-fapple-kext', '-fno-rtti', '-fno-exceptions']
    imports, warnings, objects = {}, {}, {}
    for label, text in [('previous', previous), ('handoff', proposed)]:
        base = out / label
        closure = {DRIVER: text.encode(), 'src/phxbringup/PhxNativeABI.h': inputs['src/phxbringup/PhxNativeABI.h'],
                   'src/amd/phx_topology.h': inputs['src/amd/phx_topology.h'], 'src/phxbringup/build34_exact_ownership.h': ownership.encode()}
        closure.update({'src/phxbringup/' + n: inputs['tools/' + n] for n in HEADERS})
        for n, b in closure.items():
            p = base / n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        result = run([compiler, *flags, '-MMD', '-MF', dep, '-c', base / DRIVER, '-o', obj], label + '-native-compile')
        warnings[label] = re.findall(r'warning: (.+)', result.stderr.decode())
        if sorted(warnings[label]) != sorted(prior['compiler_warnings']['public']):
            raise ValueError('Unexpected native compiler diagnostics')
        dependencies(dep, {(base / n).resolve() for n in closure} | {(out / 'sdk' / n).resolve() for n in sdk_blobs})
        if any((base / n).read_bytes() != b for n, b in closure.items()):
            raise ValueError('Native source drift')
        blob = obj.read_bytes()
        if struct.unpack_from('<4I', blob) != (0xfeedfacf, 0x1000007, 3, 1):
            raise ValueError('Nonloadable x86_64 MH_OBJECT only')
        objects[label] = sha(blob)
        imports[label] = set(run([nm, '-arch', 'x86_64', '-uj', obj], label + '-imports').stdout.decode().splitlines())
    boot_warnings = {}
    for label, text in [('bootstrap-previous', boot_original), ('bootstrap-handoff', boot_proposed)]:
        base = out / label
        closure = {BOOT_DRIVER: text.encode(), **{'tools/phxctl/' + n: inputs['tools/phxctl/' + n] for n in BOOT_HEADERS}}
        for n, b in closure.items():
            p = base / n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        result = run([compiler, '--driver-mode=gcc', '-isysroot', host_sdk, '-arch', 'x86_64', '-O2', '-Wall',
                      '-MMD', '-MF', dep, '-c', base / BOOT_DRIVER, '-o', obj], label + '-native-compile')
        boot_warnings[label] = re.findall(r'warning: (.+)', result.stderr.decode())
        dependencies(dep, {(base / n).resolve() for n in closure})
        if any((base / n).read_bytes() != b for n, b in closure.items()):
            raise ValueError('Bootstrap native source drift')
        if struct.unpack_from('<4I', obj.read_bytes()) != (0xfeedfacf, 0x1000007, 3, 1):
            raise ValueError('Bootstrap object only')
        objects[label] = sha(obj.read_bytes())
    if boot_warnings['bootstrap-previous'] != boot_warnings['bootstrap-handoff']:
        raise ValueError('New native bootstrap compiler diagnostics')
    kernel_defs = set(run([nm, '-arch', 'x86_64', '-gUj', kernel], 'KDK-kernel-defined-externals').stdout.decode().splitlines())
    exports = {}
    for name, paths in providers.items():
        if plistlib.loads(provider_blobs[paths[1]]).get('OSKernelResource') is True:
            targets = interface_exports(provider_blobs[paths[0]])
            if set(targets.values()) - kernel_defs:
                raise ValueError('KPI target not defined by matching KDK kernel')
            exports[name] = set(targets)
        else:
            exports[name] = set(run([nm, '-arch', 'x86_64', '-gUj', out / 'kdk' / paths[0]], name + '-exports').stdout.decode().splitlines())
    available = set().union(*exports.values())
    if (imports['previous'] != imports['handoff'] or len(imports['previous']) != prior['proposed_import_count'] or
            imports['handoff'] - available or '_thread_call_cancel_wait' in imports['handoff']):
        raise ValueError('New, unavailable or private native import')
    if any((ROOT / n).read_bytes() != b or (out / 'frozen' / n).read_bytes() != b for n, b in inputs.items()):
        raise ValueError('Frozen input drift')
    if any((ROOT / n).read_bytes() != b for n, b in protected.items()) or sdk_inputs(sdk) != sdk_blobs:
        raise ValueError('Production or SDK drift')
    if (any((out / 'sdk' / n).read_bytes() != b for n, b in sdk_blobs.items()) or file_sha(kernel) != kernel_hash or
            metadata.read_bytes() != metadata_blob or any((kdk / n).read_bytes() != b or (out / 'kdk' / n).read_bytes() != b for n, b in provider_blobs.items()) or
            any(file_sha(p) != h for p, h in tools.items())):
        raise ValueError('SDK/KDK/toolchain drift')
    report = dict(status='passed-CPU-and-native-object-one-way-raw-handoff-prerequisite', kernel_build=34,
        os_version=os_version, os_build=os_build, sdk_commit=SDK_PIN, input_sha256={n: sha(b) for n, b in inputs.items()},
        staged_driver_sha256=sha(proposed.encode()), staged_header_sha256=sha(ownership.encode()),
        staged_bootstrap_sha256=sha(boot_proposed.encode()),
        production_file_count=len(protected), production_prior_ABI_dependencies_runtime_unchanged=True,
        actual_method_bodies_tested=len(SIGNATURES), actual_raw_writers_tested=len(WRITERS), actual_readers_tested=len(READERS),
        prior_CPU_counterexamples_reproduced=True, asan_ubsan=True, tsan=True, checks=int(normal[1]), tsan_checks=int(tsan[1]),
        groups=int(normal[2]), threaded_scenarios=int(normal[3]), detected_mutations=list(mutations),
        bootstrap_checks=int(boot_match[1]), bootstrap_detected_mutations=list(boot_mutations),
        actual_bootstrap_main_adoption_blocks_and_helper_tested=True, full_original_and_staged_bootstrap_objects_compiled=True,
        bootstrap_compiler_warnings=boot_warnings, bootstrap_error_refusal_and_partial_handoff_retention_tested=True,
        raw_transactions_service_wide_exclusive=True, raw_transaction_leases_cover_all_sleep_and_lock_paths=True,
        queue_handoff_closes_then_checks_drain_without_waiting_under_gpuLock=True, one_adoption_per_queue_latched=True,
        queue_regions_self_and_peer_disjoint_and_doorbells_unique=True,
        initial_external_queue_ownership_or_GPU_drain_proved=False, firmware_transport_helpers_CPU_stubs=True,
        unmodified_service_timer_global_VM_BO_receipt_watchdog_and_client_methods=True,
        native_complete_translation_units_compiled=True, native_object_only=True, native_object_sha256=objects,
        compiler_warnings=warnings, native_import_count=len(imports['handoff']), native_import_set_unchanged=True,
        all_native_imports_have_existing_declared_KDK_provider=True, native_reader_or_mode_bound=False,
        service_permanent_quarantine_removed=False, full_platform_start_unwind_tested=False, native_lifecycle_accepted=False,
        native_candidate_admitted=False, linked=False, kernel_bundle_created=False, signed=False, installed=False, loaded=False,
        IOKit_opened=False, GPU_executed=False, physical_FPS_measured=False, long_term_stability_accepted=False,
        R3_goal_complete=False, R4_R6_started=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['status', 'checks', 'tsan_checks', 'groups', 'threaded_scenarios', 'native_import_count', 'GPU_executed', 'R3_goal_complete']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--kdk', type=Path, required=True)
    args = parser.parse_args()
    test(args.out, args.sdk, args.kdk)
