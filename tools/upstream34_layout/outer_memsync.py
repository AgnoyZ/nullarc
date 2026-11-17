#!/usr/bin/env python3
"""CPU-only original34 outer-ring NOP/ACQUIRE comparison; never build a kext."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess

if __package__:
    from . import mec_range, ring_padding
else:
    import mec_range
    import ring_padding

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL_SOURCE_SHA = 'beffab5dc13e4018ff2ab9f90c82d85c0982ce7e3563e3175999399c7bc083e5'
POLICIES = ('original', 'nop-prefix', 'acquire-prefix')
NOP = (0xc0061000, 0, 0, 0, 0, 0, 0, 0)
ACQUIRE = (0xc0065800, 0, 0xffffffff, 0x00ffffff, 0, 0, 10, 0xc3b1)
OLD_NEED = '    const uint32_t need = n * 4 + 8;\n'
NEW_NEED = '    const uint32_t need = n * 4 + 8 + (q.gfx ? 0u : 8u);\n'
OLD_START = '    uint32_t k = 0;\n'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def transform(function, policy):
    if sha(function.encode()) != ring_padding.FUNCTION_SHA:
        raise ValueError('Original34 submit drift; refuse transformation')
    if policy not in POLICIES:
        raise ValueError('Unknown outer-ring comparison policy')
    if policy == 'original':
        return function
    if function.count(OLD_NEED) != 1 or function.count(OLD_START) != 1:
        raise ValueError('Ambiguous outer-ring insertion sites')
    words = NOP if policy == 'nop-prefix' else ACQUIRE
    start = OLD_START + '    if (!q.gfx) {\n' + ''.join(
        '        ringPut(q, k++, 0x%08xu);\n' % word for word in words) + '    }\n'
    changed = function.replace(OLD_NEED, NEW_NEED).replace(OLD_START, start)
    if changed.replace(NEW_NEED, OLD_NEED).replace(start, OLD_START) != function:
        raise ValueError('Change outside the two reviewed sites')
    return changed


def candidate_source(original, policy):
    if sha(original) != ORIGINAL_SOURCE_SHA:
        raise ValueError('Original34 complete source drift')
    text = original.decode()
    function = ring_padding.extract(text)
    changed = transform(function, policy)
    if text.count(function) != 1:
        raise ValueError('Ambiguous complete-source replacement')
    result = text.replace(function, changed).encode()
    if result.decode().replace(changed, function).encode() != original:
        raise ValueError('Source outside submit changed')
    return result


def exercise(destination):
    if platform.machine() not in ('x86_64', 'AMD64'):
        raise RuntimeError('Actual original34 function requires x86 CPU fences')
    compiler = shutil.which('clang++')
    if not compiler:
        raise RuntimeError('Requires Clang++; no kernel build is supported')
    destination = Path(destination).resolve()
    if ROOT / 'build' not in destination.parents or destination.exists():
        raise ValueError('Use a fresh private CPU destination inside worktree build')
    protected = mec_range.verify_current_inputs(mec_range.protected_base_inputs(), ROOT)
    paths = [Path(__file__).resolve(), ROOT / 'tests/test_build34_outer_memsync.cpp',
             ROOT / 'tests/test_upstream34_outer_memsync.py',
             ROOT / 'tools/upstream34_layout/ring_padding.py',
             ROOT / 'tools/upstream34_layout/mec_range.py']
    snapshots = {p: p.read_bytes() for p in paths}
    original = (ROOT / 'src/phxbringup/PhxBringup.cpp').read_bytes()
    function = ring_padding.extract(original.decode())
    template = snapshots[paths[1]].decode()
    marker = '// PHX34_EXTRACTED_GPU_SUBMIT_FUNCTION'
    if template.count(marker) != 1:
        raise ValueError('CPU fixture marker drift')
    destination.mkdir(parents=True, mode=0o700)
    results = {}
    for number, policy in enumerate(POLICIES):
        body = transform(function, policy)
        source = destination / (policy + '.cpp')
        source.write_text(template.replace(marker, body))
        binary = destination / (policy + '-CPU-only')
        argv = [compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-g',
                '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                '-DPHX34_CPU_PREFIX=' + str(number),
                '-I' + str(ROOT / 'src/phxbringup'), str(source), '-o', str(binary)]
        subprocess.run(argv, check=True, stdin=subprocess.DEVNULL, timeout=90)
        if platform.system() == 'Darwin':
            linked = subprocess.check_output(['/usr/bin/otool', '-L', str(binary)], text=True, timeout=15)
            if 'IOKit.framework' in linked or 'CoreFoundation.framework' in linked:
                raise RuntimeError('CPU fixture linked a real device framework')
        run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120,
                             stdin=subprocess.DEVNULL, check=True)
        if run.stderr:
            raise RuntimeError('CPU fixture diagnostics retained in private output')
        row = json.loads(run.stdout)
        if row['policy'] != policy or not row['passed'] or row['GPU_executed']:
            raise RuntimeError('Unexpected CPU fixture result')
        results[policy] = row
        print(json.dumps(row), flush=True)
    mec_range.verify_current_inputs(mec_range.protected_base_inputs(), ROOT)
    if any(p.read_bytes() != data for p, data in snapshots.items()):
        raise RuntimeError('CPU recipe/fixture changed during verification')
    report = {
        'result': 'passed', 'base_commit': mec_range.BASE,
        'original_gpuSubmit_sha256': ring_padding.FUNCTION_SHA,
        'function_sha256': {policy: sha(transform(function, policy).encode()) for policy in POLICIES},
        'complete_source_sha256': {policy: sha(candidate_source(original, policy)) for policy in POLICIES},
        'prefix_dwords': 8, 'position': 'outer compute ring before all user IB descriptors',
        'graphics_changed': False, 'release_mem_remains_last': True,
        'equal_footprint_NOP_control': True, 'policies': results,
        'production_protected_sha256': protected,
        'recipe_sha256': {str(p.relative_to(ROOT)): sha(data) for p, data in snapshots.items()},
        'sanitizers': 'ASan/UBSan', 'real_IOKit_linked': False,
        'kernel_built': False, 'production_source_modified': False,
        'installed': False, 'GPU_executed': False, 'hardware_scope_armed': False,
        'limitation': 'Actual extracted submit accounting with CPU fakes. No CP, prefetch, GPU cache, DMA, MMIO or real completion model; no repair acceptance.'}
    (destination / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    exercise(parser.parse_args().out)
