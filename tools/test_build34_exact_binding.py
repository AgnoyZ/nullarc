#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise staged embedded-registry identity admission without native execution."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shlex
import subprocess

from build34_exact_binding import CLIENT_VALID, stage, stage_header
from build34_exact_observer import stage as previous_stage, stage_header as previous_header
from build34_exact_submit import once
from test_build34_exact_observer import PRIOR as OBSERVER_PRIOR
from test_build34_exact_ownership import DRIVER, PINNED, ROOT, method, sha

PRIOR = {
    **OBSERVER_PRIOR,
    'tools/build34_exact_observer.py': '4a49181112765dea271f68114a9bb9d3b620aee02d84b9eea7f0e2c9f5775941',
    'tools/test_build34_exact_observer.py': '93153a4acc92112545824bc8099d660641efff7765e28dbec6c312fe22a37682',
    'tests/test_build34_exact_ownership.cpp': 'a772507438e0e223f216e23aa67857ea8a5774df5ad222f04e56632db9686748',
}
HEADER = 'tools/build34_exact_ownership.h'
FIXTURE = 'tests/test_build34_exact_binding.cpp'
COUNTER = 'tests/test_build34_exact_owner_counter.cpp'
OWNERSHIP = 'tests/test_build34_exact_ownership.cpp'
TRANSFORM = 'tools/build34_exact_binding.py'
RUNNER = 'tools/test_build34_exact_binding.py'
SIGNATURES = [
    'bool PhxBringup::bindExactClient(', 'bool IOAccelPhxNativeClient::start(',
    'IOReturn IOAccelPhxNativeClient::clientClose(', 'IOReturn IOAccelPhxNativeClient::doSubmit(',
    'IOReturn PhxBringup::gpuSubmit(', 'phx34_exact::Status IOAccelPhxNativeClient::queryExact(',
    'phx34_exact::Status PhxBringup::observeExact(', 'IOReturn PhxBringup::adoptQueue(',
    'void PhxBringup::invalidateExactQueues(', 'void PhxBringup::stop(',
    'uint64_t PhxBringup::queueFence(', 'uint64_t PhxBringup::gpuRetired(',
]


