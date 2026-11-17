#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify the integrated build34 submit source with CPU fakes; never load a kext."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess

if __package__:
    from . import mec_range, outer_memsync
else:
    import mec_range
    import outer_memsync

ROOT = Path(__file__).resolve().parents[2]
DRIVER = 'src/phxbringup/PhxBringup.cpp'
SOURCE_SHA = 'fffd2bdfea25ca87312679e194949f2538807b43610d157f06c9dde0d33a70d0'
FUNCTION_SHA = '12fcaa4cb7ab0a19df9ac16491e7654362547625e4fbe879840cbfb9d351e722'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def reviewed_inputs():
    """Allow only the exact tested two-site change; retain original diagnostics."""
    expected = mec_range.protected_base_inputs()
    expected[DRIVER] = outer_memsync.candidate_source(expected[DRIVER], 'acquire-prefix')
    if sha(expected[DRIVER]) != SOURCE_SHA:
        raise ValueError('Reviewed complete submit source drift')
    return expected


def verify_inputs(expected, root):
    for name, data in expected.items():
        path = Path(root) / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
            raise ValueError('Integrated build34 input drift: ' + name)
    return {name: sha(data) for name, data in expected.items()}


def extract(source):
    if sha(source) != SOURCE_SHA:
        raise ValueError('Unreviewed integrated build34 source')
    text = source.decode()
    signature = 'IOReturn PhxBringup::gpuSubmit('
    if text.count(signature) != 1:
        raise ValueError('Ambiguous integrated submit function')
    start = text.index(signature)
    function = text[start:text.index('\n}\n', start) + 3]
    if sha(function.encode()) != FUNCTION_SHA:
        raise ValueError('Integrated submit function drift')
    return function


def exercise(destination):
    if platform.machine() not in ('x86_64', 'AMD64'):
        raise RuntimeError('Actual build34 function requires x86 CPU fences')
    compiler = shutil.which('clang++')
    if not compiler:
        raise RuntimeError('Clang++ is required for the CPU fixture')
    destination = Path(destination).resolve()
    if ROOT / 'build' not in destination.parents or destination.exists():
        raise ValueError('Use a fresh CPU destination inside the worktree build directory')
    expected = reviewed_inputs()
    protected = verify_inputs(expected, ROOT)
    production = (ROOT / DRIVER).read_bytes()
    function = extract(production)
    paths = [Path(__file__).resolve(), ROOT / 'tests/test_build34_outer_memsync.cpp',
             ROOT / 'tests/test_upstream34_submit_memsync.py']
    snapshots = {path: path.read_bytes() for path in paths}
    template = snapshots[paths[1]].decode()
    marker = '// PHX34_EXTRACTED_GPU_SUBMIT_FUNCTION'
    if template.count(marker) != 1:
        raise ValueError('CPU fixture marker drift')
    destination.mkdir(mode=0o700, parents=True)
    source, binary = destination / 'integrated-submit.cpp', destination / 'integrated-submit-CPU-only'
    source.write_text(template.replace(marker, function))
    subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-g',
                    '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                    '-DPHX34_CPU_PREFIX=2', '-I' + str(ROOT / 'src/phxbringup'),
                    str(source), '-o', str(binary)],
                   check=True, stdin=subprocess.DEVNULL, timeout=90)
    if platform.system() == 'Darwin':
        linked = subprocess.check_output(['/usr/bin/otool', '-L', str(binary)], text=True, timeout=15)
        if 'IOKit.framework' in linked or 'CoreFoundation.framework' in linked:
            raise RuntimeError('CPU fixture linked a device framework')
    run = subprocess.run([str(binary)], check=True, capture_output=True,
                         text=True, stdin=subprocess.DEVNULL, timeout=120)
    row = json.loads(run.stdout)
    if (run.stderr or row.get('passed') is not True or row.get('GPU_executed') is not False or
            row.get('policy') != 'acquire-prefix' or row.get('scenarios') != 36111):
        raise RuntimeError('Integrated CPU verification failed')
    verify_inputs(expected, ROOT)
    if any(path.read_bytes() != data for path, data in snapshots.items()):
        raise RuntimeError('Integrated CPU recipe changed during verification')
    result = {'result': 'passed', 'approved_source_checkpoint': mec_range.BASE,
              'complete_source_sha256': sha(production), 'function_sha256': sha(function.encode()),
              'production_input_sha256': protected, 'actual_function': row,
              'recipe_sha256': {str(path.relative_to(ROOT)): sha(data) for path, data in snapshots.items()},
              'sanitizers': 'ASan/UBSan', 'real_IOKit_linked': False,
              'kernel_built': False, 'installed': False, 'GPU_executed': False,
              'original34_diagnostic_admission_unchanged': True,
              'limitation': 'Actual integrated function with CPU fakes, no GPU cache, DMA, MMIO or completion model. Hardware acceptance is separate.'}
    (destination / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key not in ('production_input_sha256', 'recipe_sha256')}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    exercise(parser.parse_args().out)
