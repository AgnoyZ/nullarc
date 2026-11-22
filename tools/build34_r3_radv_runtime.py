#!/usr/bin/env python3
"""Link the reviewed build34 exact-only RADV sources without loading the result."""

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import struct
import subprocess

from build34_exact_submit import once
from build34_r3_radv_entry import PHYSICAL, WINSYS, WRAPPER
from upstream34_layout import mec_range
from upstream34_layout.radv_ib_tail_runtime import (
    LOCK, ROOT, TARGET, digest, inventory, inventory_digest, logged, meson_command,
)


DARWIN = 'src/amd/common/darwin/'
COMMON_MESON = 'src/amd/common/meson.build'
RADV_MESON = 'src/amd/vulkan/meson.build'
RADV_CS = 'src/amd/vulkan/winsys/amdgpu/radv_amdgpu_cs.c'
RADV_CS_BASE_SHA256 = '7ab9313d4f746c06893433b07ac12312a2807f14082018641c5ee74540e4d516'
ENTRY_RECORD = ROOT / 'docs/validation/build34-r3-radv-exact-entry-offline-20261122.json'
TRANSPORT_RECORD = ROOT / 'docs/validation/build34-r3-transport-offline-20261121.json'
ADAPTER = 'build34_r3_mesa_wire.c'
ABI_SOURCE = 'src/phxbringup/PhxNativeABI.h'
ABI_HEADER = DARWIN + 'r3/phxbringup/PhxNativeABI.h'
NEW_FILES = {DARWIN + name: 'tools/' + name for name in (
    ADAPTER, 'build34_r3_mesa_wire.h', 'build34_r3_mesa_iokit.h', 'build34_r3_mesa_drm.h',
    'build34_r3_radv_entry.h', 'build34_exact_submit_wire.h', 'build34_exact_receipt_wire.h',
    'build34_exact_progress_wire.h', 'build34_exact_open_wire.h',
)}
NEW_FILES.update({ABI_HEADER: ABI_SOURCE, DARWIN + 'r3/amd/phx_topology.h': 'src/amd/phx_topology.h'})
COMPILED = {WRAPPER: [DARWIN + 'build34_r3_radv_entry.h'],
            PHYSICAL: [DARWIN + 'build34_r3_radv_entry.h'], WINSYS: [],
            DARWIN + 'ac_darwin_kext.c': [DARWIN + 'ac_darwin_kext.h'],
            DARWIN + 'ac_darwin_iokit.c': [DARWIN + 'build34_exact_open_wire.h', ABI_HEADER],
            DARWIN + 'ac_darwin_drm.c': [DARWIN + 'build34_r3_radv_entry.h'],
            DARWIN + 'ac_darwin_sync.c': [DARWIN + 'build34_r3_mesa_drm.h'],
            DARWIN + ADAPTER: [DARWIN + 'build34_exact_progress_wire.h', ABI_HEADER]}
PROTOCOL_SYMBOLS = {'_acd_kext_open_exact_iokit', '_acd_device_open_exact_iokit',
                    '_phx34_mesa_wire_backend', '_acd_sync_detach_backend',
                    '_ac_drm_darwin_exact_profile', '_radv_darwin_enumerate_physical_devices',
                    '_radv_amdgpu_winsys_create', '_radv_amdgpu_winsys_query_info'}


def production_snapshot():
    paths = ['src', 'tools/phxctl', 'tools/build_kext.py']
    subprocess.run(['/usr/bin/git', 'diff', '--quiet', 'e9ee265ce005693f2928b4f981dfd097ca53fb80',
                    '--', *paths], cwd=ROOT, check=True, timeout=15)
    names = subprocess.check_output(['/usr/bin/git', 'ls-files', '--', *paths],
                                    cwd=ROOT, text=True, timeout=15).splitlines()
    if len(names) != 172:
        raise ValueError('Protected build34 inventory changed')
    return {name: digest(ROOT / name) for name in names}


