# SPDX-License-Identifier: MIT
"""Verify staged exact event hints with CPU threads and nonloadable objects."""

import argparse
import json
from pathlib import Path
import re
import subprocess

from build34_exact_event_wait import (AVAILABLE, ENTRY, FIELDS, INVALIDATE, METHODS, NOTIFY, PARK,
                                      SNAPSHOT, WAIT, WAKE_INVALIDATED, previous_stage, stage, stage_header)
from build34_exact_submit import once
from build34_native_object_check import check as native_check
from test_build34_exact_claim_lifecycle import FACTORY, REFERENCE, git, xcrun
from test_build34_exact_ownership import DRIVER, ROOT, method, sha


BASE = '0a784faf65bc8fe23946960c38deb126aade4c3e'
BASE_STAGED_SHA = 'b92f57f2c22ce440692880f7b353fa8ed195f3d4e83ce0bd5c878ca2ae2b57af'
FIXTURE = 'tests/test_build34_exact_event_wait.cpp'
HEADER = 'tools/build34_exact_ownership.h'
GATES = 'tools/build34_exact_callbacks.h'


def test(out, sdk, kdk):
    out = out.resolve()
    if (out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private') or
            git('symbolic-ref', '--short', 'HEAD').strip() != 'upstream34/vram-layout-fix'):
        raise ValueError('Require default build34 and a fresh private output')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    protected = git('ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py').splitlines()
    if len(protected) != 172 or git('diff', '--name-only', BASE, '--', 'src', 'tools/phxctl', 'tools/build_kext.py'):
        raise ValueError('Production inputs drifted')
    reference, factory = (json.loads((ROOT / n).read_bytes()) for n in (REFERENCE, FACTORY))
    frozen = {n: (ROOT / n).read_bytes() for n in set(protected) | set(factory['input_sha256']) | {FACTORY, REFERENCE, FIXTURE}}
    if any(sha(frozen[n]) != digest for n, digest in factory['input_sha256'].items()):
        raise ValueError('Frozen factory inputs drifted')
    old, new = (fn(frozen[DRIVER].decode()) for fn in (previous_stage, stage))
    header = stage_header(frozen[HEADER].decode())
    back = once(once(once(once(new, ENTRY, ''), FIELDS, ''), METHODS, ''), WAKE_INVALIDATED, '')
    if (sha(old.encode()) != BASE_STAGED_SHA or once(back, method(new, WAIT), method(old, WAIT)) != old or
            sha(header.encode()) != factory['staged_header_sha256']):
        raise ValueError('Staged change exceeded the exact wait and invalidation path')
    out.mkdir(mode=0o700)
    compiler, host_sdk, otool = [xcrun(*args) for args in (('--find', 'clang++'), ('--show-sdk-path',), ('--find', 'otool'))]
    (out / Path(HEADER).name).write_text(header)
    (out / Path(GATES).name).write_bytes(frozen[GATES])

    def run(label, args):
        p = subprocess.run([str(a) for a in args], cwd=out, stdin=subprocess.DEVNULL, capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        return p

    def exercise(label, text, sanitizer='address,undefined', broken=False):
        fixture = once(frozen[FIXTURE].decode(), '    // PHX34_EVENT_FIELDS\n', ENTRY + FIELDS)
        fixture = once(fixture, '// PHX34_EVENT_METHODS', '\n'.join(
            method(text, sig) for sig in (AVAILABLE, SNAPSHOT, PARK, NOTIFY, INVALIDATE, WAIT)))
        source, binary = out / (label + '.cpp'), out / label
        source.write_text(fixture)
        p = run(label + '-compile', [compiler, '--driver-mode=g++', '-std=c++17', '-isysroot', host_sdk, '-O1', '-g',
                '-Wall', '-Wextra', '-Werror', '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all', source, '-o', binary])
        if p.returncode:
            raise RuntimeError(label + ' compile failed; see private diagnostics')
        links = run(label + '-links', [otool, '-L', binary])
        if links.returncode or re.search(rb'IOKit|Metal|vulkan', links.stdout, re.I):
            raise ValueError('Unexpected CPU fixture linkage')
        result = run(label, [binary])
        if broken and result.returncode == 86 and result.stderr.startswith(b'failed '):
            return 0
        count = re.fullmatch(rb'PASS (\d+) exact event-wait checks\n', result.stdout)
        if broken or not count or result.returncode or result.stderr:
            raise ValueError(label + ' produced unexpected test result; see private diagnostics')
        return int(count[1])

    asan = exercise('asan', new)
    tsan = exercise('tsan', new, 'thread')
    mutations = {
        'lost-wake': ('        exactEventSerial[receipt.queue] == stamp) {',
                      '        stamp != UINT64_MAX) {'),
        'stale-generation': ('           exactQueueGeneration[queue] == generation && exactEventSerial[queue] != UINT64_MAX;',
                             '           generation != 0 && exactEventSerial[queue] != UINT64_MAX;'),
        'ignore-invalidation': (WAKE_INVALIDATED, ''),
        'no-spurious-backoff': ('retryEvent = exactEventSerial[receipt.queue] != stamp || parked >= slice;',
                                'retryEvent = true;'),
        'ignore-earlier-wait-time': ('const uint64_t remaining = timeout - elapsed;', 'const uint64_t remaining = timeout;'),
    }
    for label, pair in mutations.items():
        exercise(label, once(new, *pair), broken=True)
    native = native_check(out / 'native', frozen, old, new, header, sdk, kdk, 377,
                          reference['compiler_warnings']['public'], reference, compiler)
    if any((ROOT / n).read_bytes() != blob for n, blob in frozen.items()):
        raise ValueError('Input changed during verification')
    print(json.dumps(dict(status='passed-staged-event-wait-offline', PhxBringup_build=34, predecessor_commit=BASE,
                          production_inputs_unchanged=len(protected), predecessor_sha256=sha(old.encode()),
                          staged_sha256=sha(new.encode()), ASan_UBSan_checks=asan, TSan_checks=tsan,
                          broken_variants_detected=list(mutations), **native, native_event_backend_bound=False,
                          GPU_executed=False, installed=False, R3_complete=False), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('out', 'sdk', 'kdk'):
        parser.add_argument('--' + flag, type=Path, required=True)
    args = parser.parse_args()
    test(args.out, args.sdk, args.kdk)
