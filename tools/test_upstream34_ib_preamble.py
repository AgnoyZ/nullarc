#!/usr/bin/env python3
"""Run the actual original34 preamble probe with fake IOKit; no GPU execution."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess

from upstream34_layout import mec_range

ROOT = Path(__file__).resolve().parents[1]

PASS = 'PASS: native GPUVM shader probe; two guarded dispatches, not Metal or display acceptance'
CHECK = 'CHECK: target identity and ABI readiness only; no GPU work submitted'


def cases():
    yield from ('ok', 'number-ok', 'create-mappable', 'va-exact', 'check-ok', 'arg-missing', 'arg-mode',
        'arg-option', 'arg-many', 'host-status', 'host-linux', 'host-arm', 'host-sonoma', 'host-prefix',
        'matching-null', 'enumerate-status', 'iterator-null', 'no-service', 'parent-status', 'non-pci',
        'ambiguous', 'mixed-services', 'release-parent', 'release-iterator', 'release-service',
        'release-open-service', 'open-status', 'open-null', 'hello-abi', 'hello-limit', 'hello-vmid',
        'info-abi', 'info-minor', 'info-build', 'info-vmid', 'info-gc', 'info-limit', 'info-hung',
        'info-not-native', 'info-not-ready', 'va-unaligned', 'va-reversed', 'va-short', 'va-hole',
        'va-noncanonical', 'va-null', 'va-wrap', 'va-low-wide', 'ctx-alloc-zero', 'ctx-alloc-wide',
        'ctx-alloc-flags', 'ctx-alloc-id', 'ctx-alloc-priority', 'create-zero', 'create-wide',
        'create-limit', 'create-size', 'create-domain', 'create-unzeroed', 'create-bits', 'cpu-map-zero',
        'cpu-map-unaligned', 'cpu-map-wrap', 'cpu-map-short', 'cpu-map-long', 'cpu-map-status',
        'gpu-map-status', 'cpu-unmap-status', 'gpu-unmap-status', 'free-status', 'close-status',
        'ctx-free-nonzero', 'ctx-free-flags', 'ctx-free-id', 'ctx-free-priority', 'submit-2-repeat')
    for field in ('vendor', 'device'):
        for suffix in ('missing', 'wrong', 'negative', 'wide', 'number-status', 'type', 'short', 'long', 'null'):
            yield f'{field}-{suffix}'
    for operation in ('hello', 'info', 'ctx-alloc', 'create', 'ctx-free', 'submit-1', 'submit-2', 'wait-1', 'wait-2'):
        for suffix in ('status', 'short', 'long'):
            yield f'{operation}-{suffix}'
    for stage in (1, 2):
        for suffix in ('zero', 'last'):
            yield f'submit-{stage}-{suffix}'
        for suffix in ('timeout', 'retired', 'last', 'emitted', 'missing'):
            yield f'wait-{stage}-{suffix}'
        for prefix, count in (('code', 79), ('ib', 80), ('output', 256)):
            for index in range(count): yield f'{prefix}-{stage}-{index}'
        for offset in (316, 4095, 4416, 8191, 8192, 8207, 9232, 12287, 12288, 16383):
            yield f'byte-{stage}-{offset}'


BASE_CASES = tuple(cases())
CASE_SET = frozenset(BASE_CASES)


def baseline_expected(fault):
    if fault not in CASE_SET: raise ValueError('Unknown native probe test case')
    e = []
    if fault.startswith('arg-'): return 64, e
    e.append('host')
    if fault.startswith('host-'): return 4, e
    e.append('matching')
    if fault == 'matching-null': return 4, e
    e.append('enumerate')
    if fault in ('enumerate-status', 'iterator-null'): return 74, e
    if fault == 'no-service': return 4, e + ['release-iterator']
    if fault == 'mixed-services': e += ['parent', 'release-parent', 'release-service']
    e.append('parent')
    if fault == 'parent-status': return 4, e + ['release-service', 'release-iterator']
    if fault == 'non-pci': return 4, e + ['release-parent', 'release-service', 'release-iterator']
    e.append('vendor')
    if fault.startswith('vendor-'):
        if fault == 'vendor-wrong': e.append('device')
        return 4, e + ['release-parent', 'release-service', 'release-iterator']
    e.append('device')
    if fault.startswith('device-'): return 4, e + ['release-parent', 'release-service', 'release-iterator']
    e.append('release-parent')
    if fault == 'ambiguous':
        return 4, e + ['parent', 'vendor', 'device', 'release-parent', 'release-service', 'release-iterator', 'release-service']
    e.append('release-iterator')
    if fault in ('release-parent', 'release-iterator'): return 74, e + ['release-service']
    e += ['open', 'release-service']
    if fault in ('open-status', 'open-null'): return 74, e
    if fault in ('release-service', 'release-open-service'): return 74, e + ['close']
    mapped = False

    def stop(code): return code, e + (['cpu-unmap'] if mapped else []) + ['close']

    def transport(name): return fault in (name + '-status', name + '-short', name + '-long')

    e.append('hello')
    if transport('hello'): return stop(74)
    if fault.startswith('hello-'): return stop(75)
    e.append('info')
    if transport('info'): return stop(74)
    if fault.startswith('info-'): return stop(75)
    if fault == 'check-ok': return stop(0)
    if fault.startswith('va-') and fault != 'va-exact': return stop(75)
    e.append('ctx-alloc')
    if transport('ctx-alloc'): return stop(74)
    if fault.startswith('ctx-alloc-'): return stop(75)
    e.append('create')
    if transport('create'): return stop(74)
    if fault.startswith('create-') and fault != 'create-mappable': return stop(75)
    e.append('cpu-map')
    if fault == 'cpu-map-status': return stop(74)
    mapped = True
    if fault.startswith('cpu-map-'): return stop(75)
    e.append('gpu-map')
    if fault == 'gpu-map-status': return stop(74)
    for stage in (1, 2):
        submit, wait = f'submit-{stage}', f'wait-{stage}'
        e.append(submit)
        if transport(submit): return stop(74)
        if fault.startswith(submit + '-'): return stop(75)
        e.append(wait)
        if transport(wait): return stop(74)
        if fault.startswith(wait + '-') or any(fault.startswith(f'{prefix}-{stage}-') for prefix in ('code', 'ib', 'output', 'byte')):
            return stop(75)
    e.append('cpu-unmap'); mapped = False
    if fault == 'cpu-unmap-status': return stop(74)
    for name in ('gpu-unmap', 'free', 'ctx-free'):
        e.append(name)
        if transport(name): return stop(74)
        if fault.startswith(name + '-'): return stop(75)
    return stop(74 if fault == 'close-status' else 0)


EXTRA_CASES = (
    'legacy-run', 'legacy-fresh', 'legacy-reuse', 'legacy-publish',
    'info-build41', 'info-build42', 'stale-output-2',
) + tuple(f'wait-{stage}-pending-{kind}' for stage in (1, 2) for kind in ('short', 'cap'))
EXTRA_CASES += tuple(f'slot-{word}' for word in range(80))
EXTRA_CASES += tuple(f'preamble-{stage}-{byte}' for stage in (1, 2) for byte in range(32))
CASES = BASE_CASES + EXTRA_CASES
POLICIES = ('single', 'control', 'nop-tail', 'memsync')
EXEC_EQUIVALENCE_CASES = ('ok', 'arg-mode', 'info-build41', 'stale-output-2',
                          'submit-2-status', 'byte-2-16383', 'wait-2-pending-cap', 'check-ok')


def marker(policy):
    if policy not in POLICIES:
        raise ValueError('Unknown preamble policy')
    return f'DIAGNOSTIC-PASS: original34 preamble={policy}; two guarded dispatches; no driver or display acceptance'


def expected(fault):
    if fault not in CASES:
        raise ValueError('Unknown preamble case')
    if fault.startswith('legacy-'):
        return 64, []
    base = fault
    if fault in ('info-build41', 'info-build42'):
        base = 'info-build'
    elif fault.startswith('slot-') or fault == 'stale-output-2':
        base = 'output-2-0'
    elif fault.startswith('preamble-'):
        base = f'ib-{fault.split("-")[1]}-0'
    elif fault in EXTRA_CASES:
        base = 'ok'
    code, events = baseline_expected(base)
    events = list(events)
    for stage in (1, 2):
        count = 3 if fault in (f'wait-{stage}-timeout', f'wait-{stage}-pending-cap') else (
            2 if fault == f'wait-{stage}-pending-short' else 1)
        name = f'wait-{stage}'
        if name in events:
            index = events.index(name)
            events[index:index + 1] = [name] * count
    if code and 'hello' in events and 'gpu-unmap' not in events and fault != 'cpu-unmap-status':
        assert events[-1] == 'close'
        events.pop()
        if events[-1] == 'cpu-unmap':
            events.pop()
        events.append('hold')
    return code, events


def check_result(result, fault, policy):
    code, events = expected(fault)
    prefix = 'fake-native-shader-summary '
    if result.returncode != code or result.stderr.count(prefix) != 1:
        raise RuntimeError(f'Preamble {policy}/{fault}: exit {result.returncode}, wanted {code}: {result.stderr}')
    if json.loads(result.stderr.split(prefix)[1].strip()) != {'events': events}:
        raise RuntimeError(f'Preamble {policy}/{fault}: unexpected continuation')
    if any(word in result.stderr for word in ('AddressSanitizer', 'UndefinedBehaviorSanitizer', 'runtime error:')):
        raise RuntimeError('Sanitizer finding')
    lines = result.stdout.splitlines()
    if code:
        if 'DIAGNOSTIC-PASS:' in result.stdout or CHECK in result.stdout:
            raise RuntimeError('Failed case printed success')
    elif fault == 'check-ok':
        if lines != [CHECK]:
            raise RuntimeError('Readiness check changed scope')
    elif not lines or lines[-1] != marker(policy) or result.stdout.count('DIAGNOSTIC-PASS:') != 1:
        raise RuntimeError('Missing or false diagnostic marker')
    if ('HOLD:' in result.stderr) != ('hold' in events):
        raise RuntimeError('Missing or spurious HOLD')
    if 'hold' in events and any(e in events for e in ('cpu-unmap', 'gpu-unmap', 'free', 'ctx-free', 'close')):
        raise RuntimeError('Exercise failure continued into cleanup')
    waits = [json.loads(line) for line in lines if line.startswith('{')]
    transport_waits = tuple(f'wait-{stage}-{kind}' for stage in (1, 2) for kind in ('status', 'short', 'long'))
    unlogged = int(fault in transport_waits)
    if len(waits) + unlogged != sum(e.startswith('wait-') for e in events):
        raise RuntimeError('Wait accounting mismatch')
    for row in waits:
        if set(row) != {'pass', 'budget_ns', 'busy', 'elapsed_ns'} or row['pass'] not in (0, 1) or row['busy'] not in (0, 1) or row['elapsed_ns'] != 4000:
            raise RuntimeError('Invalid synthetic wait observation')
    for stage in range(2):
        rows = [row for row in waits if row['pass'] == stage]
        if [row['budget_ns'] for row in rows] != [0, 50000, 2000000000][:len(rows)]:
            raise RuntimeError('Wait order changed')
        if not code and fault != 'check-ok' and (not rows or rows[-1]['busy'] or any(not row['busy'] for row in rows[:-1])):
            raise RuntimeError('Missing positive retirement or continued wait')
    if fault == 'stale-output-2' and 'mismatch at byte 8208 (pass=1 actual=0xde expected=0xdf)' not in result.stderr:
        raise RuntimeError('Stale pattern was not rejected')
    if fault.startswith('preamble-'):
        _, stage, byte = fault.split('-')
        if f'mismatch at byte {0x1400 + int(byte)} (pass={int(stage) - 1} ' not in result.stderr:
            raise RuntimeError('Immutable preamble corruption not guarded')
    if fault.startswith('slot-') and f'mismatch at byte {0x1200 + int(fault[5:]) * 4} (pass=1 ' not in result.stderr:
        raise RuntimeError('Unused slot corruption not guarded')
    return {'events': events, 'wait_observations': waits}


def batch_results(result, count):
    """Require complete, matching frames from both streams before checking cases."""
    if result.returncode:
        raise RuntimeError('Mock batch process failed')
    streams = []
    for text in (result.stdout, result.stderr):
        frames = []
        start = 0
        for match in re.finditer(r'^fake-native-case-end (\{[^\n]*\})\n', text, re.MULTILINE):
            meta = json.loads(match[1])
            if (set(meta) != {'index', 'returncode'} or type(meta['index']) is not int or
                    type(meta['returncode']) is not int or meta['index'] != len(frames) or
                    not 0 <= meta['returncode'] <= 255):
                raise RuntimeError('Malformed mock batch frame')
            frames.append((meta, text[start:match.start()]))
            start = match.end()
        if len(frames) != count or start != len(text):
            raise RuntimeError('Incomplete or unframed mock output')
        streams.append(frames)
    parsed = []
    for (out_meta, stdout), (err_meta, stderr) in zip(*streams):
        if out_meta != err_meta:
            raise RuntimeError('Mock stdout/stderr case mismatch')
        parsed.append(subprocess.CompletedProcess([], out_meta['returncode'], stdout, stderr))
    return parsed


def exercise(out):
    compiler = shutil.which('clang++')
    if not compiler or platform.system() not in ('Darwin', 'Linux'):
        raise RuntimeError('Requires POSIX Clang++; not a hardware test')
    out = Path(out).resolve()
    if out.exists():
        raise ValueError('Choose a fresh output directory')
    protected = mec_range.verify_current_inputs(mec_range.protected_base_inputs(), ROOT)
    out.mkdir(parents=True, mode=0o700)
    binary = out / 'preamble-simulation'
    command = [compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-g',
               '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
               '-I' + str(ROOT / 'tests/fake_build34_ib_preamble'),
               '-I' + str(ROOT / 'src/phxbringup'),
               str(ROOT / 'tests/test_build34_ib_preamble.cpp'), '-o', str(binary)]
    subprocess.run(command, check=True, timeout=90, stdin=subprocess.DEVNULL)
    if platform.system() == 'Darwin':
        linked = subprocess.check_output(['/usr/bin/otool', '-L', str(binary)], text=True, timeout=15)
        if 'IOKit.framework' in linked or 'CoreFoundation.framework' in linked:
            raise RuntimeError('Mock binary linked a real device framework')
    results = []
    for variant in ('low', 'upper'):
        for policy in POLICIES:
            batch = subprocess.run([str(binary), '--batch', variant, policy, *CASES], capture_output=True,
                                   text=True, timeout=180, stdin=subprocess.DEVNULL)
            for fault, result in zip(CASES, batch_results(batch, len(CASES))):
                if fault in EXEC_EQUIVALENCE_CASES:
                    separate = subprocess.run([str(binary), variant, fault, policy], capture_output=True,
                                              text=True, timeout=10, stdin=subprocess.DEVNULL)
                    if (separate.returncode, separate.stdout, separate.stderr) != (result.returncode, result.stdout, result.stderr):
                        raise RuntimeError(f'Batch/separate-process behavior differs: {variant}/{policy}/{fault}')
                try:
                    checked = check_result(result, fault, policy)
                except Exception as error:
                    raise RuntimeError(f'Preamble {variant}/{policy}/{fault}: {error}') from error
                results.append({'variant': variant, 'policy': policy, 'case': fault, **checked})
            print(json.dumps({'completed': variant + '/' + policy, 'cases': len(CASES), 'hardware_executed': False}), flush=True)
    paths = [ROOT / name for name in ('tools/upstream34_layout/ib_preamble_probe.cpp',
             'tools/upstream34_layout/ib_preamble_packets.h', 'tools/test_upstream34_ib_preamble.py',
             'tests/test_build34_ib_preamble.cpp')]
    paths += sorted((ROOT / 'tests/fake_build34_ib_preamble').rglob('*.h'))
    record = {'base_commit': mec_range.BASE, 'original34_protected_sha256': protected,
              'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
              'cases': results, 'sanitizers': 'ASan/UBSan', 'hardware_executed': False,
              'native_IOKit_linked': False, 'shader_executed': False,
              'case_isolation': 'reset fake fixture per case; synthetic clock stays monotonic; no per-case fork or exec',
              'separate_process_equivalence_cases': len(EXEC_EQUIVALENCE_CASES) * len(POLICIES) * 2,
              'limitation': 'Fake IOKit/CF, synthetic clock and injected bytes. No GPU ISA, cache/coherency or synchronization emulation; passing memsync is not a hardware result.'}
    (out / 'report.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'result': 'passed', 'scenarios': len(results), 'hardware_executed': False}), flush=True)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    exercise(parser.parse_args().out)
