"""Exercise staged native-submit mapping admission with frozen CPU doubles."""

import argparse
import json
from pathlib import Path
import re
import subprocess

from build34_exact_cpu_fences import FIELDS
from build34_exact_submit import once
from build34_exact_vm_ready import (
    COVERED, DECL, DECL_READY, GEM, LEGACY, MAP, MAP_READY, READY, TYPED,
    previous_stage, stage,
)
from test_build34_exact_ownership import DRIVER, ROOT, method, sha
from test_build34_exact_vm_detach import (
    BRANCH, HEADERS, LEGACY_REPORT, OWNERSHIP, PRODUCTION, TOPOLOGY, git,
    stage_header,
)
from test_build34_exact_vm_unmap import BUFFER_DOUBLE


BASE = 'fbc4e7cd3c9ab940c553e6c1bb25321cb53bb9c6'
PRIOR = 'docs/validation/build34-r3-vm-unmap-offline-20261122.json'
FIXTURE = 'tests/test_build34_exact_vm_ready.cpp'
CPU_FIXTURE = 'build/build34-r3-vm-unmap-second-20261122-private/asan-ubsan.cpp'
CPU_SHA = 'fae1dcbd93471145eb79b3db0e811491c9be078b779c4ac232e1b6fece486087'
CASES = ('resident', 'typed-resident', 'mock', 'logical-executable',
         'typed-logical-executable', 'logical-data', 'typed-logical-data')
PASS_CASES = ('resident', 'typed-resident', 'mock')
REFUSALS = ('logical-executable', 'typed-logical-executable', 'logical-data', 'typed-logical-data')
PUBLISH = 'bool IOAccelPhxNativeClient::publishCpuFence('
FENCE_METHODS = ('bool IOAccelPhxNativeClient::checkCpuFences(',
                 'bool IOAccelPhxNativeClient::appendCpuFence(',
                 'IOReturn IOAccelPhxNativeClient::prepareCpuFence(')
LOGICAL_DECLARATION = '    bool ibCovered(uint64_t,uint64_t) { CHECK(clientHeld); return true; }\n'
VM_METHODS = ('uint64_t *PhxBringup::ptTable(', 'uint64_t PhxBringup::ptTablePhys(',
              'uint64_t *PhxBringup::vmPte(')
READY_METHODS = ('bool IOAccelPhxNativeClient::nativeMappingsReady(', 'bool IOAccelPhxNativeClient::ibCovered(')


