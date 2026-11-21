#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check isolated BAR0 metadata preparation; nonloadable objects and CPU only."""
import argparse
import json
from pathlib import Path
import platform
import plistlib
import re
import shlex
import struct
import subprocess

import build34_map_observation as observation
from build34_exact_factory import stage, stage_header
from build34_native_object_check import check as native_check
from build34_kpi_symbolset import interface_exports
from test_build34_exact_ownership import ROOT, DRIVER, sha
from test_build34_exact_native_sdk import file_sha
from upstream34_layout.ring_padding_candidate import SOURCE_INPUTS

PRIOR = 'docs/validation/build34-r3-factory-offline-20261121.json'
NEW = ['tools/build34_map_observation.py', 'tools/test_build34_map_observation.py',
       'tests/test_build34_map_observation.py', 'tests/test_build34_map_observation.cpp']
BASE_BINARY = '0414c22119bad9526a33ec97bb56b9e7a8fd26320976cf24e0cb541d0d882d10'


def test(out, sdk, kdk):
    if platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        raise ValueError('Require native Intel macOS')
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require fresh private worktree build output')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    if subprocess.check_output(['/usr/bin/git', 'symbolic-ref', '--short', 'HEAD'], cwd=ROOT, text=True, timeout=15).strip() != 'upstream34/vram-layout-fix':
        raise ValueError('Default build34 only')
    prior_blob = (ROOT / PRIOR).read_bytes()
    prior = json.loads(prior_blob)
    inputs = {name: (ROOT / name).read_bytes() for name in prior['input_sha256']}
    if any(sha(blob) != prior['input_sha256'][name] for name, blob in inputs.items()):
        raise ValueError('Frozen production/prerequisite drift')
    inputs.update({name: (ROOT / name).read_bytes() for name in NEW + [PRIOR]})
    names = subprocess.check_output(['/usr/bin/git', 'ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py'], cwd=ROOT, text=True, timeout=15).splitlines()
    protected = {name: (ROOT / name).read_bytes() for name in names}
    for name in SOURCE_INPUTS:
        if subprocess.check_output(['/usr/bin/git', 'show', observation.BASE_COMMIT + ':' + name], cwd=ROOT, timeout=15) != (ROOT / name).read_bytes():
            raise ValueError('Accepted R1b source/license/build inputs differ')
    reference_binary = ROOT / 'build/build34-r1b1-backpressure-20261120-private/native/source/src/phxbringup/build/PhxBringup.kext/Contents/MacOS/PhxBringup'
    if file_sha(reference_binary) != BASE_BINARY:
        raise ValueError('Accepted R1b reference artifact differs')
    original = inputs[DRIVER].decode()
    previous, proposed = stage(original), observation.stage_factory(original)
    baseline_proposed = observation.stage_baseline(original)
    if (sha(previous.encode()) != prior['staged_driver_sha256'] or
            proposed.replace(observation.OBSERVATION, '', 1) != previous or
            baseline_proposed.replace(observation.OBSERVATION, '', 1) != original):
        raise ValueError('Unrelated source changes')
    out.mkdir(parents=True, mode=0o700)
    for name, blob in inputs.items():
        path = out / 'frozen' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    compiler = Path(subprocess.check_output(['/usr/bin/xcrun', '--find', 'clang++'], text=True, timeout=15).strip()).resolve()
    host_sdk = Path(subprocess.check_output(['/usr/bin/xcrun', '--show-sdk-path'], text=True, timeout=15).strip()).resolve()
    tool_hashes = {path: file_sha(path) for path in [compiler, host_sdk / 'SDKSettings.json']}
    tmp = out / 'tmp-private'
    tmp.mkdir()
    env = {'PATH': str(compiler.parent) + ':/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': str(tmp)}

    def run(args, label, expected=0):
        p = subprocess.run([str(a) for a in args], cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if p.returncode != expected:
            raise RuntimeError(label + ' failed; preserve private evidence')
        return p

    unit = run(['/usr/bin/python3', '-B', ROOT / NEW[2]], 'python-tests')
    if b'Ran 13 tests' not in unit.stderr or not unit.stderr.rstrip().endswith(b'OK'):
        raise ValueError('Expected complete Python unit suite')
    block = observation.ANCHOR.replace('    }\n', observation.OBSERVATION + '    }\n')
    if proposed.count(block) != 1 or baseline_proposed.count(block) != 1:
        raise ValueError('CPU fixture must use the actual unique staged block')
    fixture = inputs[NEW[3]].decode()
    if fixture.count('// PHX34_MAPPING_BLOCK') != 1:
        raise ValueError('Unique CPU fixture insertion only')
    source = out / 'mapping-CPU-only.cpp'
    binary = out / 'mapping-CPU-only'
    source.write_text(fixture.replace('// PHX34_MAPPING_BLOCK', block))
    cc = [compiler, '--driver-mode=g++', '-isysroot', host_sdk, '-std=c++17', '-O1', '-g',
          '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-fno-sanitize-recover=all']
    compiled = run([*cc, source, '-o', binary], 'cpu-compile')
    if compiled.stderr:
        raise ValueError('Unexpected CPU compiler diagnostics')
    linkage = run(['/usr/bin/otool', '-L', binary], 'cpu-linkage').stdout.decode()
    if re.search(r'IOKit|Metal|vulkan|PhxAccel', linkage, re.I):
        raise ValueError('CPU fixture must not link device runtime')
    cpu = run([binary], 'cpu-test')
    if cpu.stderr:
        raise ValueError('Unexpected sanitizer diagnostics')
    # These regressions must fail at an assertion, never merely fail to compile.
    mutants = [observation.OBSERVATION.replace('if (optionsPublished && cachePublished)', 'if (true || (optionsPublished && cachePublished))'),
               observation.OBSERVATION.replace('(observedBar0MapOptions & kIOMapCacheMask)', '(observedBar0MapOptions & (kIOMapCacheMask | ~0u))'),
               observation.OBSERVATION.replace('fbAper->getMapOptions()', '(fbAper->getMapOptions(), 0x400u)')]
    for i, mutant in enumerate(mutants):
        broken_block = block.replace(observation.OBSERVATION, mutant)
        broken_source, broken_binary = out / f'mutant-{i}-CPU-only.cpp', out / f'mutant-{i}-CPU-only'
        broken_source.write_text(fixture.replace('// PHX34_MAPPING_BLOCK', broken_block))
        run([*cc, broken_source, '-o', broken_binary], f'mutant-{i}-compile')
        result = run([broken_binary], f'mutant-{i}-test', expected=86)
        if not result.stderr.startswith(b'failed '):
            raise ValueError('Mutant did not hit intended assertion')
    ownership = stage_header(inputs['tools/build34_exact_ownership.h'].decode())
    reference = json.loads(inputs['docs/validation/build34-r3-public-timer-offline-20261121.json'])
    native = native_check(out / 'native', inputs, previous, proposed, ownership, sdk, kdk,
                          prior['native_import_count'], prior['compiler_warnings']['proposed'], reference, compiler)
    # Compile both complete accepted-baseline forms too, without creating a kext.
    # Its inherited private cancellation import is reported, never whitewashed
    # by the public-provider check on the separate composed R3 source above.
    native_out = out / 'native'
    flags = ['-arch', 'x86_64', '-mmacosx-version-min=11.0', '-mkernel', '-fno-builtin', '-fno-common', '-nostdinc',
             '-I' + str(native_out / 'sdk/Headers'), '-DKERNEL', '-DKERNEL_PRIVATE', '-DDRIVER_PRIVATE', '-DAPPLE', '-DNeXT',
             '-Os', '-Wall', '-std=c++17', '-fapple-kext', '-fno-rtti', '-fno-exceptions']
    imports, baseline_objects = {}, {}
    for role, text in [('baseline', original), ('baseline-observation', baseline_proposed)]:
        base = out / role
        closure = {DRIVER: text.encode(), 'src/phxbringup/PhxNativeABI.h': inputs['src/phxbringup/PhxNativeABI.h'],
                   'src/amd/phx_topology.h': inputs['src/amd/phx_topology.h']}
        for name, blob in closure.items():
            path = base / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
        obj, dep = out / (role + '.o'), out / (role + '.d')
        result = run([compiler, *flags, '-MMD', '-MF', dep, '-c', base / DRIVER, '-o', obj], role + '-compile')
        if re.findall(r'warning: (.+)', result.stderr.decode()) != ["declaration shadows a field of 'PhxBringup' [-Wshadow]"] * 3:
            raise ValueError('Changed baseline warnings')
        if struct.unpack_from('<4I', obj.read_bytes()) != (0xfeedfacf, 0x1000007, 3, 1):
            raise ValueError('Require nonloadable x86_64 MH_OBJECT')
        allowed = {(base / n).resolve() for n in closure} | {(native_out / 'sdk' / p).resolve() for p in reference_sdk_paths(native_out)}
        deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        if not deps or any(Path(n).resolve() not in allowed for n in deps):
            raise ValueError('Unfrozen baseline native dependency')
        imports[role] = set(run(['/usr/bin/nm', '-arch', 'x86_64', '-uj', obj], role + '-imports').stdout.decode().splitlines())
        baseline_objects[role] = file_sha(obj)
    if imports['baseline'] != imports['baseline-observation'] or len(imports['baseline']) != 375:
        raise ValueError('Baseline observation changed native import set')
    offered = set()
    for path in sorted((native_out / 'kdk').rglob('*')):
        if path.is_file() and path.name in ('BSDKernel', 'IOKit', 'Libkern', 'Mach', 'Unsupported'):
            offered.update(interface_exports(path.read_bytes()))
        elif path.is_file() and path.name == 'IOPCIFamily' and path.parent.name == 'MacOS':
            offered.update(run(['/usr/bin/nm', '-arch', 'x86_64', '-gUj', path], 'baseline-pci-exports').stdout.decode().splitlines())
    missing = sorted(imports['baseline'] - offered)
    if missing != ['_thread_call_cancel_wait']:
        raise ValueError('Re-audit changed inherited baseline provider gap')
    passive = observation.collect()
    if passive['status'] != 'mapping-metadata-unavailable':
        raise ValueError('Live runtime changed; require independent observation review')
    if any((ROOT / n).read_bytes() != b or (out / 'frozen' / n).read_bytes() != b for n, b in inputs.items()):
        raise ValueError('Frozen input drift')
    if any((ROOT / n).read_bytes() != b for n, b in protected.items()) or file_sha(reference_binary) != BASE_BINARY:
        raise ValueError('Production/reference artifact drift')
    if any(file_sha(p) != h for p, h in tool_hashes.items()):
        raise ValueError('Compiler/host SDK drift')
    report = dict(schema_version=1, date='2026-11-21',
                  status='passed-source-CPU-native-object-mapping-observation-preparation',
                  branch='upstream34/vram-layout-fix', kernel_build=34,
                  accepted_R1b_source_commit=observation.BASE_COMMIT,
                  accepted_R1b_reference_binary_sha256=BASE_BINARY,
                  accepted_R1b_source_license_build_inputs_identical=True,
                  baseline_observation_driver_sha256=sha(baseline_proposed.encode()),
                  staged_driver_sha256=sha(proposed.encode()), staged_header_sha256=sha(ownership.encode()),
                  input_sha256={n: sha(b) for n, b in inputs.items()},
                  original_production_file_count=len(protected), production_unchanged=True,
                  python_unit_tests=13, actual_block_ASan_UBSan_result=cpu.stdout.decode().strip(),
                  assertion_mutants_detected=len(mutants), baseline_native_object_sha256=baseline_objects,
                  baseline_imports_unchanged=True, baseline_native_import_count=375,
                  baseline_imports_missing_from_declared_providers=missing,
                  inherited_private_dependency_is_not_new_admission=True,
                  passive_current_boot_observation=passive,
                  effective_mapping_cache_proven=False, native_reader_or_mode_bound=False,
                  native_candidate_admitted=False, native_lifecycle_accepted=False,
                  kernel_linked_or_packaged=False, installed=False, loaded=False, GPU_executed=False,
                  power_actions=0, physical_FPS_measured=False, long_term_stability_accepted=False,
                  **native)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['status', 'actual_block_ASan_UBSan_result', 'baseline_native_import_count',
          'native_import_count', 'production_unchanged', 'native_candidate_admitted', 'GPU_executed']}, sort_keys=True))
    return report


def reference_sdk_paths(native_out):
    return [p.relative_to(native_out / 'sdk') for p in (native_out / 'sdk').rglob('*') if p.is_file()]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--sdk', required=True, type=Path)
    parser.add_argument('--kdk', required=True, type=Path)
    args = parser.parse_args()
    test(args.out, args.sdk, args.kdk)
