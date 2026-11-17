#!/usr/bin/env python3
"""Stage the pinned build34 RADV transport patch; never install or execute it."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shlex
import sys

if __package__:
    from . import mec_range
else:
    import mec_range

ROOT = Path(__file__).resolve().parents[2]
PATCH = 'mesa-patches-build34/0001-radv-original34-immutable-ib-tail.patch'
PREFIX = 'src/amd/common/darwin/'
MANIFEST = ROOT / 'tools/upstream34_layout/radv_ib_tail_sources.json'
BASE_SHA256 = {
    PREFIX + 'ac_darwin_kext.c': '4c35beed2ebdcc2658822e6bebefb5eae1a120947dd7b11c1cb8f7f576a2db50',
    PREFIX + 'ac_darwin_kext.h': '9af0b3ef565544b19654ff1b872630d6a810c8e7e4d7cc9f7588c14413026f53',
    PREFIX + 'ac_darwin_drm.c': '42d35104174bf3c967a7a3d91f3235fd24514f00367961143c9da8ac0e6561a5',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verified_source(mesa_source):
    expected = json.loads(MANIFEST.read_text())['base_source_sha256']
    if any(expected.get(name) != digest for name, digest in BASE_SHA256.items()):
        raise ValueError('Dependency manifest does not match the reviewed transport baseline')
    blobs = {name: (Path(mesa_source) / name).read_bytes() for name in expected}
    if {name: sha(data) for name, data in blobs.items()} != expected:
        raise ValueError('Mesa source/dependency differs from the pinned reviewed source')
    return blobs


def prepare(mesa_source, destination):
    mesa_source, destination = Path(mesa_source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError('Output must be fresh; never overwrite a source or candidate')
    protected = mec_range.verify_current_inputs(mec_range.protected_base_inputs(), ROOT)
    blobs = verified_source(mesa_source)
    patch = (ROOT / PATCH).read_bytes()
    destination.mkdir(parents=True, mode=0o700)
    stage = destination / 'source'
    for name, data in blobs.items():
        path = stage / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    # A private repo fixes git-apply's cwd semantics inside the outer worktree.
    # Without it git can silently skip a patch relative to the parent's prefix.
    subprocess.run(['git', 'init', '-q', str(stage)], check=True, capture_output=True)
    for check in (True, False):
        subprocess.run(['git', '-C', str(stage), 'apply'] + (['--check'] if check else []) + ['-'],
                       input=patch, check=True, capture_output=True, timeout=30)
    outputs = {name: sha((stage / name).read_bytes()) for name in BASE_SHA256}
    if any(outputs[name] == BASE_SHA256[name] for name in outputs):
        raise RuntimeError('Patch skipped an expected source; output is unusable')
    mec_range.verify_current_inputs(mec_range.protected_base_inputs(), ROOT)
    if any((mesa_source / name).read_bytes() != data for name, data in blobs.items()):
        raise RuntimeError('Source drift during preparation')
    report = {'approved_build34_checkpoint': mec_range.BASE, 'base_source_sha256': BASE_SHA256,
              'dependency_manifest_sha256': sha(MANIFEST.read_bytes()),
              'patched_source_sha256': outputs, 'patch_sha256': sha(patch),
              'protected_source_sha256': protected, 'input_modified': False,
              'default_enabled': False, 'compute_only': True, 'installed': False,
              'GPU_executed': False, 'hardware_scope_armed': False}
    (destination / 'preparation.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def compile_probe(mesa_source, destination):
    """Compile/sign from a fully pinned closure; NEVER execute the native probe."""
    if sys.platform != 'darwin':
        raise RuntimeError('Native compilation requires macOS')
    report = prepare(mesa_source, destination)
    destination = Path(destination).resolve()
    source = destination / 'source'
    repo_inputs = ('tools/upstream34_layout/radv_ib_tail_probe.cpp',
                   'tools/upstream34_layout/ib_preamble_packets.h',
                   'LICENSE', 'LICENSES/MIT.txt', 'THIRD_PARTY_NOTICES.md')
    snapshots = {name: (ROOT / name).read_bytes() for name in repo_inputs}
    for name, data in snapshots.items():
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    flags = ['-arch', 'x86_64', '-mmacosx-version-min=12.0', '-O2', '-Wall', '-Wextra',
             '-Werror', '-Wno-unused-parameter']
    flags += ['-I' + str(source / name) for name in
              ('include', 'include/darwin', PREFIX, 'src', 'src/amd', 'tools/upstream34_layout')]
    inputs = [PREFIX + name for name in
              ('ac_darwin_kext.c', 'ac_darwin_drm.c', 'ac_darwin_sync.c', 'amdgpu_vamgr.c')]
    inputs += ['src/amd/common/amdgpu_devices.c', 'tools/upstream34_layout/radv_ib_tail_probe.cpp']
    objects = []
    frozen = {str(p.relative_to(source)): sha(p.read_bytes()) for p in source.rglob('*')
              if p.is_file() and '.git' not in p.relative_to(source).parts}
    for name in inputs:
        path = source / name
        cpp = path.suffix == '.cpp'
        obj = destination / (path.stem + '.o')
        command = ['/usr/bin/xcrun', 'clang++' if cpp else 'clang',
                   '-std=c++17' if cpp else '-std=gnu11'] + flags
        command += ['-MMD', '-MF', str(obj.with_suffix('.d')), '-c', str(path), '-o', str(obj)]
        result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, timeout=90)
        (destination / (path.stem + '.compile.log')).write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError('Native compile failed; inspect private compiler log')
        dependencies = shlex.split(obj.with_suffix('.d').read_text().replace('\\\n', ' ').split(':', 1)[1])
        for dependency in dependencies:
            rel = str(Path(dependency).relative_to(source))
            if rel not in frozen or sha((source / rel).read_bytes()) != frozen[rel]:
                raise RuntimeError('Native compile used an unfrozen or drifted dependency')
        objects.append(obj)
    binary = destination / 'build34-radv-ib-tail-probe'
    command = ['/usr/bin/xcrun', 'clang++', '-arch', 'x86_64', '-mmacosx-version-min=12.0']
    command += [str(obj) for obj in objects] + ['-framework', 'IOKit', '-framework', 'CoreFoundation', '-o', str(binary)]
    result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, timeout=90)
    (destination / 'link.log').write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('Native link failed; inspect private linker log')
    for command in (['/usr/bin/codesign', '--force', '--sign', '-', str(binary)],
                    ['/usr/bin/codesign', '--verify', '--strict', str(binary)],
                    ['/usr/bin/lipo', str(binary), '-verify_arch', 'x86_64']):
        subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=30)
    verified_source(mesa_source)
    mec_range.verify_current_inputs(mec_range.protected_base_inputs(), ROOT)
    if any((ROOT / name).read_bytes() != data for name, data in snapshots.items()):
        raise RuntimeError('Probe inputs changed during native compilation')
    if any(sha((source / name).read_bytes()) != digest for name, digest in frozen.items()):
        raise RuntimeError('Frozen source drift during native compilation')
    report.update({'compiled': True, 'binary_sha256': sha(binary.read_bytes()),
                   'signature_and_x86_64_verified': True, 'frozen_source_sha256': frozen,
                   'native_binary_executed': False, 'recipe_sha256': sha(Path(__file__).read_bytes()),
                   'dispatch_limit': 2, 'initialization_performed': False})
    (destination / 'preparation.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesa-source', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--compile-probe', action='store_true')
    args = parser.parse_args()
    result = (compile_probe if args.compile_probe else prepare)(args.mesa_source, args.out)
    print(json.dumps({key: result[key] for key in
                     ('input_modified', 'default_enabled', 'compute_only', 'installed',
                      'GPU_executed', 'hardware_scope_armed')}))
