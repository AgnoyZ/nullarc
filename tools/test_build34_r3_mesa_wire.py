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

from build34_exact_overlap_snapshot import DECLARATIONS, GLOBAL
from build34_exact_progress_wire import (
    DISPATCH, PREFIX as NATIVE_PREFIX, PREFIX_DECL, PROGRESS, PROGRESS_DECL,
    previous_stage, stage as progress_stage, stage_header as progress_header,
)
from build34_exact_submit import once
from build34_r3_mesa_drm import stage_drm, stage_sync
from build34_r3_mesa_iokit import IOKIT, IOKIT_SHA256, stage as iokit_stage
from build34_r3_mesa_open import stage_drm as open_drm_stage, stage_iokit as open_iokit_stage
from test_build34_exact_ownership import DRIVER, ROOT, method, sha
from test_build34_exact_transport import DRM, KEXT, PATCH, PREFIX, SHAPE_PATCHES
from test_build34_exact_multitarget import apply, stage
from upstream34_layout import radv_ib_tail


EXACT_OPEN_WIRE = 'tools/build34_exact_open_wire.h'
EXACT_OPEN_WIRE_SHA256 = '3871eccc5e3aca90936d1fc76ea01a7824c5fe534712a225a8c1ab6d4099a5e8'


def test(mesa, out, *, iokit=False, drm=False, exact_open=False):
    drm = drm or exact_open
    iokit = iokit or drm
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
    dispatch_record = 'docs/validation/build34-r3-mesa-dispatch-offline-20261122.json'
    drm_record = 'docs/validation/build34-r3-mesa-drm-offline-20261122.json'
    adapter = 'tools/build34_r3_mesa_wire.c'
    fixture = 'tests/test_build34_r3_mesa_wire.cpp'
    iokit_fixture = 'tests/test_build34_r3_mesa_iokit.c'
    sync = PREFIX + 'ac_darwin_sync.c'
    vamgr = PREFIX + 'amdgpu_vamgr.c'
    native_evidence = json.loads((ROOT / native_record).read_text())
    mesa_evidence = json.loads((ROOT / transport_record).read_text())
    patches = [*SHAPE_PATCHES, PATCH]
    paths = [adapter, 'tools/build34_r3_mesa_wire.h', 'tools/test_build34_r3_mesa_wire.py', fixture,
             'tools/build34_exact_dispatch_mode.py', 'tools/build34_exact_progress_wire.py',
             'tools/build34_exact_progress_wire.h', 'tools/build34_exact_fence32.h', dispatch_record,
             transport_record, native_record,
             *patches, *native_evidence['input_sha256']]
    if iokit:
        paths.extend(['tools/build34_r3_mesa_iokit.py', 'tools/build34_r3_mesa_iokit.h', iokit_fixture])
        iokit_source = (mesa / IOKIT).read_bytes()
        if sha(iokit_source) != IOKIT_SHA256:
            raise ValueError('Previously reviewed Mesa IOKit input changed')
        iokit_staged = iokit_stage(iokit_source.decode()).encode()
        if not iokit_staged.startswith(iokit_source.split(b'#include', 1)[0]):
            raise ValueError('Original Mesa IOKit notice changed')
    if drm:
        paths.extend(['tools/build34_r3_mesa_drm.py', 'tools/build34_r3_mesa_drm.h',
                      'docs/validation/build34-r3-mesa-iokit-offline-20261122.json'])
    if exact_open:
        paths.extend([drm_record, 'tools/build34_r3_mesa_open.py', EXACT_OPEN_WIRE])
    inputs = {name: (ROOT / name).read_bytes() for name in paths}
    pinned = {**native_evidence['input_sha256'], **{name: mesa_evidence['input_sha256'][name] for name in patches}}
    if exact_open:
        pinned[EXACT_OPEN_WIRE] = EXACT_OPEN_WIRE_SHA256
    if any(sha(inputs[name]) != digest for name, digest in pinned.items()):
        raise ValueError('Previously reviewed inputs changed')
    driver = inputs[DRIVER].decode()
    before, after = previous_stage(driver), progress_stage(driver)
    restored = once(after, method(after, DISPATCH), method(before, DISPATCH))
    restored = once(restored, method(after, NATIVE_PREFIX) + '\n' + method(after, PROGRESS) + '\n', '')
    for addition in ('#include "build34_exact_progress_wire.h"\n', PREFIX_DECL, PROGRESS_DECL):
        restored = once(restored, addition, '')
    if sha(before.encode()) != json.loads(inputs[dispatch_record])['staged_dispatch_source_sha256'] or restored != before:
        raise ValueError('Unexpected progress wire predecessor or out-of-scope delta')
    out.mkdir(parents=True, mode=0o700)
    frozen, closure, native = out / 'frozen', out / 'mesa', out / 'native-private'
    stage(inputs, frozen)
    stage(mesa_source, closure)

    def run(args, label, *, cwd=out, timeout=90, expected_stderr=rb''):
        result = subprocess.run([str(arg) for arg in args], cwd=cwd, stdin=subprocess.DEVNULL,
                                timeout=timeout, capture_output=True)
        (out / (label + '.stdout')).write_bytes(result.stdout)
        (out / (label + '.stderr')).write_bytes(result.stderr)
        if result.returncode or not re.fullmatch(expected_stderr, result.stderr):
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
    if iokit:
        stage({IOKIT: iokit_source}, out / 'iokit-baseline')
        (closure / IOKIT).write_bytes(iokit_staged)
    if drm:
        prior_iokit = json.loads(inputs['docs/validation/build34-r3-mesa-iokit-offline-20261122.json'])
        if sha(iokit_staged) != prior_iokit['staged_iokit_source_sha256']:
            raise ValueError('Previously reviewed IOKit stage changed')
        for name, transform in [(DRM, stage_drm), (sync, stage_sync)]:
            source = mesa_staged[name]
            candidate = transform(source.decode()).encode()
            if not candidate.startswith(source.split(b'#include', 1)[0]):
                raise ValueError('Original Mesa notice changed: ' + name)
            (closure / name).write_bytes(candidate)
            mesa_staged[name] = candidate
    if exact_open:
        prior_drm = json.loads(inputs[drm_record])
        for stage_name, source in [('iokit', iokit_staged), ('drm', mesa_staged[DRM]), ('sync', mesa_staged[sync])]:
            if sha(source) != prior_drm['staged_' + stage_name + '_source_sha256']:
                raise ValueError('Previously reviewed DRM predecessor changed: ' + stage_name)
        iokit_staged = open_iokit_stage(iokit_staged.decode()).encode()
        (closure / IOKIT).write_bytes(iokit_staged)
        mesa_staged[DRM] = open_drm_stage(mesa_staged[DRM].decode()).encode()
        (closure / DRM).write_bytes(mesa_staged[DRM])

    native_result = json.loads(run([sys.executable, '-B', ROOT / native_case, '--out', native],
                                   'native-regressions', cwd=ROOT, timeout=360))
    for key in ('staged_driver_sha256', 'staged_ownership_sha256', 'checks', 'groups'):
        if native_result[key] != native_evidence[key]:
            raise ValueError('Previously reviewed native result differs: ' + key)
    paired_native = native / 'paired-native-receipt.h'
    generated_native = (native / 'submit-receipt.cpp').read_text()
    generated_native = once(generated_native, 'int main() {\n', 'void previous_receipt_suite() {\n')
    native_headers = native / 'source/src/phxbringup'
    ownership = native_headers / 'build34_exact_ownership.h'
    ownership.write_text(progress_header(ownership.read_text()))
    binding = (native / 'submit-binding-CPU-only.h').read_text()
    paired_binding = native / 'paired-native-binding.h'
    binding = once(binding, '    bool hello=false;\n', '    bool hello=false, boCleanupFault=false;\n'
                   '    uint32_t legacyState=2;\n' + PROGRESS_DECL)
    binding = once(binding, '    bool exactAdmissionClosed() const;\n',
                   '    bool exactAdmissionClosed() const;\n' + PREFIX_DECL + DECLARATIONS +
                   '    bool exactVMFault=false, exactQueueAdopted[2]{true,true};\n'
                   '    phx34_exact::FenceWindow32 exactFenceWindow[2];\n'
                   '    bool (*exactDwordReader)(const volatile uint32_t *, uint32_t *)=nullptr;\n'
                   '    bool readExactFence32(uint32_t, uint64_t *);\n'
                   '    struct VmCtx { bool busy=false; uint64_t queueSequence[2]{}, queueGeneration[2]{}, newest=0; };\n'
                   '    static constexpr unsigned kMaxCtx=2;\n'
                   '    VmCtx vm[kMaxCtx];\n'
                   '    bool vmWorkCurrent(const VmCtx &) const;\n')
    binding = once(binding, '#include "build34_exact_callbacks.h"',
                   '#include "build34_exact_callbacks.h"\n#include "build34_exact_fence32.h"')
    binding = once(binding, '    exactQueueSubmitted[actualQueue] = seq;',
                   '    if (exactDwordReader) CHECK(exactFenceWindow[actualQueue].submit(exactQueueGeneration[actualQueue], seq));\n'
                   '    exactQueueSubmitted[actualQueue] = seq;')
    binding = once(binding, 'CHECK(ms==1 && !gpuHeld); testTicks+=1000000;',
                   'CHECK(ms==1 && !gpuHeld); event("poll-sleep"); testTicks+=1000000;')
    paired_binding.write_text(binding)
    generated_native = once(generated_native, '#include "submit-binding-CPU-only.h"',
                            '#include "paired-native-binding.h"\n#include "build34_exact_progress_wire.h"\n'
                            'static constexpr unsigned PHX_KEXT_BUILD = 34;')
    generated_native = once(generated_native, method(generated_native, DISPATCH), method(after, DISPATCH))
    signatures = [NATIVE_PREFIX, PROGRESS, GLOBAL, 'bool PhxBringup::readExactFence32(', 'bool PhxBringup::vmWorkCurrent(']
    paired_native.write_text(generated_native + '\n'.join(method(after, sig) for sig in signatures))
    includes = ['-I' + str(path) for path in [native, native_headers, frozen / 'tools',
                native / 'frozen/src/phxbringup', *(closure / name for name in ('include', 'include/darwin', 'src', 'src/amd', PREFIX))]]
    allowed = {str(path.resolve()) for root in (frozen, closure, native_headers, native / 'frozen')
               for path in root.rglob('*') if path.is_file() and '.git' not in path.relative_to(root).parts}
    allowed |= {str(paired_native), str(paired_binding)}
    checks = {}
    sources = [closure / KEXT, frozen / adapter, frozen / fixture,
               native / 'frozen/tests/test_build34_exact_submit_peer.c',
               native / 'frozen/tests/test_build34_exact_receipt_peer.c']
    if iokit:
        sources.extend([closure / IOKIT, frozen / iokit_fixture])
    if drm:
        sources.extend(closure / name for name in (DRM, sync, vamgr, 'src/amd/common/amdgpu_devices.c'))
    for label, sanitizer in [('memory', 'address,undefined'), ('thread', 'thread')]:
        flags = ['-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                 '-fno-omit-frame-pointer', '-fno-sanitize-recover=all', '-fsanitize=' + sanitizer]
        objects = []
        for source in sources:
            obj = out / (label + '-' + source.stem + '.o')
            dep = obj.with_suffix('.d')
            cpp = source.suffix == '.cpp'
            cc = 'clang++' if cpp else 'clang'
            standard = '-std=c++20' if cpp else '-std=gnu11'
            extra = ['-Wno-missing-field-initializers', '-Wno-deprecated-volatile'] if cpp else []
            if iokit and source == frozen / fixture:
                extra.append('-DPHX34_TEST_IOKIT=1')
            if iokit and source in (closure / KEXT, closure / IOKIT):
                extra.append('-Dcalloc=phx34_fixture_calloc')
            if drm and source == frozen / fixture:
                extra.append('-DPHX34_TEST_DRM=1')
            if exact_open and source in (frozen / fixture, frozen / iokit_fixture):
                extra.append('-DPHX34_TEST_EXACT_OPEN=1')
            if drm and source in (closure / DRM, closure / sync):
                extra.append('-Dcalloc=phx34_fixture_calloc')
            if drm and source == closure / vamgr:
                extra.append('-Dlibdrm_container_of(ptr,sample,member)=((void *)((char *)(ptr) - '
                             '__builtin_offsetof(__typeof__(*(sample)), member)))')
            run(['/usr/bin/xcrun', cc, standard, *flags, *includes, *extra,
                 '-MMD', '-MF', dep, '-c', source, '-o', obj], obj.stem + '-compile')
            deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
            if not deps or any(str(Path(name).resolve()) not in allowed for name in deps):
                raise ValueError('Unfrozen compilation dependency')
            if iokit and source == closure / IOKIT:
                imports = run(['/usr/bin/nm', '-u', obj], obj.stem + '-imports')
                required = ['_IOConnectCallMethod', '_IOServiceClose']
                if exact_open:
                    required.extend(['_IOServiceMatching', '_IOServiceGetMatchingService', '_IOServiceOpen',
                                     '_IOObjectRelease'])
                if any(symbol not in imports.split() for symbol in required):
                    raise ValueError('Incomplete IOKit transport compile')
            objects.append(obj)
        binary = out / (label + '-CPU-only')
        run(['/usr/bin/xcrun', 'clang++', *flags, '-Wl,-dead_strip', *objects, '-o', binary], label + '-link')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', run(['/usr/bin/otool', '-L', binary], label + '-linkage'), re.I):
            raise ValueError('Device runtime linked')
        log = (rb'radv-darwin: native kext: ABI 1\.9, build 34, VMID 8, max 64 IBs/submit, GB_ADDR_CONFIG '
               rb'0x[0-9a-f]{8}, VRAM 0 MiB visible \+ 0 MiB hi, GTT cap 0 MiB\n') if drm else rb''
        result = re.fullmatch(r'PASS staged Mesa/native wire: (\d+) checks; GPU_executed=false\n',
                              run([binary], label + '-test', expected_stderr=log))
        if not result:
            raise ValueError('Paired receipt suite did not pass')
        checks[label] = int(result[1])

    if checks['memory'] != checks['thread'] or radv_ib_tail.verified_source(mesa) != mesa_source:
        raise ValueError('Unequal coverage or Mesa source drift')
    if any((ROOT / name).read_bytes() != data or (frozen / name).read_bytes() != data for name, data in inputs.items()):
        raise ValueError('Frozen input drift')
    if any((closure / name).read_bytes() != data for name, data in mesa_staged.items()):
        raise ValueError('Staged Mesa input drift')
    if iokit and ((mesa / IOKIT).read_bytes() != iokit_source or
                  (out / 'iokit-baseline' / IOKIT).read_bytes() != iokit_source or
                  (closure / IOKIT).read_bytes() != iokit_staged):
        raise ValueError('Mesa IOKit input drift')
    if protected != {name: sha((ROOT / name).read_bytes()) for name in names}:
        raise ValueError('Production input drift')
    report = dict(status='passed-CPU-only-paired-Mesa-native-receipt-wire', kernel_build=34,
                  asan_ubsan_checks=checks['memory'], tsan_checks=checks['thread'],
                  frozen_Mesa_inputs=len(mesa_source), protected_production_inputs=len(names),
                  staged_native_submit_source_sha256=native_evidence['staged_driver_sha256'],
                  staged_progress_source_sha256=sha(after.encode()),
                  staged_Mesa_transport_sha256=sha(mesa_staged[KEXT]),
                  native_regression_groups=native_result['groups'],
                  actual_checked_prefix_in_cpu_fixture=True, session_discovered_in_cpu_fixture=True,
                  native_mode_admitted=False, iokit_opened=False,
                  production_exact_capability_enabled=False, installed=False, loaded=False,
                  GPU_executed=False, R3_complete=False)
    if iokit:
        report.update(status='passed-CPU-only-staged-Mesa-IOKit-call-transport',
                      iokit_source_sha256=IOKIT_SHA256, staged_iokit_source_sha256=sha(iokit_staged),
                      actual_iokit_transport_compiled=True, iokit_symbols_test_doubles=True,
                      real_IOKit_called=False, native_hello_modeled=True,
                      drm_core_adopted=False, native_session_opened=False)
    if drm:
        report.update(status='passed-CPU-only-staged-Mesa-DRM-exact-publication-and-drain',
                      staged_drm_source_sha256=sha(mesa_staged[DRM]),
                      staged_sync_source_sha256=sha(mesa_staged[sync]),
                      drm_core_adopted=True, drm_cs_dual_queue_paired_in_fixture=True,
                      sync_backend_close_waits_for_transport_callback=True,
                      native_drain_attested=False)
    if exact_open:
        report.update(status='passed-CPU-only-staged-Mesa-R3-exact-service-open',
                      open_type='N48R', open_service='PhxBringup', cpu_fixture_service_open=True,
                      fixture_open_refusal_does_not_fall_back=True,
                      fixture_open_reuses_exact_core_and_refuses_while_draining=True,
                      normal_RADV_entry_changed=False)
    (out / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesa-source', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--iokit', action='store_true')
    parser.add_argument('--drm', action='store_true')
    parser.add_argument('--exact-open', action='store_true')
    args = parser.parse_args()
    test(args.mesa_source, args.out, iokit=args.iokit, drm=args.drm, exact_open=args.exact_open)
