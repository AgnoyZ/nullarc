#!/usr/bin/env python3
"""Exercise an extracted original34 submit function with CPU fakes, never a kext."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess

if __package__:
    from . import mec_range
else:
    import mec_range

ROOT = Path(__file__).resolve().parents[2]
FUNCTION_SHA = 'f4cce20334d98ebdb58ef3ddf7cd13673ba35d6b1e5109483321b5acf4c7a845'
OLD_RESERVATION = '''    const uint32_t need = n * 4 + 8;
    if (need + 16 > q.ringDw)
        return kIOReturnBadArgument;
    IOLockLock(gpuLock);
'''
NEW_RESERVATION = '''    IOLockLock(gpuLock);
    const uint32_t rawNeed = n * 4 + 8;
    const uint32_t need = rawNeed + (q.gfx ? 0u : ((0u - static_cast<uint32_t>(q.wptr + rawNeed)) & 0xffu));
    if (need + 16 > q.ringDw) {
        IOLockUnlock(gpuLock);
        return kIOReturnBadArgument;
    }
'''
OLD_FENCE = '    const uint64_t seq = ++gSeq;\n'
NEW_FENCE = '''    // CPU-only experiment: keep RELEASE_MEM last in the padded frame.
    if (!q.gfx)
        while ((q.wptr + k + 8) & 0xffu)
            ringPut(q, k++, 0xffff1000u);
    const uint64_t seq = ++gSeq;
'''


def extract(source):
    signature = 'IOReturn PhxBringup::gpuSubmit('
    if source.count(signature) != 1:
        raise ValueError('Expected one original34 gpuSubmit')
    start = source.index(signature)
    end = source.index('\n}\n', start) + 3
    function = source[start:end]
    if hashlib.sha256(function.encode()).hexdigest() != FUNCTION_SHA:
        raise ValueError('Original34 gpuSubmit drift; refuse extraction')
    return function


def transform(function):
    if hashlib.sha256(function.encode()).hexdigest() != FUNCTION_SHA:
        raise ValueError('Unreviewed submit function')
    if function.count(OLD_RESERVATION) != 1 or function.count(OLD_FENCE) != 1:
        raise ValueError('Ambiguous padding insertion sites')
    candidate = function.replace(OLD_RESERVATION, NEW_RESERVATION).replace(OLD_FENCE, NEW_FENCE)
    if candidate.replace(NEW_RESERVATION, OLD_RESERVATION).replace(NEW_FENCE, OLD_FENCE) != function:
        raise ValueError('Change outside the two reviewed sites')
    return candidate


def exercise(destination):
    if platform.machine() not in ('x86_64', 'AMD64'):
        raise RuntimeError('Actual original34 function contains x86 CPU fences')
    compiler = shutil.which('clang++')
    if not compiler:
        raise RuntimeError('Requires Clang++; no kernel build is supported')
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Choose a fresh CPU output directory')
    protected = mec_range.verify_current_inputs(mec_range.protected_base_inputs(), ROOT)
    paths = [Path(__file__).resolve(), ROOT / 'tests/test_build34_ring_padding.cpp',
             ROOT / 'tests/test_upstream34_ring_padding_recipe.py']
    snapshots = {p:p.read_bytes() for p in paths}
    function = extract((ROOT / 'src/phxbringup/PhxBringup.cpp').read_text())
    template = snapshots[paths[1]].decode()
    marker = '// PHX34_EXTRACTED_GPU_SUBMIT_FUNCTION'
    if template.count(marker) != 1:
        raise ValueError('CPU fixture marker drift')
    destination.mkdir(parents=True, mode=0o700)
    results = {}
    for policy in ('original', 'compute-padding'):
        body = function if policy == 'original' else transform(function)
        source = destination / (policy + '.cpp')
        source.write_text(template.replace(marker, body))
        binary = destination / (policy + '-CPU-only')
        command = [compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-g',
                   '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                   '-DPHX34_CPU_PADDING=' + str(int(policy != 'original')),
                   '-I' + str(ROOT / 'src/phxbringup'), str(source), '-o', str(binary)]
        subprocess.run(command, check=True, stdin=subprocess.DEVNULL, timeout=90)
        if platform.system() == 'Darwin':
            linked = subprocess.check_output(['/usr/bin/otool', '-L', str(binary)], text=True, timeout=15)
            if 'IOKit.framework' in linked or 'CoreFoundation.framework' in linked:
                raise RuntimeError('CPU fixture linked a real device framework')
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120,
                                stdin=subprocess.DEVNULL, check=True)
        if result.stderr:
            raise RuntimeError('CPU fixture produced diagnostics; inspect private output')
        row = json.loads(result.stdout)
        if row['policy'] != policy or not row['passed'] or row['GPU_executed']:
            raise RuntimeError('Unexpected CPU fixture result')
        results[policy] = row
        print(json.dumps(row), flush=True)
    mec_range.verify_current_inputs(mec_range.protected_base_inputs(), ROOT)
    if any(p.read_bytes() != data for p,data in snapshots.items()):
        raise RuntimeError('CPU recipe/fixture changed during verification')
    report = {'result':'passed', 'base_commit':mec_range.BASE,
              'original_gpuSubmit_sha256':FUNCTION_SHA,
              'experiment_gpuSubmit_sha256':hashlib.sha256(transform(function).encode()).hexdigest(),
              'padding_position':'between IB descriptors and final RELEASE_MEM',
              'original34_protected_sha256':protected,
              'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(b).hexdigest() for p,b in snapshots.items()},
              'policies':results, 'sanitizers':'ASan/UBSan', 'real_IOKit_linked':False,
              'kernel_built':False, 'kernel_source_modified':False, 'installed':False,
              'GPU_executed':False, 'hardware_scope_armed':False,
              'limitation':'CPU stubs execute actual extracted submit control flow and a two-site source experiment. No CP, GPU cache, MMIO, DMA, scheduling or coherency simulation; no repair acceptance.'}
    (destination / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    exercise(parser.parse_args().out)
