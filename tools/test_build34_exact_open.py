"""Verify the staged exact open gate on CPU and in complete MH_OBJECTs."""

import argparse
import json
from pathlib import Path
import re
import subprocess
from unittest.mock import patch

import build34_native_object_check as native_objects
from build34_exact_legacy_close import REFERENCE
from build34_exact_open import ADMITTED, BIND, FACTORY, INIT, OPEN_PROOF, SNAPSHOT, previous_stage, stage, stage_header
from build34_exact_submit import once
from test_build34_exact_ownership import DRIVER, ROOT, method, sha


PROTECTED = ['src', 'tools/phxctl', 'tools/build_kext.py']
BASE = 'e9ee265ce005693f2928b4f981dfd097ca53fb80'
VALIDATION = 'docs/validation/'
PROGRESS = VALIDATION + 'build34-r3-mesa-progress-offline-20261122.json'
SUBMIT = VALIDATION + 'build34-r3-submit-receipt-offline-20261121.json'
FACTORY_RECORD = VALIDATION + 'build34-r3-factory-offline-20261121.json'
KDK_RECORD = VALIDATION + 'build34-r3-public-timer-offline-20261121.json'
EXTRA = ('build34_exact_progress_wire.h', 'build34_exact_open_wire.h')
FIXTURE = 'tests/test_build34_exact_open.cpp'
METHODS = (ADMITTED, SNAPSHOT, FACTORY, INIT, BIND, 'bool IOAccelPhxNativeClient::start(',
           'bool PhxBringup::registerLegacyClient(', 'bool PhxBringup::requestLegacyClose(',
           'IOReturn IOAccelPhxNativeClient::clientClose(', 'void PhxBringup::stop(',
           'void PhxBringup::sealStoppedQueues(', 'void PhxBringup::invalidateExactQueues(',
           'IOReturn PhxBringup::setPowerState(')


def git(*args):
    return subprocess.check_output(['/usr/bin/git', *args], cwd=ROOT, text=True, timeout=20).strip()


