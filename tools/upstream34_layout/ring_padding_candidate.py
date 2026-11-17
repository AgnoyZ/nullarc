#!/usr/bin/env python3
"""Build a private original34-derived ring-padding kext; never install or load it."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import platform
import plistlib
import shutil
import struct
import subprocess
import tarfile
import uuid

if __package__:
    from . import mec_range, ring_padding
else:
    import mec_range
    import ring_padding

ROOT = Path(__file__).resolve().parents[2]
SDK_PIN = '3f750085caa17ec3a7880f11c11bf4f48cd6a164'
ORIGINAL_SHA = 'beffab5dc13e4018ff2ab9f90c82d85c0982ce7e3563e3175999399c7bc083e5'
CANDIDATE_SHA = 'b34f262fe5cd05b6aa8b18d9500a23121e838dea0c3ffb86cf63f74fbdfc06c0'
SOURCE_PLIST_SHA = '05d17cf6d755730497021298d4f57153066d4d64228fdcf28e358b61a82375a5'
CONTROL_PLIST_SHA = 'aaeef27a947e0a2a70b358628ff21216a5edaf0a5d65f32651f8654cef654af7'
DRIVER = 'src/phxbringup/PhxBringup.cpp'
SOURCE_INPUTS = (DRIVER, 'src/phxbringup/PhxNativeABI.h', 'src/phxbringup/kmod_info.c',
                 'src/phxbringup/Info.plist', 'src/phxbringup/build.sh',
                 'src/amd/phx_topology.h', 'LICENSE', 'THIRD_PARTY_NOTICES.md',
                 'LICENSES/MIT.txt', 'LICENSES/GPL-2.0-only.txt')
SDK_PATHS = ('Headers', 'Library/x86_64', 'LICENSE.txt')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def candidate_source(original):
    if sha(original) != ORIGINAL_SHA:
        raise ValueError('Original34 complete driver hash drift')
    text = original.decode()
    function = ring_padding.extract(text)
    changed = ring_padding.transform(function)
    if text.count(function) != 1:
        raise ValueError('Ambiguous driver function')
    result = text.replace(function, changed).encode()
    if sha(result) != CANDIDATE_SHA or result.decode().replace(changed, function).encode() != original:
        raise ValueError('Candidate differs from the reviewed two-site source proposal')
    return result


def control_metadata(source):
    """Match the independently read original image's target restriction exactly."""
    if sha(source) != SOURCE_PLIST_SHA:
        raise ValueError('Unreviewed source bundle metadata')
    old = b'0x19001002 0x15bf1002 0x15c81002 0x164e1002'
    if source.count(old) != 1:
        raise ValueError('Ambiguous PCI match restriction')
    result = source.replace(old, b'0x19001002')
    expected = plistlib.loads(source)
    expected['IOKitPersonalities']['PhxBringup']['IOPCIMatch'] = '0x19001002'
    if sha(result) != CONTROL_PLIST_SHA or plistlib.loads(result) != expected:
        raise ValueError('Candidate metadata differs from the original-image control')
    return result


def archive_inputs(data):
    """Validate every SDK archive entry before materializing any of them."""
    if len(data) > 32 * 1024 * 1024:
        raise ValueError('Unexpected SDK archive size')
    blobs = {}
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as archive:
        for item in archive.getmembers():
            path = PurePosixPath(item.name)
            if (path.is_absolute() or '..' in path.parts or not path.parts or
                    str(path) != item.name.rstrip('/') or str(path) in seen):
                raise ValueError('Unsafe or duplicate SDK archive path')
            seen.add(str(path))
            allowed = (str(path) == 'LICENSE.txt' or str(path) == 'Headers' or
                       str(path).startswith('Headers/') or str(path) == 'Library' or
                       str(path) == 'Library/x86_64' or str(path).startswith('Library/x86_64/'))
            if not allowed or not (item.isdir() or item.isfile()):
                raise ValueError('Unexpected SDK archive entry or link')
            if item.isfile():
                if item.size > 16 * 1024 * 1024:
                    raise ValueError('Unexpected SDK member size')
                blobs[str(path)] = archive.extractfile(item).read()
    if not {'LICENSE.txt', 'Headers/IOKit/IOService.h', 'Library/x86_64/libkmod.a'} <= blobs.keys():
        raise ValueError('Incomplete SDK snapshot')
    return blobs


