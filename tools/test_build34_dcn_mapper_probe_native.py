#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile the source-only mapper resolver against the reviewed native SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import plistlib
import shlex
import struct
import subprocess

from upstream34_layout.ring_padding_candidate import SDK_PIN, sdk_inputs

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/build34_dcn_mapper_probe_native.cpp'
HEADER = ROOT / 'src/phxbringup/PhxDcnMapperProbe.h'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def test(out, sdk, kdk):
    if platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        raise ValueError('Require native Intel macOS')
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored private build output')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    branch = subprocess.check_output(['/usr/bin/git', 'symbolic-ref', '--short', 'HEAD'],
                                     cwd=ROOT, text=True, timeout=15).strip()
    if branch != 'upstream34/vram-layout-fix':
        raise ValueError('Default build34 branch only')

    sdk = Path(sdk).resolve()
    sdk_blobs = sdk_inputs(sdk)
    fixture_blob, header_blob = FIXTURE.read_bytes(), HEADER.read_bytes()
    kdk = Path(kdk).resolve()
    metadata = kdk / 'System/Library/CoreServices/SystemVersion.plist'
    metadata_blob = metadata.read_bytes()
    kdk_info = plistlib.loads(metadata_blob)
    os_version = subprocess.check_output(['/usr/bin/sw_vers', '-productVersion'], text=True,
                                         timeout=15).strip()
    os_build = subprocess.check_output(['/usr/bin/sw_vers', '-buildVersion'], text=True,
                                       timeout=15).strip()
    if (kdk_info['ProductVersion'], kdk_info['ProductBuildVersion']) != (os_version, os_build):
        raise ValueError('KDK and current OS version/build do not match')

    compiler = Path(subprocess.check_output(['/usr/bin/xcrun', '--find', 'clang++'],
                                            text=True, timeout=15).strip()).resolve()
    compiler_hash = file_sha(compiler)
    out.mkdir(parents=True, mode=0o700)
    source_dir = out / 'source-private'
    source_dir.mkdir()
    source_fixture = source_dir / FIXTURE.name
    source_header = source_dir / HEADER.name
    source_fixture.write_bytes(fixture_blob)
    source_header.write_bytes(header_blob)
    temporary = out / 'tmp-private'
    temporary.mkdir()
    env = {'PATH': str(compiler.parent) + ':/usr/bin:/bin:/usr/sbin:/sbin',
           'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': str(temporary)}
    obj = out / 'mapper-probe.o'
    dependencies = out / 'mapper-probe.d'
    command = [str(compiler), '-arch', 'x86_64', '-mmacosx-version-min=11.0', '-mkernel',
               '-fno-builtin', '-fno-common', '-nostdinc', '-I' + str(sdk / 'Headers'),
               '-I' + str(source_dir), '-DKERNEL', '-DKERNEL_PRIVATE', '-DDRIVER_PRIVATE',
               '-DAPPLE', '-DNeXT', '-Os', '-Wall', '-Wextra', '-Werror', '-std=c++17',
               '-fapple-kext', '-fno-rtti', '-fno-exceptions', '-MMD', '-MF', str(dependencies),
               '-c', str(source_fixture), '-o', str(obj)]
    result = subprocess.run(command, cwd=out, env=env, stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=90)
    (out / 'compile.stderr').write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError('Native mapper probe object compilation failed; preserve private output')
    dep_paths = [Path(path).resolve() for path in shlex.split(
        dependencies.read_text().replace('\\\n', ' ').split(':', 1)[1])]
    expected_paths = {(source_fixture.resolve(), fixture_blob), (source_header.resolve(), header_blob)}
    allowed = {path: blob for path, blob in expected_paths}
    allowed.update({(sdk / name).resolve(): blob for name, blob in sdk_blobs.items()})
    if not dep_paths or any(path not in allowed for path in dep_paths):
        raise ValueError('Native compile escaped the fixture and reviewed SDK inputs')
    if any(path.read_bytes() != blob for path, blob in allowed.items()):
        raise ValueError('Native source or reviewed SDK input drift')
    if struct.unpack_from('<4I', obj.read_bytes()) != (0xfeedfacf, 0x1000007, 3, 1):
        raise ValueError('Require x86_64 MH_OBJECT, never a loadable kernel bundle')
    imports = subprocess.check_output(['/usr/bin/nm', '-arch', 'x86_64', '-uj', str(obj)],
                                      text=True, timeout=15).splitlines()
    if not any('getMatchingServices' in name for name in imports):
        raise ValueError('Native object did not reference the current-service enumeration API')
    if any('copyMapperForDevice' in name or 'waitForMatchingService' in name for name in imports):
        raise ValueError('Blocking mapper resolution API leaked into the source-only object')
    if sha(FIXTURE.read_bytes()) != sha(fixture_blob) or sha(HEADER.read_bytes()) != sha(header_blob):
        raise ValueError('Repository source changed during native compile')
    if sdk_inputs(sdk) != sdk_blobs or metadata.read_bytes() != metadata_blob:
        raise ValueError('Reviewed SDK or KDK metadata changed during native compile')
    if file_sha(compiler) != compiler_hash:
        raise ValueError('Native compiler changed during compile')

    report = dict(status='passed-source-only-nonwaiting-mapper-sdk-object-check',
                  based_on_commit=subprocess.check_output(['/usr/bin/git', 'rev-parse', 'HEAD'],
                                                          cwd=ROOT, text=True, timeout=15).strip(),
                  branch=branch, kernel_build=34, os_version=os_version, os_build=os_build,
                  sdk_commit=SDK_PIN, sdk_tracked_input_count=len(sdk_blobs),
                  fixture_sha256=sha(fixture_blob), resolver_header_sha256=sha(header_blob),
                  compiler_sha256=compiler_hash, object_sha256=sha(obj.read_bytes()),
                  native_kernel_sdk_compile=True, nonloadable_x86_64_MH_OBJECT=True,
                  imports=sorted(imports), current_services_api_imported=True,
                  blocking_mapper_apis_imported=False, linked=False, kext_bundle_created=False,
                  signed=False, installed=False, loaded=False, IOKit_opened=False,
                  mapper_lookup_executed=False, DMA_mapping_created=False,
                  GPU_executed=False, device_dma_domain_proven=False,
                  route_provider_proven=False, raw_registry_saved=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ['status', 'sdk_commit',
                                                   'nonloadable_x86_64_MH_OBJECT',
                                                   'blocking_mapper_apis_imported',
                                                   'GPU_executed']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', required=True, type=Path)
    parser.add_argument('--kdk', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    arguments = parser.parse_args()
    test(arguments.out, arguments.sdk, arguments.kdk)
