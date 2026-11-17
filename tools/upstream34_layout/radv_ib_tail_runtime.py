#!/usr/bin/env python3
"""Compile the pinned opt-in RADV runtime privately; never enumerate, install or submit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import signal
import struct
import subprocess
import sys

if __package__:
    from . import mec_range, radv_ib_tail
else:
    import mec_range
    import radv_ib_tail

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / 'tools/upstream34_layout/radv_ib_tail_runtime_sources.json'
SMOKE = ROOT / 'tools/upstream34_layout/radv_ib_tail_dylib_smoke.c'
TARGET = 'src/amd/vulkan/libvulkan_radeon.dylib'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory(source):
    source = Path(source).resolve()
    result = {}
    for path in sorted(source.rglob('*')):
        relative = path.relative_to(source)
        if '.git' in relative.parts:
            continue
        if path.is_symlink():
            target = path.readlink()
            if target.is_absolute():
                raise ValueError('Absolute source symlink')
            (path.parent / target).resolve().relative_to(source)
            result[relative.as_posix()] = {'symlink': target.as_posix()}
        elif path.is_file():
            result[relative.as_posix()] = {'sha256': digest(path), 'executable': bool(path.stat().st_mode & 0o111)}
        elif not path.is_dir():
            raise ValueError('Special source file')
    return result


def inventory_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def logged(command, log, env, timeout=120):
    with Path(log).open('xb') as stream:
        proc = subprocess.Popen(list(map(str, command)), env=env, stdin=subprocess.DEVNULL,
                                stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            raise RuntimeError('CPU build deadline expired; inspect private log') from None
        if code:
            raise RuntimeError('CPU build/check failed; inspect private log: ' + Path(log).name)


def meson_command(meson, source, native):
    return [meson, 'setup', native, source, '--buildtype=release', '--wrap-mode=nofallback',
            '-Dvulkan-drivers=amd', '-Dgallium-drivers=', '-Dplatforms=', '-Dllvm=disabled',
            '-Dglx=disabled', '-Degl=disabled', '-Dgbm=disabled', '-Dopengl=false',
            '-Dgles1=disabled', '-Dgles2=disabled', '-Dxmlconfig=disabled', '-Dvalgrind=disabled',
            '-Dlibunwind=disabled', '-Dzstd=disabled', '-Dspirv-tools=disabled',
            '-Dbuild-tests=false', '-Dvulkan-layers=', '-Dtools=']


def build(mesa, output, tool_directories):
    if sys.version_info < (3, 10) or platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        raise ValueError('Native x86_64 macOS and Python >= 3.10 are required')
    mesa, output = Path(mesa).resolve(), Path(output).resolve()
    output.relative_to((ROOT / 'build').resolve())
    if output.exists() or mesa == output or mesa in output.parents or output in mesa.parents:
        raise ValueError('Use a fresh, separate ignored build output')
    os.setpriority(os.PRIO_PROCESS, 0, max(15, os.getpriority(os.PRIO_PROCESS, 0)))
    lock = json.loads(LOCK.read_text())
    snapshots = {str(path.relative_to(ROOT)): path.read_bytes() for path in (Path(__file__).resolve(), LOCK, SMOKE)}
    baseline = inventory(mesa)
    if (len(baseline) != lock['full_baseline_files_and_links'] or
            inventory_digest(baseline) != lock['full_baseline_inventory_sha256']):
        raise ValueError('Complete source differs from reviewed Mesa plus the pinned 19 patches')
    report = radv_ib_tail.prepare(mesa, output)
    transport = output / 'source'
    source = output / 'mesa'
    shutil.copytree(mesa, source, symlinks=True, ignore=shutil.ignore_patterns('.git'))
    if inventory(source) != baseline:
        raise RuntimeError('Source copy drifted')
    for name, expected in lock['patched_source_sha256'].items():
        if digest(transport / name) != expected:
            raise ValueError('Staged patch differs from hardware-tested transport')
        shutil.copyfile(transport / name, source / name)
    frozen = inventory(source)
    changed = {name for name in baseline if baseline[name] != frozen.get(name)}
    if set(baseline) != set(frozen) or changed != set(lock['patched_source_sha256']):
        raise RuntimeError('Unexpected full-source change')
    subprocess.run(['git', 'init', '-q', str(source)], check=True, capture_output=True)
    for name in ('home', 'tmp', 'pkgconfig-empty'):
        (output / name).mkdir(mode=0o700)
    path = ':'.join([str(Path(p).resolve()) for p in tool_directories] + ['/usr/bin', '/bin', '/usr/sbin', '/sbin'])
    env = {'PATH': path, 'HOME': str(output / 'home'), 'TMPDIR': str(output / 'tmp'),
           'LANG': 'C', 'LC_ALL': 'C', 'CC': '/usr/bin/clang', 'CXX': '/usr/bin/clang++',
           'OBJC': '/usr/bin/clang', 'AR': '/usr/bin/ar', 'MACOSX_DEPLOYMENT_TARGET': '15.0',
           'PKG_CONFIG_LIBDIR': str(output / 'pkgconfig-empty'), 'PYTHONNOUSERSITE': '1',
           'PYTHONDONTWRITEBYTECODE': '1', 'CMAKE_BUILD_PARALLEL_LEVEL': '1'}
    tools = {name: shutil.which(name, path=path) for name in ('meson', 'ninja', 'glslangValidator', 'pkg-config')}
    if not all(tools.values()):
        raise ValueError('Missing explicit build tools; no dependency is installed automatically')
    versions = {name: subprocess.check_output([tools[name], '--version'], env=env, text=True).strip()
                for name in ('meson', 'ninja', 'glslangValidator')}
    if (versions['meson'] != lock['build_tools']['meson'] or
            versions['ninja'].split('.git')[0] != lock['build_tools']['ninja'] or
            versions['glslangValidator'].splitlines()[0] != 'Glslang Version: 11:' + lock['build_tools']['glslang']):
        raise ValueError('Build tool version differs from the reviewed toolchain')
    (output / 'frozen-full-source.json').write_text(json.dumps(frozen, indent=2) + '\n')
    native = output / 'native'
    print(json.dumps({'phase': 'full-source-frozen', 'files_and_links': len(frozen), 'GPU_executed': False}), flush=True)
    logged(meson_command(tools['meson'], source, native), output / 'configure.log', env)
    print(json.dumps({'phase': 'full-runtime-compile-started', 'parallel_jobs': 1}), flush=True)
    logged([tools['ninja'], '-C', native, '-j', '1', TARGET], output / 'compile.log', env, 7200)
    library = native / TARGET
    if struct.unpack('<IiiII', library.read_bytes()[:20])[0:2] != (0xfeedfacf, 0x1000007):
        raise RuntimeError('Unexpected Mach-O architecture')
    if struct.unpack('<IiiII', library.read_bytes()[:20])[3] != 6:
        raise RuntimeError('Output is not a dylib')
    deps = subprocess.check_output(['/usr/bin/xcrun', 'otool', '-L', library], text=True).splitlines()
    deps = [line.strip().split(' (', 1)[0] for line in deps[1:] if line.strip()]
    if not deps or deps[0] != '@rpath/libvulkan_radeon.dylib' or any(
            not item.startswith(('/usr/lib/', '/System/Library/')) for item in deps[1:]):
        raise RuntimeError('Unexpected runtime identity or non-system dependency')
    exports = subprocess.check_output(['/usr/bin/xcrun', 'nm', '-gU', library], text=True)
    defined = {line.split()[-1] for line in exports.splitlines() if line.split()}
    if not {'_vk_icdGetInstanceProcAddr', '_vk_icdNegotiateLoaderICDInterfaceVersion',
            '_radv_darwin_set_service_class'} <= defined:
        raise RuntimeError('Missing runtime exports')
    commands = json.loads((native / 'compile_commands.json').read_text())
    closure = {}
    for name in ('ac_darwin_kext.c', 'ac_darwin_drm.c', 'ac_darwin_iokit.c'):
        rows = [row for row in commands if Path(row['file']).name == name]
        if len(rows) != 1:
            raise RuntimeError('Ambiguous transport compilation')
        row = rows[0]
        compiled = Path(row['file'])
        if not compiled.is_absolute():
            compiled = Path(row['directory']) / compiled
        if compiled.resolve() != source / radv_ib_tail.PREFIX / name:
            raise RuntimeError('Transport compiled from an unexpected source')
        words = shlex.split(row['command'])
        obj = words[words.index('-o') + 1]
        dependencies = subprocess.check_output([tools['ninja'], '-C', native, '-t', 'deps', obj], env=env, text=True)
        header = source / radv_ib_tail.PREFIX / 'ac_darwin_kext.h'
        actual = {(native / item.strip()).resolve() for item in dependencies.splitlines()[1:] if item.strip()}
        if header not in actual:
            raise RuntimeError('Transport header dependency was not established')
        closure[name] = {'sha256': digest(compiled), 'reviewed_header_used': True}
    link_commands = subprocess.check_output([tools['ninja'], '-C', native, '-t', 'commands', TARGET], env=env)
    (output / 'link-closure.log').write_bytes(link_commands)
    if not all(name.encode() in link_commands for name in closure) or b'libamd_common.a' not in link_commands:
        raise RuntimeError('Reviewed transport not in dylib link closure')
    smoke_source = output / 'smoke.c'
    smoke_source.write_bytes(snapshots[str(SMOKE.relative_to(ROOT))])
    cc = ['/usr/bin/xcrun', 'clang', '-arch', 'x86_64', '-std=c11', '-Wall', '-Wextra', '-Werror']
    frameworks = ['-framework', 'IOKit', '-framework', 'CoreFoundation']
    guard = output / 'libsmoke_guard.dylib'
    smoke = output / 'dylib-smoke'
    logged(cc + ['-DPHX34_SMOKE_GUARD', '-dynamiclib', smoke_source, *frameworks,
                 '-Wl,-install_name,@rpath/libsmoke_guard.dylib', '-o', guard], output / 'guard-compile.log', env)
    logged(cc + [smoke_source, guard, *frameworks, '-Wl,-rpath,@executable_path', '-o', smoke],
           output / 'smoke-compile.log', env)
    for index, binary in enumerate((library, guard, smoke)):
        logged(['/usr/bin/codesign', '--force', '--sign', '-', binary], output / ('sign-' + str(index) + '.log'), env)
        logged(['/usr/bin/codesign', '--verify', '--strict', binary], output / ('verify-' + str(index) + '.log'), env)
    logged([smoke, library], output / 'smoke-result.json', env, 30)
    smoke_result = json.loads((output / 'smoke-result.json').read_text())
    if smoke_result != {'dylib_loaded': True, 'guard_self_test': True, 'required_exports': True,
                        'Phoenix_service_policy': True, 'IOKit_calls': 0,
                        'physical_device_enumeration': False, 'GPU_executed': False}:
        raise RuntimeError('Unexpected smoke result')
    if inventory(mesa) != baseline or inventory(source) != frozen:
        raise RuntimeError('Full source changed during compilation')
    if any((ROOT / name).read_bytes() != data for name, data in snapshots.items()):
        raise RuntimeError('Runtime recipe changed during compilation')
    mec_range.verify_current_inputs(mec_range.protected_base_inputs(), ROOT)
    report.update({'full_runtime_built': True, 'library_sha256': digest(library), 'library_bytes': library.stat().st_size,
                   'full_source_files_and_links': len(frozen), 'baseline_inventory_sha256': inventory_digest(baseline),
                   'compiled_inventory_sha256': inventory_digest(frozen), 'compiled_transport': closure,
                   'runtime_dependencies': deps[1:], 'runtime_smoke': smoke_result, 'parallel_jobs': 1,
                   'tool_versions': versions, 'tool_executable_sha256': {name: digest(value) for name, value in tools.items()},
                   'build_python_version': platform.python_version(),
                   'compiler': subprocess.check_output(['/usr/bin/xcrun', 'clang', '--version'], text=True).splitlines()[0],
                   'recipe_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in snapshots.items()},
                   'runtime_GPU_executed': False, 'runtime_installed': False, 'binary_uploaded': False,
                   'OS_version': subprocess.check_output(['/usr/bin/sw_vers', '-productVersion'], text=True).strip(),
                   'OS_build': subprocess.check_output(['/usr/bin/sw_vers', '-buildVersion'], text=True).strip()})
    (output / 'runtime-build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({name: report[name] for name in ('full_runtime_built', 'library_sha256', 'parallel_jobs',
                                                    'runtime_smoke', 'runtime_GPU_executed', 'runtime_installed')}), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesa-source', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--toolchain-bin', action='append', type=Path, required=True)
    args = parser.parse_args()
    build(args.mesa_source, args.out, args.toolchain_bin)
