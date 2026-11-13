"""Execute actual allocation-refusal diagnostics with CPU-only OS/device fakes."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess

from test_bo_retirement import extract_source as extract_busy, check_result
from test_bo_create import extract_source as extract_host, extract_state

ROOT = Path(__file__).resolve().parents[1]
BUSY_CASES = (
    'map-pending', 'unmap-pending', 'map-invalid', 'unmap-invalid',
    'map-other-queue-pending', 'map-other-queue-invalid', 'map-invalid-short-circuit',
    'map-snapshot-once', 'map-late-completion', 'map-zero-sequence-silent',
    'map-not-ready-silent', 'reclaim-silent', 'pending-overlap', 'pending-overlap-cap',
    'ordinary-overlap-silent', 'retirement-cap-matrix', 'independent-context-cap',
    'diagnostic-sample-saturation', 'bo-lifetime-unchanged', 'snapshot-context-reuse',
) + tuple('progress-' + reason for reason in (
    'missing-output', 'no-aperture', 'inactive', 'unaligned-fence', 'history-overflow',
    'future-floor', 'all-ones-fence', 'regressed-fence', 'future-fence', 'zero-sequence',
    'nonmonotonic-sequence', 'future-sequence', 'unknown-fence', 'pending', 'complete'))
HOST_CASES = (
    'host-protection', 'host-unknown-result', 'host-descriptor', 'host-budget-silent',
    'host-invalid-silent', 'host-cap-stages', 'host-independent-client',
    'host-success-after-failure', 'host-success-silent',
)


def extract(source):
    constants, shared, declarations, maps, methods, _ = extract_busy(source)
    host = extract_host(source)
    structures = re.findall(r'^struct PhxClientBo \{.*?^\};', host, re.M | re.S)
    if len(structures) != 1:
        raise RuntimeError('Expected actual host BO structure')
    return {
        'bo-constants.inc': constants, 'bo-shared.inc': shared,
        'bo-structures.inc': declarations, 'bo-maps.inc': maps, 'bo-methods.inc': methods,
        'bo-struct.inc': structures[0], 'bo-state.inc': extract_state(source),
        'host-methods.inc': host.replace(structures[0], '', 1),
    }


def exercise(out):
    compiler = shutil.which('clang++')
    if platform.system() not in ('Linux', 'Darwin') or not compiler:
        raise RuntimeError('Allocation diagnostic tests require POSIX Clang; not kernel execution')
    out = Path(out).resolve()
    if out.exists():
        raise RuntimeError('Allocation diagnostic output exists; choose a fresh directory')
    source = ROOT / 'src/phxbringup/PhxBringup.cpp'
    fragments = extract(source.read_text(encoding='utf-8'))
    busy = out / 'busy'; host = out / 'host'
    busy.mkdir(parents=True); host.mkdir()
    for name, text in fragments.items():
        if name in ('bo-struct.inc', 'bo-state.inc', 'host-methods.inc'):
            (host / ('bo-methods.inc' if name == 'host-methods.inc' else name)).write_text(text + '\n', encoding='utf-8')
        else:
            (busy / name).write_text(text + '\n', encoding='utf-8')
    rows = []
    for directory, harness, cases in ((busy, 'test_allocation_diagnostic.cpp', BUSY_CASES),
                                      (host, 'test_host_import_diagnostic.cpp', HOST_CASES)):
        binary = directory / 'diagnostic-test'
        subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-g',
                        '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                        '-I' + str(directory), '-I' + str(ROOT / 'src/phxbringup'),
                        str(ROOT / 'tests' / harness), '-o', str(binary)], check=True, timeout=120)
        rows.extend(check_result(subprocess.run([str(binary), case], capture_output=True,
                                               text=True, timeout=15), case) for case in cases)
    inputs = [source, ROOT / 'src/phxbringup/PhxAllocationDiagnostic.hpp',
              ROOT / 'src/phxbringup/PhxAllocationSnapshot.h',
              ROOT / 'src/phxbringup/PhxNativeABI.h', ROOT / 'src/phxbringup/PhxHardwarePolicy.hpp',
              ROOT / 'src/phxbringup/PhxBoPolicy.hpp',
              *(ROOT / 'tests' / name for name in ('test_bo_retirement.cpp', 'test_bo_create.cpp',
                                                  'test_allocation_diagnostic.cpp', 'test_host_import_diagnostic.cpp'))]
    result = {
        'cases': rows, 'hardware_executed': False, 'kernel_loaded': False,
        'actual_fragments_sha256': {name: hashlib.sha256(text.encode()).hexdigest() for name, text in fragments.items()},
        'inputs_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        'limitation': ('Actual queue validator, retirement, VM mutation guard, map/unmap, pending overlap and host-import methods, '
                       'with actual diagnostic state/header. CPU fakes for descriptors, locks, page tables, registers and device completion. '
                       'No real pinning, GPU progress, kernel logging persistence, concurrent hardware or desktop acceptance.'),
    }
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    exercise(parser.parse_args().out)