def stage_exact_cs(path):
    if digest(path) != RADV_CS_BASE_SHA256:
        raise ValueError('Unreviewed RADV CS source')
    source = path.read_text()
    source = once(source, '#include "ac_linux_drm.h"\n', '''#include "ac_linux_drm.h"
#ifdef HAVE_AMDGPU_DARWIN
#include "build34_r3_radv_entry.h"
#endif
''')
    source = once(source, '   bool has_user_fence = radv_amdgpu_cs_has_user_fence(request);\n',
                  '''   bool has_user_fence = radv_amdgpu_cs_has_user_fence(request);
#ifdef HAVE_AMDGPU_DARWIN
   struct phx_topology exact_profile;
   if (has_user_fence && !ac_drm_darwin_exact_profile(ctx->ws->dev, &exact_profile))
      has_user_fence = false;
#endif
''')
    path.write_text(source)


def stage_full_source(baseline, destination, prior, reviewed, exact_cs):
    expected = json.loads(TRANSPORT_RECORD.read_text())['staged_Mesa_sha256']
    expected.update(reviewed['entry_staged_source_sha256'])
    for field in ('iokit', 'drm', 'sync'):
        expected[DARWIN + 'ac_darwin_' + field + '.c'] = reviewed['staged_' + field + '_source_sha256']
    overlay = {name: (prior / 'mesa' / name).read_bytes() for name in expected}
    if {name: mec_range.sha(data) for name, data in overlay.items()} != expected:
        raise ValueError('Reviewed staged Mesa sources differ')
    new = {name: (ROOT / path).read_bytes() for name, path in NEW_FILES.items()}
    for name, path in NEW_FILES.items():
        frozen = prior / 'frozen' / path
        if not frozen.is_file():
            frozen = prior / 'native-private/frozen' / path
        if frozen.read_bytes() != new[name]:
            raise ValueError('Previous pairing input changed: ' + path)
    shutil.copytree(baseline, destination, symlinks=True, ignore=shutil.ignore_patterns('.git'))
    original = inventory(destination)
    if set(new) & original.keys() or not set(overlay) <= original.keys():
        raise ValueError('Unexpected source overlay names')
    for name, data in overlay.items():
        (destination / name).write_bytes(data)
    for name, data in new.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    path = destination / COMMON_MESON
    common = once(path.read_text(), 'if with_amdgpu_darwin\n',
                  "inc_r3_darwin = []\nif with_amdgpu_darwin\n"
                  "  inc_r3_darwin = include_directories('darwin', 'darwin/r3/phxbringup')\n")
    common = once(common, "    'darwin/ac_darwin_sync.c',\n",
                  "    'darwin/ac_darwin_sync.c',\n    'darwin/" + ADAPTER + "',\n")
    common = once(common, 'inc_include, inc_src, inc_amd, inc_virtio_gpu,\n',
                  'inc_include, inc_src, inc_amd, inc_virtio_gpu, inc_r3_darwin,\n')
    path.write_text(common)
    path = destination / RADV_MESON
    radv = once(path.read_text(), '    inc_util, inc_virtio_gpu\n',
                '    inc_util, inc_virtio_gpu, inc_r3_darwin\n')
    path.write_text(radv)
    allowed = (set(overlay) - {WINSYS}) | set(new) | {COMMON_MESON, RADV_MESON}
    if exact_cs:
        stage_exact_cs(destination / RADV_CS)
        allowed.add(RADV_CS)
    staged = inventory(destination)
    if {name for name in original.keys() | staged.keys() if original.get(name) != staged.get(name)} != allowed:
        raise ValueError('Unexpected full-source delta')
    return original, staged, sorted(allowed)


