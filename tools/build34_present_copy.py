#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Freeze/build only the reviewed R2a PhxAccel copy delta; never install/load."""
import argparse
import json
from pathlib import Path
import platform
import subprocess

from upstream34_layout import ring_padding_candidate as common

ROOT = Path(__file__).resolve().parents[1]
BASE = '439f8a5bc3e086770df7b576897fbb11d7ccc9f1'
DRIVER = 'src/phxaccel/accel/nvrm-accel.cpp'
OLD_SHA = 'f794a1a2da4c629964a832a7d97e7ee8faebf3d6c779dcd301e5dfd11deea635'
NEW_SHA = '4855ecaf223a64f3da747d43f81d29e43b1066d7a72c11b5500c97609dff0335'
ACCEPTED_BINARY = 'a206d983fca62dd7959cc701fb9f95d5490da78986aac02dbb67ed00410325e7'


def git(*args):
    return subprocess.check_output(['/usr/bin/git', *args], cwd=ROOT, timeout=20)


def read_sources():
    names = git('ls-tree', '-r', '--name-only', BASE, '--', 'src/phxaccel').decode().splitlines()
    if set(names) != set(git('ls-files', '--', 'src/phxaccel').decode().splitlines()):
        raise ValueError('accelerator source-input set drift')
    # Include the actual notice paths present in the pinned source, rather
    # than treating copied NVIDIA/AMD sources as one licence.
    names += git('ls-tree', '-r', '--name-only', BASE, '--', 'LICENSE', 'LICENSES',
                 'THIRD_PARTY_NOTICES.md').decode().splitlines()
    baseline = {n: git('show', BASE + ':' + n) for n in names}
    current = {}
    for name in names:
        p = ROOT / name
        if p.is_symlink() or not p.is_file():
            raise ValueError('regular build input required')
        current[name] = p.read_bytes()
    if common.sha(baseline[DRIVER]) != OLD_SHA or common.sha(current[DRIVER]) != NEW_SHA:
        raise ValueError('unreviewed complete copy source')
    if any(baseline[n] != current[n] for n in names if n != DRIVER):
        raise ValueError('change outside the one reviewed accelerator source')
    start = b'    const bool wide ='
    end = b'    fIopVblSeq ='
    before, after = baseline[DRIVER], current[DRIVER]
    if before.split(start)[0] != after.split(start)[0] or before.split(end)[1:] != after.split(end)[1:]:
        raise ValueError('change outside display copy block')
    return baseline, current


def freeze(root, values):
    for name, blob in values.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)


def build(sdk, out):
    if platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        raise RuntimeError('Intel macOS required')
    out = out.resolve()
    if ROOT / 'build' not in out.parents or out.exists():
        raise ValueError('fresh private output under the ignored build directory required')
    baseline, candidate = read_sources()
    sdk_values = common.sdk_inputs(sdk)
    recipe = Path(__file__).read_bytes()
    out.mkdir(mode=0o700, parents=True)
    freeze(out / 'MacKernelSDK-pinned-private', sdk_values)
    images = {}
    for label, inputs in [('baseline', baseline), ('candidate', candidate)]:
        source = out / label / 'source'
        freeze(source, inputs)
        result = subprocess.run(['/usr/bin/nice', '-n', '12', '/bin/sh',
            str(source / 'src/phxaccel/build.sh'), str(out / 'MacKernelSDK-pinned-private')],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
        (out / (label + '-build-private.log')).write_bytes(result.stdout)
        if result.returncode:
            raise RuntimeError(label + ' compile failed; see private log')
        bundle = source / 'src/phxaccel/build/PhxAccel.kext'
        binary = bundle / 'Contents/MacOS/PhxAccel'
        for args in (['/usr/bin/codesign', '--verify', '--strict', str(bundle)],
                     ['/usr/bin/lipo', str(binary), '-verify_arch', 'x86_64']):
            checked = subprocess.run(args, capture_output=True, timeout=15)
            if checked.returncode:
                raise RuntimeError(label + ' signature/architecture refusal')
        identity = common.macho_identity(binary.read_bytes())
        if label == 'baseline' and identity['binary_sha256'] != ACCEPTED_BINARY:
            raise ValueError('baseline native build does not reproduce the accepted executable')
        imports = subprocess.check_output(['/usr/bin/nm', '-u', str(binary)], text=True, timeout=10).splitlines()
        images[label] = dict(identity_private=identity, imports=sorted(imports),
                             bundle_files=common.tree_files(bundle))
        if any((source / n).read_bytes() != blob for n, blob in inputs.items()):
            raise ValueError('frozen source drift')
    if images['baseline']['imports'] != images['candidate']['imports']:
        raise ValueError('candidate import set changed')
    if read_sources() != (baseline, candidate) or Path(__file__).read_bytes() != recipe:
        raise ValueError('worktree inputs changed during build')
    if common.tree_files(out / 'MacKernelSDK-pinned-private') != {n: common.sha(b) for n, b in sdk_values.items()}:
        raise ValueError('frozen SDK drift')
    report = dict(status='built-offline-not-installed', kernel_build=34,
        accepted_accelerator_source=BASE, baseline_reproduces_accepted_binary=True,
        baseline_source_sha256=OLD_SHA, candidate_source_sha256=NEW_SHA,
        source_sha256={n: common.sha(b) for n, b in candidate.items()},
        sdk_commit=common.SDK_PIN, recipe_sha256=common.sha(recipe), images_private=images,
        installed=False, loaded=False, GPU_executed=False)
    (out / 'build-report-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], baseline_reproduced=True,
                         imports_unchanged=True, candidate_binary_sha256=images['candidate']['identity_private']['binary_sha256'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    build(args.sdk, args.out)
