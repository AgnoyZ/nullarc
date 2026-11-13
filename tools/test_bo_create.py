"""Run actual BO-create/import methods with host-only allocation and IOKit fakes."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def extract_state(source):
    state = re.findall(r'^    uint8_t allocationFailureLogs\[3\]\{\};[^\n]*$', source, re.M)
    if len(state) != 1:
        raise RuntimeError('Expected actual allocation diagnostic counters')
    return state[0] + '\n'


def extract_source(source):
    parts = []
    patterns = [r'^struct PhxClientBo \{.*?^\};',
                r'^static bool shape\([^\n]*\) \{.*?^\}',
                r'^IOReturn IOAccelPhxNativeClient::doBoCreate\([^\n]*\) \{.*?^\}',
                r'^IOReturn IOAccelPhxNativeClient::doBoImportHost\([^\n]*\) \{.*?^\}']
    for pattern in patterns:
        matches = re.findall(pattern, source, re.M | re.S)
        if len(matches) != 1:
            raise RuntimeError('Expected exactly one actual BO allocation definition: ' + pattern)
        parts.append(matches[0])
    constants = re.findall(r'^static constexpr uint64_t k(?:VisTotal|HiTotal|GttCap|GttMaxBo|HostCap) =[^\n]+', source, re.M)
    if len(constants) != 5:
        raise RuntimeError('Missing actual BO budgets')
    return '\n'.join(constants + parts) + '\n'


def exercise(out):
    compiler = shutil.which('clang++')
    if platform.system() not in ('Linux', 'Darwin') or not compiler:
        raise RuntimeError('BO allocation execution requires POSIX Clang; not a pass on this host')
    out = Path(out).resolve()
    if out.exists():
        raise RuntimeError('Output exists; choose a fresh directory')
    source = ROOT / 'src/phxbringup/PhxBringup.cpp'
    text = source.read_text(encoding='utf-8')
    extracted = extract_source(text)
    state = extract_state(text)
    out.mkdir(parents=True)
    # These methods refer only to this ABI, the policy header and explicit fakes.
    # Read current bytes directly; report hashes rather than silently exporting an older HEAD.
    structure = re.search(r'^struct PhxClientBo \{.*?^\};', extracted, re.M | re.S)[0]
    (out / 'bo-struct.inc').write_text(structure, encoding='utf-8')
    (out / 'bo-state.inc').write_text(state, encoding='utf-8')
    (out / 'bo-methods.inc').write_text(extracted.replace(structure, '', 1), encoding='utf-8')
    binary = out / 'bo-create-test'
    subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                    '-I' + str(out), '-I' + str(ROOT / 'src/phxbringup'),
                    str(ROOT / 'tests/test_bo_create.cpp'), '-o', str(binary)], check=True, timeout=120)
    completed = subprocess.run([str(binary)], capture_output=True, text=True, check=True, timeout=30)
    result = json.loads(completed.stdout)
    if result != {'allocation_cases': 30, 'hardware_executed': False}:
        raise RuntimeError('Unexpected allocation test report')
    inputs = [source, ROOT / 'src/phxbringup/PhxBoPolicy.hpp', ROOT / 'src/phxbringup/PhxNativeABI.h',
              ROOT / 'src/phxbringup/PhxAllocationDiagnostic.hpp',
              ROOT / 'tests/test_bo_create.cpp']
    result['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    result['actual_methods_sha256'] = hashlib.sha256(extracted.encode()).hexdigest()
    result['actual_diagnostic_state_sha256'] = hashlib.sha256(state.encode()).hexdigest()
    result['kernel_loaded'] = False
    result['limitation'] = 'Actual allocation control flow, arithmetic and cleanup; fake allocation, task, pins and locks. No real GPU or kernel-address-space pressure measurement.'
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    exercise(parser.parse_args().out)