def sdk_inputs(sdk):
    sdk = Path(sdk).resolve()
    def git(*args):
        return subprocess.check_output(['/usr/bin/git', *args], cwd=sdk, timeout=45)
    if Path(git('rev-parse', '--show-toplevel').decode().strip()).resolve() != sdk:
        raise ValueError('SDK must be its own checkout, not an ancestor repository')
    if git('rev-parse', 'HEAD').decode().strip() != SDK_PIN:
        raise ValueError('Use the reviewed pinned MacKernelSDK')
    if git('status', '--porcelain', '--untracked-files=all', '--', *SDK_PATHS).strip():
        raise ValueError('SDK inputs are not clean')
    data = git('archive', '--format=tar', SDK_PIN, '--', *SDK_PATHS)
    blobs = archive_inputs(data)
    expected = {}
    for row in git('ls-tree', '-rz', SDK_PIN, '--', *SDK_PATHS).split(b'\0'):
        if not row:
            continue
        metadata, name = row.split(b'\t', 1)
        mode, kind, digest = metadata.decode().split()
        if mode != '100644' or kind != 'blob':
            raise ValueError('Unreviewed SDK input mode')
        expected[name.decode()] = digest
    actual = {name: hashlib.sha1(b'blob ' + str(len(blob)).encode() + b'\0' + blob).hexdigest()
              for name, blob in blobs.items()}
    if actual != expected:
        raise ValueError('SDK archive does not match the pinned Git objects')
    return blobs


def macho_identity(data):
    if len(data) < 32:
        raise ValueError('Truncated Mach-O header')
    magic, cpu, subtype, kind, count, size, flags, reserved = struct.unpack_from('<8I', data)
    if (magic, cpu, subtype, kind) != (0xfeedfacf, 0x1000007, 3, 11):
        raise ValueError('Expected an x86_64 MH_KEXT_BUNDLE')
    end = 32 + size
    if count > 1024 or end > len(data):
        raise ValueError('Invalid Mach-O load commands')
    offset = 32
    identities = []
    for _ in range(count):
        if offset + 8 > end:
            raise ValueError('Truncated load command')
        command, length = struct.unpack_from('<II', data, offset)
        if length < 8 or length % 8 or offset + length > end:
            raise ValueError('Invalid load command length')
        if command == 0x1b:
            if length != 24:
                raise ValueError('Invalid LC_UUID')
            identities.append(data[offset + 8:offset + 24])
        offset += length
    if offset != end or len(identities) != 1 or identities[0] == bytes(16):
        raise ValueError('Missing, duplicate or invalid candidate identity')
    return {'architecture': 'x86_64', 'filetype': 'MH_KEXT_BUNDLE',
            'image_uuid_private': str(uuid.UUID(bytes=identities[0])), 'binary_sha256': sha(data)}


def tree_files(path):
    result = {}
    for file in sorted(path.rglob('*')):
        if file.is_symlink() or not (file.is_file() or file.is_dir()):
            raise ValueError('Unexpected link or special file in bundle')
        if file.is_file():
            result[str(file.relative_to(path))] = sha(file.read_bytes())
    return result


