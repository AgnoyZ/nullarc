#!/usr/bin/env python3
"""Freeze/build the guarded complete-runtime probe; only run its no-client guard self-test."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mec_range

ROOT = Path(__file__).resolve().parents[2]
PREFIX = 'tools/upstream34_layout/'
FILES = tuple(PREFIX + name for name in ('radv_ib_tail_runtime_guard.h', 'radv_ib_tail_runtime_guard.cpp',
                                        'radv_ib_tail_runtime_probe.c', 'radv_ib_tail_runtime_probe.comp',
                                        'radv_ib_tail_runtime_probe.py'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(runtime, output, glslang, cpu_fixture=None):
    runtime, output, glslang = (Path(p).resolve() for p in (runtime, output, glslang))
    output.relative_to((ROOT / 'build').resolve())
    if output.exists():
        raise ValueError('Fresh private output required')
    if cpu_fixture is not None and Path(cpu_fixture).resolve() != ROOT / 'tests/build34_radv_runtime_platform.cpp':
        raise ValueError('Only the reviewed CPU fixture is supported')
    record = json.loads((runtime / 'runtime-build.json').read_text())
    lock = json.loads((ROOT / (PREFIX + 'radv_ib_tail_runtime_sources.json')).read_text())
    library = runtime / 'native/src/amd/vulkan/libvulkan_radeon.dylib'
    if (record['approved_build34_checkpoint'] != mec_range.BASE or not record['full_runtime_built'] or
            record['runtime_GPU_executed'] or record['runtime_installed'] or sha(library) != record['library_sha256'] or
            record['patched_source_sha256'] != lock['patched_source_sha256'] or
            record['enumeration_owner'] != lock['enumeration_owner'] or
            sha(glslang) != record['tool_executable_sha256']['glslangValidator']):
        raise ValueError('Pinned complete original34 runtime/toolchain required')
    for name, digest in record['recipe_sha256'].items():
        if sha(ROOT / name) != digest:
            raise ValueError('Runtime recipe drift: ' + name)
    protected = mec_range.verify_current_inputs(mec_range.protected_base_inputs(), ROOT)
    names = FILES + ((str(Path(cpu_fixture).resolve().relative_to(ROOT)),) if cpu_fixture else ())
    snapshots = {name: (ROOT / name).read_bytes() for name in names}
    frozen = json.loads((runtime / 'frozen-full-source.json').read_text())
    output.mkdir(parents=True, mode=0o700)
    for name in ('source', 'include', 'home', 'tmp'):
        (output / name).mkdir(mode=0o700)
    for name, data in snapshots.items():
        (output / 'source' / Path(name).name).write_bytes(data)
    env = {'PATH':'/usr/bin:/bin:/usr/sbin:/sbin', 'HOME':str(output / 'home'), 'TMPDIR':str(output / 'tmp'), 'LANG':'C', 'LC_ALL':'C'}

    def command(name, args, timeout=90):
        proc = subprocess.run(list(map(str,args)), env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, timeout=timeout)
        (output / (name + '.stdout')).write_bytes(proc.stdout)
        (output / (name + '.stderr')).write_bytes(proc.stderr)
        if proc.returncode:
            raise RuntimeError('Probe preparation failed: ' + name + '; inspect private logs')
        return proc.stdout

    source = output / 'source'
    command('shader', [glslang,'-V','--target-env','vulkan1.2','--vn','runtime_probe_spv','-o',output / 'include/runtime_probe_spv.h',source / 'radv_ib_tail_runtime_probe.comp'])
    common = ['-arch','x86_64','-O1','-g','-Wall','-Wextra','-Werror','-fno-omit-frame-pointer',
              '-I'+str(source),'-I'+str(output / 'include'),'-I'+str(runtime / 'mesa/include'),'-I'+str(runtime / 'mesa/include/darwin')]
    if cpu_fixture:
        common += ['-fsanitize=address,undefined','-fno-sanitize-recover=all']
    guard, main = output / 'libbuild34_runtime_guard.dylib', output / 'build34-radv-runtime-probe'
    guard_sources = [source / 'radv_ib_tail_runtime_guard.cpp']
    if cpu_fixture:
        guard_sources += [source / Path(cpu_fixture).name]
    frameworks = ['-framework','IOKit','-framework','CoreFoundation']
    dependencies = []
    objects = []
    for index, path in enumerate(guard_sources):
        obj, dep = output / ('guard-'+str(index)+'.o'), output / ('guard-'+str(index)+'.d')
        flags = ['-DPHX34_RUNTIME_GUARD_CPU'] if cpu_fixture else []
        command('guard-compile-'+str(index), ['/usr/bin/xcrun','clang++','-std=c++17',*common,*flags,'-MMD','-MF',dep,'-c',path,'-o',obj])
        objects.append(obj); dependencies.append(dep)
    command('guard-link', ['/usr/bin/xcrun','clang++','-dynamiclib',*common,*objects,*frameworks,
                           '-Wl,-install_name,@rpath/libbuild34_runtime_guard.dylib','-o',guard])
    main_object, main_dep = output / 'probe.o', output / 'probe.d'
    command('probe-compile', ['/usr/bin/xcrun','clang','-std=c11',*common,'-MMD','-MF',main_dep,'-c',source / 'radv_ib_tail_runtime_probe.c','-o',main_object])
    dependencies.append(main_dep)
    command('probe-link', ['/usr/bin/xcrun','clang++',*common,main_object,guard,*frameworks,'-Wl,-rpath,@executable_path','-o',main])
    headers = {}
    for dep in dependencies:
        for name in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
            path = Path(name).resolve()
            if path.is_relative_to(output):
                continue
            relative = path.relative_to(runtime / 'mesa').as_posix()
            if sha(path) != frozen[relative]['sha256']:
                raise ValueError('Unfrozen probe dependency')
            headers[relative] = sha(path)
    exports = command('guard-symbols',['/usr/bin/xcrun','nm','-g',guard]).decode()
    if ('_phx34_cpu_' in exports) != bool(cpu_fixture):
        raise ValueError('Guard CPU/native identity differs from the requested build')
    shutil.copyfile(library, output / 'libvulkan_radeon.dylib')
    if sha(output / 'libvulkan_radeon.dylib') != record['library_sha256']:
        raise ValueError('Copied runtime library drift')
    for index, binary in enumerate((guard, main, output / 'libvulkan_radeon.dylib')):
        if binary.name != 'libvulkan_radeon.dylib':
            command('sign-'+str(index), ['/usr/bin/codesign','--force','--sign','-',binary])
        command('verify-'+str(index), ['/usr/bin/codesign','--verify','--strict',binary])
        command('arch-'+str(index), ['/usr/bin/lipo',binary,'-verify_arch','x86_64'])
    text = command('guard-selftest',[main,'--guard-selftest'],15).decode()
    if text != 'GUARD-SELFTEST: passed; no service enumeration or GPU client\n':
        raise RuntimeError('Guard self-test did not complete')
    if any((ROOT / name).read_bytes() != data for name,data in snapshots.items()) or sha(library) != record['library_sha256']:
        raise RuntimeError('Probe preparation input drift')
    mec_range.verify_current_inputs(mec_range.protected_base_inputs(), ROOT)
    report = {'compiled':True,'CPU_platform':bool(cpu_fixture),'guard_selftest_passed':True,
              'guard_selftest_real_GPU_client_opened':False,'native_GPU_probe_executed':False,'hardware_scope_armed':False,
              'installed':False,'GPU_executed':False,'approved_original34_checkpoint':mec_range.BASE,
              'library_sha256':record['library_sha256'],'glslang_sha256':sha(glslang),
              'binaries_sha256':{p.name:sha(p) for p in (guard,main,output / 'libvulkan_radeon.dylib')},
              'sources_sha256':{name:hashlib.sha256(data).hexdigest() for name,data in snapshots.items()},
              'reviewed_header_sha256':headers,'protected_source_sha256':protected}
    (output / 'preparation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:report[key] for key in ('compiled','CPU_platform','guard_selftest_passed','GPU_executed','hardware_scope_armed')}),flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--glslang',type=Path,required=True)
    args = parser.parse_args()
    prepare(args.runtime,args.out,args.glslang)
