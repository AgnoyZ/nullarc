#!/usr/bin/env python3
"""Exercise the pinned full R3 Vulkan lifecycle with no system IOKit dependency."""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

from build34_r3_radv_runtime import DARWIN, ROOT, TARGET, digest, inventory, inventory_digest, production_snapshot


LINK_RECORD = ROOT / 'docs/validation/build34-r3-radv-full-link-offline-20261123.json'
FIXTURE_LIBRARY = ROOT / 'tests/build34_radv_runtime_iokit.c'
FIXTURE_MAIN = ROOT / 'tests/test_build34_radv_runtime_enumeration.c'
IOKIT = '/System/Library/Frameworks/IOKit.framework/Versions/A/IOKit'
STUB = '@loader_path/libcpu_iokit.dylib'


def dylibs(path):
    lines = subprocess.check_output(['/usr/bin/otool', '-L', path], text=True, timeout=20).splitlines()
    return [line.strip().split(' (', 1)[0] for line in lines[1:]]


def symbols(path):
    return subprocess.check_output(['/usr/bin/nm', '-m', path], text=True, timeout=20)


def imports_from(path, provider):
    return set(re.findall(r'^\s*\(undefined\).*? (\S+) \(from ' + re.escape(provider) + r'\)$',
                          symbols(path), re.M))


def text_section(path):
    result = subprocess.check_output(['/usr/bin/otool', '-s', '__TEXT', '__text', path], timeout=45)
    marker = b'(__TEXT,__text) section\n'
    if result.count(marker) != 1 or len(result.partition(marker)[2]) < 1000:
        raise ValueError('Require a nonempty x86_64 text section')
    return result.partition(marker)[2]


def test(runtime, output):
    runtime, output = Path(runtime).resolve(), Path(output).resolve()
    if (ROOT / 'build' not in output.parents or output.exists() or not output.name.endswith('-private') or
            output == runtime or runtime in output.parents or output in runtime.parents):
        raise ValueError('Use a fresh separate ignored worktree output ending -private')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(output)], cwd=ROOT, check=True, timeout=15)
    recorded = json.loads(LINK_RECORD.read_text())
    library = runtime / 'native' / TARGET
    if (json.loads((runtime / 'result-private.json').read_text()) != recorded or
            digest(library) != recorded['library_sha256']):
        raise ValueError('Full R3 link does not match the reviewed evidence')
    mesa = runtime / 'mesa'
    manifest = inventory(mesa)
    if inventory_digest(manifest) != recorded['staged_inventory_sha256']:
        raise ValueError('Reviewed full Mesa inputs changed')
    expected = {*recorded['IOKit_imports'], '_kIOMainPortDefault'}
    original_deps = dylibs(library)
    if original_deps.count(IOKIT) != 1 or imports_from(library, 'IOKit') != expected:
        raise ValueError('Full binary IOKit imports are not all modeled')
    if re.search(r'\(undefined\).*? _dl(?:open|sym)\s', symbols(library)):
        raise ValueError('Unexpected library dynamic-loading entry point')
    protected = production_snapshot()
    inputs = {path: digest(path) for path in (Path(__file__).resolve(), LINK_RECORD, FIXTURE_LIBRARY, FIXTURE_MAIN)}
    output.mkdir(mode=0o700, parents=True)

    def run(args, label, *, timeout=90):
        result = subprocess.run(args, cwd=output, env=env, capture_output=True, text=True, timeout=timeout)
        (output / (label + '.stdout')).write_text(result.stdout)
        (output / (label + '.stderr')).write_text(result.stderr)
        if result.returncode:
            raise RuntimeError(label + ' failed; inspect private logs')
        return result.stdout

    env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'HOME': str(output), 'TMPDIR': str(output),
           'LANG': 'C', 'LC_ALL': 'C', 'MESA_SHADER_CACHE_DISABLE': 'true'}
    cc = ['/usr/bin/xcrun', 'clang', '-arch', 'x86_64', '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
          '-DPHX34_CPU_R3=1', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
    cc.extend('-I' + str(mesa / name) for name in ('include', 'include/darwin', DARWIN))
    stub = output / 'libcpu_iokit.dylib'
    executable = output / 'cpu-radv-r3-lifecycle'
    run([*cc, '-MMD', '-MF', 'stub.d', '-dynamiclib', FIXTURE_LIBRARY, '-Wl,-install_name,' + STUB,
         '-o', stub], 'compile-stub')
    run([*cc, '-MMD', '-MF', 'main.d', FIXTURE_MAIN, stub, '-o', executable], 'compile-main')
    for depfile in ('stub.d', 'main.d'):
        args = shlex.split((output / depfile).read_text().replace('\\\n', ' ').split(':', 1)[1])
        for name in args:
            path = Path(name).resolve()
            if path not in inputs and digest(path) != manifest[path.relative_to(mesa).as_posix()]['sha256']:
                raise ValueError('CPU fixture compiled with unreviewed header')
    exported = subprocess.check_output(['/usr/bin/nm', '-gU', stub], text=True, timeout=20)
    if not expected <= {line.split()[-1] for line in exported.splitlines() if line.split()}:
        raise ValueError('Missing required SDK-compatible stub symbol')
    if IOKIT in {*dylibs(stub), *dylibs(executable)} or STUB not in dylibs(executable):
        raise ValueError('Fixture unexpectedly links system IOKit or misses the stub')

    copy = output / 'radv-r3-CPU-only.dylib'
    shutil.copyfile(library, copy)
    run(['/usr/bin/install_name_tool', '-change', IOKIT, STUB, copy], 'retarget-test-copy')
    run(['/usr/bin/codesign', '--force', '--sign', '-', copy], 'sign-host-test-copy')
    run(['/usr/bin/codesign', '--verify', '--strict', copy], 'verify-host-test-copy')
    if (dylibs(copy) != [STUB if name == IOKIT else name for name in original_deps] or
            imports_from(copy, 'libcpu_iokit') != expected or text_section(copy) != text_section(library)):
        raise ValueError('Test-copy substitution or compiled text does not match')

    results = {}
    for index, name in enumerate(('success', 'open_refused', 'missing_capability', 'short_session_reply')):
        results[name] = json.loads(run([executable, copy, str(index)], name))
        if (results[name]['scenario'] != index or results[name]['GPU_executed'] or results[name]['native_submits'] or
                results[name]['physical_devices'] != (index == 0) or results[name]['open_attempts'] != 1):
            raise ValueError('Incomplete or unexpected Vulkan lifecycle evidence')
    if (digest(library) != recorded['library_sha256'] or inventory(mesa) != manifest or
            production_snapshot() != protected or any(digest(path) != sha for path, sha in inputs.items())):
        raise ValueError('Source, library or fixture changed during verification')
    report = dict(status='passed-full-RADV-R3-CPU-lifecycle', kernel_build=34,
                  linked_library_sha256=recorded['library_sha256'], staged_inventory_sha256=inventory_digest(manifest),
                  retargeted_test_copy_only=True, executable_text_identical=True, system_IOKit_linked=False,
                  all_nine_IOKit_imports_modeled=True, fixture_ASan_UBSan=True, runtime_sanitized=False,
                  scenarios=results, protected_production_inputs=len(protected), native_mode_admitted=False,
                  real_IOKit_called=False, installed=False, binary_uploaded=False, native_submits=0,
                  GPU_executed=False, R3_complete=False)
    (output / 'result-private.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    test(args.runtime, args.out)