def build(destination, sdk):
    if platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        raise RuntimeError('Requires native Intel macOS; no cross-target fallback')
    destination = Path(destination).resolve()
    if ROOT / 'build' not in destination.parents or destination.exists():
        raise ValueError('Use a fresh private destination inside this worktree build directory')
    protected_blobs = mec_range.protected_base_inputs()
    protected = mec_range.verify_current_inputs(protected_blobs, ROOT)
    source_blobs = {name: mec_range.read_base(name) for name in SOURCE_INPUTS}
    for name, blob in source_blobs.items():
        if (ROOT / name).read_bytes() != blob:
            raise ValueError('Source input drift: ' + name)
    proposed = candidate_source(source_blobs[DRIVER])
    packaged_plist = control_metadata(source_blobs['src/phxbringup/Info.plist'])
    sdk_blobs = sdk_inputs(sdk)
    recipe_paths = (Path(__file__), ROOT / 'tools/upstream34_layout/ring_padding.py',
                    ROOT / 'tools/upstream34_layout/mec_range.py',
                    ROOT / 'tests/test_upstream34_ring_padding_candidate.py')
    recipes = {path: path.read_bytes() for path in recipe_paths}
    destination.mkdir(parents=True, mode=0o700)
    source = destination / 'source'
    sdk_copy = destination / 'MacKernelSDK-pinned-private'
    compiler = Path(subprocess.check_output(['/usr/bin/xcrun', '--find', 'clang'], text=True,
                                           timeout=15).strip()).resolve()
    linker = Path(subprocess.check_output(['/usr/bin/xcrun', '--find', 'ld'], text=True,
                                         timeout=15).strip()).resolve()
    resource = Path(subprocess.check_output([str(compiler), '-print-resource-dir'], text=True,
                                           timeout=15).strip()).resolve()
    host_sdk = Path(subprocess.check_output(['/usr/bin/xcrun', '--show-sdk-path'], text=True,
                                           timeout=15).strip()).resolve()
    tool_paths = (compiler, linker, Path('/usr/bin/codesign'), Path('/usr/bin/lipo'), Path('/bin/sh'),
                  resource / 'lib/darwin/libclang_rt.cc_kext.a', compiler.parent.parent / 'lib/libLTO.dylib',
                  host_sdk / 'SDKSettings.json', host_sdk / 'SDKSettings.plist')
    tools = {path: file_sha(path) for path in tool_paths}
    environment = {'PATH': str(compiler.parent) + ':/usr/bin:/bin:/usr/sbin:/sbin',
                   'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': str(destination / 'tmp-private')}
    (destination / 'tmp-private').mkdir()
    for name, blob in source_blobs.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(proposed if name == DRIVER else blob)
    for name, blob in sdk_blobs.items():
        path = sdk_copy / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    for path, blob in recipes.items():
        frozen = destination / 'recipe-private' / path.relative_to(ROOT)
        frozen.parent.mkdir(parents=True, exist_ok=True)
        frozen.write_bytes(blob)
    report = {'result': 'source-frozen', 'identity_class': 'original34-derived-ringpad-experimental',
              'base_commit': mec_range.BASE, 'sdk_commit': SDK_PIN,
              'original_driver_sha256': ORIGINAL_SHA, 'candidate_driver_sha256': CANDIDATE_SHA,
              'production_protected_sha256': protected,
              'source_sha256': {name: sha(proposed if name == DRIVER else blob)
                                for name, blob in source_blobs.items()},
              'recipe_sha256': {str(path.relative_to(ROOT)): sha(blob) for path, blob in recipes.items()},
              'sdk_files_sha256': {name: sha(blob) for name, blob in sdk_blobs.items()},
              'toolchain_sha256_private': {str(path): digest for path, digest in tools.items()},
              'checks': [], 'kernel_built': False, 'installed': False, 'loaded': False,
              'GPU_executed': False, 'hardware_scope_armed': False,
              'untouched_original_admission_changed': False, 'production_source_modified': False,
              'metadata_build_marker_unchanged': True,
              'packaging_metadata': {'source_plist_sha256': SOURCE_PLIST_SHA,
                                     'control_matching_plist_sha256': CONTROL_PLIST_SHA,
                                     'only_change': 'IOPCIMatch restricted to 0x19001002, byte-identical to the original deployed control bundle',
                                     'production_plist_modified': False},
              'limitation': 'Build and static identity only. The unchanged build marker is not candidate admission. No installation, load, initialization, GPU test or repair acceptance.'}
    def save():
        (destination / 'build-report-private.json').write_text(json.dumps(report, indent=2) + '\n')
    def command(name, argv):
        result = subprocess.run(argv, cwd=source, env=environment, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=120)
        log = result.stdout + result.stderr
        (destination / (name + '-private.log')).write_bytes(log)
        report['checks'].append({'name': name, 'exit_code': result.returncode, 'log_sha256': sha(log)})
        save()
        if result.returncode:
            raise RuntimeError(name + ' failed; inspect the retained private build log')
    save()
    try:
        command('compile', ['/bin/sh', str(source / 'src/phxbringup/build.sh'), str(sdk_copy)])
        bundle = destination / 'original34-derived-ringpad-experimental.kext'
        shutil.copytree(source / 'src/phxbringup/build/PhxBringup.kext', bundle)
        (bundle / 'Contents/Info.plist').write_bytes(packaged_plist)
        binary = bundle / 'Contents/MacOS/PhxBringup'
        before_sign = macho_identity(binary.read_bytes())
        command('sign', ['/usr/bin/codesign', '--force', '--sign', '-', str(bundle)])
        command('signature', ['/usr/bin/codesign', '--verify', '--strict', str(bundle)])
        command('architecture', ['/usr/bin/lipo', str(binary), '-verify_arch', 'x86_64'])
        identity = macho_identity(binary.read_bytes())
        if before_sign['image_uuid_private'] != identity['image_uuid_private']:
            raise ValueError('Image identity changed across signing')
        for name, blob in source_blobs.items():
            if (source / name).read_bytes() != (proposed if name == DRIVER else blob):
                raise ValueError('Frozen source changed during compilation')
            if (ROOT / name).read_bytes() != blob:
                raise ValueError('Production source changed during compilation')
        if (bundle / 'Contents/Info.plist').read_bytes() != packaged_plist:
            raise ValueError('Candidate bundle metadata drift')
        for name, blob in sdk_blobs.items():
            if (sdk_copy / name).read_bytes() != blob:
                raise ValueError('SDK changed during compilation')
        mec_range.verify_current_inputs(protected_blobs, ROOT)
        if any(path.read_bytes() != blob for path, blob in recipes.items()):
            raise ValueError('Recipe changed during compilation')
        if any(file_sha(path) != digest for path, digest in tools.items()):
            raise ValueError('Toolchain changed during compilation')
        report.update(result='built-and-statically-verified-not-installed', kernel_built=True,
                      candidate_identity_private=identity, candidate_bundle_files_sha256=tree_files(bundle))
        save()
    except BaseException as error:
        report.update(result='failed-retained-for-review', error_type=type(error).__name__)
        save()
        raise
    print(json.dumps({key: report[key] for key in ('result', 'identity_class', 'kernel_built',
                      'installed', 'loaded', 'GPU_executed', 'hardware_scope_armed')}))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    args = parser.parse_args()
    build(args.out, args.sdk)
