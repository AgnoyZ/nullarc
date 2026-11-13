"""Export pinned diagnostic source only; never compile, transfer, install or execute it."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
BRANCH = 'downstream/780m-tahoe'
REVIEWED = '1c17a1712cb3a64db31148cb33d0c2c9741e7e5d'
SDK = '3f750085caa17ec3a7880f11c11bf4f48cd6a164'
CORE_PATHS = (
    'src/phxbringup', 'src/amd/phx_topology.h', 'tools/allocation_snapshot.cpp',
    'tools/test_allocation_snapshot.py', 'tools/test_submit_diagnostic.py',
    'tests/test_allocation_snapshot.cpp', 'tests/test_allocation_snapshot_reader.cpp',
    'tests/fake_native_iokit',
)
SOURCE_PATHS = CORE_PATHS + (
    'tools/allocation_source_packet.py', 'docs/ALLOCATION-SOURCE-PACKET.md',
    'tests/test_allocation_source_packet.py',
    '.github/workflows/kernel-compile-check.yml', '.gitignore', 'upstream.lock.json',
    'LICENSE', 'LICENSES', 'THIRD_PARTY_NOTICES.md', 'docs/KEXT-PROVENANCE.md',
    'docs/kext-notices',
)
REVIEW_PATHS = CORE_PATHS + (
    'upstream.lock.json', 'LICENSE', 'LICENSES', 'THIRD_PARTY_NOTICES.md',
    'docs/KEXT-PROVENANCE.md', 'docs/kext-notices',
    '.github/workflows/kernel-compile-check.yml',
)
GENERATED_INCLUDES = frozenset(('snapshot-constants.inc', 'snapshot-state.inc',
                               'snapshot-stubs.inc', 'snapshot-methods.inc'))


class PacketError(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise PacketError(reason)


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, timeout=30)
    require(result.returncode == 0, 'Git source read failed')
    return result.stdout


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def blob_id(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def tree_entries(root, commit):
    result = {}
    for entry in git(root, 'ls-tree', '-r', '-z', commit, '--', *SOURCE_PATHS).split(b'\0'):
        if not entry:
            continue
        meta, path = entry.split(b'\t', 1)
        mode, kind, blob = meta.decode('ascii').split()
        name = path.decode('utf-8')
        parts = PurePosixPath(name)
        require(not parts.is_absolute() and '..' not in parts.parts and '\\' not in name,
                'Unsafe source path')
        require(mode in ('100644', '100755') and kind == 'blob', 'Non-regular source entry')
        require(name not in result, 'Duplicate source entry')
        result[name] = {'git_blob': blob, 'git_mode': mode}
    for requested in SOURCE_PATHS:
        require(any(p == requested or p.startswith(requested + '/') for p in result),
                'Required source or notice missing: ' + requested)
    return result


def checked_archive(root, commit, entries):
    data = git(root, '-c', 'tar.umask=0022', 'archive', '--format=tar',
               '--prefix=nullarc/', commit, '--', *SOURCE_PATHS)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for item in archive:
            path = PurePosixPath(item.name)
            require(not path.is_absolute() and '..' not in path.parts and '\\' not in item.name,
                    'Unsafe archive path')
            require(path.parts and path.parts[0] == 'nullarc', 'Unexpected archive prefix')
            if item.isdir():
                continue
            name = path.relative_to('nullarc').as_posix()
            require(item.isfile() and name in entries and name not in files,
                    'Unexpected archive entry')
            require(item.size <= 1024 * 1024, 'Oversized source file')
            content = archive.extractfile(item).read()
            require(b'\0' not in content, 'Binary content is not a source packet')
            try:
                content.decode('utf-8')
            except UnicodeError as exc:
                raise PacketError('Source packet requires UTF-8 text') from exc
            require(blob_id(content) == entries[name]['git_blob'], 'Archive differs from committed blob')
            require(item.mode == (int(entries[name]['git_mode'], 8) & 0o777), 'Archive mode mismatch')
            files[name] = content
    require(set(files) == set(entries), 'Archive omitted a committed source')
    require(sum(len(v) for v in files.values()) <= 8 * 1024 * 1024, 'Oversized source packet')
    for name, content in files.items():
        if not name.endswith(('.h', '.hpp', '.c', '.cpp')):
            continue
        for include in re.findall(r'^\s*#\s*include\s*"([^"\n]+)"', content.decode(), re.M):
            candidates = (posixpath.normpath(str(PurePosixPath(name).parent / include)),
                          posixpath.normpath('src/phxbringup/' + include))
            require(any(candidate in files for candidate in candidates) or
                    (name == 'tests/test_allocation_snapshot.cpp' and include in GENERATED_INCLUDES),
                    'Missing quoted include in ' + name + ': ' + include)
    lock = json.loads(files['upstream.lock.json'])
    require(lock['MacKernelSDK']['commit'] == SDK, 'Unreviewed SDK pin')
    require(re.search(rb'^#define PHX_KEXT_BUILD\s+37u\s*$',
                      files['src/phxbringup/PhxBringup.cpp'], re.M), 'Not reviewed build37 source')
    return data, files


def export_packet(out, commit, root=ROOT, *, reviewed=REVIEWED):
    root = Path(root).resolve()
    out = Path(os.path.abspath(out))
    require(re.fullmatch('[0-9a-f]{40}', commit) is not None, 'Require exact full commit')
    require(git(root, 'rev-parse', 'HEAD').decode().strip() == commit, 'HEAD does not match requested commit')
    require(git(root, 'branch', '--show-current').decode().strip() == BRANCH, 'Unexpected branch')
    require(not git(root, 'status', '--porcelain', '--untracked-files=all').strip(), 'Checkout is not clean')
    require(out.parent == root / 'build' and out.name not in ('.', '..'), 'Use a fresh direct child of build/')
    require(not out.exists() and not out.is_symlink(), 'Output already exists')
    for path in (out.parent, *out.parent.parents):
        require(not path.is_symlink(), 'Symlink in output path')
    for path in REVIEW_PATHS:
        require(git(root, 'rev-parse', commit + ':' + path) ==
                git(root, 'rev-parse', reviewed + ':' + path), 'Source changed since reviewed snapshot: ' + path)
    entries = tree_entries(root, commit)
    tar, files = checked_archive(root, commit, entries)
    manifest = {
        'format': 1, 'kind': 'source-only; not a binary build or provenance attestation',
        'source_commit': commit, 'source_tree': git(root, 'rev-parse', commit + '^{tree}').decode().strip(),
        'reviewed_snapshot_source': reviewed, 'candidate_build': 37,
        'source_paths': list(SOURCE_PATHS),
        'files': {name: {**entries[name], 'sha256': sha256(content), 'bytes': len(content)}
                  for name, content in sorted(files.items())},
        'external_build_inputs': {
            'MacKernelSDK_commit': SDK,
            'MacKernelSDK_sources_or_prebuilt_libraries_included': False,
            'native_reader_frameworks': ['IOKit', 'CoreFoundation'],
            'Apple_SDK_or_framework_binaries_included': False,
        },
        'limits': {'native_compile': False, 'target_binary_included': False, 'transfer': False,
                   'installation': False, 'service_open': False, 'GPU_execution': False,
                   'startup_change': False, 'reboot': False, 'root_cause_confirmed': False},
    }
    # Re-read admission after gathering input; never publish a packet from changed source state.
    require(git(root, 'rev-parse', 'HEAD').decode().strip() == commit and
            not git(root, 'status', '--porcelain', '--untracked-files=all').strip(), 'Checkout changed during export')
    out.parent.mkdir(mode=0o700, exist_ok=True)
    out.mkdir(mode=0o700)
    payloads = {
        'nullarc-allocation-source.tar.gz': gzip.compress(tar, mtime=0),
        'source-manifest.json': (json.dumps(manifest, indent=2) + '\n').encode(),
    }
    payloads['SHA256SUMS'] = ''.join(sha256(content) + '  ' + name + '\n'
                                    for name, content in sorted(payloads.items())).encode()
    for name, content in payloads.items():
        fd = os.open(out / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    return {'source_commit': commit, 'source_files': len(files),
            'archive_sha256': sha256(payloads['nullarc-allocation-source.tar.gz']),
            'source_only': True, 'target_binary_included': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    print(json.dumps(export_packet(args.out, args.commit), indent=2))