def test(out, sdk, kdk):
    out = Path(out).resolve()
    if out.exists() or ROOT / 'build' not in out.parents or not out.name.endswith('-private'):
        raise ValueError('Require a fresh ignored build directory ending -private')
    git('check-ignore', '-q', str(out))
    if git('symbolic-ref', '--short', 'HEAD') != 'upstream34/vram-layout-fix':
        raise ValueError('Default build34 only')
    git('diff', '--quiet', BASE, '--', *PROTECTED)
    production = git('ls-files', *PROTECTED).splitlines()
    if len(production) != 172:
        raise ValueError('Protected production inventory drift')
    records = {name: json.loads((ROOT / name).read_bytes()) for name in (PROGRESS, SUBMIT, FACTORY_RECORD, KDK_RECORD)}
    pinned = records[SUBMIT]['input_sha256']
    header_names = native_objects.HEADERS + EXTRA
    paths = {DRIVER, 'src/phxbringup/Info.plist', 'tools/build34_exact_ownership.h',
             'tools/build34_exact_open.py', 'tools/test_build34_exact_open.py', 'tools/build34_native_object_check.py',
             FIXTURE, *records, *pinned, *production, *('tools/' + name for name in header_names)}
    inputs = {name: (ROOT / name).read_bytes() for name in sorted(paths)}
    if any(sha(inputs[name]) != digest for name, digest in pinned.items()):
        raise ValueError('Preceding submit receipt evidence drift')
    original = inputs[DRIVER].decode()
    previous, proposed = previous_stage(original), stage(original)
    if sha(previous.encode()) != records[PROGRESS]['staged_progress_source_sha256'] or '#define PHX_KEXT_BUILD 34u\n' not in proposed:
        raise ValueError('Preceding progress wire stage or driver build drift')
    admitted = method(proposed, ADMITTED)
    if admitted != 'bool PhxBringup::exactNativeOpenAdmitted() const {\n    return false;\n}\n':
        raise ValueError('Native admission must remain disabled')
    if any(re.search(member + r'\s*=', proposed) or proposed.count(member + '{nullptr}') != 1
           for member in ('exactFenceReader', 'exactDwordReader', 'exactEventOps')):
        raise ValueError('Device reader or event binding is forbidden in this stage')
    ownership = stage_header(inputs['tools/build34_exact_ownership.h'].decode())
    expected = ('void PhxBringup::stop(', 'void PhxBringup::invalidateExactQueues(', 'IOReturn PhxBringup::setPowerState(',
                'IOReturn IOAccelPhxNativeClient::externalMethod(', 'IOReturn IOAccelPhxNativeClient::doExactProgress(')
    if any(method(previous, sig) != method(proposed, sig) for sig in expected):
        raise ValueError('Unexpected dispatch or lifecycle delta')

    out.mkdir(parents=True, mode=0o700)
    cpu = out / 'cpu'
    cpu.mkdir()
    headers = {name: inputs['tools/' + name] for name in header_names}
    headers['build34_exact_ownership.h'] = ownership.encode()
    headers['PhxNativeABI.h'] = inputs['src/phxbringup/PhxNativeABI.h']
    for name, blob in headers.items():
        (cpu / name).write_bytes(blob)
    (out / 'amd').mkdir()
    (out / 'amd/phx_topology.h').write_bytes(inputs['src/amd/phx_topology.h'])
    compiler, otool = (Path(subprocess.check_output(['/usr/bin/xcrun', '--find', name], text=True, timeout=15).strip()).resolve()
                       for name in ('clang++', 'otool'))
    pattern = r'PASS exact open: (\d+) checks; modeled=(0|1); GPU_executed=false\n'

    def run(args, label, fail=False):
        process = subprocess.run([str(arg) for arg in args], cwd=cpu, capture_output=True, timeout=45, stdin=subprocess.DEVNULL)
        (out / (label + '.stdout')).write_bytes(process.stdout)
        (out / (label + '.stderr')).write_bytes(process.stderr)
        if fail:
            if process.returncode != 86 or not process.stderr.startswith(b'failed '):
                raise ValueError(label + ' did not detect its intended defect')
        elif process.returncode or process.stderr:
            raise RuntimeError(label + ' failed; inspect private logs')
        return process.stdout.decode()

    def exercise(label, source, modeled, sanitizer, fail=False):
        methods = [method(source, sig) for sig in METHODS]
        if modeled:
            methods[0] = once(methods[0], 'return false;', 'return modeledAdmission;')
        fixture = once(inputs[FIXTURE].decode(), '// EXACT_OPEN_PROOF', OPEN_PROOF)
        fixture = once(fixture, '// EXACT_OPEN_METHODS', REFERENCE + '\n'.join(methods))
        test_source, binary = cpu / (label + '.cpp'), cpu / (label + '-CPU-only')
        test_source.write_text(fixture)
        run([compiler, '--driver-mode=g++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
             '-Wno-unused-function', '-fno-sanitize-recover=all', '-fsanitize=' + sanitizer,
             '-DMODELED_OPEN=' + str(int(modeled)), test_source, '-o', binary], label + '-compile')
        if re.search(r'IOKit|Metal|vulkan|PhxAccel', run([otool, '-L', binary], label + '-linkage'), re.I):
            raise ValueError('CPU fixture links device runtime')
        result = run([binary], label + '-test', fail=fail)
        if not fail:
            match = re.fullmatch(pattern, result)
            if not match or int(match[2]) != modeled:
                raise ValueError('Incomplete CPU open run')
            return int(match[1])

    counts = {label: {mode: exercise(label + '-' + mode, proposed, mode == 'modeled', sanitizer)
                      for mode in ('closed', 'modeled')}
              for label, sanitizer in [('asan_ubsan', 'address,undefined'), ('tsan', 'thread')]}
    if counts['asan_ubsan'] != counts['tsan']:
        raise ValueError('Sanitizers did not cover the same CPU cases')
    mutations = {
        'native-gate-bypass': (SNAPSHOT, '!exactNativeOpenAdmitted() || ', '', False),
        'reader-optional': (SNAPSHOT, '!exactDwordReader || ', '', True),
        'permission-from-security-cookie': (FACTORY, 'clientHasPrivilege(owningTask,', 'clientHasPrivilege(securityID,', True),
        'request-loses-mode': (INIT, 'exactRequested = type == PHX34_R3_UC_TYPE;', 'exactRequested = false;', True),
        'bind-accepts-a-different-generation': (BIND, '!client->requestedExactOpen.matches(current) || ', '', True),
        'publish-accepts-a-different-generation': (FACTORY, ' && requested.matches(current)', '', True),
        'unexposed-registration-not-closed': (FACTORY, '        (void)client->clientClose();\n', '', True),
    }
    for label, (signature, old, new, modeled) in mutations.items():
        body = method(proposed, signature)
        exercise(label, once(proposed, body, once(body, old, new)), modeled, 'address,undefined', fail=True)

    prior = records[FACTORY_RECORD]
    with patch.object(native_objects, 'HEADERS', header_names):
        native = native_objects.check(out / 'native', inputs, previous, proposed, ownership, sdk, kdk,
                                      381, prior['compiler_warnings']['proposed'], records[KDK_RECORD], compiler)
    git('diff', '--quiet', BASE, '--', *PROTECTED)
    if any((ROOT / name).read_bytes() != blob for name, blob in inputs.items()):
        raise ValueError('Production or test input drift')
    result = dict(status='passed-offline-exact-open-admission', build=34, checks=counts,
                  rejected_mutants=list(mutations), staged_source_sha256=sha(proposed.encode()),
                  previous_source_sha256=sha(previous.encode()), protected_production_inputs=len(production),
                  native_open_admitted=False, native_reader_bound=False, IOKit_opened=False, GPU_executed=False,
                  R3_complete=False, **native)
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('out', 'sdk', 'kdk'):
        parser.add_argument('--' + option, required=True)
    args = parser.parse_args()
    print(json.dumps(test(args.out, args.sdk, args.kdk), indent=2))
