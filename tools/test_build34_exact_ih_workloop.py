"""Verify staged IH workloop lifetime with CPU doubles and pinned native KPIs."""

import argparse
import json
from pathlib import Path
import re
import subprocess
from unittest.mock import patch

import build34_native_object_check as native_objects
from build34_exact_event_iokit import DECLARATIONS as IOKIT_DECLARATIONS, FIELDS_AT
from build34_exact_event_wait import ENTRY, FIELDS, WAIT
from build34_exact_ih_ingress import ADMIT, CLOSE, DECLARATIONS
from build34_exact_ih_workloop import ADMISSION_FIELDS, CLOSE_WORK, ROUTE_ADMISSION, SOURCE, STOP, STOP_ADMISSION
from build34_exact_ih_workloop import BOUNDED_POLL, POLL, POLL_DECL, POLL_METHOD, PRIOR_POLL
from build34_exact_ih_workloop import PREPARE_CHECKED_PUBLISH, PREPARE_ENTRY, PREPARE_LEASE, PREPARE_PUBLISH, checked_adapter
from build34_exact_ih_workloop import PROVIDER_ADMISSION_FIELDS, PROVIDER_DETACH_CHECK, provider_adapter, stage_provider
from build34_exact_ih_workloop import previous_stage, stage, stage_bounded_poll, stage_header, stage_lifecycle
from build34_exact_submit import once
from test_build34_exact_event_iokit import DOUBLES
from test_build34_exact_ih_ingress import BASE_FIXTURE, METHODS, OWNERSHIP
from test_build34_exact_open import BASE, EXTRA, FACTORY_RECORD, KDK_RECORD, PROTECTED, git
from test_build34_exact_ownership import DRIVER, ROOT, method, sha

REFERENCE = 'docs/validation/build34-r3-ih-signal-handoff-offline-20261123.json'
LIFECYCLE = 'docs/validation/build34-r3-ih-workloop-lifecycle-offline-20261123.json'
POLL_REFERENCE = 'docs/validation/build34-r3-ih-poll-deadline-offline-20261123.json'
PREPARE_REFERENCE = 'docs/validation/build34-r3-ih-prepare-revocation-offline-20261123.json'
FIXTURE = 'tests/test_build34_exact_ih_workloop.cpp'
GATE = 'build34_exact_callbacks.h'
POWER = 'IOReturn PhxBringup::setPowerState('
SEAL = 'void PhxBringup::sealStoppedQueues('
ADDED_IMPORTS = (
    '__ZN13IOEventSource10gMetaClassE', '__ZN13IOEventSource11setWorkLoopEP10IOWorkLoop',
    '__ZN13IOEventSource19signalWorkAvailableEv',
    *(f'__ZN13IOEventSource23_RESERVEDIOEventSource{slot}Ev' for slot in range(8)),
    '__ZN13IOEventSource4initEP8OSObjectPFvS1_zE', '__ZN13IOEventSource6enableEv',
    '__ZN13IOEventSource7disableEv', '__ZN13IOEventSource7setNextEPS_',
    '__ZN13IOEventSource9setActionEPFvP8OSObjectzE', '__ZN13IOEventSourceC2EPK11OSMetaClass',
    '__ZN13IOEventSourceD2Ev', '__ZN8OSObject8DispatchE5IORPC',
    '__ZNK13IOEventSource11getWorkLoopEv', '__ZNK13IOEventSource7getNextEv',
    '__ZNK13IOEventSource8onThreadEv', '__ZNK13IOEventSource9getActionEv',
    '__ZNK13IOEventSource9isEnabledEv', '__ZTV13IOEventSource',
)
OSOBJECT = '''using IOReturn = int;
static constexpr IOReturn IOPMAckImplied = 0;
struct IOService {};
static void IOLog(const char *) {}

class OSObject {
public:
    std::atomic<unsigned> references{1};
    virtual ~OSObject() = default;
    virtual void free() { delete this; }
    void retain() { CHECK(references.fetch_add(1) > 0); }
    void release() {
        const auto old = references.fetch_sub(1);
        CHECK(old > 0);
        if (old == 1) free();
    }
};

class PhxBringup : public OSObject {
'''
POLL_DOUBLES = '''static constexpr unsigned THREAD_UNINT = 0;
static thread_local unsigned pollSliceCount = 0;
static thread_local uint64_t pollSlices[8]{};
static thread_local uint64_t conversionDelay = 0;
'''
POLL_SLEEP = '''    if (kind == THREAD_UNINT) {
        CHECK(gpuHeld && !clientHeld && key && key != p->keys[0] && key != p->keys[1]);
        CHECK(deadline > now && deadline - now <= 1000000 && pollSliceCount < 8);
        pollSlices[pollSliceCount++] = deadline - now;
        IOLockUnlock(p);
        now = deadline;
        if (onPoll) std::exchange(onPoll, {})();
        IOLockLock(p);
        return 2;
    }
'''


