"""Run actual build34 table-chunk and software walker methods against CPU doubles."""

import argparse
import json
from pathlib import Path
import re
import subprocess

from build34_exact_submit import once
from build34_exact_vm_chunk import ALLOC, previous_stage, stage
from test_build34_exact_ownership import DRIVER, PINNED, ROOT, method, sha


BASE = '16940c9c210c102266f1d475312531f752c21775'
PRIOR = 'docs/validation/build34-r3-vm-detach-offline-20261122.json'
FIXTURE = 'tests/test_build34_exact_vm_chunk.cpp'
PRODUCTION = ('src', 'tools/phxctl', 'tools/build_kext.py')
SIGNATURES = ('uint64_t *PhxBringup::ptTable(', ALLOC, 'uint64_t *PhxBringup::vmPte(')
BAD = ('missing-map', 'short-descriptor', 'short-segment', 'zero-base',
       'misaligned', 'above-mask', 'crosses-mask')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, timeout=15).strip()


def test(out):
    out = out.resolve()
    if (out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private') or
            git('symbolic-ref', '--short', 'HEAD') != 'upstream34/vram-layout-fix'):
        raise ValueError('Require default build34 and a fresh private output')
    subprocess.run(['git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    protected = git('ls-files', *PRODUCTION).splitlines()
    if len(protected) != 172 or git('diff', '--name-only', BASE, '--', *PRODUCTION):
        raise ValueError('Production inputs drifted')
    frozen = {name: (ROOT / name).read_bytes() for name in (DRIVER, FIXTURE, PRIOR)}
    original = frozen[DRIVER].decode()
    old, new = previous_stage(original), stage(original)
    if (sha(frozen[DRIVER]) != PINNED[DRIVER] or '#define PHX_KEXT_BUILD 34u\n' not in original or
            sha(old.encode()) != json.loads(frozen[PRIOR])['staged_sha256'] or
            once(new, method(new, ALLOC), method(old, ALLOC)) != old):
        raise ValueError('Unexpected predecessor or change outside the staged table allocator')

    fields = old[old.index('    static constexpr uint32_t kPtChunkBytes ='):
                 old.index('    static constexpr uint32_t kMaxCtx =')]
    masks = re.findall(r'^static constexpr uint64_t kPtAddrMask = [^\n]+;', original, re.M)
    if len(masks) != 1:
        raise ValueError('Unexpected frame address mask')
    fixture = once(frozen[FIXTURE].decode(), '// PT_MASK', masks[0])
    fixture = once(fixture, '    // PT_FIELDS\n', fields)
    out.mkdir(mode=0o700)

    def run(label, args):
        result = subprocess.run(args, cwd=out, stdin=subprocess.DEVNULL, capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_bytes(result.stdout)
        (out / (label + '.stderr')).write_bytes(result.stderr)
        return result

    def checked(label, args):
        result = run(label, args)
        if result.returncode or result.stderr:
            raise RuntimeError(label + ' failed; see private diagnostics')
        return result.stdout

    def build(label, source, sanitizer):
        target, binary = out / (label + '.cpp'), out / label
        target.write_text(once(fixture, '// PT_METHODS', '\n'.join(method(source, s) for s in SIGNATURES)))
        checked(label + '-build', ['/usr/bin/xcrun', 'clang++', '-std=c++17', '-O1', '-g',
                                   '-Wall', '-Wextra', '-Werror', '-fno-sanitize-recover=all',
                                   '-fsanitize=' + sanitizer, str(target), '-o', str(binary)])
        linkage = checked(label + '-linkage', ['/usr/bin/otool', '-L', str(binary)])
        if re.search(rb'IOKit|Metal|vulkan|PhxAccel', linkage, re.I):
            raise ValueError('Device runtime linked into CPU fixture')
        return binary

    def passes(binary, scenario):
        result = checked(binary.name + '-' + scenario, [str(binary), scenario])
        match = re.fullmatch(rb'PASS (\d+) checks; GPU_executed=false\n', result)
        if not match or int(match[1]) <= 0:
            raise RuntimeError('Unexpected CPU fixture result: ' + scenario)
        return int(match[1])

    control = build('before', old, 'address,undefined')
    for scenario in ('accepted', 'allocation-failed'):
        passes(control, scenario)
    for scenario in BAD:
        result = run('before-' + scenario, [str(control), scenario])
        assertion = ('memory && length == chunkBytes && next && next->words.data() == memory'
                     if scenario == 'missing-map'
                     else 'service.ptTablePhys(context, PhxBringup::kPtChunkPages + 1) == 0')
        if result.returncode != 86 or result.stdout or result.stderr != f'failed: {assertion}\n'.encode():
            raise ValueError('Expected before-stage counterexample not observed: ' + scenario)

    counts = []
    for label, sanitizer in (('asan-ubsan', 'address,undefined'), ('tsan', 'thread')):
        binary = build(label, new, sanitizer)
        counts.append(sum(passes(binary, scenario) for scenario in ('accepted', 'allocation-failed', *BAD)))
    if (counts[0] != counts[1] or git('diff', '--name-only', BASE, '--', *PRODUCTION) or
            any((ROOT / name).read_bytes() != blob for name, blob in frozen.items())):
        raise ValueError('Changed inputs or inconsistent CPU results')
    print(json.dumps(dict(status='passed-staged-vm-chunk-CPU-only', checks_per_sanitizer=counts[0],
                          predecessor_sha256=sha(old.encode()), staged_sha256=sha(new.encode()),
                          before_expected_failures=list(BAD), scenarios=len(BAD) + 2,
                          production_inputs_unchanged=len(protected),
                          installed=False, GPU_executed=False, R3_complete=False), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    test(parser.parse_args().out)
