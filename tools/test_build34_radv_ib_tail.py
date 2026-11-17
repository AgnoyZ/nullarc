#!/usr/bin/env python3
"""Compile/run real patched Mesa transport against CPU fakes, never IOKit."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from upstream34_layout import radv_ib_tail

ROOT = Path(__file__).resolve().parents[1]


def run(args, out, name, timeout=90):
    result = subprocess.run([str(a) for a in args], stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=timeout)
    (out / (name + '.stdout')).write_bytes(result.stdout)
    (out / (name + '.stderr')).write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError(name + ' failed; inspect private logs')
    return result.stdout.decode()


def test(mesa, out):
    mesa, out = Path(mesa).resolve(), Path(out).resolve()
    preparation = radv_ib_tail.prepare(mesa, out)
    source = out / 'source' / radv_ib_tail.PREFIX
    cc = ['/usr/bin/xcrun', 'clang', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
          '-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
          '-fno-omit-frame-pointer', '-I' + str(source), '-I' + str(mesa / 'include'),
          '-I' + str(mesa / 'include/darwin'), '-I' + str(mesa / radv_ib_tail.PREFIX)]
    binary = out / 'cpu-transport-test'
    run(cc + [ROOT / 'tests/test_build34_radv_ib_tail.c', source / 'ac_darwin_kext.c', '-o', binary],
        out, 'compile')
    text = run([binary], out, 'transport')
    match = re.fullmatch(r'PASS actual Mesa transport: (\d+) checks; 1028 split/fence cases; admission, ownership and validation\n', text)
    if not match:
        raise RuntimeError('Missing complete transport-test framing')

    # Enumerators are parsed from this exact C fixture, rather than duplicated
    # numeric constants that can silently drift when a fault is added.
    fixture = (ROOT / 'tests/test_build34_radv_ib_tail.c').read_text()
    fields = re.search(r'enum fault \{([^}]+)\}', fixture).group(1).split(',')
    faults = {field.strip(): index for index, field in enumerate(fields)}
    hold_names = [key for key in faults if key.startswith(('SUBMIT_', 'RETIRE_'))]
    for name in hold_names:
        with (out / (name + '.stdout')).open('wb') as stdout, (out / (name + '.stderr')).open('wb') as stderr:
            process = subprocess.Popen([str(binary), '--hold', str(faults[name])],
                                       stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
            try:
                try:
                    process.wait(timeout=0.8)
                except subprocess.TimeoutExpired:
                    log = (out / (name + '.stderr')).read_text()
                    if log != 'HOLD: original34 IB-tail teardown lacks positive retirement; recovery required\n':
                        raise RuntimeError('HOLD not established: ' + name)
                else:
                    raise RuntimeError('CPU failure case exited instead of retaining the connection: ' + name)
            finally:
                # This binary has only fake CPU ops. NEVER apply this cleanup
                # to a native/GPU probe, which must retain all resources.
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)

    # Original tests predate downstream's Phoenix-only service restriction.
    # Prove the exact same eight failures on baseline and patched source before
    # counting any unaffected upstream checks; do not silently drop failures.
    upstream = mesa / radv_ib_tail.PREFIX / 'test/acd_kext_test.c'
    baseline = out / 'upstream-baseline'
    patched = out / 'upstream-patched'
    expected_lines = None
    for target, csource in ((baseline, mesa / radv_ib_tail.PREFIX / 'ac_darwin_kext.c'),
                            (patched, source / 'ac_darwin_kext.c')):
        run(cc + [upstream, csource, '-o', target], out, target.name + '-compile')
        result = subprocess.run([str(target)], capture_output=True, timeout=30)
        (out / (target.name + '.stdout')).write_bytes(result.stdout)
        (out / (target.name + '.stderr')).write_bytes(result.stderr)
        lines = result.stdout.decode().splitlines()
        failures = [line.split(': ', 1)[1] for line in lines if line.startswith('FAIL ')]
        if result.returncode != 1 or len(failures) != 8 or lines[-1] != 'acd_kext_test: 134 checks, 8 failures':
            raise RuntimeError('Unexpected upstream baseline result')
        if any('service_class' not in line for line in failures):
            raise RuntimeError('Upstream failure unrelated to historical service restriction')
        if expected_lines is None:
            expected_lines = failures
        elif failures != expected_lines:
            raise RuntimeError('Patched transport introduces an upstream regression')

    # These translation units have pre-existing unused parameters. Suppress
    # only that warning, matching Mesa's policy; all others remain errors.
    run(cc + ['-Wno-unused-parameter', '-I' + str(mesa / 'src'),
              '-I' + str(mesa / 'src/amd'), '-fsyntax-only', source / 'ac_darwin_drm.c'],
        out, 'core-syntax')
    core_binary = out / 'cpu-core-test'
    run(cc + ['-Wno-unused-parameter', '-I' + str(mesa / 'src'),
              '-I' + str(mesa / 'src/amd'), '-Wl,-dead_strip',
              # Vendored libdrm's overridable container_of spells offsetof as
              # &((type *)0)->member, which trips UBSan even on baseline. Use
              # the compiler's equivalent offset intrinsic in this CPU build;
              # retain every sanitizer and leave Mesa source unchanged.
              '-Dlibdrm_container_of(ptr,sample,member)=((void *)((char *)(ptr) - __builtin_offsetof(__typeof__(*(sample)), member)))',
              ROOT / 'tests/test_build34_radv_ib_tail_core.c', source / 'ac_darwin_kext.c',
              mesa / radv_ib_tail.PREFIX / 'amdgpu_vamgr.c', '-o', core_binary],
        out, 'core-compile')
    core_text = run([core_binary], out, 'core')
    core_match = re.fullmatch(r'PASS real Mesa core and VA allocator: (\d+) checks; shared ownership, reserved VA, fail-closed opt-in\n', core_text)
    if not core_match:
        raise RuntimeError('Missing complete core-test framing')
    # Run the actual native-probe control flow with fake IOKit only. Link the
    # real core, sync provider, canned device and VA allocator: no alternate CS
    # implementation and no GPU ISA simulation enters this executable.
    objects = []
    actual_c = [source / 'ac_darwin_kext.c', source / 'ac_darwin_drm.c',
                mesa / radv_ib_tail.PREFIX / 'ac_darwin_sync.c',
                mesa / radv_ib_tail.PREFIX / 'amdgpu_vamgr.c',
                mesa / 'src/amd/common/amdgpu_devices.c']
    extra = ['-Wno-unused-parameter', '-I' + str(mesa / 'src'), '-I' + str(mesa / 'src/amd')]
    offset_macro = '-Dlibdrm_container_of(ptr,sample,member)=((void *)((char *)(ptr) - __builtin_offsetof(__typeof__(*(sample)), member)))'
    for path in actual_c:
        obj = out / (path.stem + '.o')
        run(cc + extra + ([offset_macro] if path.stem == 'amdgpu_vamgr' else []) +
            ['-c', path, '-o', obj], out, 'probe-' + path.stem)
        objects.append(obj)
    cpp = [arg.replace('clang', 'clang++') if arg == 'clang' else
           '-std=c++17' if arg == '-std=gnu11' else arg for arg in cc]
    fake_probe = out / 'cpu-probe-test'
    run(cpp + extra + ['-I' + str(ROOT / 'tests/fake_build34_ib_preamble'),
                       ROOT / 'tests/test_build34_radv_ib_tail_probe.cpp'] + objects + ['-o', fake_probe],
        out, 'probe-link')
    probe_faults = ['ok', 'check', 'args', 'host-arm', 'host-old', 'wrong-pci', 'non-pci',
                    'ambiguous', 'build41', 'build42', 'minor', 'hung', 'ctx-zero', 'ctx-flags',
                    'create-size', 'map-short', 'submit-first', 'submit-second',
                    'wait-error', 'wait-busy', 'wait-retired', 'stale']
    probe_faults += ['corrupt-' + str(i) for i in (0, 315, 316, 4095, 4096, 4415,
                                                  4608, 5120, 8191, 8208, 9232, 16383)]
    for mode in ('single', 'tail'):
        for fault in probe_faults:
            text = run([fake_probe, fault, mode], out, 'probe-' + mode + '-' + fault, timeout=10)
            if not re.search(r'^CPU-PROBE-PASS ' + mode + ' ' + fault + r' submitted=\d+ held=[01]\n$', text, re.M):
                raise RuntimeError('Incomplete CPU probe case: ' + mode + '/' + fault)
    radv_ib_tail.verified_source(mesa)
    report = {'actual_marshaller_compiled_and_executed': True, 'asan_ubsan': True,
              'transport_checks': int(match.group(1)), 'split_fence_cases': 1028,
              'independent_CPU_hold_cases': len(hold_names),
              'upstream_checks_unchanged': 126,
              'historical_upstream_service_assertion_failures_unchanged': 8,
              'core_translation_unit_compiled': True, 'core_lifecycle_executed': True,
              'core_lifecycle_checks': int(core_match.group(1)), 'concurrent_submit_threads': 2,
              'CPU_allocator_container_of': 'compiler offsetof; no sanitizer disabled',
              'actual_probe_CPU_cases': 2 * len(probe_faults),
              'patch_sha256': preparation['patch_sha256'], 'installed': False,
              'GPU_executed': False, 'native_binary_executed': False}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesa-source', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    test(args.mesa_source, args.out)
