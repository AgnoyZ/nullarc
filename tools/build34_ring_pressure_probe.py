#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Freeze, compile and CPU-check the bounded native R1b probe; never run GPU."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from build34_ring_backpressure import read_sources
from upstream34_layout.ib_preamble import INPUTS as PREAMBLE_INPUTS

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'tools/upstream34_layout/ring_pressure_probe.cpp'
INPUTS = PREAMBLE_INPUTS + (SOURCE,)


def build(out):
    out = out.resolve()
    if sys.platform != 'darwin' or ROOT / 'build' not in out.parents or out.exists():
        raise ValueError('native macOS and a fresh ignored worktree build output required')
    read_sources()  # Require the exact reviewed R1b build34 source/ABI.
    blobs = {name: (ROOT / name).read_bytes() for name in INPUTS}
    out.mkdir(mode=0o700)
    for name, data in blobs.items():
        p = out / 'source' / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    binary = out / 'ring-pressure-probe'
    command = ['/usr/bin/xcrun', 'clang++', '-arch', 'x86_64', '-mmacosx-version-min=12.0',
               '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
               '-I' + str(out / 'source/src/phxbringup'), str(out / 'source' / SOURCE),
               '-framework', 'IOKit', '-framework', 'CoreFoundation', '-o', str(binary)]
    commands = [('compile', command),
                ('sign', ['/usr/bin/codesign', '--force', '--sign', '-', str(binary)]),
                ('signature', ['/usr/bin/codesign', '--verify', '--strict', str(binary)]),
                ('architecture', ['/usr/bin/lipo', str(binary), '-verify_arch', 'x86_64']),
                ('CPU-self-test', [str(binary), '--self-test'])]
    for label, args in commands:
        p = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, timeout=90)
        (out / (label + '.log')).write_bytes(p.stdout + p.stderr)
        if p.returncode:
            raise RuntimeError(label + ' failed; see private log')
    read_sources()
    assert all((ROOT / name).read_bytes() == data for name, data in blobs.items())
    assert all((out / 'source' / name).read_bytes() == data for name, data in blobs.items())
    report = {'status': 'built-signed-and-CPU-self-tested-no-GPU', 'kernel_build': 34,
              'source_sha256': {n: hashlib.sha256(b).hexdigest() for n, b in blobs.items()},
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
              'recipe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'maximum_compute_submissions': 17, 'maximum_GFX_submissions': 41,
              'maximum_dispatches_per_compute_IB': 24, 'arena_bytes_per_client': 16384,
              'driver_modified': False, 'GPU_executed': False, 'installed': False}
    (out / 'build-report-private.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'source_sha256'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    build(parser.parse_args().out)
