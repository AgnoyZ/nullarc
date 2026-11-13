"""Exercise the actual passive selector/dispatcher and bounded software store on CPU."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from test_submit_diagnostic import extract as extract_dispatcher

ROOT = Path(__file__).resolve().parents[1]


def extract(source):
    methods = [extract_dispatcher(source)[0]]
    for name in ('IOAccelPhxNativeClient::doAllocationSnapshot', 'PhxBringup::recordAllocation',
                 'PhxBringup::copyAllocationSnapshot', 'shape'):
        pattern = r'^(?:static )?[^\n]*\b' + re.escape(name) + r'\([^\n]*\) \{.*?^\}\n'
        found = re.findall(pattern, source, re.M | re.S)
        if len(found) != 1:
            raise RuntimeError('Expected one actual snapshot method: ' + name)
        methods.insert(0, found[0])
    stubs = sorted(set(re.findall(r'\b(do\w+)\(a\)', methods[-1])) - {'doAllocationSnapshot'})
    fragments = {'snapshot-methods.inc': '\n'.join(methods),
                 'snapshot-stubs.inc': '\n'.join('IOReturn ' + name + '(IOExternalMethodArguments *) { assert(false); return kIOReturnBadArgument; }' for name in stubs)}
    for filename, pattern in (
        ('snapshot-state.inc', r'^    PhxAllocationHistory allocationHistory\{\};[^\n]*$'),
        ('snapshot-constants.inc', r'^#define PHX_KEXT_BUILD [^\n]+$'),
    ):
        found = re.findall(pattern, source, re.M)
        if len(found) != 1:
            raise RuntimeError('Expected actual snapshot state/build')
        fragments[filename] = found[0]
    return fragments


def exercise(out):
    out = Path(out).resolve()
    if out.exists():
        raise RuntimeError('Snapshot output exists; choose a fresh directory')
    compiler = shutil.which('clang++')
    if not compiler:
        raise RuntimeError('Snapshot CPU tests require Clang')
    source = ROOT / 'src/phxbringup/PhxBringup.cpp'
    fragments = extract(source.read_text(encoding='utf-8'))
    out.mkdir(parents=True)
    for name, text in fragments.items():
        (out / name).write_text(text + '\n', encoding='utf-8')
    binary = out / 'snapshot-test'
    subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-g',
                    '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                    '-I' + str(out), '-I' + str(ROOT / 'src/phxbringup'),
                    str(ROOT / 'tests/test_allocation_snapshot.cpp'), '-o', str(binary)], check=True, timeout=120)
    completed = subprocess.run([str(binary)], capture_output=True, text=True, check=True, timeout=30)
    result = json.loads(completed.stdout)
    if result != {'cases': 30, 'passed': True, 'hardware_executed': False, 'kernel_loaded': False}:
        raise RuntimeError('Unexpected snapshot test result: ' + str(result))
    reader = out / 'reader-test'
    subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-g',
                    '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                    '-I' + str(ROOT / 'tests/fake_native_iokit'),
                    str(ROOT / 'tests/test_allocation_snapshot_reader.cpp'), '-o', str(reader)], check=True, timeout=120)
    reader_cases = ('empty', 'samples', 'no-service', 'open-refusal', 'request-refusal', 'close-refusal',
                    'short', 'long', 'scalars', 'version', 'reasons', 'capacity', 'arguments',
                    'bad-count', 'bad-total', 'bad-record', 'bad-queue')
    for case in reader_cases:
        run = subprocess.run([str(reader), case], capture_output=True, text=True, check=True, timeout=15)
        if case in ('empty', 'samples'):
            reply = json.loads(run.stdout)
            assert reply['version'] == 1 and reply['kext_build'] == 37 and len(reply['reasons']) == 7
            assert reply['observed'] == (0 if case == 'empty' else 21)
            if case == 'samples':
                invalid = reply['reasons'][1]['records'][0]
                assert invalid['status_hex'] == '0xe00002d5' and invalid['retired'] == 0 and not invalid['observation_valid']
                assert invalid['queues'][0]['reason'] == 'future-fence' and invalid['queues'][0]['done'] == 6
                assert invalid['queues'][1]['reason'] == 'unobserved' and not invalid['queues'][1]['fence_read']
                imports = reply['reasons'][6]
                assert imports['count'] == 20 and len(imports['records']) == 4
                assert all(r['status'] == 2 and r['bytes'] == 4096 for r in imports['records'])
        elif run.stdout:
            raise RuntimeError('Refused reader must not publish JSON')
    result['reader_cases'] = len(reader_cases)
    inputs = [source, ROOT / 'src/phxbringup/PhxAllocationDiagnostic.hpp',
              ROOT / 'src/phxbringup/PhxAllocationSnapshot.h', ROOT / 'src/phxbringup/PhxNativeABI.h',
              ROOT / 'tests/test_allocation_snapshot.cpp', ROOT / 'tests/test_allocation_snapshot_reader.cpp',
              ROOT / 'tests/fake_native_iokit/IOKit/IOKitLib.h', ROOT / 'tools/allocation_snapshot.cpp', Path(__file__)]
    result['inputs_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    result['fragments_sha256'] = {name: hashlib.sha256(text.encode()).hexdigest() for name, text in fragments.items()}
    result['limitation'] = ('Actual dispatcher, snapshot checks, service wrappers and history header; fake locks, '
                            'privilege/lifecycle flags and non-snapshot handlers. No real concurrency, kernel load, '
                            'GPU access, persistence over reboot or display acceptance.')
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    exercise(parser.parse_args().out)
