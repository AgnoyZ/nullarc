"""Verify staged IH workloop lifetime with CPU doubles and pinned native KPIs."""

import argparse
import json
from pathlib import Path
import re
import subprocess
from unittest.mock import patch

import build34_native_object_check as native_objects
from build34_exact_event_iokit import DECLARATIONS as IOKIT_DECLARATIONS, FIELDS_AT
from build34_exact_event_wait import ENTRY, FIELDS
from build34_exact_ih_ingress import ADMIT, CLOSE, DECLARATIONS
from build34_exact_ih_workloop import ADMISSION_FIELDS, CLOSE_WORK, ROUTE_ADMISSION, SOURCE, STOP, STOP_ADMISSION
from build34_exact_ih_workloop import previous_stage, stage, stage_header
from build34_exact_submit import once
from test_build34_exact_event_iokit import DOUBLES
from test_build34_exact_ih_ingress import BASE_FIXTURE, METHODS, OWNERSHIP
from test_build34_exact_open import BASE, EXTRA, FACTORY_RECORD, KDK_RECORD, PROTECTED, git
from test_build34_exact_ownership import DRIVER, ROOT, method, sha

REFERENCE = 'docs/validation/build34-r3-ih-signal-handoff-offline-20261123.json'
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
        REFERENCE, FACTORY_RECORD, KDK_RECORD, BASE_FIXTURE, FIXTURE,
        'tools/build34_exact_ih_workloop.py', 'tools/test_build34_exact_ih_workloop.py', 'tools/build34_native_object_check.py',
    }}
    reference = json.loads(inputs[REFERENCE])
    original = inputs[DRIVER].decode()
    previous, proposed = previous_stage(original), stage(original)
    if sha(previous.encode()) != reference['staged_source_sha256']:
        raise ValueError('Prior staged IH source drift')
    if method(proposed, ADMIT) != 'bool PhxBringup::exactIHIngressAdmitted() const {\n    return false;\n}\n':
        raise ValueError('Native IH admission must remain disabled')
    if any(re.search(name + r'\s*=', proposed) or proposed.count(name + '{nullptr}') != 1
           for name in ('exactDwordReader', 'exactFenceReader', 'exactEventOps')):
        raise ValueError('Unexpected native binding')
    unchanged = (*(signature for signature in METHODS if signature != CLOSE), 'bool PhxBringup::start(',
                 POWER, SEAL, 'bool PhxBringup::exactNativeOpenAdmitted(', 'IOReturn IOAccelPhxNativeClient::externalMethod(')
    if any(method(previous, signature) != method(proposed, signature) for signature in unchanged):
        raise ValueError('Unexpected lifecycle, transport or IH ingress change')
    for signature, anchor in ((STOP, STOP_ADMISSION), (CLOSE, ROUTE_ADMISSION)):
        if method(proposed, signature) != once(method(previous, signature), anchor, anchor + CLOSE_WORK):
            raise ValueError('Workloop admission must close without changing other lifecycle behavior')
    if proposed.count(SOURCE) != 1 or proposed.count('PhxExactIHWorkSource::prepare(') != 1:
        raise ValueError('Workloop source must remain unbound')
    ownership = stage_header(inputs[OWNERSHIP].decode())
    out.mkdir(mode=0o700)
    (out / Path(OWNERSHIP).name).write_text(ownership)
    (out / GATE).write_bytes(inputs['tools/' + GATE])
    compiler, otool = (Path(subprocess.check_output(['/usr/bin/xcrun', '--find', tool], text=True,
                                                    timeout=15).strip()).resolve()
                       for tool in ('clang++', 'otool'))
    base = inputs[BASE_FIXTURE].decode().partition('int main() {')[0]
    base = once(base, 'class PhxBringup {\n', OSOBJECT)
    fields = ENTRY + once(FIELDS, FIELDS_AT, IOKIT_DECLARATIONS + FIELDS_AT)
    fields = once(fields, '    bool notifyExactEvent(uint32_t queue, uint64_t generation); // deferred context only\n',
                  ADMISSION_FIELDS + DECLARATIONS)
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

    def exercise(label, adapter, sanitizer, modeled, broken=False, skip_close=None, admission=ADMISSION_FIELDS):
        signatures = (*METHODS, STOP, POWER, SEAL)
        methods = [method(proposed, signature) for signature in signatures]
        power_index = signatures.index(POWER)
        methods[power_index] = once(methods[power_index], 'IOService *whichDevice) {\n',
                                    'IOService *whichDevice) {\n    (void)whichDevice;\n')
        if skip_close:
            index = signatures.index(skip_close)
            methods[index] = once(methods[index], CLOSE_WORK, '')
        if modeled:
            index = METHODS.index(ADMIT)
            methods[index] = once(methods[index], 'return false;', 'return modeledIHAdmission;')
        fixture = once(once(base, ADMISSION_FIELDS, admission), '// PHX34_EVENT_METHODS', DOUBLES + '\n'.join(methods))
        adapter = once(adapter, 'void PhxExactIHWorkSource::kick() {\n',
                       'void PhxExactIHWorkSource::kick() {\n    if (beforeKick) std::exchange(beforeKick, {})();\n')
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

    counts = {label: {mode: exercise(label + '-' + mode, SOURCE, sanitizer, mode == 'modeled')
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
        'remove-from-worker': ('    if (loop->onThread() || loop->inGate()) return kIOReturnNotPermitted;\n', '', True),
        'ignore-remove-status': ('removed == kIOReturnSuccess && !getWorkLoop()', '!getWorkLoop()', True),
        'ignore-attachment-readback': ('removed == kIOReturnSuccess && !getWorkLoop()', 'removed == kIOReturnSuccess', True),
        'forget-ambiguous-hold': ('    if (detached) release();', '    release();', True),
    }
    for label, (old, new, modeled) in mutations.items():
        exercise(label, once(SOURCE, old, new), 'address,undefined', modeled, True)
    lifecycle_mutants = {'leave-work-admission-open-on-stop': STOP, 'leave-work-admission-open-on-route-loss': CLOSE}
    for label, signature in lifecycle_mutants.items():
        exercise(label, SOURCE, 'address,undefined', True, True, skip_close=signature)
    exercise('leave-copier-turn-admission-open', SOURCE, 'address,undefined', True, True,
             admission=once(ADMISSION_FIELDS, '        exactIHTurns.close();\n', ''))
    with patch.object(native_objects, 'HEADERS', header_names):
        native = native_objects.check(out / 'native', inputs, previous, proposed, ownership, sdk, kdk,
                                      reference['native_import_count'] + len(ADDED_IMPORTS),
                                      json.loads(inputs[FACTORY_RECORD])['compiler_warnings']['proposed'],
                                      json.loads(inputs[KDK_RECORD]), compiler, added_imports=ADDED_IMPORTS)
    git('diff', '--quiet', BASE, '--', *PROTECTED)
    if any((ROOT / name).read_bytes() != blob for name, blob in inputs.items()):
        raise ValueError('Inputs changed during verification')
    result = dict(status='passed-offline-IH-providerless-workloop', build=34, checks=counts,
                  rejected_mutants=[*mutations, *lifecycle_mutants, 'leave-copier-turn-admission-open'],
                  previous_source_sha256=sha(previous.encode()),
                  staged_source_sha256=sha(proposed.encode()), protected_production_inputs=len(production),
                  staged_providerless_scheduler=True, native_irq_scheduler_bound=False,
                  copier_turn_drained_before_workloop_removal=True,
                  lifecycle_closes_work_admission_without_removal=True,
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
