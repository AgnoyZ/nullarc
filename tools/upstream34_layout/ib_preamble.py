#!/usr/bin/env python3
"""Freeze/compile the original34 preamble diagnostic; never execute or install it."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

if __package__:
    from . import mec_range
else:
    import mec_range

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ('tools/upstream34_layout/ib_preamble_probe.cpp',
          'tools/upstream34_layout/ib_preamble_packets.h',
          'src/phxbringup/PhxNativeABI.h', 'src/amd/phx_topology.h',
          'LICENSE', 'LICENSES/MIT.txt', 'LICENSES/GPL-2.0-only.txt',
          'THIRD_PARTY_NOTICES.md')


def prepare(destination, compile_native=False):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Output must be fresh; never overwrite a candidate')
    protected = mec_range.verify_current_inputs(mec_range.protected_base_inputs(), ROOT)
    if (ROOT / 'src/amd/phx_topology.h').read_bytes() != mec_range.read_base('src/amd/phx_topology.h'):
        raise ValueError('Topology header differs from approved original34')
    blobs = {name: (ROOT / name).read_bytes() for name in INPUTS}
    destination.mkdir(parents=True, mode=0o700)
    source = destination / 'source'
    for name, data in blobs.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    report = {'base_commit': mec_range.BASE,
              'original34_protected_sha256': protected,
              'recipe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'source_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in blobs.items()},
              'policies': {'single': 'reused dispatch IB alone; identical staged arena',
                           'control': 'prewritten NOP then reused dispatch IB',
                           'nop-tail': 'reused dispatch IB then prewritten NOP',
                           'memsync': 'prewritten ACQUIRE_MEM then reused dispatch IB'},
              'original34_build_required': True, 'dispatch_limit': 2,
              'kernel_or_production_helpers_modified': False,
              'compiled': False, 'native_binary_executed': False, 'installed': False,
              'GPU_executed': False, 'hardware_scope_armed': False}
    if compile_native:
        if sys.platform != 'darwin':
            raise RuntimeError('Native compile requires macOS; source remains frozen')
        binary = destination / 'build34-ib-preamble-probe'
        command = ['/usr/bin/xcrun', 'clang++', '-arch', 'x86_64', '-mmacosx-version-min=12.0',
                   '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                   '-I' + str(source / 'src/phxbringup'),
                   str(source / 'tools/upstream34_layout/ib_preamble_probe.cpp'),
                   '-framework', 'IOKit', '-framework', 'CoreFoundation', '-o', str(binary)]
        result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, timeout=90)
        (destination / 'native-compile.log').write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError('Native compile failed; inspect private compiler log')
        for args in (('/usr/bin/codesign', '--force', '--sign', '-', str(binary)),
                     ('/usr/bin/codesign', '--verify', '--strict', str(binary)),
                     ('/usr/bin/lipo', str(binary), '-verify_arch', 'x86_64')):
            subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, timeout=20, check=True)
        report.update({'compiled': True, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
                       'signature_and_x86_64_verified': True})
    # Reject source drift across compilation, not only before it.
    mec_range.verify_current_inputs(mec_range.protected_base_inputs(), ROOT)
    if any((ROOT / name).read_bytes() != data for name, data in blobs.items()):
        raise RuntimeError('Input changed during preparation; do not use this output')
    (destination / 'preparation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('base_commit', 'compiled', 'native_binary_executed',
                     'installed', 'GPU_executed', 'hardware_scope_armed')}))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--compile', action='store_true')
    args = parser.parse_args()
    prepare(args.destination, args.compile)
