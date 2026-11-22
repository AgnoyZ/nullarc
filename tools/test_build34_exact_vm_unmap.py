"""Check actual unmap and BO cleanup with a software walker and CPU doubles."""

import argparse
import json
from pathlib import Path
import re
import subprocess

from build34_exact_submit import once
from build34_exact_vm_chunk import ALLOC
from build34_exact_vm_unmap import (
    CHECKED_DECLARATION, DECLARATION, TABLE, UNMAP, WALK, previous_stage, stage,
)
from test_build34_exact_ownership import DRIVER, ROOT, method, sha
from test_build34_exact_vm_detach import (
    BRANCH, FREE, HEADERS, LEGACY_REPORT, LEGACY_TU_SHA, OWNERSHIP, PRODUCTION,
    TOPOLOGY, git, stage_header,
)


BASE = 'd65fcd35d893d636e908c7dd6eecc3360afbce5c'
PRIOR = 'docs/validation/build34-r3-vm-chunk-offline-20261122.json'
FIXTURE = 'tests/test_build34_exact_vm_unmap.cpp'
PASS_CASES = ('no-context', 'empty-branch', 'resident')
FAIL_CASES = ('missing-chunk', 'missing-view')
BUFFER_DOUBLE = '''static constexpr unsigned kIODirectionInOut = 1, kIOMemoryPhysicallyContiguous = 2;
static constexpr unsigned kernel_task = 7;
struct IOBufferMemoryDescriptor {
    std::vector<uint64_t> words = std::vector<uint64_t>(8192, UINT64_MAX);
    uint64_t base = 0;
    bool mapped = true;
    void *getBytesNoCopy() { CHECK(gpuHeld == 1); return mapped ? words.data() : nullptr; }
    IOByteCount getLength() const { return words.size() * sizeof(uint64_t); }
    uint64_t getPhysicalSegment(IOByteCount offset, IOByteCount *length) const {
        CHECK(gpuHeld == 1 && !offset && length);
        *length = getLength();
        return base;
    }
    void release() { CHECK(false); }
    static IOBufferMemoryDescriptor *inTaskWithPhysicalMask(unsigned, unsigned, IOByteCount, uint64_t);
};
static std::vector<std::unique_ptr<IOBufferMemoryDescriptor>> tableStorage;
IOBufferMemoryDescriptor *IOBufferMemoryDescriptor::inTaskWithPhysicalMask(
        unsigned task, unsigned options, IOByteCount size, uint64_t mask) {
    CHECK(gpuHeld == 1 && task == kernel_task && options == (kIODirectionInOut | kIOMemoryPhysicallyContiguous));
    CHECK(size == 65536 && mask == kPtAddrMask);
    tableStorage.emplace_back(new IOBufferMemoryDescriptor);
    auto *descriptor = tableStorage.back().get();
    descriptor->base = 0x100000000ull + tableStorage.size() * size;
    return descriptor;
}
'''