def test(out, sdk, kdk):
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored output ending -private')
    git('check-ignore', '-q', str(out))
    if git('symbolic-ref', '--short', 'HEAD') != 'upstream34/vram-layout-fix':
        raise ValueError('Default build34 only')
    git('diff', '--quiet', BASE, '--', *PROTECTED)
    production = git('ls-files', *PROTECTED).splitlines()
    if len(production) != 172:
        raise ValueError('Protected production inventory drift')
    header_names = native_objects.HEADERS + EXTRA
    inputs = {name: (ROOT / name).read_bytes() for name in {
        *production, *('tools/' + name for name in header_names), OWNERSHIP,
        REFERENCE, LIFECYCLE, POLL_REFERENCE, PREPARE_REFERENCE, FACTORY_RECORD, KDK_RECORD, BASE_FIXTURE, FIXTURE,
        'tools/build34_exact_ih_workloop.py', 'tools/test_build34_exact_ih_workloop.py', 'tools/build34_native_object_check.py',
    }}
    reference = json.loads(inputs[REFERENCE])
    original = inputs[DRIVER].decode()
    ingress, lifecycle, poll, previous, proposed = (transform(original) for transform in
        (previous_stage, stage_lifecycle, stage_bounded_poll, stage, stage_provider))
    prepared = checked_adapter(SOURCE)
    adapter = provider_adapter(prepared)
    if (sha(ingress.encode()) != reference['staged_source_sha256'] or
            sha(lifecycle.encode()) != json.loads(inputs[LIFECYCLE])['staged_source_sha256'] or
            sha(poll.encode()) != json.loads(inputs[POLL_REFERENCE])['staged_source_sha256'] or
            sha(previous.encode()) != json.loads(inputs[PREPARE_REFERENCE])['staged_source_sha256']):
        raise ValueError('Prior staged IH, lifecycle, poll or preparation source drift')
    if method(proposed, ADMIT) != 'bool PhxBringup::exactIHIngressAdmitted() const {\n    return false;\n}\n':
        raise ValueError('Native IH admission must remain disabled')
    if any(re.search(name + r'\s*=', proposed) or proposed.count(name + '{nullptr}') != 1
           for name in ('exactDwordReader', 'exactFenceReader', 'exactEventOps')):
        raise ValueError('Unexpected native binding')
    unchanged = (*METHODS, POLL, 'bool PhxBringup::start(', STOP,
                 POWER, SEAL, 'bool PhxBringup::exactNativeOpenAdmitted(', 'IOReturn IOAccelPhxNativeClient::externalMethod(')
    if any(method(previous, signature) != method(proposed, signature) for signature in unchanged):
        raise ValueError('Unexpected lifecycle, transport or IH ingress change')
    for signature, anchor in ((STOP, STOP_ADMISSION), (CLOSE, ROUTE_ADMISSION)):
        if method(lifecycle, signature) != once(method(ingress, signature), anchor, anchor + CLOSE_WORK):
            raise ValueError('Workloop admission must close without changing other lifecycle behavior')
    reverted = once(once(once(poll, POLL_DECL, ''), POLL_METHOD, ''), BOUNDED_POLL, PRIOR_POLL)
    if (reverted != lifecycle or once(previous, prepared, SOURCE) != poll or
            once(once(proposed, adapter, prepared), PROVIDER_ADMISSION_FIELDS, ADMISSION_FIELDS) != previous):
        raise ValueError('Unexpected change outside the isolated workloop derivation')
    if proposed.count(adapter) != 1 or any(proposed.count(signature) != 2 for signature in (
            'armProvider(', 'retireProvider(')) or proposed.count('PhxExactIHWorkSource::prepare(') != 1:
        raise ValueError('Workloop source and provider operations must remain unbound')
    ownership = stage_header(inputs[OWNERSHIP].decode())
    out.mkdir(mode=0o700)
    (out / Path(OWNERSHIP).name).write_text(ownership)
    (out / GATE).write_bytes(inputs['tools/' + GATE])
    compiler, otool = (Path(subprocess.check_output(['/usr/bin/xcrun', '--find', tool], text=True,
                                                    timeout=15).strip()).resolve()
                       for tool in ('clang++', 'otool'))
    base = inputs[BASE_FIXTURE].decode().partition('int main() {')[0]
    base = once(base, 'class PhxBringup {\n', OSOBJECT)
    base = once(base, 'static void IOSleep(unsigned ms)', '[[maybe_unused]] static void IOSleep(unsigned ms)')
    fields = ENTRY + once(FIELDS, FIELDS_AT, POLL_DECL + IOKIT_DECLARATIONS + FIELDS_AT)
    fields = once(fields, '    bool notifyExactEvent(uint32_t queue, uint64_t generation); // deferred context only\n',
                  PROVIDER_ADMISSION_FIELDS + DECLARATIONS)
    fields += '''    bool modeledIHAdmission = false;
    uint64_t getRegistryEntryID() const { return 1; }
    struct { bool active = false, terminal = false; } watchdogRecovery;
    unsigned hangDrainRequests = 0;
    void requestHangDrain() { ++hangDrainRequests; }
    void sealStoppedQueues();
    void stop(IOService *);
    IOReturn setPowerState(unsigned long, IOService *);
'''
    base = once(base, '    // PHX34_EVENT_FIELDS\n', fields)
    doubles = POLL_DOUBLES + once(DOUBLES, '    CHECK(kind == THREAD_ABORTSAFE',
                                  POLL_SLEEP + '    CHECK(kind == THREAD_ABORTSAFE')
    doubles = once(doubles, '*ticks = ns / nsPerTick;',
                   '*ticks = ns / nsPerTick; now += std::exchange(conversionDelay, 0);')

    def run(args, label, broken=False):
        process = subprocess.run([str(arg) for arg in args], cwd=out, capture_output=True, timeout=45,
                                 stdin=subprocess.DEVNULL)
        (out / (label + '.stdout')).write_bytes(process.stdout)
        (out / (label + '.stderr')).write_bytes(process.stderr)
        if broken:
            if process.returncode != 86 or not process.stderr.startswith(b'failed '):
                raise ValueError(label + ' did not detect its intended defect')
        elif process.returncode or process.stderr:
            raise RuntimeError(label + ' failed; inspect private diagnostics')
        return process.stdout.decode()

    def exercise(label, adapter, sanitizer, modeled, broken=False, skip_close=None, admission=PROVIDER_ADMISSION_FIELDS,
                 driver=None):
        signatures = (*METHODS, STOP, POWER, SEAL, POLL)
        methods = [method(proposed if driver is None else driver, signature) for signature in signatures]
        power_index = signatures.index(POWER)
        methods[power_index] = once(methods[power_index], 'IOService *whichDevice) {\n',
                                    'IOService *whichDevice) {\n    (void)whichDevice;\n')
        if skip_close:
            index = signatures.index(skip_close)
            methods[index] = once(methods[index], CLOSE_WORK, '')
        if modeled:
            index = METHODS.index(ADMIT)
            methods[index] = once(methods[index], 'return false;', 'return modeledIHAdmission;')
        fixture = once(once(base, PROVIDER_ADMISSION_FIELDS, admission),
                       '// PHX34_EVENT_METHODS', doubles + '\n'.join(methods))
        adapter = once(adapter, 'void PhxExactIHWorkSource::kick() {\n',
                       'void PhxExactIHWorkSource::kick() {\n    if (beforeKick) std::exchange(beforeKick, {})();\n')
        adapter = once(once(adapter, '    bool activate();\n', ''),
                       '    IOReturn detach();\n', '    bool activate();\n    IOReturn detach();\n')
        adapter = once(adapter, '        ProviderLease registering(gpu->exactIHProviderCalls);\n',
                       '        if (beforeProviderGate) std::exchange(beforeProviderGate, {})();\n'
                       '        ProviderLease registering(gpu->exactIHProviderCalls);\n')
        fixture += once(inputs[FIXTURE].decode(), '// PHX34_WORKLOOP_SOURCE', adapter)
        code, binary = out / (label + '.cpp'), out / label
        code.write_text(fixture)
        run([compiler, '--driver-mode=g++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
             '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all', '-DMODELED_IH=' + str(int(modeled)),
             code, '-o', binary], label + '-compile')
        if re.search(r'IOKit|Metal|vulkan', run([otool, '-L', binary], label + '-links'), re.I):
            raise ValueError('CPU-only fixture links device interfaces')
        result = run([binary], label + '-test', broken)
        if not broken:
            parsed = re.fullmatch(r'PASS IH workloop: (\d+) checks; modeled=(0|1)\n', result)
            if not parsed or int(parsed[2]) != int(modeled):
                raise ValueError('Incomplete workloop fixture')
            return int(parsed[1])

    counts = {label: {mode: exercise(label + '-' + mode, adapter, sanitizer, mode == 'modeled')
                      for mode in ('closed', 'modeled')}
              for label, sanitizer in [('asan_ubsan', 'address,undefined'), ('tsan', 'thread')]}
    if counts['asan_ubsan'] != counts['tsan']:
        raise ValueError('Sanitizers did not cover the same CPU cases')
    mutations = {
        'allow-pre-admission-allocation': (' || !gpu->exactIHIngressAdmitted()', '', False),
        'discard-inline-hint': ('    if (wake) kick();\n    return accepting();', '    return accepting();', True),
        'discard-batch-continuation': ('        if (wake) kick();', '', True),
        'signal-detached-loop': ('if (!(earlier & kKickClosed)) signalWorkAvailable();',
                                 '(void)earlier; signalWorkAvailable();', True),
        'remove-with-kick-in-flight': ('if (__atomic_load_n(&gpu->exactIHKicks, __ATOMIC_ACQUIRE) != kKickClosed)',
                                       'if (!(__atomic_load_n(&gpu->exactIHKicks, __ATOMIC_ACQUIRE) & kKickClosed))', True),
        'remove-with-copy-in-flight': ('    if (!gpu->exactIHTurns.drained()) {\n'
                                       '        setAttachment(Attachment::Attached);\n'
                                       '        return kIOReturnBusy;\n'
                                       '    }\n', '', True),
        'no-copier-turn-lease': ('    decltype(gpu->exactIHTurns)::Lease turn(gpu->exactIHTurns);\n'
                                 '    if (turn && accepting()) {',
                                 '    if (accepting()) {', True),
        'remove-from-worker': ('IOReturn PhxExactIHWorkSource::detach() {\n'
                               '    if (loop->onThread() || loop->inGate()) return kIOReturnNotPermitted;\n',
                               'IOReturn PhxExactIHWorkSource::detach() {\n', True),
        'ignore-remove-status': ('removed == kIOReturnSuccess && !getWorkLoop()', '!getWorkLoop()', True),
        'ignore-attachment-readback': ('removed == kIOReturnSuccess && !getWorkLoop()', 'removed == kIOReturnSuccess', True),
        'forget-ambiguous-hold': ('    if (detached) release();', '    release();', True),
    }
    for label, (old, new, modeled) in mutations.items():
        exercise(label, once(adapter, old, new), 'address,undefined', modeled, True)
    lifecycle_mutants = {'leave-work-admission-open-on-stop': STOP, 'leave-work-admission-open-on-route-loss': CLOSE}
    for label, signature in lifecycle_mutants.items():
        exercise(label, adapter, 'address,undefined', True, True, skip_close=signature)
    exercise('leave-copier-turn-admission-open', adapter, 'address,undefined', True, True,
             admission=once(PROVIDER_ADMISSION_FIELDS, '        exactIHTurns.close();\n', ''))
    poll_mutants = {
        'fixed-ms-poll': (BOUNDED_POLL, PRIOR_POLL),
        'uncapped-poll': ('const uint64_t slice = remaining < 1000000 ? remaining : 1000000;',
                          'const uint64_t slice = remaining;'),
        'sleep-after-poll-expiry': ('if (mach_absolute_time() < deadline)\n                    (void)IOLockSleepDeadline(gpuLock, &deadline, deadline, THREAD_UNINT);',
                                    '(void)IOLockSleepDeadline(gpuLock, &deadline, deadline, THREAD_UNINT);'),
        'use-event-key-for-poll': ('IOLockSleepDeadline(gpuLock, &deadline, deadline, THREAD_UNINT)',
                                   'IOLockSleepDeadline(gpuLock, &exactEventSerial[receipt.queue], deadline, THREAD_UNINT)'),
    }
    poll_method = method(proposed, POLL)
    for label, (old, new) in poll_mutants.items():
        broken = once(proposed, old, new) if old == BOUNDED_POLL else once(proposed, poll_method, once(poll_method, old, new))
        exercise(label, adapter, 'address,undefined', False, True, driver=broken)
    prepare_mutants = {
        'publish-revoked-preparation': (PREPARE_CHECKED_PUBLISH, PREPARE_PUBLISH),
        'omit-prepare-service-lease': (PREPARE_LEASE, PREPARE_ENTRY),
        'release-ambiguous-prepare-pin': ('        if (source->detach() == kIOReturnBusy) source->setAttachment(Attachment::Held);',
                                          '        if (source->detach() != kIOReturnSuccess) source->release();'),
    }
    for label, (old, new) in prepare_mutants.items():
        exercise(label, once(adapter, old, new), 'address,undefined', True, True)
    provider_mutants = {
        'register-after-revocation': ('if (!registering || gpu->exactCallbacks.closed() || !accepting()) {',
                                      'if (false && (!registering || gpu->exactCallbacks.closed() || !accepting())) {'),
        'enable-after-revocation': ('if (enabling && !gpu->exactCallbacks.closed() && accepting())\n'
                                    '            enabled = ops.enableTarget(context, this) == kIOReturnSuccess;',
                                    'enabled = ops.enableTarget(context, this) == kIOReturnSuccess;'),
        'unretained-provider-context': ('        context->retain();\n', ''),
        'unretained-callback-target': ('        retain();\n        context->retain();\n', '        context->retain();\n'),
        'detach-before-provider-retirement': (PROVIDER_DETACH_CHECK, ''),
        'ignore-provider-callback-drain': ('retired.status != kIOReturnSuccess || !retired.callbacksDrained',
                                           'retired.status != kIOReturnSuccess'),
        'ignore-provider-unregister-status': ('retired.status != kIOReturnSuccess || !retired.callbacksDrained',
                                               '!retired.callbacksDrained'),
    }
    for label, (old, new) in provider_mutants.items():
        exercise(label, once(adapter, old, new), 'address,undefined', True, True)
    exercise('leave-provider-admission-open', adapter, 'address,undefined', True, True,
             admission=once(PROVIDER_ADMISSION_FIELDS, '        exactIHProviderCalls.close();\n', ''))
    with patch.object(native_objects, 'HEADERS', header_names):
        native = native_objects.check(out / 'native', inputs, previous, proposed, ownership, sdk, kdk,
                                      reference['native_import_count'] + len(ADDED_IMPORTS),
                                      json.loads(inputs[FACTORY_RECORD])['compiler_warnings']['proposed'],
                                      json.loads(inputs[KDK_RECORD]), compiler)
    git('diff', '--quiet', BASE, '--', *PROTECTED)
    if any((ROOT / name).read_bytes() != blob for name, blob in inputs.items()):
        raise ValueError('Inputs changed during verification')
    result = dict(status='passed-offline-IH-provider-call-lifecycle', build=34, checks=counts,
                  rejected_mutants=[*mutations, *lifecycle_mutants, 'leave-copier-turn-admission-open', *poll_mutants,
                                    *prepare_mutants, *provider_mutants, 'leave-provider-admission-open'],
                  previous_source_sha256=sha(previous.encode()),
                  staged_source_sha256=sha(proposed.encode()), protected_production_inputs=len(production),
                  staged_providerless_scheduler=True, native_irq_scheduler_bound=False,
                  copier_turn_drained_before_workloop_removal=True,
                  lifecycle_closes_work_admission_without_removal=True,
                  fallback_poll_clips_to_remaining_budget=True,
                  observed_revocation_refuses_prepare_publication=True,
                  register_and_enable_admitted_separately=True, attempted_provider_pins_retained=True,
                  simulated_unregister_and_callback_drain_required_before_detach=True,
                  native_provider_ops_bound=False,
                  native_event_backend_bound=False, native_teardown_deadline_proved=False,
                  native_open_admitted=False, old_writer_drain_proved=False,
                  IH_accessed=False, ISR_registered=False, GPU_executed=False, R3_complete=False, **native)
    (out / 'result-private.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('out', 'sdk', 'kdk'):
        parser.add_argument('--' + option, required=True)
    args = parser.parse_args()
    print(json.dumps(test(args.out, args.sdk, args.kdk), indent=2))
