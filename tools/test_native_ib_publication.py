"""Simulate the CPU IB publication diagnostic; never flush a real line or open a device."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess

from prepare_source import ROOT, prepare
from test_native_shader_probe import CHECK
from test_native_ib_freshness import CASES as BASE_CASES, expected as baseline_expected

EXTRA_CASES = ('cpu-no-clflush', 'cpu-line-zero', 'cpu-line-32', 'cpu-line-128',
               'legacy-fresh', 'legacy-reuse', 'stale-ib-cpu-2')
CASES = BASE_CASES + EXTRA_CASES


def marker(policy):
    if policy not in ('control', 'ib-publish'):
        raise ValueError('Unknown CPU IB policy')
    return f'DIAGNOSTIC-PASS: CPU IB policy={policy}; two guarded dispatches; no driver or display acceptance'


def expected(fault, policy):
    marker(policy)
    if fault not in CASES:
        raise ValueError('Unknown CPU IB diagnostic case')
    if fault in ('legacy-fresh', 'legacy-reuse'):
        return 64, []
    if fault.startswith('cpu-') and fault in EXTRA_CASES:
        return 4, ['host', 'cpu-clflush-capability']
    base = ('ok' if policy == 'ib-publish' else 'stale-output-2') if fault == 'stale-ib-cpu-2' else fault
    code, events = baseline_expected(base, 'reuse')
    events = list(events)
    if 'matching' in events:
        events.insert(events.index('matching'), 'cpu-clflush-capability')
    if policy == 'ib-publish' and 'submit-2' in events:
        index = events.index('submit-2')
        events[index:index] = [f'ib-clflush-{n}' for n in range(5)] + ['ib-publication-fence']
    return code, events


def check_result(result, fault, policy):
    code, events = expected(fault, policy)
    prefix = 'fake-native-shader-summary '
    if result.returncode != code or result.stderr.count(prefix) != 1:
        raise RuntimeError(f'CPU IB diagnostic case {policy}/{fault} failed: code {result.returncode}, wanted {code}')
    transcript = json.loads(result.stderr.split(prefix)[1].strip())
    if transcript != {'events': events}:
        raise RuntimeError(f'CPU IB diagnostic trace mismatch: {policy}/{fault}')
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
    if fault == 'stale-output-2' or fault == 'stale-ib-fetch-2' or (fault == 'stale-ib-cpu-2' and policy == 'control'):
        if 'mismatch at byte 8208 (pass=1 actual=0xde expected=0xdf)' not in result.stderr:
            raise RuntimeError('Stale-pattern injection was not rejected')
    return {'events': events, 'wait_observations': waits}


def exercise(out):
    compiler = shutil.which('clang++')
    if not compiler or platform.system() == 'Windows':
        raise RuntimeError('CPU IB diagnostic simulation requires POSIX Clang++; no hardware test')
    out = Path(out).resolve()
    if out.exists():
        raise RuntimeError('CPU IB diagnostic output exists; choose a fresh directory')
    stage = out / 'stage'
    provenance = prepare(stage)
    binary = out / 'ib-publication-simulation'
    subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-g', '-fsanitize=address,undefined',
        '-fno-sanitize-recover=all', '-DPHX_IB_CPU_PUBLICATION_DIAGNOSTIC',
        '-I' + str(ROOT / 'tests/fake_native_iokit'), '-I' + str(stage / 'src/phxbringup'),
        '-I' + str(stage / 'tools/phxctl'), str(ROOT / 'tests/test_native_shader_probe.cpp'),
        '-o', str(binary)], check=True, timeout=120)
    results = []
    for variant in ('low', 'upper'):
        for policy in ('control', 'ib-publish'):
            for fault in CASES:
                result = subprocess.run([str(binary), variant, fault, policy], capture_output=True, text=True, timeout=15)
                results.append({'variant': variant, 'policy': policy, 'case': fault, **check_result(result, fault, policy)})
    paths = ('tools/native_ib_publication_probe.cpp', 'tools/test_native_ib_publication.py',
             'tools/phxctl/ib_publication_arch.h', 'tests/fake_native_iokit/ib_publication_arch.h',
             'tests/test_native_shader_probe.cpp', 'tests/fake_native_iokit/mach/mach_time.h',
             'src/phxbringup/PhxNativeABI.h', 'tools/phxctl/gfx11_shader_probe.h')
    report = {'source_provenance': provenance, 'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths},
        'cases': results, 'hardware_executed': False, 'shader_executed': False, 'native_iokit_linked': False,
        'CPU_cache_operations_mocked': True,
        'limitation': 'Fake IOKit, CPU capabilities/cache-operation trace, synthetic clock and injected result/cache models. No ISA, real CLFLUSH/MFENCE, cache coherence, GPUVM or hardware validation.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'result': 'passed', 'scenarios': len(results), 'cases_per_policy_and_VA': len(CASES),
        'hardware_executed': False, 'shader_executed': False, 'CPU_cache_operations_mocked': True}), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    exercise(parser.parse_args().out)
