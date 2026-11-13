"""Exercise the actual native dispatcher diagnostic with explicit CPU-only API fakes."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def extract(source):
    definitions = re.findall(
        r'^IOReturn IOAccelPhxNativeClient::externalMethod\([^)]*\) \{.*?^\}\n',
        source, re.M | re.S)
    declarations = re.findall(r'^    bool submitFailureLogged\{false\};[^\n]*$', source, re.M)
    if len(definitions) != 1 or len(declarations) != 1:
        raise RuntimeError('Expected one actual native dispatcher and diagnostic latch declaration')
    return definitions[0], declarations[0] + '\n'


def exercise(out):
    compiler = shutil.which('clang++')
    if platform.system() not in ('Linux', 'Darwin') or not compiler:
        raise RuntimeError('Submission diagnostic tests require POSIX Clang; not kernel execution')
    out = Path(out).resolve()
    if out.exists():
        raise RuntimeError('Submission diagnostic output exists; choose a fresh directory')
    source = ROOT / 'src/phxbringup/PhxBringup.cpp'
    method, state = extract(source.read_text(encoding='utf-8'))
    out.mkdir(parents=True)
    (out / 'submit-diagnostic-method.inc').write_text(method, encoding='utf-8')
    (out / 'submit-diagnostic-state.inc').write_text(state, encoding='utf-8')
    binary = out / 'submit-diagnostic-test'
    subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-g',
                    '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                    '-I' + str(out), '-I' + str(ROOT / 'src/phxbringup'),
                    str(ROOT / 'tests/test_submit_diagnostic.cpp'), '-o', str(binary)],
                   check=True, timeout=120)
    process = subprocess.run([str(binary)], capture_output=True, text=True, check=True, timeout=30)
    result = json.loads(process.stdout)
    expected = {'cases': 72, 'non_submit_dispatch_paths': 30,
                'hardware_executed': False, 'kernel_loaded': False}
    if result != expected or any(type(result[k]) is not type(v) for k, v in expected.items()):
        raise RuntimeError('Unexpected actual-dispatcher diagnostic report')
    result['actual_dispatcher_SHA256'] = hashlib.sha256(method.encode()).hexdigest()
    result['actual_latch_declaration_SHA256'] = hashlib.sha256(state.encode()).hexdigest()
    inputs = [source, ROOT / 'src/phxbringup/PhxNativeABI.h',
              ROOT / 'src/phxbringup/PhxBootMemory.h', ROOT / 'src/phxbringup/PhxPspLayout.h',
              ROOT / 'src/amd/phx_topology.h', ROOT / 'tests/test_submit_diagnostic.cpp']
    result['inputs_SHA256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in inputs}
    result['limitation'] = ('Actual dispatcher and latch declaration; fake locks, logging and all dispatched '
                            'handlers. Checks lock ordering, exact status propagation and per-client log '
                            'limiting. Does not execute real submission, concurrency, IOKit, kernel logging '
                            'persistence, GPU work or a display workload.')
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    exercise(parser.parse_args().out)