def verify_link(source, native, ninja, env, exact_cs):
    commands = json.loads((native / 'compile_commands.json').read_text())
    link = subprocess.check_output([ninja, '-C', native, '-t', 'commands', TARGET], env=env, text=True, timeout=30)
    used = {}
    reviewed_units = dict(COMPILED)
    if exact_cs:
        reviewed_units[RADV_CS] = [DARWIN + 'build34_r3_radv_entry.h']
    for relative, headers in reviewed_units.items():
        path = source / relative
        rows = [row for row in commands if (Path(row['directory']) / row['file']).resolve() == path]
        if len(rows) != 1:
            raise RuntimeError('Missing or ambiguous compile command for ' + relative)
        words = shlex.split(rows[0]['command'])
        obj = words[words.index('-o') + 1]
        deps = subprocess.check_output([ninja, '-C', native, '-t', 'deps', obj], env=env, text=True, timeout=15)
        actual = {(native / item.strip()).resolve() for item in deps.splitlines()[1:] if item.strip()}
        if path not in actual or not {source / header for header in headers} <= actual or obj not in link:
            raise RuntimeError('Incomplete R3 compile or link closure: ' + relative)
        used[relative] = digest(path)

    library = native / TARGET
    with library.open('rb') as stream:
        magic, cpu, _, filetype = struct.unpack('<IiiI', stream.read(16))
    if (magic, cpu, filetype) != (0xfeedfacf, 0x1000007, 6):
        raise RuntimeError('Expected a single x86_64 Mach-O dylib')
    dylibs = subprocess.check_output(['/usr/bin/otool', '-L', library], text=True, timeout=30).splitlines()[1:]
    deps = [line.strip().split(' (', 1)[0] for line in dylibs]
    if (not deps or deps[0] != '@rpath/libvulkan_radeon.dylib' or
            any(not name.startswith(('/usr/lib/', '/System/Library/')) for name in deps[1:])):
        raise RuntimeError('Unexpected runtime name or non-system dylib dependency')
    symbols = subprocess.check_output(['/usr/bin/nm', '-m', library], text=True, timeout=30)
    defined = {line.split()[-1] for line in symbols.splitlines() if '(__TEXT,__text)' in line}
    required = PROTOCOL_SYMBOLS | {'_vk_icdGetInstanceProcAddr', '_vk_icdNegotiateLoaderICDInterfaceVersion'}
    strong_dynamic = [line for line in symbols.splitlines() if '(dynamically looked up)' in line and ' weak ' not in line]
    if not required <= defined or strong_dynamic:
        raise RuntimeError('Missing linked R3 functions or unresolved strong dynamic imports')
    imports = set(re.findall(r'^\s*\(undefined\).*? (_IO\w+) \(from IOKit\)$', symbols, re.M))
    if imports != {'_IOServiceMatching', '_IOServiceGetMatchingService', '_IOServiceOpen', '_IOServiceClose',
                   '_IOObjectRelease', '_IOConnectCallMethod', '_IOConnectMapMemory64', '_IOConnectUnmapMemory64'}:
        raise RuntimeError('IOKit import surface differs from the CPU fixture closure')
    return used, sorted(imports), deps[1:]


