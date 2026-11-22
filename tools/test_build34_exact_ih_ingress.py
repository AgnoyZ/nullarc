"""Test actual staged IH ingress methods with CPU-only vector/clock doubles."""

import argparse
import json
from pathlib import Path
import re
import subprocess
from unittest.mock import patch

import build34_native_object_check as native_objects
from build34_exact_event_iokit import DECLARATIONS as IOKIT_DECLARATIONS, FIELDS_AT, SLEEP, WAKE
from build34_exact_event_wait import AVAILABLE, ENTRY, FIELDS, INVALIDATE, PARK, SNAPSHOT, WAIT
from build34_exact_ih_ingress import (ACTIVATE, ADMIT, CLOSE, COLLECT, CURSOR, DECLARATIONS, DELIVER, LIVE, LOSE, MATCH,
                                     OPEN, SIGNAL, WORKER_DRAIN, previous_stage, stage, stage_header)
from build34_exact_submit import once
from test_build34_exact_event_iokit import DOUBLES
from test_build34_exact_open import BASE, EXTRA, FACTORY_RECORD, KDK_RECORD, PROTECTED, git
from test_build34_exact_ownership import DRIVER, ROOT, method, sha

REFERENCE = 'docs/validation/build34-r3-exact-open-offline-20261122.json'
BASE_FIXTURE = 'tests/test_build34_exact_event_wait.cpp'
FIXTURE = 'tests/test_build34_exact_ih_ingress.cpp'
OWNERSHIP = 'tools/build34_exact_ownership.h'
METHODS = (AVAILABLE, SNAPSHOT, PARK, SLEEP, WAKE, ADMIT, CURSOR, OPEN, MATCH, ACTIVATE, SIGNAL, LIVE, CLOSE, LOSE, WORKER_DRAIN,
           COLLECT, DELIVER, INVALIDATE, WAIT)


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
        'tools/build34_exact_ih_ingress.py', 'tools/test_build34_exact_ih_ingress.py',
    }}
    reference = json.loads(inputs[REFERENCE])
    original = inputs[DRIVER].decode()
    previous, proposed = previous_stage(original), stage(original)
    if sha(previous.encode()) != reference['staged_source_sha256']:
        raise ValueError('Prior exact-open source drift')
    if method(proposed, ADMIT) != 'bool PhxBringup::exactIHIngressAdmitted() const {\n    return false;\n}\n':
        raise ValueError('Native IH admission must remain disabled')
    if any(re.search(name + r'\s*=', proposed) or proposed.count(name + '{nullptr}') != 1
           for name in ('exactDwordReader', 'exactFenceReader', 'exactEventOps')):
        raise ValueError('Unexpected native binding')
    unchanged = (SNAPSHOT, PARK, WAIT, 'bool PhxBringup::exactNativeOpenAdmitted(',
                 'bool PhxBringup::readExactPrefix(', 'IOReturn IOAccelPhxNativeClient::externalMethod(',
                 'void PhxBringup::stop(', 'IOReturn PhxBringup::setPowerState(',
                 'void PhxBringup::sealStoppedQueues(')
    if any(method(previous, signature) != method(proposed, signature) for signature in unchanged):
        raise ValueError('Unexpected event wait, sequence or platform lifecycle change')
    ownership = stage_header(inputs[OWNERSHIP].decode())
    out.mkdir(mode=0o700)
    (out / Path(OWNERSHIP).name).write_text(ownership)
    gates = 'build34_exact_callbacks.h'
    (out / gates).write_bytes(inputs['tools/' + gates])
    compiler, otool = (Path(subprocess.check_output(['/usr/bin/xcrun', '--find', tool], text=True, timeout=15).strip()).resolve()
                       for tool in ('clang++', 'otool'))
    base = inputs[BASE_FIXTURE].decode().partition('int main() {')[0]
    fields = ENTRY + once(FIELDS, FIELDS_AT, IOKIT_DECLARATIONS + FIELDS_AT)
    fields = once(fields, '    bool notifyExactEvent(uint32_t queue, uint64_t generation); // deferred context only\n', DECLARATIONS)
    fields += '''    bool modeledIHAdmission = false;
    uint64_t serviceId = 1;
    uint64_t getRegistryEntryID() const { return serviceId; }
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

    def exercise(label, source, sanitizer, modeled, broken=False, fixture_fields=fields):
        methods = [method(source, signature) for signature in METHODS]
        if modeled:
            index = METHODS.index(ADMIT)
            methods[index] = once(methods[index], 'return false;', 'return modeledIHAdmission;')
        fixture = once(base, '// PHX34_EVENT_METHODS', DOUBLES + '\n'.join(methods))
        if fixture_fields != fields:
            fixture = once(fixture, fields, fixture_fields)
        fixture += inputs[FIXTURE].decode()
        code, binary = out / (label + '.cpp'), out / label
        code.write_text(fixture)
        run([compiler, '--driver-mode=g++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
             '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all', '-DMODELED_IH=' + str(int(modeled)),
             code, '-o', binary], label + '-compile')
        if re.search(r'IOKit|Metal|vulkan', run([otool, '-L', binary], label + '-links'), re.I):
            raise ValueError('CPU-only fixture links device interfaces')
        result = run([binary], label + '-test', broken)
        if not broken:
            parsed = re.fullmatch(r'PASS IH ingress: (\d+) checks; modeled=(0|1)\n', result)
            if not parsed or int(parsed[2]) != int(modeled):
                raise ValueError('Incomplete CPU ingress check')
            return int(parsed[1])

    counts = {label: {mode: exercise(label + '-' + mode, proposed, sanitizer, mode == 'modeled')
                      for mode in ('closed', 'modeled')}
              for label, sanitizer in [('asan_ubsan', 'address,undefined'), ('tsan', 'thread')]}
    if counts['asan_ubsan'] != counts['tsan']:
        raise ValueError('Sanitizers did not cover the same CPU cases')
    mutations = {
        'bypass-admission': ('exactIHIngressAdmitted() && ', '', False),
        'accept-tagged-MES-vector': (' || (vector[19] & 1)', '', True),
        'swap-native-queue-indices': ('ring == 0x04 ? 0 : 1', 'ring == 0x04 ? 1 : 0', True),
        'accept-other-service': (' && route.service == exactIHRoute.service', '', True),
        'accept-other-generation': ('route.generation[0] == exactIHRoute.generation[0] && ', '', True),
        'accept-other-peer-generation': ('route.generation[1] == exactIHRoute.generation[1];', 'true;', True),
        'accept-old-route': (' && route.epoch == exactIHRoute.epoch', '', True),
        'rearm-after-stream-loss': ('exactIHState == ExactIHState::Empty &&',
                                    'exactIHState != ExactIHState::Active && exactIHState != ExactIHState::Retiring &&', True),
        'rearm-before-old-route-drain': ('exactIHState == ExactIHState::Empty &&',
                                         'exactIHState != ExactIHState::Active && exactIHState != ExactIHState::Lost &&', True),
        'admit-batch-from-nonactive-route': ('return exactIHRouteMatches(route) && exactIHState == ExactIHState::Active &&',
                                            'return exactIHRouteMatches(route) &&', True),
        'ignore-loss-during-retirement': (' ||\n        exactIHState == ExactIHState::Retiring', '', True),
        'erase-retiring-identity': ('exactIHState = ExactIHState::Retiring;',
                                     'exactIHRoute = {}; exactIHState = ExactIHState::Retiring;', True),
        'accept-wrapped-replay': ('batch.ordinal != exactIHBatchOrdinal + 1 || ', '', True),
        'skip-consumer-cursor': ('batch.read != exactIHNext || ', '', True),
        'accept-unstable-writeback': ('batch.before != batch.after || ', '', True),
        'accept-invalid-producer-cursor': (' || !validExactIHCursor(batch.before, exactIHRingSize)', '', True),
        'accept-incomplete-batch': ('batch.count != expected', 'batch.count > expected', True),
        'jump-over-partial-batch': ('exactIHNext = (batch.read + batch.count * kExactIHEntryBytes) & (exactIHRingSize - 1);',
                                    'exactIHNext = batch.before;', True),
        'wake-twice-for-same-queue': ('!(queueMask & bit) && ', '', True),
        'skip-post-copy-route-validation': ('if (exactIHRouteLiveLocked(route)) {', 'if (true) {', True),
        'declare-worker-drained-at-close': ('exactIHWorker.drained()', 'exactIHWorker.closed()', True),
        'omit-worker-gate-close': ('    exactIHWorker.close();\n', '', True),
        'drain-other-route': ('exactIHRouteMatches(route) && exactIHWorker.drained()',
                              '(static_cast<void>(route), exactIHWorker.drained())', True),
        'lose-inline-signal-on-activation': ('kick = (__atomic_fetch_or(&exactIHSignals, kIHEnabled, __ATOMIC_ACQ_REL) & kIHPending) != 0;',
                                             '__atomic_fetch_or(&exactIHSignals, kIHEnabled, __ATOMIC_ACQ_REL);', True),
        'kick-while-arming': ('== kIHEnabled;\n}', '== (previous & kIHEnabled);\n}', True),
        'ignore-callback-close-in-signal': ('!= kIHPublished || exactCallbacks.closed() ||', '!= kIHPublished ||', True),
        'leave-signal-open-on-retire': ('    __atomic_fetch_or(&exactIHSignals, kIHClosed, __ATOMIC_ACQ_REL);\n', '', True),
        'leave-worker-open-when-arming': ('exactIHState != ExactIHState::Arming && exactIHState != ExactIHState::Active',
                                          'exactIHState != ExactIHState::Active', True),
        'kick-while-collector-busy': ('(kIHEnabled | kIHPending | kIHClosed | kIHCollecting)', '(kIHEnabled | kIHPending | kIHClosed)', True),
        'consume-before-worker-admission': ('if (!worker) {\n', 'if (!worker) {\n            __atomic_fetch_and(&exactIHSignals, ~kIHPending, __ATOMIC_ACQ_REL);\n', True),
        'omit-partial-batch-repost': (' && exactIHNext != batch.before', ' && false', True),
        'omit-worker-repost': ('&& exactIHRouteLiveLocked(route);\n', '&& false;\n', True),
        'collect-without-signal': ('& kIHPending) {', '& (kIHPending | kIHCollecting)) {', True),
    }
    for label, (old, new, modeled) in mutations.items():
        exercise(label, once(proposed, old, new), 'address,undefined', modeled, True)
    exercise('allow-concurrent-IH-workers', proposed, 'address,undefined', True, True,
             once(fields, 'CallbackGate<1> exactIHWorker', 'CallbackGate<2> exactIHWorker'))
    with patch.object(native_objects, 'HEADERS', header_names):
        native = native_objects.check(out / 'native', inputs, previous, proposed, ownership, sdk, kdk,
                                      reference['native_import_count'],
                                      json.loads(inputs[FACTORY_RECORD])['compiler_warnings']['proposed'],
                                      json.loads(inputs[KDK_RECORD]), compiler)
    git('diff', '--quiet', BASE, '--', *PROTECTED)
    if any((ROOT / name).read_bytes() != blob for name, blob in inputs.items()):
        raise ValueError('Inputs changed during verification')
    result = dict(status='passed-offline-IH-signal-handoff', build=34, checks=counts,
                  rejected_mutants=[*mutations, 'allow-concurrent-IH-workers'], staged_source_sha256=sha(proposed.encode()),
                  previous_source_sha256=sha(previous.encode()), protected_production_inputs=len(production),
                  max_entries_per_batch=32, native_ring_consumer_bound=False,
                  max_concurrent_capture_workers=1, worker_drain_is_not_device_or_ISR_drain=True,
                  inline_signal_latched_before_activation=True, pending_signal_survives_busy=True,
                  partial_batch_requests_deferred_kick=True, native_irq_scheduler_bound=False,
                  hold_rearm_until_old_route_drain=True, old_writer_drain_proved=False,
                  native_event_backend_bound=False, native_open_admitted=False, IH_accessed=False,
                  ISR_registered=False, GPU_executed=False, R3_complete=False, **native)
    (out / 'result-private.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('out', 'sdk', 'kdk'):
        parser.add_argument('--' + option, required=True)
    args = parser.parse_args()
    print(json.dumps(test(args.out, args.sdk, args.kdk), indent=2))
