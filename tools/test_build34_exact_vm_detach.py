# SPDX-License-Identifier: MIT
"""Check VM close ordering in the frozen legacy CPU harness, with the latest VM method."""

import argparse
import json
from pathlib import Path
import re
import subprocess

from build34_exact_legacy_close import stage_header
from build34_exact_submit import once
from build34_exact_vm_detach import FREE, previous_stage, stage
from test_build34_exact_ownership import DRIVER, ROOT, method, sha


BRANCH = 'upstream34/vram-layout-fix'
BASE = 'a8edc7268d9770a3fef82c5670980c0e6cc04046'
PREDECESSOR_SHA = '6687d48f9c02323659093563b1f601a4425b406112992a8100457f79ed1977ec'
LEGACY_TU_SHA = 'd4e493bf1a6e57b2387795d3bf0fa6aee00691bf3809af8feea88dfe790bf72c'
LEGACY_REPORT = 'docs/validation/build34-r3-legacy-close-offline-20261121.json'
FIXTURE = 'tests/test_build34_exact_vm_detach.cpp'
OWNERSHIP = 'tools/build34_exact_ownership.h'
TOPOLOGY = 'src/amd/phx_topology.h'
HEADERS = (OWNERSHIP, 'src/phxbringup/PhxNativeABI.h', 'tools/build34_exact_submit_wire.h',
           'tools/build34_exact_receipt_wire.h', 'tools/build34_exact_fence32.h',
           'tools/build34_exact_callbacks.h', TOPOLOGY)
PRODUCTION = ('src', 'tools/phxctl', 'tools/build_kext.py')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, timeout=15).strip()


def test(out, legacy_fixture):
    out, legacy_fixture = out.resolve(), legacy_fixture.resolve()
    build = ROOT / 'build'
    if (out.exists() or build not in out.parents or not out.name.endswith('-private') or
            build not in legacy_fixture.parents or git('symbolic-ref', '--short', 'HEAD') != BRANCH):
        raise ValueError('Require default build34 and private build paths with a fresh output')
    for path in (out, legacy_fixture):
        subprocess.run(['git', 'check-ignore', '-q', str(path)], cwd=ROOT, check=True, timeout=15)
    protected = git('ls-files', *PRODUCTION).splitlines()
    if len(protected) != 172 or git('diff', '--name-only', BASE, '--', *PRODUCTION):
        raise ValueError('Production inputs drifted')
    frozen = {n: (ROOT / n).read_bytes() for n in (DRIVER, FIXTURE, LEGACY_REPORT, *HEADERS)}
    pinned = json.loads(frozen[LEGACY_REPORT])['input_sha256']
    legacy = legacy_fixture.read_bytes()
    if sha(legacy) != LEGACY_TU_SHA or any(sha(frozen[n]) != pinned[n] for n in (DRIVER, *HEADERS)):
        raise ValueError('Legacy test fixture or its build34 inputs drifted')

    original = frozen[DRIVER].decode()
    old, new = previous_stage(original), stage(original)
    # The latest stage and the legacy fixture must agree on the method under test.
    prefix, marker, _ = legacy.decode().partition('static unsigned registered(')
    if sha(old.encode()) != PREDECESSOR_SHA or not marker or method(old, FREE) != method(prefix, FREE):
        raise ValueError('Cannot reproduce vmidFree on the pinned close path')
    out.mkdir(mode=0o700)
    includes = out / 'include' / 'phxbringup'
    includes.mkdir(parents=True)
    (includes.parent / 'amd').mkdir()
    for name in HEADERS:
        blob = frozen[name]
        if name == OWNERSHIP:
            blob = stage_header(blob.decode()).encode()
        directory = includes.parent / 'amd' if name == TOPOLOGY else includes
        (directory / Path(name).name).write_bytes(blob)

    def run(label, args):
        p = subprocess.run(args, cwd=out, stdin=subprocess.DEVNULL, capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        return p

    def checked(label, args):
        p = run(label, args)
        if p.returncode or p.stderr:
            raise RuntimeError(label + ' failed; see private diagnostics')
        return p.stdout.decode()

    def exercise(label, code, sanitizer):
        target, binary = out / (label + '.cpp'), out / label
        target.write_text(once(prefix, method(old, FREE), method(code, FREE)) + frozen[FIXTURE].decode())
        checked(label + '-compile', ['/usr/bin/xcrun', 'clang++', '-std=c++17', '-O1', '-g',
                                     '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                                     '-Wno-unused-function', '-fno-sanitize-recover=all',
                                     '-fsanitize=' + sanitizer, '-I' + str(includes),
                                     str(target), '-o', str(binary)])
        linkage = checked(label + '-linkage', ['/usr/bin/otool', '-L', str(binary)])
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', linkage, re.I):
            raise ValueError('Device runtime linked into CPU fixture')
        return run(label, [str(binary)])

    before = exercise('before', old, 'address,undefined')
    if (before.returncode != 86 or before.stdout or
            not re.fullmatch(rb'failed \d+: lineFlushes == flushed \+ 17 \* 64\n', before.stderr)):
        raise ValueError('The preceding CPU stage did not fail at the expected ordering assertion')
    counts = []
    for label, sanitizer in [('asan-ubsan', 'address,undefined'), ('tsan', 'thread')]:
        result = exercise(label, new, sanitizer)
        match = re.fullmatch(rb'PASS (\d+) checks; GPU_executed=false\n', result.stdout)
        if result.returncode or result.stderr or not match:
            raise RuntimeError(label + ' failed; see private diagnostics')
        counts.append(int(match[1]))
    if (counts[0] != counts[1] or legacy_fixture.read_bytes() != legacy or
            any((ROOT / n).read_bytes() != b for n, b in frozen.items()) or
            git('diff', '--name-only', BASE, '--', *PRODUCTION)):
        raise ValueError('Changed inputs or inconsistent CPU results')
    print(json.dumps(dict(before_failed_at_clear_order=True, checks_per_sanitizer=counts[0],
                          legacy_fixture_sha256=LEGACY_TU_SHA, predecessor_sha256=sha(old.encode()),
                          staged_sha256=sha(new.encode()), production_inputs_unchanged=len(protected),
                          installed=False, GPU_executed=False, R3_complete=False), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--legacy-fixture', required=True, type=Path)
    args = parser.parse_args()
    test(args.out, args.legacy_fixture)
