# SPDX-License-Identifier: MIT
"""Test actual staged mesboot with CPU doubles and host SDK objects only."""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import struct
import subprocess

from build34_exact_bootstrap_progress import method, once, prior_bootstrap, stage_bootstrap


ROOT = Path(__file__).resolve().parents[1]
PRIOR = 'docs/validation/build34-r3-raw-handoff-offline-20261121.json'
BOOT = 'tools/phxctl/mesboot.c'
FIXTURE = 'tests/test_build34_exact_bootstrap_progress.c'
INPUTS = (PRIOR, BOOT, FIXTURE, 'tools/build34_exact_bootstrap_progress.py',
          'tools/test_build34_exact_bootstrap_progress.py')
HEADERS = ('mes_v11_api_def.h', 'PhxUpstream34Layout.h', 'csb_gfx11.h')


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def git(*args):
    return subprocess.check_output(['/usr/bin/git', *args], cwd=ROOT, timeout=15)


def xcrun(*args):
    return Path(subprocess.check_output(['/usr/bin/xcrun', *args], text=True, timeout=15).strip()).resolve()


def test(out):
    if (platform.system(), platform.machine()) != ('Darwin', 'x86_64'):
        raise ValueError('Require x86_64 macOS')
    out = Path(out).resolve()
    if (out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private') or
            git('symbolic-ref', '--short', 'HEAD').strip() != b'upstream34/vram-layout-fix'):
        raise ValueError('Require default build34 and a fresh ignored private output path')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    prior = json.loads((ROOT / PRIOR).read_bytes())
    if (prior['status'] != 'passed-CPU-and-native-object-one-way-raw-handoff-prerequisite' or prior['GPU_executed'] or
            any(sha((ROOT / name).read_bytes()) != digest for name, digest in prior['input_sha256'].items())):
        raise ValueError('Existing raw handoff inputs drifted')
    protected = git('ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py').decode().splitlines()
    if len(protected) != 172 or git('status', '--porcelain', '--', *protected):
        raise ValueError('Production input drift')
    production_before = {name: sha((ROOT / name).read_bytes()) for name in protected}
    frozen = {name: (ROOT / name).read_bytes() for name in INPUTS}
    source = frozen[BOOT].decode()
    old = prior_bootstrap(source)
    checked = stage_bootstrap(source)
    if sha(old.encode()) != prior['staged_bootstrap_sha256'] or old == checked:
        raise ValueError('Unexpected bootstrap predecessor or no change')
    compiler = xcrun('--find', 'clang')
    sdk = xcrun('--show-sdk-path')
    out.mkdir(mode=0o700)
    include = out / 'frozen-headers'
    include.mkdir()
    for name in HEADERS:
        header = 'tools/phxctl/' + name
        frozen[header] = (ROOT / header).read_bytes()
        (include / name).write_bytes(frozen[header])
    common = [str(compiler), '-arch', 'x86_64', '-isysroot', str(sdk), '-I', str(include), '-std=gnu11']
    fixture = out / 'fixture.c'
    fixture.write_bytes(frozen[FIXTURE])

    def run(args, label, expected=0):
        result = subprocess.run([str(arg) for arg in args], cwd=out, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=60)
        (out / (label + '.stdout')).write_bytes(result.stdout)
        (out / (label + '.stderr')).write_bytes(result.stderr)
        if expected is not None and result.returncode != expected:
            raise RuntimeError(f'{label} exited {result.returncode} (expected {expected}); preserved private diagnostics')
        return result

    checks, wrapper_exits, objects, warnings = {}, {}, {}, {}
    for label, text in [('prior', old), ('checked', checked)]:
        full = out / (label + '.c')
        full.write_text(text)
        obj = out / (label + '.o')
        compiled = run([*common, '-Wall', '-Wextra', '-c', full, '-o', obj], label + '-native-object')
        data = obj.read_bytes()
        if struct.unpack_from('<IIII', data)[:2] != (0xfeedfacf, 0x01000007) or struct.unpack_from('<I', data, 12)[0] != 1:
            raise ValueError('Require a nonloadable x86_64 MH_OBJECT')
        objects[label] = sha(data)
        warnings[label] = re.findall(r'warning: ([^\n]+)', compiled.stderr.decode())
        cpu = once(text, method(text, 'static int open_kext('), 'static int open_kext(void) { return mockOpen(); }\n')
        cpu_source = out / 'cpu-mesboot.inc'
        cpu_source.write_text(cpu)
        binary = out / (label + '-cpu')
        flags = ['-DCHECKED_STAGE'] if label == 'checked' else []
        build = [*common, *flags, '-g', '-O1', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                 fixture, '-o', binary]
        if label == 'prior':
            run(build, 'prior-alignment-build')
            misaligned = run([binary], 'prior-alignment', expected=None)
            if not misaligned.returncode or b'runtime error: store to misaligned address' not in misaligned.stderr:
                raise ValueError('Pinned predecessor did not exhibit the known packed-store error')
            # Isolate this known UB only in the control that exercises the old flow.
            cpu_source.write_text(once(cpu, 'static int mes_submit(',
                                       '__attribute__((no_sanitize("alignment"))) static int mes_submit('))
        run(build, label + '-cpu-build')
        result = run([binary], label + '-cpu')
        match = re.fullmatch(rb'PASS ([0-9]+) mesboot progress checks\n', result.stdout)
        if not match or result.stderr:
            raise ValueError('Unexpected sanitizer output')
        checks[label] = int(match[1])
        wrapper_exits[label] = []
        for case, selector in [('doorbell', 110), ('short-reply', 2), ('second-adoption', 112)]:
            result = run([binary, case], f'{label}-{case}', expected=74)
            message = rb'upstream34-layout: selector %d transport/size failure: [^\n]+\n' % selector
            if result.stdout or not re.fullmatch(message, result.stderr):
                raise ValueError(f'Unexpected output from {label}-{case}')
            wrapper_exits[label].append(case)
    if warnings['prior'] != warnings['checked']:
        raise ValueError('Host SDK warning drift')
    if any(sha((ROOT / name).read_bytes()) != digest for name, digest in production_before.items()):
        raise ValueError('Production input changed during checks')
    evidence = dict(status='passed-checked-paired-mesboot-CPU-and-native-object', kernel_build=34,
                    parent_source_checkpoint=git('rev-parse', 'HEAD').decode().strip(),
                    frozen_input_sha256={name: sha(blob) for name, blob in frozen.items()},
                    prior_bootstrap_sha256=sha(old.encode()), checked_bootstrap_sha256=sha(checked.encode()),
                    ASan_UBSan_checks=checks, existing_wrapper_exit_cases=wrapper_exits, x86_64_MH_OBJECT_sha256=objects,
                    prior_packed_store_UB_reproduced=True, prior_flow_control_suppresses_alignment_only_in_mes_submit=True,
                    unchanged_compiler_warnings=len(warnings['checked']), production_inputs_unchanged=len(protected),
                    hardware_candidate_created_or_installed=False, hardware_completion_or_writer_drain_accepted=False,
                    effective_cache_or_native_reader_accepted=False, IOKit_opened=False, GPU_executed=False,
                    power_actions=0, FPS_accepted=False, R3_complete=False)
    (out / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    test(parser.parse_args().out)
