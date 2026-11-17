#!/usr/bin/env python3
"""Exercise complete RADV enumeration/device lifetime with an all-fake IOKit dylib."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(runtime, output):
    runtime, output = Path(runtime).resolve(), Path(output).resolve()
    output.relative_to((ROOT / 'build').resolve())
    if output.exists():
        raise ValueError('Fresh ignored output required')
    record = json.loads((runtime / 'runtime-build.json').read_text())
    frozen = json.loads((runtime / 'frozen-full-source.json').read_text())
    library = runtime / 'native/src/amd/vulkan/libvulkan_radeon.dylib'
    if (not record['full_runtime_built'] or record['runtime_GPU_executed'] or
            sha(library) != record['library_sha256']):
        raise ValueError('Pinned, CPU-only built runtime required')
    undefined = subprocess.check_output(['/usr/bin/xcrun', 'nm', '-u', library], text=True)
    allowed = {'_IOServiceMatching', '_IOServiceGetMatchingService', '_IOServiceOpen', '_IOServiceClose',
               '_IOObjectRelease', '_IOConnectCallMethod', '_IOConnectMapMemory64', '_IOConnectUnmapMemory64'}
    if set(re.findall(r'\b(_IO\w+)\b', undefined)) != allowed:
        raise ValueError('Runtime has an unexpected IOKit import; CPU fixture cannot run')
    sources = (Path(__file__).resolve(), ROOT / 'tests/build34_radv_runtime_iokit.c',
               ROOT / 'tests/test_build34_radv_runtime_enumeration.c')
    snapshots = {p: p.read_bytes() for p in (*sources, runtime / 'runtime-build.json', runtime / 'frozen-full-source.json')}
    output.mkdir(parents=True, mode=0o700)
    cc = ['/usr/bin/xcrun', 'clang', '-arch', 'x86_64', '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
    for path in ('include', 'include/darwin'):
        cc.append('-I' + str(runtime / 'mesa' / path))
    frameworks = ['-framework', 'IOKit', '-framework', 'CoreFoundation']
    guard, binary = output / 'libcpu_iokit.dylib', output / 'cpu-runtime-enumeration'
    commands = {
        'guard': cc + ['-MMD', '-MF', str(output / 'guard.d'), '-dynamiclib', str(sources[1]), *frameworks,
                       '-Wl,-install_name,@rpath/libcpu_iokit.dylib', '-o', str(guard)],
        'main': cc + ['-MMD', '-MF', str(output / 'main.d'), str(sources[2]), str(guard), *frameworks,
                      '-Wl,-rpath,@executable_path', '-o', str(binary)],
    }
    for name, command in commands.items():
        proc = subprocess.run(command, capture_output=True, timeout=90)
        (output / (name + '-compile.log')).write_bytes(proc.stdout + proc.stderr)
        if proc.returncode:
            raise RuntimeError('CPU fixture compilation failed; inspect private ' + name + ' log')
    header_hashes = {}
    for depfile in (output / 'guard.d', output / 'main.d'):
        dependencies = shlex.split(depfile.read_text().replace('\\\n', ' ').split(':', 1)[1])
        for name in dependencies:
            path = Path(name).resolve()
            if path in sources:
                continue
            relative = path.relative_to(runtime / 'mesa').as_posix()
            if sha(path) != frozen[relative]['sha256']:
                raise RuntimeError('CPU fixture used an unfrozen header')
            header_hashes[relative] = sha(path)
    env = {key: value for key, value in os.environ.items() if not key.startswith(('RADV_', 'MESA_', 'AMD_', 'VK_', 'DYLD_'))}
    env['MESA_SHADER_CACHE_DISABLE'] = 'true'
    results = {}
    for policy in ('0', '1'):
        proc = subprocess.run([str(binary), str(library), policy], env=env, capture_output=True, text=True, timeout=90)
        (output / (policy + '.stdout')).write_text(proc.stdout)
        (output / (policy + '.stderr')).write_text(proc.stderr)
        if proc.returncode:
            raise RuntimeError('CPU full-runtime lifecycle failed; inspect private logs, policy ' + policy)
        data = json.loads(proc.stdout)
        if data['native_submits'] or data['GPU_executed'] or not data['CPU_only']:
            raise RuntimeError('Unexpected CPU lifecycle result')
        results[policy] = data
    if sha(library) != record['library_sha256'] or any(p.read_bytes() != data for p, data in snapshots.items()):
        raise RuntimeError('CPU runtime test input drift')
    report = {'result': 'passed', 'library_sha256': sha(library), 'policies': results,
              'ASan_UBSan_on_CPU_fixtures': True, 'full_runtime_sanitizer_instrumented': False,
              'all_runtime_IOKit_imports_audited': True, 'IOServiceMatching_dictionary_only': True,
              'native_submits': 0, 'GPU_executed': False, 'legacy_profile_sync_clone_orphan_fixed': False,
              'reviewed_header_sha256': header_hashes,
              'inputs_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(snapshots[p]).hexdigest() for p in sources}}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    run(args.runtime, args.out)