def build(baseline, entry, output, tool_dirs, exact_cs=False):
    if platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        raise ValueError('Native x86_64 macOS required')
    baseline, entry, output = (Path(path).resolve() for path in (baseline, entry, output))
    if (output.exists() or ROOT / 'build' not in output.parents or not output.name.endswith('-private') or
            any(path == output or path in output.parents or output in path.parents for path in (baseline, entry))):
        raise ValueError('Use a fresh, separate ignored worktree output ending -private')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(output)], cwd=ROOT, check=True, timeout=15)
    lock = json.loads(LOCK.read_text())
    reviewed = json.loads(ENTRY_RECORD.read_text())
    if json.loads((entry / 'result-private.json').read_text()) != reviewed:
        raise ValueError('Require the exact reviewed RADV CPU pairing result')
    protected = production_snapshot()
    original = inventory(baseline)
    if (len(original) != lock['full_baseline_files_and_links'] or
            inventory_digest(original) != lock['full_baseline_inventory_sha256']):
        raise ValueError('Full Mesa source differs from the reviewed baseline')
    inputs = [Path(__file__).resolve(), LOCK, ENTRY_RECORD, TRANSPORT_RECORD, *(ROOT / path for path in NEW_FILES.values())]
    frozen_inputs = {str(path.relative_to(ROOT)): digest(path) for path in inputs}
    output.mkdir(parents=True, mode=0o700)
    source, native = output / 'mesa', output / 'native'
    copied, staged, changed = stage_full_source(baseline, source, entry, reviewed, exact_cs)
    if copied != original:
        raise RuntimeError('Baseline source copy drift')

    for name in ('home', 'tmp', 'pkgconfig-empty'):
        (output / name).mkdir(mode=0o700)
    path = ':'.join([str(Path(item).resolve()) for item in tool_dirs] + ['/usr/bin', '/bin', '/usr/sbin', '/sbin'])
    env = {'PATH': path, 'HOME': str(output / 'home'), 'TMPDIR': str(output / 'tmp'), 'LANG': 'C', 'LC_ALL': 'C',
           'CC': '/usr/bin/clang', 'CXX': '/usr/bin/clang++', 'OBJC': '/usr/bin/clang', 'AR': '/usr/bin/ar',
           'MACOSX_DEPLOYMENT_TARGET': '15.0', 'PKG_CONFIG_LIBDIR': str(output / 'pkgconfig-empty'),
           'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'CMAKE_BUILD_PARALLEL_LEVEL': '1'}
    tools = {name: shutil.which(name, path=path) for name in ('meson', 'ninja', 'glslangValidator', 'pkg-config')}
    if not all(tools.values()):
        raise ValueError('Missing explicit reviewed build tools')
    versions = {name: subprocess.check_output([tools[name], '--version'], env=env, text=True, timeout=15).strip()
                for name in ('meson', 'ninja', 'glslangValidator')}
    if (versions['meson'] != lock['build_tools']['meson'] or
            versions['ninja'].split('.git')[0] != lock['build_tools']['ninja'] or
            versions['glslangValidator'].splitlines()[0] != 'Glslang Version: 11:' + lock['build_tools']['glslang']):
        raise ValueError('Build tool version differs from reviewed toolchain')
    print('Staged reviewed exact-only sources. Configuring private build.', flush=True)
    logged(meson_command(tools['meson'], source, native), output / 'configure.log', env)
    print('Compiling/linking three build jobs; the library will not be loaded.', flush=True)
    logged([tools['ninja'], '-C', native, '-j', '3', TARGET], output / 'compile.log', env, 1800)
    units, imports, deps = verify_link(source, native, tools['ninja'], env, exact_cs)
    if inventory(baseline) != original or inventory(source) != staged or any(
            digest(ROOT / name) != expected for name, expected in frozen_inputs.items()):
        raise RuntimeError('Source or recipe changed during compilation')
    if production_snapshot() != protected:
        raise RuntimeError('Production inputs changed during compilation')
    library = native / TARGET
    report = dict(status='passed-private-R3-RADV-full-link-only', kernel_build=34, full_runtime_linked=True,
                  baseline_files_and_links=len(original), staged_files_and_links=len(staged),
                  baseline_inventory_sha256=inventory_digest(original), staged_inventory_sha256=inventory_digest(staged),
                  changed_source_paths=changed, checked_translation_units=units, IOKit_imports=imports,
                  system_dylib_dependencies=deps, library_sha256=digest(library), library_bytes=library.stat().st_size,
                  protected_production_inputs=len(protected), tool_versions=versions,
                  compiler=subprocess.check_output(['/usr/bin/clang', '--version'], text=True, timeout=15).splitlines()[0],
                  native_mode_admitted=False, installed=False, loaded=False, binary_uploaded=False,
                  real_IOKit_called=False, GPU_executed=False, R3_complete=False)
    if exact_cs:
        report['exact_cs_omits_legacy_fence_chunk'] = True
    (output / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesa-source', type=Path, required=True)
    parser.add_argument('--entry-evidence', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--toolchain-bin', action='append', type=Path, required=True)
    parser.add_argument('--exact-cs', action='store_true', help='Derive the separate staged exact-CS variant')
    args = parser.parse_args()
    build(args.mesa_source, args.entry_evidence, args.out, args.toolchain_bin, args.exact_cs)