def test(out, legacy_fixture):
    out, legacy_fixture = out.resolve(), legacy_fixture.resolve()
    build = ROOT / 'build'
    if (out.exists() or build not in out.parents or not out.name.endswith('-private') or
            build not in legacy_fixture.parents or git('symbolic-ref', '--short', 'HEAD') != BRANCH):
        raise ValueError('Require default build34 and ignored, private fixture and output paths')
    for path in (out, legacy_fixture):
        subprocess.run(['git', 'check-ignore', '-q', str(path)], cwd=ROOT, check=True, timeout=15)
    protected = git('ls-files', *PRODUCTION).splitlines()
    if len(protected) != 172 or git('diff', '--name-only', BASE, '--', *PRODUCTION):
        raise ValueError('Production inputs drifted')
    frozen = {n: (ROOT / n).read_bytes() for n in (DRIVER, PRIOR, FIXTURE, LEGACY_REPORT, *HEADERS)}
    pinned = json.loads(frozen[LEGACY_REPORT])['input_sha256']
    legacy = legacy_fixture.read_bytes()
    if sha(legacy) != LEGACY_TU_SHA or any(sha(frozen[n]) != pinned[n] for n in (DRIVER, *HEADERS)):
        raise ValueError('Legacy fixture or pinned driver/header drift')
    original = frozen[DRIVER].decode()
    before, after = previous_stage(original), stage(original)
    unchanged = once(after, CHECKED_DECLARATION, DECLARATION)
    for signature in (TABLE, WALK, UNMAP):
        unchanged = once(unchanged, method(after, signature), method(before, signature))
    if (unchanged != before or '#define PHX_KEXT_BUILD 34u\n' not in original or
            sha(before.encode()) != json.loads(frozen[PRIOR])['staged_sha256']):
        raise ValueError('Unexpected predecessor or change outside the checked software walk')

    prefix, marker, _ = legacy.decode().partition('static unsigned registered(')
    if not marker or any(method(prefix, signature) != method(before, signature) for signature in (
            UNMAP, 'IOReturn PhxBringup::vmMap(', 'IOReturn PhxBringup::vmBoSnapshot(',
            'IOReturn IOAccelPhxNativeClient::doBoFree(', 'IOReturn IOAccelPhxNativeClient::doGemVa(')):
        raise ValueError('Actual legacy CPU caller or VM method drift')
    buffer_start = prefix.index('struct IOBufferMemoryDescriptor {')
    prefix = once(prefix, prefix[buffer_start:prefix.index('struct Memory {', buffer_start)], BUFFER_DOUBLE)
    walker_start = prefix.index('    uint64_t ptTablePhys(VmCtx &c,uint32_t i) {')
    prefix = once(prefix, prefix[walker_start:prefix.index('    void wreg(', walker_start)],
                  '    uint64_t ptTablePhys(VmCtx &c, uint32_t index);\n'
                  '    uint64_t *ptTable(const VmCtx &c, uint64_t phys) const;\n'
                  '    // WALK_DECLARATION\n')
    prefix = once(prefix, method(prefix, FREE), method(before, FREE))
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
        result = subprocess.run(args, cwd=out, stdin=subprocess.DEVNULL, capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_bytes(result.stdout)
        (out / (label + '.stderr')).write_bytes(result.stderr)
        return result

    def checked(label, args):
        result = run(label, args)
        if result.returncode or result.stderr:
            raise RuntimeError(label + ' failed; see private diagnostics')
        return result.stdout

    def build_cpu(label, code, declaration, sanitizer):
        target, binary = out / (label + '.cpp'), out / label
        fixture = once(prefix, '    // WALK_DECLARATION', declaration)
        fixture = once(fixture, method(before, UNMAP), method(code, UNMAP))
        fixture += '\n'.join(method(code, signature) for signature in (TABLE, ALLOC, WALK))
        target.write_text(fixture + frozen[FIXTURE].decode())
        checked(label + '-compile', ['/usr/bin/xcrun', 'clang++', '-std=c++17', '-O1', '-g',
                                     '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-unused-function',
                                     '-fno-sanitize-recover=all', '-fsanitize=' + sanitizer,
                                     '-I' + str(includes), str(target), '-o', str(binary)])
        linkage = checked(label + '-linkage', ['/usr/bin/otool', '-L', str(binary)])
        if re.search(rb'IOKit|Metal|vulkan|PhxAccel', linkage, re.I):
            raise ValueError('Device runtime linked into CPU fixture')
        return binary

    def pass_case(binary, scenario):
        result = checked(binary.name + '-' + scenario, [str(binary), scenario])
        match = re.fullmatch(rb'PASS (\d+) checks; GPU_executed=false\n', result)
        if not match or int(match[1]) <= 0:
            raise ValueError('Unexpected CPU result: ' + scenario)
        return int(match[1])

    control = build_cpu('before', before, DECLARATION, 'address,undefined')
    for scenario in PASS_CASES:
        pass_case(control, scenario)
    for scenario in FAIL_CASES:
        counterexample = run('before-' + scenario, [str(control), scenario])
        expected = rb'failed \d+: !falseSuccess\n'
        if counterexample.returncode != 86 or counterexample.stdout or not re.fullmatch(expected, counterexample.stderr):
            raise ValueError('Expected before-stage false success not reproduced: ' + scenario)

    counts = []
    for label, sanitizer in (('asan-ubsan', 'address,undefined'), ('tsan', 'thread')):
        binary = build_cpu(label, after, CHECKED_DECLARATION, sanitizer)
        counts.append(sum(pass_case(binary, scenario) for scenario in (*PASS_CASES, *FAIL_CASES)))
    if (counts[0] != counts[1] or legacy_fixture.read_bytes() != legacy or
            any((ROOT / name).read_bytes() != blob for name, blob in frozen.items()) or
            git('diff', '--name-only', BASE, '--', *PRODUCTION)):
        raise ValueError('Changed inputs or inconsistent CPU results')
    print(json.dumps(dict(status='passed-staged-vm-unmap-CPU-only', checks_per_sanitizer=counts[0],
                          legacy_fixture_sha256=LEGACY_TU_SHA, predecessor_sha256=sha(before.encode()),
                          staged_sha256=sha(after.encode()), scenarios=len(PASS_CASES) + len(FAIL_CASES),
                          before_false_successes=list(FAIL_CASES), production_inputs_unchanged=len(protected),
                          installed=False, GPU_executed=False, R3_complete=False), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--legacy-fixture', required=True, type=Path)
    args = parser.parse_args()
    test(args.out, args.legacy_fixture)
