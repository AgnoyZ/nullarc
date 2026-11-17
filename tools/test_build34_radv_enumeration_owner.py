#!/usr/bin/env python3
"""CPU-test the actual Vulkan enumeration function with real Mesa core/VA and wrappers."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from upstream34_layout import mec_range, radv_ib_tail

ROOT = Path(__file__).resolve().parents[1]
PHYSICAL = 'src/amd/vulkan/radv_physical_device.c'
BASE = '967de26f3cb4ce7e01bb5534aba815228acdd92aa2cb21e283e690cbac908b02'
PATCHED = 'd0c56ce1fe611744c42d8ea34bfefe28c1ebaa2c3a14cf38ceeaa8a121d1a072'
PATCH = ROOT / 'mesa-patches-build34/0002-radv-original34-tail-enumeration-owner.patch'
LOCK = ROOT / 'tools/upstream34_layout/radv_ib_tail_runtime_sources.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(mesa, transport, output):
    mesa, transport, output = (Path(p).resolve() for p in (mesa, transport, output))
    output.relative_to((ROOT / 'build').resolve())
    if output.exists() or sha(mesa / PHYSICAL) != BASE:
        raise ValueError('Fresh output and the pinned full Mesa source are required')
    lock = json.loads(LOCK.read_text())
    owner = lock['enumeration_owner']
    if (owner['source'] != PHYSICAL or owner['patch'] != str(PATCH.relative_to(ROOT)) or
            owner['base_source_sha256'] != BASE or owner['patched_source_sha256'] != PATCHED or
            owner['patch_sha256'] != sha(PATCH)):
        raise ValueError('Enumeration patch differs from the reviewed source pins')
    baseline = radv_ib_tail.verified_source(mesa)
    wrapper_path = mesa / 'src/amd/common/ac_linux_drm.c'
    wrapper_bytes = wrapper_path.read_bytes()
    if sha(wrapper_path) != owner['baseline_wrapper_sha256']:
        raise ValueError('Unexpected DRM wrapper source')
    transport_paths = {name: transport / Path(name).name for name in lock['patched_source_sha256']}
    if {name: sha(path) for name, path in transport_paths.items()} != lock['patched_source_sha256']:
        raise ValueError('Transport differs from the hardware-tested three-file source')
    protected = mec_range.verify_current_inputs(mec_range.protected_base_inputs(), ROOT)
    snapshots = {p: p.read_bytes() for p in
                 (PATCH, Path(__file__).resolve(), LOCK, ROOT / radv_ib_tail.PATCH,
                  Path(radv_ib_tail.__file__).resolve(), radv_ib_tail.MANIFEST,
                  Path(mec_range.__file__).resolve(),
                  ROOT / 'tests/test_build34_radv_enumeration_owner.c',
                  ROOT / 'tests/test_build34_radv_ib_tail_core.c',
                  ROOT / 'tests/test_build34_radv_ib_tail.c')}
    output.mkdir(parents=True, mode=0o700)
    staged = output / 'patched'
    (staged / PHYSICAL).parent.mkdir(parents=True)
    (staged / PHYSICAL).write_bytes((mesa / PHYSICAL).read_bytes())
    subprocess.run(['git', 'init', '-q', str(staged)], check=True, capture_output=True)
    for check in (True, False):
        subprocess.run(['git', '-C', str(staged), 'apply'] + (['--check'] if check else []) + [str(PATCH)], check=True, capture_output=True)
    if sha(staged / PHYSICAL) != PATCHED:
        raise ValueError('Unexpected patched enumeration source')
    prefix = (ROOT / 'tests/test_build34_radv_ib_tail_core.c').read_text().split('static struct fake backend;')[0]
    (output / 'core-prefix.h').write_text(prefix)
    wrapper = wrapper_bytes.decode()
    blocks = [re.search(r'^struct ac_drm_device \{.*?^};', wrapper, re.M | re.S).group(0)]
    for signature in ('int ac_drm_device_initialize(', 'void ac_drm_device_deinitialize('):
        blocks.append(re.search('^' + re.escape(signature) + r'.*?^}', wrapper, re.M | re.S).group(0))
    (output / 'wrapper.inc').write_text('\n'.join(blocks) + '\n')
    cc = ['/usr/bin/xcrun', 'clang', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-Wno-unused-parameter', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
          '-fno-omit-frame-pointer', '-Wl,-dead_strip',
          '-Dlibdrm_container_of(ptr,sample,member)=((void *)((char *)(ptr) - __builtin_offsetof(__typeof__(*(sample)), member)))']
    for path in (output, ROOT / 'tests', transport, mesa / 'include', mesa / 'include/darwin',
                 mesa / 'src/amd/common/darwin', mesa / 'src', mesa / 'src/amd'):
        cc.append('-I' + str(path))
    results = {}
    for policy, source in (('baseline', mesa / PHYSICAL), ('patched', staged / PHYSICAL)):
        text = source.read_text()
        function = re.search(r'^VkResult\nradv_darwin_enumerate_physical_devices\(.*?^}', text, re.M | re.S).group(0)
        (output / 'enumeration.inc').write_text(function + '\n')
        binary = output / ('enumeration-' + policy)
        compile_command = cc + [str(ROOT / 'tests/test_build34_radv_enumeration_owner.c'), str(transport / 'ac_darwin_kext.c'),
                                 str(mesa / 'src/amd/common/darwin/amdgpu_vamgr.c'), '-o', str(binary)]
        for name, command in (('compile', compile_command), ('run', [str(binary), policy])):
            result = subprocess.run(command, capture_output=True, text=True, timeout=90)
            (output / (policy + '-' + name + '.stdout')).write_text(result.stdout)
            (output / (policy + '-' + name + '.stderr')).write_text(result.stderr)
            if result.returncode:
                raise RuntimeError(policy + ' ' + name + ' failed; inspect private logs')
        match = re.fullmatch(r'PASS enumeration owner ' + policy + r': (\d+) cases, (\d+) checks; real core/VA and wrappers; no GPU; legacy profile-clone orphan unchanged\n', result.stdout)
        if not match:
            raise RuntimeError('Missing complete CPU test result')
        results[policy] = {'cases': int(match[1]), 'checks': int(match[2])}
    if (radv_ib_tail.verified_source(mesa) != baseline or sha(mesa / PHYSICAL) != BASE or
            wrapper_path.read_bytes() != wrapper_bytes or sha(staged / PHYSICAL) != PATCHED or
            {name: sha(path) for name, path in transport_paths.items()} != lock['patched_source_sha256'] or
            any(p.read_bytes() != data for p, data in snapshots.items())):
        raise RuntimeError('Enumeration test input drift')
    mec_range.verify_current_inputs(mec_range.protected_base_inputs(), ROOT)
    report = {'result': 'passed', 'ASan_UBSan': True, 'actual_enumeration_function_compiled': True,
              'actual_wrapper_functions_compiled': True, 'real_transport_core_and_VA_allocator': True,
              'physical_device_construction': 'CPU fixture with actual core acquire/release, not full Vulkan execution',
              'legacy_profile_clone_orphan_per_successful_identity_call': 1, 'legacy_orphan_changed': False,
              'CPU': results, 'GPU_executed': False, 'base_source_sha256': BASE, 'patched_source_sha256': PATCHED,
              'patch_sha256': sha(PATCH), 'baseline_wrapper_sha256': sha(wrapper_path),
              'baseline_dependency_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in baseline.items()},
              'hardware_tested_transport_sha256': lock['patched_source_sha256'],
              'protected_source_sha256': protected,
              'inputs_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(data).hexdigest()
                               for p, data in snapshots.items()}}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesa-source', type=Path, required=True)
    parser.add_argument('--transport-source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    run(args.mesa_source, args.transport_source, args.out)
