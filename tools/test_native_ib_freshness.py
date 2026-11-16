"""Simulate the two-policy IB diagnostic with fake IOKit; never open a device."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess

from prepare_source import ROOT, prepare
from test_native_shader_probe import CASES as BASE_CASES, CHECK, expected_result

EXTRA_CASES = tuple(f'wait-{stage}-pending-{kind}' for stage in (1, 2) for kind in ('short', 'cap')) + (
    'stale-output-2', 'stale-ib-fetch-2', 'legacy-run') + tuple(f'slot-{word}' for word in range(80))
CASES = BASE_CASES + EXTRA_CASES


def marker(policy):
    if policy not in ('reuse', 'fresh'):
        raise ValueError('Unknown IB policy')
    return f'DIAGNOSTIC-PASS: IB policy={policy}; two guarded dispatches; no driver or display acceptance'


def expected(fault, policy):
    marker(policy)
    if fault not in CASES:
        raise ValueError('Unknown IB diagnostic case')
    if fault == 'legacy-run':
        return 64, []
    base = fault
    if fault.startswith('slot-') or fault == 'stale-output-2':
        base = 'output-2-0'
    elif fault == 'stale-ib-fetch-2':
        base = 'ok' if policy == 'fresh' else 'output-2-0'
    elif fault in EXTRA_CASES:
        base = 'ok'
    code, events = expected_result(base)
    events = list(events)
    # The diagnostic uses zero/short/capped waits. A pending response may never
    # authorize another dispatch or cleanup; all three timeout calls still fail.
    for stage in (1, 2):
        count = 3 if fault in (f'wait-{stage}-timeout', f'wait-{stage}-pending-cap') else (
            2 if fault == f'wait-{stage}-pending-short' else 1)
        name = f'wait-{stage}'
        if name in events:
            index = events.index(name)
            events[index:index + 1] = [name] * count
    # Only exercise failures go into HOLD. Successful-result cleanup failures
    # retain the adapter's existing cleanup trace; release failures before HELLO
    # have submitted nothing and follow its check-only close path.
    if code and 'hello' in events and 'gpu-unmap' not in events and fault != 'cpu-unmap-status':
        assert events[-1] == 'close'
        events.pop()
        if events[-1] == 'cpu-unmap':
            events.pop()
        events.append('hold')
    return code, events


def check_result(result, fault, policy):
    code, events = expected(fault, policy)
    prefix = 'fake-native-shader-summary '
    if result.returncode != code or result.stderr.count(prefix) != 1:
        raise RuntimeError(f'IB diagnostic case {policy}/{fault} failed: code {result.returncode}, wanted {code}')
    transcript = json.loads(result.stderr.split(prefix)[1].strip())
    if transcript != {'events': events}:
        raise RuntimeError(f'IB diagnostic trace mismatch: {policy}/{fault}')
    lines = result.stdout.splitlines()
    if code:
        if 'DIAGNOSTIC-PASS:' in result.stdout or CHECK in result.stdout:
            raise RuntimeError('Failed diagnostic printed success')
    elif fault == 'check-ok':
        if lines != [CHECK]:
            raise RuntimeError('Readiness check changed scope')
    else:
        if not lines or lines[-1] != marker(policy) or result.stdout.count('DIAGNOSTIC-PASS:') != 1:
            raise RuntimeError('Missing or false diagnostic marker')
    if bool('HOLD:' in result.stderr) != ('hold' in events):
        raise RuntimeError('Missing or spurious resource HOLD')
    if 'hold' in events and any(event in events for event in ('cpu-unmap', 'gpu-unmap', 'free', 'ctx-free', 'close')):
        raise RuntimeError('Exercise failure continued into cleanup')
    waits = [json.loads(line) for line in lines if line.startswith('{')]
    if len(waits) != sum(event.startswith('wait-') for event in events):
        # Transport failures return before writing a wait observation.
        unlogged = 1 if fault.startswith('wait-') and fault.endswith(('-status', '-short', '-long')) else 0
        if len(waits) + unlogged != sum(event.startswith('wait-') for event in events):
            raise RuntimeError('Wait observation accounting mismatch')
    for row in waits:
        if set(row) != {'pass', 'budget_ns', 'busy', 'elapsed_ns'} or row['pass'] not in (0, 1) or row['busy'] not in (0, 1) or row['elapsed_ns'] != 4000:
            raise RuntimeError('Invalid simulated wait observation')
    for stage in range(2):
        rows = [row for row in waits if row['pass'] == stage]
        if [row['budget_ns'] for row in rows] != [0, 50000, 2000000000][:len(rows)]:
            raise RuntimeError('Wait budget order changed')
    if not code and fault != 'check-ok':
        for stage in range(2):
            rows = [row for row in waits if row['pass'] == stage]
            if not rows or rows[-1]['busy'] or any(not row['busy'] for row in rows[:-1]):
                raise RuntimeError('Missing positive retirement or continued wait')
    if fault.startswith('slot-'):
        offset = 0x1200 + int(fault[5:]) * 4
        if f'mismatch at byte {offset} (pass=1 ' not in result.stderr:
            raise RuntimeError('Inactive/pre-staged IB was not guarded')
    if fault == 'stale-output-2' or (fault == 'stale-ib-fetch-2' and policy == 'reuse'):
        if 'mismatch at byte 8208 (pass=1 actual=0xde expected=0xdf)' not in result.stderr:
            raise RuntimeError('Stale-pattern injection was not rejected')
    return {'events': events, 'wait_observations': waits}


def exercise(out):
    compiler = shutil.which('clang++')
    if not compiler or platform.system() == 'Windows':
        raise RuntimeError('IB diagnostic simulation requires POSIX Clang++; no hardware test')
    out = Path(out).resolve()
    if out.exists():
        raise RuntimeError('IB diagnostic output exists; choose a fresh directory')
    stage = out / 'stage'
    provenance = prepare(stage)
    binary = out / 'ib-freshness-simulation'
    subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-g', '-fsanitize=address,undefined',
        '-fno-sanitize-recover=all', '-DPHX_IB_FRESHNESS_DIAGNOSTIC',
        '-I' + str(ROOT / 'tests/fake_native_iokit'), '-I' + str(stage / 'src/phxbringup'),
        '-I' + str(stage / 'tools/phxctl'), str(ROOT / 'tests/test_native_shader_probe.cpp'),
        '-o', str(binary)], check=True, timeout=120)
    results = []
    for variant in ('low', 'upper'):
        for policy in ('reuse', 'fresh'):
            for fault in CASES:
                result = subprocess.run([str(binary), variant, fault, policy], capture_output=True, text=True, timeout=15)
                results.append({'variant': variant, 'policy': policy, 'case': fault, **check_result(result, fault, policy)})
    paths = ('tools/native_ib_freshness_probe.cpp', 'tools/test_native_ib_freshness.py',
             'tests/test_native_shader_probe.cpp', 'tests/fake_native_iokit/mach/mach_time.h',
             'src/phxbringup/PhxNativeABI.h', 'tools/phxctl/gfx11_shader_probe.h')
    report = {'source_provenance': provenance, 'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths},
        'cases': results, 'hardware_executed': False, 'shader_executed': False, 'native_iokit_linked': False,
        'limitation': 'Fake IOKit, synthetic clock and injected GPU results/cache models. No ISA, real cache coherence, GPUVM or hardware validation.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'result': 'passed', 'scenarios': len(results), 'cases_per_policy_and_VA': len(CASES),
        'hardware_executed': False, 'shader_executed': False}), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    exercise(parser.parse_args().out)
