# SPDX-License-Identifier: MIT
"""Test the staged IOKit adapter using CPU doubles and KDK-checked objects."""

import argparse
import json
from pathlib import Path
import re
import subprocess

from build34_exact_event_iokit import (COUNTED_PARK, DECLARATIONS, FIELDS_AT, IOKIT_METHODS,
                                     LIMIT, PARK_CALL, SLEEP, WAKE, previous_stage, stage, stage_header)
from build34_exact_event_wait import AVAILABLE, ENTRY, FIELDS, INVALIDATE, NOTIFY, PARK, SNAPSHOT, WAIT
from build34_exact_submit import once
from build34_kpi_symbolset import interface_exports
from build34_native_object_check import check as native_check
from test_build34_exact_claim_lifecycle import FACTORY, REFERENCE, git, xcrun
from test_build34_exact_ownership import DRIVER, ROOT, method, sha


BASE = '251b0c44f925beb652ca0898baabb41d34a85733'
PRIOR = 'docs/validation/build34-r3-event-wait-offline-20261121.json'
PRIOR_FIXTURE = 'tests/test_build34_exact_event_wait.cpp'
FIXTURE = 'tests/test_build34_exact_event_iokit.cpp'
HEADER = 'tools/build34_exact_ownership.h'
GATES = 'tools/build34_exact_callbacks.h'
NEW_KPIS = {
    'IOKit': {'_IOLockSleepDeadline_darwin14', '_IOLockWakeup_darwin14'},
    'Mach': {'_nanoseconds_to_absolutetime'},
}
DOUBLES = '''static constexpr unsigned THREAD_ABORTSAFE = 2;
static thread_local uint64_t nsPerTick = 1;
static void nanoseconds_to_absolutetime(uint64_t ns, uint64_t *ticks) { *ticks = ns / nsPerTick; }
static int IOLockSleepDeadline(IOLock *p, void *key, uint64_t deadline, unsigned kind) {
    CHECK(kind == THREAD_ABORTSAFE && deadline > now);
    sleepEvent(p, key, now, deadline - now);
    return 2; // return value alone must never prove completion
}
static void IOLockWakeup(IOLock *p, void *key, bool one) {
    CHECK(!one);
    wakeEvent(p, key);
}
'''