def test(out):
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored worktree build path ending -private')
    subprocess.run(['git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    paths = [*PINNED, *PRIOR, FIXTURE, COUNTER, TRANSFORM, RUNNER,
             'LICENSE', 'LICENSES/MIT.txt', 'THIRD_PARTY_NOTICES.md']
    inputs = {name: (ROOT / name).read_bytes() for name in paths}
    for name, digest in {**PINNED, **PRIOR}.items():
        if sha(inputs[name]) != digest:
            raise ValueError('Production or prior experiment drift: ' + name)
    names = subprocess.check_output(['git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'],
                                    cwd=ROOT, text=True, timeout=15).splitlines()
    protected = {name: sha((ROOT / name).read_bytes()) for name in names}
    original = inputs[DRIVER].decode()
    previous, staged = previous_stage(original), stage(original)
    header = stage_header(inputs[HEADER].decode())
    if '#define PHX_KEXT_BUILD 34u\n' not in staged:
        raise ValueError('Only default build34 is admissible')
    for sig in ['uint64_t PhxBringup::queueFence(', 'uint64_t PhxBringup::gpuRetired(',
                'IOReturn IOAccelPhxNativeClient::doWaitSeq(', 'void PhxBringup::vmidFree(',
                'void PhxBringup::stop(', 'void IOAccelPhxNativeClient::free(',
                'void IOAccelPhxNativeClient::freeAll(', 'void IOAccelPhxNativeClient::boRelease(']:
        if method(previous, sig) != method(staged, sig):
            raise ValueError('Legacy observer or permanent quarantine drift')
    if staged.count('exactFenceReader{nullptr}') != 1 or re.search(r'exactFenceReader\s*=', staged):
        raise ValueError('No hardware fence reader may be bound')
    if re.search(r'exactRequested\s*=', staged) or staged.count('static phx34_exact::OwnerEpochs gExactOwners;') != 1:
        raise ValueError('No native request or reset of module owner identity is admitted')
    guard = ('    if ((exactRequested || exactOwnership) && (!(' + CLIENT_VALID +
             ') || !clientCallback)) return kIOReturnNotReady;\n')
    for name in ['externalMethod', 'clientMemoryForType', 'doSubmit']:
        if guard not in method(staged, 'IOReturn IOAccelPhxNativeClient::' + name + '('):
            raise ValueError('Missing embedded-registry entry guard: ' + name)
    out.mkdir(parents=True, mode=0o700)
    frozen = out / 'frozen'
    for name, blob in inputs.items():
        path = frozen / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    stage_path = out / 'source' / DRIVER
    stage_path.parent.mkdir(parents=True)
    stage_path.write_text(staged)
    stage_header_path = stage_path.parent / Path(HEADER).name
    stage_header_path.write_text(header)
    (stage_path.parent / 'build34_exact_callbacks.h').write_bytes(inputs['tools/build34_exact_callbacks.h'])
    for label, before, after in [('embedded-binding', previous, staged),
                                 ('registry-binding', previous_header(inputs[HEADER].decode()), header)]:
        (out / (label + '.diff')).write_text(''.join(difflib.unified_diff(
            before.splitlines(True), after.splitlines(True), fromfile='a/source', tofile='b/source')))
    cc = ['/usr/bin/xcrun', 'clang++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-Wno-unused-parameter', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer',
          '-I' + str(stage_path.parent), '-I' + str(frozen / 'src/phxbringup')]

    def run(args, label, broken=False):
        p = subprocess.run([str(a) for a in args], cwd=out, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=60)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if broken:
            if p.returncode == 0 or b'failed ' not in p.stderr:
                raise ValueError(label + ' did not detect the intended defect')
        elif p.returncode or p.stderr:
            raise RuntimeError(label + ' failed; see private logs')
        return p.stdout.decode()

    def exercise(label, code, proposed_header=header, broken=False, sanitizer='address,undefined'):
        stage_header_path.write_text(proposed_header)
        target = out / (label + '.cpp')
        target.write_text(once(inputs[FIXTURE].decode(), '// PHX34_BINDING_METHODS',
                               '\n'.join(method(code, sig) for sig in SIGNATURES)))
        binary, dep = out / (label + '-CPU-only'), out / (label + '.d')
        run([*cc, '-fsanitize=' + sanitizer, '-MMD', '-MF', dep, target, '-o', binary], label + '-compile')
        allowed = {str((frozen / name).resolve()) for name in inputs} | {
            str(target.resolve()), str(stage_header_path.resolve()),
            str((stage_path.parent / 'build34_exact_callbacks.h').resolve())}
        dependencies = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        if not dependencies or any(str(Path(name).resolve()) not in allowed for name in dependencies):
            raise ValueError('Unfrozen compilation dependency')
        linked = run(['/usr/bin/otool', '-L', binary], label + '-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linked, re.I):
            raise ValueError('Device runtime linked')
        return run([binary], label + '-test', broken)

    result = exercise('embedded-binding', staged)
    pattern = (r'PASS staged exact embedded binding: (\d+) checks; (\d+) groups; '
               r'(\d+) threaded scenarios; GPU_executed=false\n')
    match = re.fullmatch(pattern, result)
    if not match or int(match[2]) != 22 or int(match[3]) != 5:
        raise ValueError('Incomplete embedded binding suite: ' + result)
    def fixture(label, name=COUNTER, proposed_header=header, broken=False):
        stage_header_path.write_text(proposed_header)
        binary, dep = out / (label + '-CPU-only'), out / (label + '.d')
        run([*cc, '-fsanitize=address,undefined', '-MMD', '-MF', dep, frozen / name,
             '-o', binary], label + '-compile')
        deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        if set(str(Path(p).resolve()) for p in deps) != {str((frozen / name).resolve()), str(stage_header_path.resolve())}:
            raise ValueError('Unfrozen standalone fixture dependency')
        linked = run(['/usr/bin/otool', '-L', binary], label + '-linkage')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linked, re.I):
            raise ValueError('Standalone fixture linked device runtime')
        return run([binary], label + '-test', broken)

    counter_output = fixture('owner-counter')
    counter_match = re.fullmatch(r'PASS owner counter controlled contention: (\d+) checks; '
                                r'32-attempt cap; GPU_executed=false\n', counter_output)
    if not counter_match:
        raise ValueError('Controlled counter test incomplete')
    mutations = {}

    def mutate(label, sig, old, new):
        text = method(staged, sig)
        mutations[label] = (once(staged, text, once(text, old, new)), header)

    bind, start, close, submit, gpu, query, observe = SIGNATURES[:7]
    mutate('missing-client-pin', bind, '        client->retain(); // embed lifetime starts before publishing exactOwnership\n', '')
    mutate('missing-provider-pin', bind, '        retain(); // provider identity cannot be reused while this client is quarantined\n', '')
    mutate('foreign-storage-accepted', bind, '&registry != &native->exactRegistry || ', '')
    mutate('wrong-provider-accepted', bind, 'native->owner != this ||', 'false ||')
    mutate('unrequested-client-accepted', bind, '!native->exactRequested || ', '')
    mutate('unstarted-client-accepted', bind, '!native->exactStartAttempted || ', '')
    mutate('repin-started-client', bind, 'native->exactClientPinned ||', 'false ||')
    mutate('prebound-pointer-accepted', bind, '        native->exactOwnership || ', '        ')
    closed = method(staged, bind)
    closed = once(closed, 'native->exactClientCallbacks.closed()) return false;', 'false) return false;')
    closed = once(closed, ' && !native->exactClientCallbacks.closed() &&\n', ' &&\n')
    mutations['closed-client-accepted'] = (once(staged, method(staged, bind), closed), header)
    mutate('closed-client-after-lock-accepted', bind, ' && !native->exactClientCallbacks.closed() &&\n', ' &&\n')
    mutate('stopped-provider-accepted', bind, '!exactStopped && !isSleeping', '!isSleeping')
    mutate('sleeping-provider-accepted', bind, '!exactStopped && !isSleeping', '!exactStopped')
    mutate('closed-provider-after-lock-accepted', bind, '!exactCallbacks.closed() && !native->', '!native->')
    unlocked = method(staged, bind)
    unlocked = once(once(unlocked, '    IOLockLock(gpuLock);\n', ''), '    IOLockUnlock(gpuLock);\n', '')
    mutations['binding-without-provider-lock'] = (once(staged, method(staged, bind), unlocked), header)
    mutate('failed-start-retried', start, '(exactRequested && exactStartAttempted) || ', '')
    mutate('prestart-close-enters-legacy', close, '    if (exactRequested || exactOwnership) {\n', '    if (exactOwnership) {\n')
    mutate('client-submit-accepts-foreign-registry', submit,
           'exactOwnership == &exactRegistry && ', '')
    mutate('client-query-accepts-foreign-registry', query,
           'exactOwnership == &exactRegistry && ', '')
    mutate('service-submit-ignores-binding', gpu,
           '    if (exact && !exact->boundTo(this, exactClient)) return kIOReturnNotReady;\n', '')
    mutate('service-observer-ignores-binding', observe,
           '    if (!registry.boundTo(this, client)) return phx34_exact::Status::Invalid;\n', '')
    mutate('submit-omits-client-identity', submit,
           '&seq, exactOwnership, ticket, this);\n', '&seq, exactOwnership, ticket);\n')
    mutations['boundTo-ignores-provider'] = (staged, once(header, 'provider_ == provider && ', ''))
    mutations['boundTo-ignores-client'] = (staged, once(header, 'client_ == client &&\n', '\n'))
    mutations['owner-identity-reused'] = (staged, once(header, 'owner_ = owner;\n', 'owner_ = 1;\n'))
    mutations['owner-exhaustion-ignored'] = (staged, once(header, 'if (value >= UINT64_MAX - 1)', 'if (value == UINT64_MAX)'))
    for label, (code, proposed_header) in mutations.items():
        exercise(label, code, proposed_header, broken=True)
    counter_mutations = {
        'owner-retry-cap-expanded': once(header, 'attempt < 32', 'attempt < UINT32_MAX'),
        'owner-refusal-clobbers-output': once(header, '        uint64_t value = __atomic_load_n',
                                             '        out = 0;\n        uint64_t value = __atomic_load_n'),
    }
    for label, proposed_header in counter_mutations.items():
        fixture(label, proposed_header=proposed_header, broken=True)
    tsan = re.fullmatch(pattern, exercise('embedded-binding-tsan', staged, sanitizer='thread'))
    if not tsan or int(tsan[2]) != 22 or int(tsan[3]) != 5:
        raise ValueError('Incomplete embedded binding TSan suite')
    ownership_output = fixture('bound-registry-ownership', OWNERSHIP)
    if not ownership_output.startswith('PASS R3 ownership prototype: 321712 checks; 128 gaps, 128 independent model rounds,'):
        raise ValueError('Staged-header ownership regression incomplete')
    subset = out / 'binding-subset.cpp'
    subset.write_text('#include "build34_exact_ownership.h"\n'
                      'phx34_exact::Status f(phx34_exact::Registry &r, const void *p, const void *c, '
                      'phx34_exact::OwnerEpochs &o) { return r.bind(p,c,o); }\n')
    run(['/usr/bin/xcrun', 'clang++', '-std=c++14', '-Wall', '-Wextra', '-Werror',
         '-fno-exceptions', '-fno-rtti', '-I' + str(stage_path.parent), '-c', subset,
         '-o', out / 'binding-subset.o'], 'binding-subset-compile')
    if stage_path.read_text() != staged or stage_header_path.read_text() != header:
        raise ValueError('Staged source/header drift')
    if any((ROOT / name).read_bytes() != blob or (frozen / name).read_bytes() != blob for name, blob in inputs.items()):
        raise ValueError('Frozen input drift')
    if protected != {name: sha((ROOT / name).read_bytes()) for name in names}:
        raise ValueError('Production input drift')
    report = dict(status='passed-CPU-only-staged-embedded-registry-binding', kernel_build=34,
                  checks=int(match[1]), groups=int(match[2]), threaded_scenarios=int(match[3]),
                  tsan_checks=int(tsan[1]),
                  actual_and_new_staged_methods_extracted=len(SIGNATURES), asan_ubsan=True, tsan=True,
                  detected_mutations=list(mutations), module_lifetime_owner_identity_never_reset=True,
                  additional_controlled_CAS_checks=int(counter_match[1]),
                  additional_staged_header_ownership_regression_checks=321712,
                  staged_header_ownership_model_rounds=128,
                  detected_counter_mutations=list(counter_mutations),
                  owner_identity_allocation_lock_free_bounded_attempts=32,
                  unique_owner_identity_across_CPU_service_instances=True,
                  receipt_registry_embedded_in_start_pinned_client=True,
                  service_binding_checks_actual_client_type_storage_and_provider=True,
                  query_and_submit_check_immutable_provider_client_binding=True,
                  no_native_exact_request_selector_or_negotiation=True,
                  native_IOKit_finalization_unload_proven=False, coherent_device_reader_proven=False,
                  no_hardware_reader_or_legacy_fallback=True, deliberate_permanent_quarantine_preserved=True,
                  native_ack_GPU_drain_reclamation_or_blocking_wait_implemented=False,
                  staged_header_CXX14_no_exceptions_no_RTTI_compile=True,
                  input_sha256={name: sha(blob) for name, blob in inputs.items()},
                  staged_driver_sha256=sha(staged.encode()), staged_registry_header_sha256=sha(header.encode()),
                  protected_production_file_count=len(names), production_inputs_ABI_runtime_recipes_unchanged=True,
                  native_Kernel_SDK_compile=False, installed=False, loaded=False, GPU_executed=False,
                  R3_hardware_accepted=False, R4_R6_started=False, physical_FPS_measured=False,
                  public_binary_upload=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    test(parser.parse_args().out)
