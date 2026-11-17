#!/usr/bin/env python3
"""Exercise the dylib smoke guard on CPU with invalid/null IOKit handles only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / 'tools/upstream34_layout/radv_ib_tail_dylib_smoke.c'


def run(output):
    if sys.platform != 'darwin' or output.exists():
        raise ValueError('macOS and a fresh ignored output directory are required')
    output.mkdir(parents=True, mode=0o700)
    snapshots = {path: path.read_bytes() for path in (Path(__file__).resolve(), SMOKE)}
    cc = ['/usr/bin/xcrun', 'clang', '-arch', 'x86_64', '-std=c11', '-Wall', '-Wextra', '-Werror']
    frameworks = ['-framework', 'IOKit', '-framework', 'CoreFoundation']
    smoke = output / 'dylib-smoke'
    guard = output / 'libsmoke_guard.dylib'
    subprocess.run(cc + ['-DPHX34_SMOKE_GUARD', '-dynamiclib', str(SMOKE), *frameworks,
                        '-Wl,-install_name,@rpath/libsmoke_guard.dylib', '-o', str(guard)], check=True, capture_output=True)
    subprocess.run(cc + [str(SMOKE), str(guard), *frameworks, '-Wl,-rpath,@executable_path',
                        '-o', str(smoke)], check=True, capture_output=True)
    base = '''#include <IOKit/IOKitLib.h>
#include <errno.h>
#include <string.h>
void *vk_icdGetInstanceProcAddr(void) { return 0; }
int vk_icdNegotiateLoaderICDInterfaceVersion(void) { return 0; }
int radv_darwin_set_service_class(const char *s) { return strcmp(s,"PhxBringup") ? -EINVAL : 0; }
'''
    cases = {
        'benign': ('', 0, ''),
        'missing-export': ('', 5, 'required exports'),
        'matching-constructor': ('IOServiceGetMatchingService(0, IOServiceMatching("NullarcCpuTestNeverPresent"));', 4, 'IOKit activity blocked'),
        'matches-constructor': ('io_iterator_t i = 0; IOServiceGetMatchingServices(0, IOServiceMatching("NullarcCpuTestNeverPresent"), &i);', 4, 'IOKit activity blocked'),
        'open-constructor': ('io_connect_t c = 0; IOServiceOpen(0, mach_task_self(), 0, &c);', 4, 'IOKit activity blocked'),
        'call-constructor': ('IOConnectCallMethod(0, 0, 0, 0, 0, 0, 0, 0, 0, 0);', 4, 'IOKit activity blocked'),
        'map-constructor': ('mach_vm_address_t a = 0; mach_vm_size_t n = 0; IOConnectMapMemory64(0, 0, mach_task_self(), &a, &n, 0);', 4, 'IOKit activity blocked'),
        'unmap-constructor': ('IOConnectUnmapMemory64(0, 0, mach_task_self(), 0);', 4, 'IOKit activity blocked'),
        'close-constructor': ('IOServiceClose(0);', 4, 'IOKit activity blocked'),
    }
    env = {k: v for k, v in os.environ.items() if not k.startswith(('RADV_', 'MESA_', 'AMD_', 'VK_', 'DYLD_'))}
    results = {}
    for name, (constructor, expected, diagnostic) in cases.items():
        source = output / (name + '.c')
        text = base.replace('vk_icdGetInstanceProcAddr', 'missing_export') if name == 'missing-export' else base
        if constructor:
            text += '__attribute__((constructor)) static void init(void) { ' + constructor + ' }\n'
        source.write_text(text)
        dylib = output / (name + '.dylib')
        subprocess.run(cc + ['-dynamiclib', str(source), *frameworks, '-o', str(dylib)], check=True, capture_output=True)
        proc = subprocess.run([str(smoke), str(dylib)], env=env, capture_output=True, text=True, timeout=15)
        (output / (name + '.stdout')).write_text(proc.stdout)
        (output / (name + '.stderr')).write_text(proc.stderr)
        if proc.returncode != expected or diagnostic not in proc.stderr:
            raise RuntimeError('Unexpected guard result: ' + name)
        if expected == 0:
            data = json.loads(proc.stdout)
            assert data['IOKit_calls'] == 0 and not data['GPU_executed']
        else:
            assert not proc.stdout
        results[name] = {'passed': True, 'returncode': proc.returncode}
    if any(path.read_bytes() != data for path, data in snapshots.items()):
        raise RuntimeError('Smoke test input changed during execution')
    report = {'result': 'passed', 'CPU_cases': results, 'GPU_executed': False, 'real_IOKit_handle_used': False,
              'input_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(data).hexdigest()
                               for path, data in snapshots.items()}}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    run(parser.parse_args().out.resolve())