def test(out, sdk, kdk):
    out = out.resolve()
    if (out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private') or
            git('symbolic-ref', '--short', 'HEAD').strip() != 'upstream34/vram-layout-fix'):
        raise ValueError('Use default build34 and a fresh private output')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    protected = git('ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py').splitlines()
    if len(protected) != 172 or git('diff', '--name-only', BASE, '--', 'src', 'tools/phxctl', 'tools/build_kext.py'):
        raise ValueError('Production inputs drifted')
    reference, factory, prior = (json.loads((ROOT / n).read_bytes()) for n in (REFERENCE, FACTORY, PRIOR))
    frozen = {n: (ROOT / n).read_bytes() for n in set(protected) | set(factory['input_sha256']) |
              {FACTORY, REFERENCE, PRIOR, PRIOR_FIXTURE, FIXTURE}}
    if any(sha(frozen[n]) != digest for n, digest in factory['input_sha256'].items()):
        raise ValueError('Earlier inputs drifted')
    old, new = (fn(frozen[DRIVER].decode()) for fn in (previous_stage, stage))
    header = stage_header(frozen[HEADER].decode())
    reverted = once(once(once(once(new, IOKIT_METHODS, ''), DECLARATIONS, ''), LIMIT, ''), COUNTED_PARK, PARK_CALL)
    if (reverted != old or sha(old.encode()) != prior['staged_sha256'] or
            sha(header.encode()) != factory['staged_header_sha256']):
        raise ValueError('Staged driver drifted outside the event adapter')
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
        base = once(frozen[PRIOR_FIXTURE].decode(), 'int main() {', 'static void priorWaitTests() {')
        fields = ENTRY + once(FIELDS, FIELDS_AT, DECLARATIONS + FIELDS_AT)
        base = once(base, '    // PHX34_EVENT_FIELDS\n', fields)
        base = once(base, '// PHX34_EVENT_METHODS', DOUBLES + '\n'.join(method(text, s) for s in
                    (AVAILABLE, SLEEP, WAKE, SNAPSHOT, PARK, NOTIFY, INVALIDATE, WAIT)))
        source, binary = out / (label + '.cpp'), out / label
        source.write_text(base + '\n' + frozen[FIXTURE].decode())
        p = run(label + '-compile', [compiler, '--driver-mode=g++', '-std=c++17', '-isysroot', host_sdk, '-O1', '-g',
                '-Wall', '-Wextra', '-Werror', '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all', source, '-o', binary])
        if p.returncode:
            raise RuntimeError(label + ' compile failed; see private diagnostics')
        links = run(label + '-links', [otool, '-L', binary])
        if links.returncode or any(re.search(rb'IOKit|Metal|vulkan', line, re.I) for line in links.stdout.splitlines()[1:]):
            raise ValueError('Device library linked into CPU fixture')
        p = run(label, [binary])
        if broken and p.returncode == 86 and p.stderr.startswith(b'failed '):
            return 0
        count = re.fullmatch(rb'PASS 481 exact event-wait checks\nPASS (\d+) IOKit event-wait checks\n', p.stdout)
        if broken or not count or p.returncode or p.stderr:
            raise RuntimeError(label + ' failed; see private diagnostics')
        return int(count[1])

    asan = exercise('asan', new)
    tsan = exercise('tsan', new, 'thread')
    if asan != tsan:
        raise ValueError('Incomplete IOKit CPU cases')
    mutations = {
        'extend-budget-at-enrollment': ('sampledAt + ticks;', 'mach_absolute_time() + ticks;'),
        'sleep-at-expiry': ('mach_absolute_time() >= deadline', 'mach_absolute_time() > deadline'),
        'one-waiter-only': ('IOLockWakeup(lock, key, false)', 'IOLockWakeup(lock, key, true)'),
        'miss-enrollment-limit': ('exactEventSleepers >= kExactEventSleepers', 'exactEventSleepers > kExactEventSleepers'),
    }
    for label, pair in mutations.items():
        exercise(label, once(new, *pair), broken=True)

    # The immutable historical checker requires equal import sets. Use it to
    # authenticate both closures separately, then independently check the delta.
    added = set().union(*NEW_KPIS.values())
    count = prior['native_import_count']
    for label, text, imports in [('control', old, count), ('adapter', new, count + len(added))]:
        native_check(out / label, frozen, text, text, header, sdk, kdk, imports,
                     reference['compiler_warnings']['public'], reference, compiler)
    control, adapter = (set((out / n / 'proposed-imports.stdout').read_text().splitlines()) for n in ('control', 'adapter'))
    if adapter - control != added or control - adapter:
        raise ValueError('Unexpected native import delta')
    for provider, expected in NEW_KPIS.items():
        path = 'System/Library/Extensions/System.kext/PlugIns/' + provider + '.kext/' + provider
        if expected - interface_exports((out / 'adapter/kdk' / path).read_bytes()).keys():
            raise ValueError('Public KPI provider mismatch')
    if any((ROOT / n).read_bytes() != blob for n, blob in frozen.items()):
        raise ValueError('Input changed during verification')
    print(json.dumps(dict(status='passed-staged-event-iokit-offline', build=34, base_commit=BASE,
                          staged_sha256=sha(new.encode()), inherited_checks=481, new_checks_per_sanitizer=asan,
                          broken_variants_detected=list(mutations), production_inputs_unchanged=len(protected),
                          native_import_count=[len(control), len(adapter)], added_KPIs={k: sorted(v) for k, v in NEW_KPIS.items()},
                          native_object_only=True, native_event_backend_bound=False, GPU_executed=False, R3_complete=False), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('out', 'sdk', 'kdk'):
        parser.add_argument('--' + flag, type=Path, required=True)
    args = parser.parse_args()
    test(args.out, args.sdk, args.kdk)
