#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile complete staged R3 source to a nonloadable object and audit timer KPIs.

No linking, kext packaging, signing, installation, IOKit open or GPU execution.
Successful compilation is deliberately distinct from native KPI admission.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import plistlib
import re
import shlex
import struct
import subprocess

from build34_exact_native_sdk import stage, stage_header
from build34_exact_service_timer import stage as previous_stage
from test_build34_exact_ownership import DRIVER, ROOT, sha
from upstream34_layout.ring_padding_candidate import SDK_PIN, sdk_inputs

PRIOR = 'docs/validation/build34-r3-service-timer-offline-20261121.json'
RECIPES = ('tools/build34_exact_native_sdk.py', 'tools/test_build34_exact_native_sdk.py',
           'tools/upstream34_layout/ring_padding_candidate.py',
           'tools/upstream34_layout/ring_padding.py', 'tools/upstream34_layout/mec_range.py')
HEADERS = ('build34_exact_fence32.h', 'build34_exact_callbacks.h',
           'build34_exact_receipt_wire.h', 'build34_exact_submit_wire.h')


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
        raise ValueError('Require a fresh ignored worktree build path ending -private')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    branch = subprocess.check_output(['/usr/bin/git', 'symbolic-ref', '--short', 'HEAD'],
                                     cwd=ROOT, text=True, timeout=15).strip()
    if branch != 'upstream34/vram-layout-fix':
        raise ValueError('Default build34 branch only')
    prior_blob = (ROOT / PRIOR).read_bytes()
    prior = json.loads(prior_blob)
    if prior['status'] != 'passed-CPU-only-owned-service-timer-drain' or prior['GPU_executed']:
        raise ValueError('Require the completed CPU timer prerequisite, not hardware admission')
    inputs = {n: (ROOT / n).read_bytes() for n in prior['input_sha256']}
    if any(sha(b) != prior['input_sha256'][n] for n, b in inputs.items()):
        raise ValueError('Production/prior input drift')
    inputs.update({n: (ROOT / n).read_bytes() for n in RECIPES})
    inputs[PRIOR] = prior_blob
    names = subprocess.check_output(['/usr/bin/git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'],
                                    cwd=ROOT, text=True, timeout=15).splitlines()
    protected = {n: (ROOT / n).read_bytes() for n in names}
    sdk_blobs = sdk_inputs(sdk)
    kdk = Path(kdk).resolve()
    metadata = kdk / 'System/Library/CoreServices/SystemVersion.plist'
    metadata_blob = metadata.read_bytes()
    version = plistlib.loads(metadata_blob)
    os_version = subprocess.check_output(['/usr/bin/sw_vers', '-productVersion'], text=True, timeout=15).strip()
    os_build = subprocess.check_output(['/usr/bin/sw_vers', '-buildVersion'], text=True, timeout=15).strip()
    if (version['ProductVersion'], version['ProductBuildVersion']) != (os_version, os_build):
        raise ValueError('KDK and current OS version/build do not match')
    provider_root = 'System/Library/Extensions/System.kext/PlugIns/'
    providers = {}
    for name in ['Mach', 'Unsupported', 'Private']:
        for leaf in [name, 'Info.plist']:
            path = provider_root + name + '.kext/' + leaf
            if (kdk / path).is_symlink():
                raise ValueError('Unexpected KDK provider link')
            providers[path] = (kdk / path).read_bytes()
    compiler = Path(subprocess.check_output(['/usr/bin/xcrun', '--find', 'clang++'],
                                           text=True, timeout=15).strip()).resolve()
    toolchain = {str(p): file_sha(p) for p in [compiler, Path('/usr/bin/nm')]}
    original = inputs[DRIVER].decode()
    previous, staged = previous_stage(original), stage(original)
    insertion = 'class IOAccelPhxNativeClient;\n\n'
    if staged.replace(insertion, '', 1) != previous or staged.count(insertion) != 1:
        raise ValueError('Only the missing client forward declaration is in scope')
    if sha(previous.encode()) != prior['staged_driver_sha256']:
        raise ValueError('Staged predecessor source drift')
    if sha(stage_header(inputs['tools/build34_exact_ownership.h'].decode()).encode()) != prior['staged_header_sha256']:
        raise ValueError('Staged predecessor header drift')
    if '#define PHX_KEXT_BUILD 34u\n' not in staged or re.search(
            r'exactDwordReader\s*=|exactFenceReader\s*=|exactRequested\s*=', staged):
        raise ValueError('No reader, exact mode or build identity change admitted')
    out.mkdir(parents=True, mode=0o700)
    for base, blobs in [('frozen', inputs), ('sdk', sdk_blobs), ('kdk', providers)]:
        for name, blob in blobs.items():
            p = out / base / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(blob)
    tmp = out / 'tmp-private'
    tmp.mkdir()
    environment = {'PATH': str(compiler.parent) + ':/usr/bin:/bin:/usr/sbin:/sbin',
                   'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': str(tmp)}

    def run(args, label, expected_failure=False):
        result = subprocess.run([str(a) for a in args], cwd=out, env=environment,
                                stdin=subprocess.DEVNULL, capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_bytes(result.stdout)
        (out / (label + '.stderr')).write_bytes(result.stderr)
        if expected_failure:
            if not result.returncode or b"unknown type name 'IOAccelPhxNativeClient'" not in result.stderr:
                raise ValueError('Missing native forward-declaration defect did not reproduce')
        elif result.returncode:
            raise RuntimeError(label + ' failed; preserve private evidence')
        return result

    flags = ['-arch', 'x86_64', '-mmacosx-version-min=11.0', '-mkernel', '-fno-builtin',
             '-fno-common', '-nostdinc', '-I' + str(out / 'sdk/Headers'), '-DKERNEL',
             '-DKERNEL_PRIVATE', '-DDRIVER_PRIVATE', '-DAPPLE', '-DNeXT', '-Os', '-Wall',
             '-std=c++17', '-fapple-kext', '-fno-rtti', '-fno-exceptions']
    warnings, imports, objects = {}, {}, {}
    for role, text in [('control', original), ('previous', previous), ('staged', staged)]:
        source = out / role
        closure = {DRIVER: text.encode(), 'src/phxbringup/PhxNativeABI.h': inputs['src/phxbringup/PhxNativeABI.h'],
                   'src/amd/phx_topology.h': inputs['src/amd/phx_topology.h']}
        if role != 'control':
            closure['src/phxbringup/build34_exact_ownership.h'] = stage_header(inputs['tools/build34_exact_ownership.h'].decode()).encode()
            closure.update({'src/phxbringup/' + n: inputs['tools/' + n] for n in HEADERS})
        for name, blob in closure.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
        command = [str(compiler), *flags]
        if role == 'previous':
            run([*command, '-fsyntax-only', source / DRIVER], role, expected_failure=True)
            continue
        obj, dep = out / (role + '.o'), out / (role + '.d')
        result = run([*command, '-MMD', '-MF', dep, '-c', source / DRIVER, '-o', obj], role)
        messages = result.stderr.decode()
        warnings[role] = re.findall(r'warning: (.+)', messages)
        expected = (["declaration shadows a field of 'PhxBringup' [-Wshadow]"] * 3 +
                    (["private field 'exactFenceReader' is not used [-Wunused-private-field]"] if role == 'staged' else []))
        if sorted(warnings[role]) != sorted(expected):
            raise ValueError('Review unexpected compiler diagnostics in ' + role)
        allowed = {(source / n).resolve(): b for n, b in closure.items()}
        allowed.update({(out / 'sdk' / n).resolve(): b for n, b in sdk_blobs.items()})
        deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        if not deps or any(Path(n).resolve() not in allowed for n in deps):
            raise ValueError('Unfrozen native compiler dependency')
        if any(p.read_bytes() != b for p, b in allowed.items()):
            raise ValueError('Native source or SDK snapshot drift')
        data = obj.read_bytes()
        if struct.unpack_from('<4I', data) != (0xfeedfacf, 0x1000007, 3, 1):
            raise ValueError('Require x86_64 MH_OBJECT, never a loadable kernel bundle')
        undefined = run(['/usr/bin/nm', '-arch', 'x86_64', '-uj', obj], role + '-imports')
        imports[role] = set(undefined.stdout.decode().splitlines())
        objects[role] = sha(data)
    timer_symbols = sorted(s for s in imports['staged'] if s.startswith('_thread_call_'))
    exports, provider_hashes = {}, {}
    for name in ['Mach', 'Unsupported', 'Private']:
        path = provider_root + name + '.kext/' + name
        info = plistlib.loads(providers[provider_root + name + '.kext/Info.plist'])
        if info['CFBundleIdentifier'] != 'com.apple.kpi.' + name.lower():
            raise ValueError('Unexpected KDK timer provider identity')
        result = run(['/usr/bin/nm', '-arch', 'x86_64', '-gj', out / 'kdk' / path], name + '-exports')
        exports[name] = set(result.stdout.decode().splitlines())
        provider_hashes[name] = sha(providers[path])
    public = exports['Mach'] | exports['Unsupported']
    private_only = sorted(s for s in timer_symbols if s not in public and s in exports['Private'])
    unresolved = sorted(s for s in timer_symbols if not any(s in v for v in exports.values()))
    if private_only != ['_thread_call_cancel_wait'] or unresolved:
        raise ValueError('Review changed native timer KPI availability')
    if '_thread_call_cancel_wait' not in imports['control']:
        raise ValueError('Reclassify cancellation dependency: it is no longer inherited from the control')
    if '_thread_call_allocate_with_options' not in exports['Mach']:
        raise ValueError('New allocation API has no public Mach provider')
    if any((ROOT / n).read_bytes() != b or (out / 'frozen' / n).read_bytes() != b for n, b in inputs.items()):
        raise ValueError('Frozen prerequisite or recipe drift')
    if any((ROOT / n).read_bytes() != b for n, b in protected.items()):
        raise ValueError('Production input drift')
    if sdk_inputs(sdk) != sdk_blobs or metadata.read_bytes() != metadata_blob:
        raise ValueError('Reviewed SDK/KDK identity drift')
    if any((kdk / n).read_bytes() != b or (out / 'kdk' / n).read_bytes() != b for n, b in providers.items()):
        raise ValueError('KDK timer provider drift')
    if any(file_sha(Path(n)) != h for n, h in toolchain.items()):
        raise ValueError('Native toolchain changed')
    report = dict(status='passed-native-translation-unit-check-KPI-admission-refused', kernel_build=34,
                  os_version=os_version, os_build=os_build, sdk_commit=SDK_PIN, sdk_file_count=len(sdk_blobs),
                  input_sha256={n: sha(b) for n, b in inputs.items()},
                  original_production_file_count=len(protected), production_unchanged=True,
                  staged_driver_sha256=sha(staged.encode()),
                  staged_header_sha256=prior['staged_header_sha256'],
                  actual_complete_native_translation_unit_compiled=True,
                  native_Kernel_SDK_compile=True, native_object_only=True,
                  previous_missing_client_forward_declaration_reproduced=True,
                  sole_source_change='client forward declaration before service class',
                  compiler_warnings=warnings, nonloadable_object_sha256=objects,
                  control_import_count=len(imports['control']), staged_import_count=len(imports['staged']),
                  added_imports=sorted(imports['staged'] - imports['control']),
                  removed_imports=sorted(imports['control'] - imports['staged']),
                  timer_KPI_providers={s: [k for k, v in exports.items() if s in v] for s in timer_symbols},
                  private_only_timer_imports=private_only, inherited_private_cancellation_dependency=True,
                  KDK_metadata_matches_current_OS_build=True, KDK_timer_provider_sha256=provider_hashes,
                  KDK_metadata_sha256=sha(metadata_blob), native_KPI_admission=False,
                  full_import_resolution_or_collection_inclusion_tested=False,
                  native_reader_or_mode_bound=False, service_permanent_quarantine_removed=False,
                  linked=False, kernel_bundle_created=False, signed=False, installed=False, loaded=False,
                  IOKit_opened=False, GPU_executed=False, physical_FPS_measured=False,
                  long_term_stability_accepted=False, R3_goal_complete=False, R4_R6_started=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['status', 'actual_complete_native_translation_unit_compiled',
                                           'private_only_timer_imports', 'GPU_executed', 'R3_goal_complete']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--sdk', required=True, type=Path)
    parser.add_argument('--kdk', required=True, type=Path)
    args = parser.parse_args()
    test(args.out, args.sdk, args.kdk)
