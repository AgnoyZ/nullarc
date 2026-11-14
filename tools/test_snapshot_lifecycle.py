"""Join the real snapshot reader and client lifecycle across explicit OS fakes."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CASES = ('empty', 'samples', 'existing-session', 'foreign-reservation', 'unprivileged',
         'missing-gpu-lock', 'base-init-failure', 'client-allocation-failure',
         'lock-allocation-failure', 'buffer-allocation-failure', 'maps-allocation-failure',
         'attach-failure', 'start-failure', 'destructor-only', 'repeat-close', 'repeated-readers')


def unique(source, pattern):
    matches = re.findall(pattern, source, re.M | re.S)
    if len(matches) != 1:
        raise RuntimeError('Snapshot lifecycle source missing or ambiguous: ' + pattern)
    return matches[0]


def extract(source):
    methods = []
    for klass, names in (
        ('PhxBringup', ('newUserClient', 'claimSession', 'releaseSession', 'copyAllocationSnapshot')),
        ('IOAccelPhxNativeClient', ('initWithTask', 'start', 'freeAll', 'closeResources',
                                  'clientClose', 'free', 'externalMethod', 'doAllocationSnapshot')),
    ):
        for name in names:
            methods.append(unique(source, r'^(?:bool|void|IOReturn) ' + klass + '::' + name +
                                  r'\([^;]*?\) \{(?:[^\n]*\}|.*?^\})(?:\n|$)'))
    methods.insert(0, unique(source, r'^static bool shape\([^;]*?\) \{.*?^\}\n'))
    dispatcher = next(m for m in methods if '::externalMethod(' in m)
    stubs = sorted(set(re.findall(r'\b(do\w+)\(a\)', dispatcher)) - {'doAllocationSnapshot'})
    shared = [unique(source, r'^struct ' + name + r' \{.*?^\};')
              for name in ('PhxClientBo', 'PhxRetiredBuffers')]
    client = unique(source, r'^class IOAccelPhxNativeClient : public IOUserClient \{.*?^\};')
    return {
        'lifecycle-methods.inc': '\n'.join(methods),
        'lifecycle-shared.inc': '\n'.join(shared),
        'lifecycle-client.inc': unique(client, r'^    using Bo = PhxClientBo;.*?^    \};') + '\n' +
            unique(client, r'^    PhxBringup \*owner\{nullptr\};.*?^    uint64_t pendFenceSeq\{0\};'),
        'lifecycle-state.inc': unique(source, r'^    volatile SInt32 sessionOpen\{0\};') + '\n' +
            unique(source, r'^    PhxAllocationHistory allocationHistory\{\};[^\n]*'),
        'lifecycle-constants.inc': unique(source, r'^#define PHX_KEXT_BUILD [^\n]+') + '\n' +
            unique(source, r'^static constexpr int kMaxMaps = [^\n]+;'),
        'lifecycle-stubs.inc': '\n'.join('IOReturn ' + name + '(IOExternalMethodArguments *) '
            '{ forbidden("non-snapshot dispatcher"); return kIOReturnUnsupported; }' for name in stubs),
    }


def compile_harness(out):
    compiler = shutil.which('clang++')
    if not compiler:
        raise RuntimeError('Snapshot lifecycle CPU tests require Clang')
    binary = out / 'snapshot-lifecycle-test'
    result = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-g',
        '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
        '-I' + str(out), '-I' + str(ROOT / 'src/phxbringup'),
        '-I' + str(ROOT / 'tests/fake_native_iokit'),
        str(ROOT / 'tests/test_snapshot_lifecycle.cpp'), '-o', str(binary)],
        capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError('Snapshot lifecycle compile failed: ' + result.stderr)
    return binary


def exercise(out):
    out = Path(out).resolve()
    if out.exists():
        raise RuntimeError('Snapshot lifecycle output exists; choose a fresh directory')
    source = ROOT / 'src/phxbringup/PhxBringup.cpp'
    fragments = extract(source.read_text())
    out.mkdir(parents=True)
    for name, text in fragments.items():
        (out / name).write_text(text + '\n')
    binary = compile_harness(out)
    for case in CASES:
        result = subprocess.run([str(binary), case], capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise RuntimeError('Snapshot lifecycle assertion failed (' + case + '): ' + result.stderr)
        success = case not in ('unprivileged', 'missing-gpu-lock') and not case.endswith('-failure')
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        expected = 2 if case == 'repeated-readers' else int(success)
        if len(rows) != expected:
            raise RuntimeError('Unexpected lifecycle reader output: ' + case)
        for row in rows:
            if row['version'] != 1 or row['observed'] != (1 if case == 'samples' else 0):
                raise RuntimeError('Unexpected lifecycle snapshot: ' + case)
    inputs = [source, ROOT / 'tools/allocation_snapshot.cpp', Path(__file__),
              ROOT / 'tests/test_snapshot_lifecycle.cpp',
              ROOT / 'tests/fake_native_iokit/IOKit/IOKitLib.h',
              ROOT / 'tests/fake_native_iokit/CoreFoundation/CoreFoundation.h',
              ROOT / 'src/phxbringup/PhxAllocationDiagnostic.hpp',
              ROOT / 'src/phxbringup/PhxAllocationSnapshot.h', ROOT / 'src/phxbringup/PhxNativeABI.h']
    report = {'cases': list(CASES), 'passed': True, 'hardware_executed': False, 'kernel_loaded': False,
        'inputs_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        'fragments_sha256': {name: hashlib.sha256(text.encode()).hexdigest() for name, text in fragments.items()},
        'limitation': 'Actual reader, client construction/init/start/default state/dispatcher/snapshot/close/freeAll/free '
            'and provider session/copy methods. IOKit routing, object lifetime, privilege, allocations, locks and '
            'sysctl registration are explicit fakes. GPU/reaper/bootstrap cleanup entry points abort. No kernel, '
            'physical MMIO, real concurrency, timing or target binary identity validation.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report
