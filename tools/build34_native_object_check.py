#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile complete R3 source to nonloadable objects and check declared KPIs.

Never links/packages a kernel, installs, opens a device or executes GPU work.
Prior frozen runners are deliberately not rewritten to use this helper.
"""
import json
from pathlib import Path
import plistlib
import re
import shlex
import struct
import subprocess

from test_build34_exact_ownership import DRIVER, sha
from test_build34_exact_native_sdk import file_sha
from upstream34_layout.ring_padding_candidate import SDK_PIN, sdk_inputs
from build34_kpi_symbolset import interface_exports

HEADERS = ('build34_exact_fence32.h', 'build34_exact_callbacks.h', 'build34_exact_receipt_wire.h', 'build34_exact_submit_wire.h')


def check(out, inputs, previous, proposed, ownership, sdk, kdk, expected_import_count,
          expected_warnings, reference, compiler_expected):
    out = Path(out)
    if out.exists():
        raise ValueError('Fresh native-object output only')
    sdk_blobs = sdk_inputs(sdk)
    compiler, nm = [Path(subprocess.check_output(['/usr/bin/xcrun', '--find', t], text=True, timeout=15).strip()).resolve()
                    for t in ['clang++', 'nm']]
    if compiler != compiler_expected:
        raise ValueError('CPU/native compiler identity differs')
    tools = {p: file_sha(p) for p in [compiler, nm]}
    kdk = Path(kdk).resolve()
    metadata = kdk / 'System/Library/CoreServices/SystemVersion.plist'
    metadata_blob = metadata.read_bytes()
    version = plistlib.loads(metadata_blob)
    os_version = subprocess.check_output(['/usr/bin/sw_vers', '-productVersion'], text=True, timeout=15).strip()
    os_build = subprocess.check_output(['/usr/bin/sw_vers', '-buildVersion'], text=True, timeout=15).strip()
    kernel = kdk / 'System/Library/Kernels/kernel'
    kernel_hash = file_sha(kernel)
    if ((version['ProductVersion'], version['ProductBuildVersion']) != (os_version, os_build) or
            sha(metadata_blob) != reference['KDK_metadata_sha256'] or kernel_hash != reference['KDK_kernel_sha256']):
        raise ValueError('Require unchanged, current-OS-metadata-matching KDK')
    base = 'System/Library/Extensions/System.kext/PlugIns/'
    providers = {'com.apple.kpi.' + n: (base + f + '.kext/' + f, base + f + '.kext/Info.plist') for n, f in
                 [('bsd', 'BSDKernel'), ('iokit', 'IOKit'), ('libkern', 'Libkern'), ('mach', 'Mach'), ('unsupported', 'Unsupported')]}
    providers['com.apple.iokit.IOPCIFamily'] = ('System/Library/Extensions/IOPCIFamily.kext/Contents/MacOS/IOPCIFamily',
                                             'System/Library/Extensions/IOPCIFamily.kext/Contents/Info.plist')
    if set(plistlib.loads(inputs['src/phxbringup/Info.plist'])['OSBundleLibraries']) != set(providers):
        raise ValueError('No provider/dependency additions')
    provider_blobs = {p: (kdk / p).read_bytes() for paths in providers.values() for p in paths}
    for name, paths in providers.items():
        if (sha(provider_blobs[paths[0]]) != reference['KDK_declared_provider_sha256'][name] or
                plistlib.loads(provider_blobs[paths[1]])['CFBundleIdentifier'] != name):
            raise ValueError('Provider identity drift')
    out.mkdir(mode=0o700)
    for category, blobs in [('sdk', sdk_blobs), ('kdk', provider_blobs)]:
        for name, blob in blobs.items():
            p = out / category / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(blob)
    tmp = out / 'tmp-private'
    tmp.mkdir()
    env = {'PATH': str(compiler.parent) + ':/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': str(tmp)}

    def run(args, label):
        p = subprocess.run([str(a) for a in args], cwd=out, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if p.returncode:
            raise RuntimeError(label + ' failed; preserve private evidence')
        return p

    flags = ['-arch', 'x86_64', '-mmacosx-version-min=11.0', '-mkernel', '-fno-builtin', '-fno-common', '-nostdinc',
             '-I' + str(out / 'sdk/Headers'), '-DKERNEL', '-DKERNEL_PRIVATE', '-DDRIVER_PRIVATE', '-DAPPLE', '-DNeXT',
             '-Os', '-Wall', '-std=c++17', '-fapple-kext', '-fno-rtti', '-fno-exceptions']
    imports, warnings, objects = {}, {}, {}
    for label, text in [('previous', previous), ('proposed', proposed)]:
        base = out / label
        closure = {DRIVER: text.encode(), 'src/phxbringup/PhxNativeABI.h': inputs['src/phxbringup/PhxNativeABI.h'],
                   'src/amd/phx_topology.h': inputs['src/amd/phx_topology.h'], 'src/phxbringup/build34_exact_ownership.h': ownership.encode()}
        closure.update({'src/phxbringup/' + n: inputs['tools/' + n] for n in HEADERS})
        for name, blob in closure.items():
            p = base / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(blob)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        result = run([compiler, *flags, '-MMD', '-MF', dep, '-c', base / DRIVER, '-o', obj], label + '-native-compile')
        warnings[label] = re.findall(r'warning: (.+)', result.stderr.decode())
        if sorted(warnings[label]) != sorted(expected_warnings):
            raise ValueError('Unexpected native compiler diagnostics')
        allowed = {(base / n).resolve() for n in closure} | {(out / 'sdk' / n).resolve() for n in sdk_blobs}
        deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        if not deps or any(Path(n).resolve() not in allowed for n in deps):
            raise ValueError('Unfrozen native compiler dependency')
        if any((base / n).read_bytes() != b for n, b in closure.items()):
            raise ValueError('Native source snapshot drift')
        blob = obj.read_bytes()
        if struct.unpack_from('<4I', blob) != (0xfeedfacf, 0x1000007, 3, 1):
            raise ValueError('Require nonloadable x86_64 MH_OBJECT')
        objects[label] = sha(blob)
        imports[label] = set(run([nm, '-arch', 'x86_64', '-uj', obj], label + '-imports').stdout.decode().splitlines())
    kernel_defs = set(run([nm, '-arch', 'x86_64', '-gUj', kernel], 'kernel-defined-externals').stdout.decode().splitlines())
    exports = {}
    for name, paths in providers.items():
        if plistlib.loads(provider_blobs[paths[1]]).get('OSKernelResource') is True:
            targets = interface_exports(provider_blobs[paths[0]])
            if set(targets.values()) - kernel_defs:
                raise ValueError('Unresolved KPI interface target')
            exports[name] = set(targets)
        else:
            exports[name] = set(run([nm, '-arch', 'x86_64', '-gUj', out / 'kdk' / paths[0]], name + '-exports').stdout.decode().splitlines())
    if (imports['previous'] != imports['proposed'] or len(imports['proposed']) != expected_import_count or
            imports['proposed'] - set().union(*exports.values()) or '_thread_call_cancel_wait' in imports['proposed']):
        raise ValueError('Changed, unavailable or private native imports')
    if (sdk_inputs(sdk) != sdk_blobs or any((out / 'sdk' / n).read_bytes() != b for n, b in sdk_blobs.items()) or
            metadata.read_bytes() != metadata_blob or file_sha(kernel) != kernel_hash or
            any((out / 'kdk' / n).read_bytes() != b or (kdk / n).read_bytes() != b for n, b in provider_blobs.items()) or
            any(file_sha(p) != h for p, h in tools.items())):
        raise ValueError('SDK/KDK/toolchain drift')
    result = dict(sdk_commit=SDK_PIN, os_version=os_version, os_build=os_build, native_object_sha256=objects,
                  native_import_count=len(imports['proposed']), compiler_warnings=warnings,
                  all_native_imports_have_existing_declared_KDK_provider=True, native_import_set_unchanged=True,
                  actual_complete_native_translation_units_compiled=True, native_object_only=True)
    (out / 'native-result-private.json').write_text(json.dumps(result, indent=2) + '\n')
    return result
