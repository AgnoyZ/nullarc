#!/usr/bin/env python3
"""Exercise pinned full R3 Vulkan entrypoints with no system IOKit dependency."""

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
EXACT_CS_LINK_RECORD = ROOT / 'docs/validation/build34-r3-radv-exact-cs-link-offline-20261123.json'
FIXTURE_LIBRARY = ROOT / 'tests/build34_radv_runtime_iokit.c'
FIXTURE_MAIN = ROOT / 'tests/test_build34_radv_runtime_enumeration.c'
FIXTURE_HEADER = ROOT / 'tests/build34_radv_runtime_cpu.h'
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


def test(runtime, output, exact_cs=False):
    runtime, output = Path(runtime).resolve(), Path(output).resolve()
    if (ROOT / 'build' not in output.parents or output.exists() or not output.name.endswith('-private') or
            output == runtime or runtime in output.parents or output in runtime.parents):
        raise ValueError('Use a fresh separate ignored worktree output ending -private')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(output)], cwd=ROOT, check=True, timeout=15)
    link_record = EXACT_CS_LINK_RECORD if exact_cs else LINK_RECORD
    recorded = json.loads(link_record.read_text())
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
    inputs = {path: digest(path) for path in (Path(__file__).resolve(), link_record, FIXTURE_LIBRARY,
                                             FIXTURE_MAIN, FIXTURE_HEADER)}
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
    cc.extend('-I' + str(mesa / name) for name in ('include', 'include/darwin', DARWIN, DARWIN + 'r3/phxbringup'))
    stub = output / 'libcpu_iokit.dylib'
    executable = output / 'cpu-radv-r3-lifecycle'
    run([*cc, '-MMD', '-MF', 'stub.d', '-dynamiclib', FIXTURE_LIBRARY, '-Wl,-install_name,' + STUB,
         '-o', stub], 'compile-stub')
    run([*cc, '-MMD', '-MF', 'main.d', FIXTURE_MAIN, stub, '-o', executable], 'compile-main')
    for depfile in ('stub.d', 'main.d'):
        args = shlex.split((output / depfile).read_text().replace('\\\n', ' ').split(':', 1)[1])
        for name in args:
            path = Path(name).resolve()
            expected_hash = inputs[path] if path in inputs else manifest[path.relative_to(mesa).as_posix()]['sha256']
            if digest(path) != expected_hash:
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
    scenarios = [(0, 'success'), (1, 'open_refused'), (2, 'missing_capability'), (3, 'short_session_reply')]
    scenarios += [(5, 'exact_submit'), (6, 'exact_dual_queue')] if exact_cs else [(4, 'submit_refused')]
    for index, name in scenarios:
        result = results[name] = json.loads(run([executable, copy, str(index)], name))
        expected_submits = {5: 1, 6: 2}.get(index, 0)
        if (result['scenario'] != index or result['GPU_executed'] or result['native_submits'] or
                result['physical_devices'] != (index in (0, 4, 5, 6)) or result['open_attempts'] != 1 or
                any(result[key] != expected_submits for key in ('modeled_exact_submits', 'exact_acks')) or
                result['positive_waits'] != result['positive_pending'] + bool(expected_submits) or
                bool(result['positive_pending']) != (index == 6) or
                result['prefix_snapshots'] != result['zero_polls'] + result['positive_waits'] or
                (expected_submits and result['zero_polls'] < 2) or
                (not expected_submits and (result['zero_polls'] or result['prefix_snapshots'])) or
                bool(result['gap_prefixes']) != (index == 6) or result['closed_prefixes'] != (index == 6)):
            raise ValueError('Incomplete or unexpected Vulkan lifecycle evidence')
    if (digest(library) != recorded['library_sha256'] or inventory(mesa) != manifest or
            production_snapshot() != protected or any(digest(path) != sha for path, sha in inputs.items())):
        raise ValueError('Source, library or fixture changed during verification')
    status = 'passed-full-RADV-R3-CPU-exact-submit' if exact_cs else 'passed-full-RADV-R3-CPU-submit-refusal'
    report = dict(status=status, kernel_build=34,
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
    parser.add_argument('--exact-cs', action='store_true', help='Verify the separately pinned staged exact-CS variant')
    args = parser.parse_args()
    test(args.runtime, args.out, args.exact_cs)
