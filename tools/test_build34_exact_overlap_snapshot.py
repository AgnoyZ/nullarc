# SPDX-License-Identifier: MIT
"""Exercise the staged R3 snapshot and feed its CPU observations to the checker."""

import argparse
import json
from pathlib import Path
import re
import subprocess

from build34_exact_overlap_snapshot import COLLECT, DECLARATIONS, GLOBAL, previous_stage, stage
from build34_exact_submit import once
from build34_r3_wait_overlap import check
from test_build34_exact_ownership import DRIVER, ROOT, method, sha


BASE = '7ff2b2328dc0d5a9bf890efefe6be081366e23e1'
PRIOR = 'docs/validation/build34-r3-event-iokit-offline-20261121.json'
FIXTURE = 'tests/test_build34_exact_overlap_snapshot.cpp'
HEADERS = ('tools/build34_exact_callbacks.h', 'tools/build34_exact_fence32.h')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, timeout=15).strip()


def check_records(output):
    before, witness, after, drained, count = output.splitlines()

    def sample(line):
        epoch, begin, end, c_gen, c_last, c_done, g_gen, g_last, g_done, retired = map(int, line.split())
        return dict(service_epoch=epoch, begin_ns=begin, end_ns=end, retired=retired,
                    compute=dict(generation=c_gen, submitted=c_last, completed=c_done),
                    gfx=dict(generation=g_gen, submitted=g_last, completed=g_done))

    # Wait times and receipts are fixture inputs. Only the four snapshots come from the staged code.
    compute = dict(owner=4, serial=1, slot=0, sequence=100, queue=0, generation=2)
    gfx = dict(owner=5, serial=1, slot=0, sequence=101, queue=1, generation=3)
    wait = dict(service_epoch=7, begin_ns=20, end_ns=30, reply=gfx, status=0)
    result = check(compute, gfx, wait, *map(sample, (before, witness, after, drained)))
    if result != {'status': 'consistent-r3-wait-overlap-records', 'hardware_attested': False} or int(count) <= 0:
        raise ValueError('Unexpected CPU observation verdict')
    return int(count)


def test(out):
    out = out.resolve()
    if (out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private') or
            git('symbolic-ref', '--short', 'HEAD') != 'upstream34/vram-layout-fix'):
        raise ValueError('Require default build34 and a fresh private output')
    subprocess.run(['git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    scopes = ('src', 'tools/phxctl', 'tools/build_kext.py')
    protected = git('ls-files', *scopes).splitlines()
    if len(protected) != 172 or git('diff', '--name-only', BASE, '--', *scopes):
        raise ValueError('Production inputs drifted')
    frozen = {n: (ROOT / n).read_bytes() for n in (*protected, *HEADERS, FIXTURE, PRIOR)}
    prior = json.loads(frozen[PRIOR])
    original = frozen[DRIVER].decode()
    old, new = previous_stage(original), stage(original)
    if (prior['GPU_executed'] or sha(old.encode()) != prior['staged_sha256'] or
            any(frozen[n] != subprocess.check_output(['git', 'show', f'{BASE}:{n}'], cwd=ROOT, timeout=15)
                for n in (*HEADERS, PRIOR))):
        raise ValueError('Unexpected staged predecessor or fixture header drift')

    out.mkdir(mode=0o700)
    for name in HEADERS:
        (out / Path(name).name).write_bytes(frozen[name])
    fixture = once(frozen[FIXTURE].decode(), '    // PHX34_OVERLAP_FIELDS\n', DECLARATIONS)
    bodies = (COLLECT, GLOBAL, 'bool PhxBringup::readExactFence32(', 'bool PhxBringup::vmWorkCurrent(')
    source = out / 'snapshot-CPU-only.cpp'
    source.write_text(once(fixture, '// PHX34_OVERLAP_METHODS', '\n'.join(method(new, s) for s in bodies)))

    def run(label, args):
        p = subprocess.run(args, cwd=out, stdin=subprocess.DEVNULL, capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        if p.returncode or p.stderr:
            raise RuntimeError(label + ' failed; see private diagnostics')
        return p.stdout.decode()

    counts = []
    for label, sanitizer in (('asan-ubsan', 'address,undefined'), ('tsan', 'thread')):
        binary = out / label
        run(label + '-build', ['xcrun', 'clang++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                               '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all', str(source), '-o', str(binary)])
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', run(label + '-linkage', ['xcrun', 'otool', '-L', str(binary)]), re.I):
            raise ValueError('Device library linked into CPU fixture')
        counts.append(check_records(run(label, [str(binary)])))
    if counts[0] != counts[1] or any((ROOT / n).read_bytes() != blob for n, blob in frozen.items()):
        raise ValueError('Mismatched CPU results or input drift')
    print(json.dumps(dict(status='passed-staged-overlap-snapshot-CPU-only', build=34,
                          staged_sha256=sha(new.encode()), predecessor_sha256=sha(old.encode()),
                          checks_per_sanitizer=counts[0], production_inputs_unchanged=len(protected),
                          synthetic_snapshots_pass_overlap_check=True, native_reader_bound=False,
                          installed=False, GPU_executed=False, R3_complete=False), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    test(parser.parse_args().out)
