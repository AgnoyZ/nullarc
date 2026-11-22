#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pair the pinned Mesa transport and staged native receipt handlers on CPU objects."""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

from build34_exact_submit import once
from test_build34_exact_ownership import ROOT, sha
from test_build34_exact_transport import DRM, KEXT, PATCH, PREFIX, SHAPE_PATCHES
from test_build34_exact_multitarget import apply, stage
from upstream34_layout import radv_ib_tail


def test(mesa, out):
    mesa, out = Path(mesa).resolve(), Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored worktree build path ending -private')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    protected_paths = ['src', 'tools/phxctl', 'tools/build_kext.py']
    subprocess.run(['/usr/bin/git', 'diff', '--quiet', 'e9ee265ce005693f2928b4f981dfd097ca53fb80',
                    '--', *protected_paths], cwd=ROOT, check=True, timeout=15)
    names = subprocess.check_output(['/usr/bin/git', 'ls-files', *protected_paths], cwd=ROOT,
                                    timeout=15, text=True).splitlines()
    if len(names) != 172:
        raise ValueError('Protected production inventory drift')
    protected = {name: sha((ROOT / name).read_bytes()) for name in names}
    mesa_source = radv_ib_tail.verified_source(mesa)
    native_case = 'tools/test_build34_exact_submit_receipt.py'
    transport_record = 'docs/validation/build34-r3-transport-offline-20261121.json'
    native_record = 'docs/validation/build34-r3-submit-receipt-offline-20261121.json'
    adapter = 'tools/build34_r3_mesa_wire.c'
    fixture = 'tests/test_build34_r3_mesa_wire.cpp'
    native_evidence = json.loads((ROOT / native_record).read_text())
    mesa_evidence = json.loads((ROOT / transport_record).read_text())
    patches = [*SHAPE_PATCHES, PATCH]
    paths = [adapter, 'tools/build34_r3_mesa_wire.h', 'tools/test_build34_r3_mesa_wire.py', fixture,
             transport_record, native_record, *patches, *native_evidence['input_sha256']]
    inputs = {name: (ROOT / name).read_bytes() for name in paths}
    pinned = {**native_evidence['input_sha256'], **{name: mesa_evidence['input_sha256'][name] for name in patches}}
    if any(sha(inputs[name]) != digest for name, digest in pinned.items()):
        raise ValueError('Previously reviewed inputs changed')
    out.mkdir(parents=True, mode=0o700)
    frozen, closure, native = out / 'frozen', out / 'mesa', out / 'native-private'
    stage(inputs, frozen)
    stage(mesa_source, closure)

    def run(args, label, *, cwd=out, timeout=90):
        result = subprocess.run([str(arg) for arg in args], cwd=cwd, stdin=subprocess.DEVNULL,
                                timeout=timeout, capture_output=True)
        (out / (label + '.stdout')).write_bytes(result.stdout)
        (out / (label + '.stderr')).write_bytes(result.stderr)
        if result.returncode or result.stderr:
            raise RuntimeError(label + ' failed; inspect private logs')
        return result.stdout.decode()

    run(['/usr/bin/git', 'init', '-q', closure], 'mesa-init')
    for patch in patches:
        apply(inputs[patch], closure, out, Path(patch).stem)
    mesa_staged = {name: (closure / name).read_bytes() for name in mesa_source}
    if {name: sha(data) for name, data in mesa_staged.items() if data != mesa_source[name]} != mesa_evidence['staged_Mesa_sha256']:
        raise ValueError('Mesa staged closure differs from reviewed 0007 result')
    if b'const struct acd_sync_backend be = {.wait_seq = acd_backend_wait_seq, .ctx = c->kext};' not in mesa_staged[DRM]:
        raise ValueError('Production Mesa exact capability must stay off')

    native_result = json.loads(run([sys.executable, '-B', ROOT / native_case, '--out', native],
                                   'native-regressions', cwd=ROOT, timeout=360))
    for key in ('staged_driver_sha256', 'staged_ownership_sha256', 'checks', 'groups'):
        if native_result[key] != native_evidence[key]:
            raise ValueError('Previously reviewed native result differs: ' + key)
    paired_native = native / 'paired-native-receipt.h'
    paired_native.write_text(once((native / 'submit-receipt.cpp').read_text(), 'int main() {\n',
                                 'void previous_receipt_suite() {\n'))
    native_headers = native / 'source/src/phxbringup'
    includes = ['-I' + str(path) for path in [native, native_headers, frozen / 'tools',
                native / 'frozen/src/phxbringup', *(closure / name for name in ('include', 'include/darwin', 'src', 'src/amd', PREFIX))]]
    allowed = {str(path.resolve()) for root in (frozen, closure, native_headers, native / 'frozen')
               for path in root.rglob('*') if path.is_file() and '.git' not in path.relative_to(root).parts}
    allowed |= {str(paired_native), str(native / 'submit-binding-CPU-only.h')}
    checks = {}
    for label, sanitizer in [('memory', 'address,undefined'), ('thread', 'thread')]:
        flags = ['-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                 '-fno-omit-frame-pointer', '-fno-sanitize-recover=all', '-fsanitize=' + sanitizer]
        objects = []
        for source in (closure / KEXT, frozen / adapter, frozen / fixture,
                       native / 'frozen/tests/test_build34_exact_submit_peer.c',
                       native / 'frozen/tests/test_build34_exact_receipt_peer.c'):
            obj = out / (label + '-' + source.stem + '.o')
            dep = obj.with_suffix('.d')
            cpp = source.suffix == '.cpp'
            cc = 'clang++' if cpp else 'clang'
            standard = '-std=c++20' if cpp else '-std=gnu11'
            extra = ['-Wno-missing-field-initializers', '-Wno-deprecated-volatile'] if cpp else []
            run(['/usr/bin/xcrun', cc, standard, *flags, *includes, *extra,
                 '-MMD', '-MF', dep, '-c', source, '-o', obj], obj.stem + '-compile')
            deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
            if not deps or any(str(Path(name).resolve()) not in allowed for name in deps):
                raise ValueError('Unfrozen compilation dependency')
            objects.append(obj)
        binary = out / (label + '-CPU-only')
        run(['/usr/bin/xcrun', 'clang++', *flags, '-Wl,-dead_strip', *objects, '-o', binary], label + '-link')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', run(['/usr/bin/otool', '-L', binary], label + '-linkage'), re.I):
            raise ValueError('Device runtime linked')
        result = re.fullmatch(r'PASS staged Mesa/native wire: (\d+) checks; GPU_executed=false\n',
                              run([binary], label + '-test'))
        if not result:
            raise ValueError('Paired receipt suite did not pass')
        checks[label] = int(result[1])

    if checks['memory'] != checks['thread'] or radv_ib_tail.verified_source(mesa) != mesa_source:
        raise ValueError('Unequal coverage or Mesa source drift')
    if any((ROOT / name).read_bytes() != data or (frozen / name).read_bytes() != data for name, data in inputs.items()):
        raise ValueError('Frozen input drift')
    if any((closure / name).read_bytes() != data for name, data in mesa_staged.items()):
        raise ValueError('Staged Mesa input drift')
    if protected != {name: sha((ROOT / name).read_bytes()) for name in names}:
        raise ValueError('Production input drift')
    report = dict(status='passed-CPU-only-paired-Mesa-native-receipt-wire', kernel_build=34,
                  asan_ubsan_checks=checks['memory'], tsan_checks=checks['thread'],
                  frozen_Mesa_inputs=len(mesa_source), protected_production_inputs=len(names),
                  staged_native_submit_source_sha256=native_evidence['staged_driver_sha256'],
                  staged_Mesa_transport_sha256=sha(mesa_staged[KEXT]),
                  native_regression_groups=native_result['groups'],
                  fixture_prefix_only=True, native_session_negotiated=False, iokit_opened=False,
                  production_exact_capability_enabled=False, installed=False, loaded=False,
                  GPU_executed=False, R3_complete=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesa-source', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    test(args.mesa_source, args.out)