def test(out):
    out = out.resolve()
    build = ROOT / 'build'
    cpu_path = ROOT / CPU_FIXTURE
    if (out.exists() or build not in out.parents or not out.name.endswith('-private') or
            git('symbolic-ref', '--short', 'HEAD') != BRANCH):
        raise ValueError('Require default build34 and a fresh ignored private output')
    for path in (out, cpu_path):
        subprocess.run(['git', 'check-ignore', '-q', str(path)], cwd=ROOT, check=True, timeout=15)
    if not cpu_path.exists():
        raise ValueError('Require the previously generated unmap CPU fixture')
    protected = git('ls-files', *PRODUCTION).splitlines()
    if len(protected) != 172 or git('diff', '--name-only', BASE, '--', *PRODUCTION):
        raise ValueError('Production inputs drifted')
    frozen = {name: (ROOT / name).read_bytes() for name in (DRIVER, FIXTURE, PRIOR, LEGACY_REPORT, *HEADERS)}
    pinned = json.loads(frozen[LEGACY_REPORT])['input_sha256']
    cpu = cpu_path.read_bytes()
    if sha(cpu) != CPU_SHA or any(sha(frozen[name]) != pinned[name] for name in (DRIVER, *HEADERS)):
        raise ValueError('Frozen CPU fixture or driver/header drift')

    original = frozen[DRIVER].decode()
    before, after = previous_stage(original), stage(original)
    unchanged = once(once(after, MAP_READY, MAP), DECL_READY, DECL)
    unchanged = once(unchanged, method(after, READY) + '\n', '')
    for signature in (GEM, LEGACY, TYPED):
        unchanged = once(unchanged, method(after, signature), method(before, signature))
    if (unchanged != before or '#define PHX_KEXT_BUILD 34u\n' not in original or
            sha(before.encode()) != json.loads(frozen[PRIOR])['staged_sha256']):
        raise ValueError('Unexpected predecessor or change outside mapping admission')

    prefix, marker, _ = cpu.decode().partition('static void logicalOnly(')
    if not marker or method(prefix, GEM) != method(before, GEM):
        raise ValueError('CPU mapping fixture or mapping handler drift')
    legacy_submit = method(prefix, LEGACY)
    typed_submit = method(prefix, TYPED)
    legacy_replacement = once(method(before, LEGACY),
                              '    if (!clientCallback || __atomic_load_n(&legacyState, __ATOMIC_ACQUIRE) != 2 ||',
                              '    if (!clientCallback || (!(exactRequested || exactOwnership) &&\n'
                              '        __atomic_load_n(&legacyState, __ATOMIC_ACQUIRE) != 2) ||')
    legacy_replacement = once(legacy_replacement,
                              '    if (exactOwnership && (h.flags & PHXN_CS_HAS_FENCE)) return kIOReturnUnsupported;\n',
                              '')
    legacy_replacement = once(legacy_replacement,
                              '    if (!checkCpuFences()) return kIOReturnNotReady;\n', '')
    legacy_replacement = once(legacy_replacement,
                              '        if (fb) {\n'
                              '            const IOReturn prepared = prepareCpuFence();\n'
                              '            if (prepared != kIOReturnSuccess) return prepared;\n'
                              '        }\n', '')
    legacy_replacement = once(legacy_replacement,
                              '        if (fb && !appendCpuFence(h.fence_handle, h.fence_offset, seq)) return kIOReturnNotReady;\n',
                              '        if (fb) {\n'
                              '            pendFenceHandle = h.fence_handle;\n'
                              '            pendFenceOffset = h.fence_offset;\n'
                              '            pendFenceSeq = seq;\n'
                              '        }\n')
    legacy_replacement = once(legacy_replacement,
                              '    if (vmid || vmGeneration || lastSeq || cpuFenceCount) return kIOReturnNotReady;\n'
                              '    if (emitted >= UINT64_MAX - 1) return kIOReturnNoResources;\n', '')
    if legacy_submit != legacy_replacement or typed_submit != method(before, TYPED):
        raise ValueError('CPU fixture does not contain the expected actual submit methods')
    prefix = prefix.replace(LOGICAL_DECLARATION, '    // CPU_FENCE_FIELDS\n' + FIELDS, 1)
    fence_end = prefix.index('\n};', prefix.index('struct IOAccelPhxNativeClient : IOUserClient {')) + 3
    prefix = prefix[:fence_end] + '\n// IB_DECLARATION\n' + prefix[fence_end:]
    prefix = once(prefix, method(prefix, PUBLISH),
                  '\n'.join(method(before, signature) for signature in (*FENCE_METHODS, PUBLISH)))
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

    def compile_case(label, code, declaration, sanitizer):
        target, binary = out / (label + '.cpp'), out / label
        fixture = once(prefix, '    // CPU_FENCE_FIELDS', declaration)
        staged_legacy = method(code, LEGACY)
        staged_legacy = once(staged_legacy,
                             '    if (!clientCallback || __atomic_load_n(&legacyState, __ATOMIC_ACQUIRE) != 2 ||',
                             '    if (!clientCallback || (!(exactRequested || exactOwnership) &&\n'
                             '        __atomic_load_n(&legacyState, __ATOMIC_ACQUIRE) != 2) ||')
        staged_legacy = once(staged_legacy,
                             '    if (exactOwnership && (h.flags & PHXN_CS_HAS_FENCE)) return kIOReturnUnsupported;\n',
                             '')
        staged_legacy = once(staged_legacy, '    if (!checkCpuFences()) return kIOReturnNotReady;\n', '')
        staged_legacy = once(staged_legacy,
                             '        if (fb) {\n'
                             '            const IOReturn prepared = prepareCpuFence();\n'
                             '            if (prepared != kIOReturnSuccess) return prepared;\n'
                             '        }\n', '')
        staged_legacy = once(staged_legacy,
                             '        if (fb && !appendCpuFence(h.fence_handle, h.fence_offset, seq)) return kIOReturnNotReady;\n',
                             '        if (fb) {\n'
                             '            pendFenceHandle = h.fence_handle;\n'
                             '            pendFenceOffset = h.fence_offset;\n'
                             '            pendFenceSeq = seq;\n'
                             '        }\n')
        staged_legacy = once(staged_legacy,
                             '    if (vmid || vmGeneration || lastSeq || cpuFenceCount) return kIOReturnNotReady;\n'
                             '    if (emitted >= UINT64_MAX - 1) return kIOReturnNoResources;\n', '')
        fixture = once(fixture, legacy_submit, staged_legacy)
        fixture = once(fixture, typed_submit, method(code, TYPED))
        covered = method(code, COVERED)
        if code is not before:
            covered = once(covered, 'bool ok = false;\n', 'bool ok = false; bool anyMap = false;\n')
            covered = once(covered, '                ok = true;\n',
                           '                anyMap = true;\n                ok = true;\n')
            covered = once(covered, '        if (!ok)\n            return false;\n',
                           '        if (!ok)\n            return anyMap;\n')
        fixture = fixture.replace('// IB_DECLARATION\n', '', 1)
        fixture = once(fixture, LOGICAL_DECLARATION,
                       '    bool ibCovered(uint64_t vaCanon, uint64_t bytes);\n')
        fence_end = fixture.index('\n};', fixture.index('struct IOAccelPhxNativeClient : IOUserClient {')) + 3
        definitions = '\n'.join(method(code, signature) for signature in
                                (READY_METHODS if code is not before else (COVERED,)))
        fixture = fixture[:fence_end] + '\n' + definitions + '\n' + fixture[fence_end:]
        walker_start = fixture.index('uint64_t *PhxBringup::ptTable(const VmCtx &c, uint64_t phys) const {')
        walker_end = fixture.index('\n}', fixture.index('uint64_t *PhxBringup::vmPte(', walker_start)) + 2
        fixture = fixture[:walker_start] + fixture[walker_end:]
        fixture += '\n'.join(method(code, signature) for signature in VM_METHODS)
        if code is not before:
            fixture = once(fixture, MAP, MAP_READY)
            fixture = once(fixture, '        if (vmid || owner->gpuReady()) {',
                           '        const bool materialize = vmid || owner->gpuReady();\n        if (materialize) {')
            fixture = once(fixture,
                           '        maps[freei] = Map{true, v->handle, va, v->map_size, v->offset_in_bo, v->flags};',
                           '        maps[freei] = Map{true, v->handle, va, v->map_size, v->offset_in_bo, v->flags, materialize};\n'
                           '        if (!materialize) mayHaveLogicalMappings = true;')
        target.write_text(fixture + frozen[FIXTURE].decode())
        checked(label + '-compile', ['/usr/bin/xcrun', 'clang++', '-std=c++17', '-O1', '-g',
                                     '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-unused-function',
                                     '-fno-sanitize-recover=all', '-fsanitize=' + sanitizer,
                                     '-I' + str(includes), str(target), '-o', str(binary)])
        if code is not before:
            staged_logical = target.read_text().count('mayHaveLogicalMappings = true;')
            if staged_logical != 1:
                raise ValueError('Logical-mapping bookkeeping not assembled as staged')
        linkage = checked(label + '-linkage', ['/usr/bin/otool', '-L', str(binary)])
        if re.search(rb'IOKit|Metal|vulkan|PhxAccel', linkage, re.I):
            raise ValueError('Device runtime linked into CPU fixture')
        return binary

    def passed(binary, case):
        result = checked(binary.name + '-' + case, [str(binary), case])
        match = re.fullmatch(rb'PASS (\d+) checks; GPU_executed=false\n', result)
        if not match or int(match[1]) <= 0:
            raise ValueError('Unexpected CPU result: ' + case)
        return int(match[1])

    control = compile_case('before', before,
                           '    bool ibCovered(uint64_t,uint64_t) { CHECK(clientHeld); return true; }\n',
                           'address,undefined')
    for case in PASS_CASES:
        passed(control, case)
    for case in REFUSALS:
        old = run('before-' + case, [str(control), case])
        expected = rb'failed \d+: result == kIOReturnNotReady && probe\.untouched\(\)\n'
        if old.returncode != 86 or old.stdout or not re.fullmatch(expected, old.stderr):
            raise ValueError('Expected old-path native dispatch not reproduced: ' + case)

    counts = []
    for label, sanitizer in (('asan-ubsan', 'address,undefined'), ('tsan', 'thread')):
        binary = compile_case(label, after,
                              '    bool ibCovered(uint64_t,uint64_t) { CHECK(clientHeld); return true; }\n'
                              '    bool nativeMappingsReady();\n    bool mayHaveLogicalMappings{false};\n',
                              sanitizer)
        counts.append(sum(passed(binary, case) for case in CASES))
    if (counts[0] != counts[1] or cpu_path.read_bytes() != cpu or
            any((ROOT / name).read_bytes() != blob for name, blob in frozen.items()) or
            git('diff', '--name-only', BASE, '--', *PRODUCTION)):
        raise ValueError('Changed inputs or inconsistent CPU results')
    print(json.dumps(dict(status='passed-staged-vm-ready-CPU-only', checks_per_sanitizer=counts[0],
                          predecessor_sha256=sha(before.encode()), staged_sha256=sha(after.encode()),
                          scenarios=len(CASES), old_native_dispatches_reproduced=list(REFUSALS),
                          production_inputs_unchanged=len(protected), installed=False,
                          GPU_executed=False, R3_complete=False), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    test(parser.parse_args().out)
