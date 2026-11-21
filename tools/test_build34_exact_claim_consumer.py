# SPDX-License-Identifier: MIT
"""Run the staged producer and consumer start on CPU substitutes and compile native objects."""

import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import shlex
import struct
import subprocess

from build34_exact_claim_consumer import (ACCEL, ACCEL_START, FUNCTION, KEY,
                                         OVERRIDE, PLIST, previous_stage, stage, stage_accel, stage_header, stage_plist)
from build34_exact_submit import once
from build34_kpi_symbolset import interface_exports
from build34_native_object_check import check as native_check
from test_build34_exact_claim_lifecycle import (FACTORY, FIELDS as PRIOR_FIELDS, MOCK_REGISTRY, PRIOR as CLAIM, PSP, REFERENCE, SMU,
                                                fixture as lifecycle_fixture, git, xcrun)
from test_build34_exact_ownership import DRIVER, ROOT, method, sha


PRIOR = 'docs/validation/build34-r3-claim-lifecycle-offline-20261121.json'
FIXTURE = 'tests/test_build34_exact_claim_consumer.cpp'
NEW = (PRIOR, FIXTURE, 'tools/build34_exact_claim_consumer.py', 'tools/test_build34_exact_claim_consumer.py')

MODEL = '''static constexpr unsigned kIOServiceAsynchronous = 2;
struct OSSymbol {
    const char *text;
    static unsigned count;
    static const OSSymbol *withCStringNoCopy(const char *text) { ++count; return new OSSymbol{text}; }
    bool isEqualTo(const char *s) const { return !std::strcmp(text, s); }
    void release() const { --count; delete this; }
};
unsigned OSSymbol::count;
struct IOService {
    unsigned refs = 1;
    IOService *parent = nullptr;
    bool bringupClass = false, inactive = false;
    virtual ~IOService() = default;
    void retain() { ++refs; }
    void release() { --refs; }
    IOService *getProvider() { CHECK(!locksHeld); return parent; }
    bool isInactive() const { CHECK(!locksHeld); return inactive; }
    bool metaCast(const OSSymbol *s) const { return bringupClass && s->isEqualTo("PhxBringup"); }
    virtual IOReturn callPlatformFunction(const OSSymbol *, bool, void *, void *, void *, void *) {
        return kIOReturnNotPermitted;
    }
};
'''

CONSUMER = '''#define NMX_ACCEL 1
#define PHX_FB 1
#define APPLE_KEXT_OVERRIDE override
#define OSDynamicCast(T, p) dynamic_cast<T *>(p)
#define ALOG(...) ((void)0)
static bool nvrm_driver_off() { return false; }
static thread_local Pause *inFamilyStart;
struct IOGraphicsAccelerator2 : IOService {
    unsigned starts = 0, stops = 0, publishes = 0;
    bool familyOK = true;
    virtual bool start(IOService *) { CHECK(!locksHeld); ++starts; pauseOnce(inFamilyStart); return familyOK; }
    virtual void stop(IOService *) { CHECK(!locksHeld); ++stops; }
};
struct NVAccel : IOGraphicsAccelerator2 {
@START@        if (r) ++publishes;
        return r;
    }
};
'''


def fixture(driver, accel, frozen, prior=False):
    text = lifecycle_fixture(driver, frozen)
    text = once(text, 'struct IOService {};\n', MODEL)
    pair_key = 'nmxgpu-claimed' if prior else KEY
    registry = MOCK_REGISTRY.replace('nmxgpu-claimed', pair_key)
    text = once(text, 'struct IOPCIDevice {', '''struct IOPCIDevice : IOService {
    IOService *child = nullptr;
    IOService *copyClientWithCategory(const OSSymbol *category) {
        CHECK(!locksHeld && category->isEqualTo("PhxBringup"));
        if (child) child->retain();
        return child;
    }
''')
    text = once(text, '    unsigned refs = 1, properties = 0, matches = 0, removals = 0;\n',
                '    unsigned properties = 0, matches = 0, removals = 0;\n')
    text = once(text, '    void retain() { ++refs; }\n    void release() { --refs; }\n    void publicationCheck()',
                '    void publicationCheck()')
    text = text.replace('nmxgpu-claimed', pair_key)
    if text.count(registry[registry.index('    const OSObject *getProperty'):]) != 1:
        raise ValueError('Unexpected registry fixture')
    if not prior:
        text = once(text, '    void registerService() { publicationCheck(); ++matches; pauseOnce(duringMatch); }',
                    '    void registerService(unsigned mode) {\n'
                    '        CHECK(mode == kIOServiceAsynchronous); publicationCheck(); ++matches; pauseOnce(duringMatch);\n'
                    '    }')
    text = once(text, 'struct PhxBringup {', 'struct PhxBringup : IOService {')
    if not prior:
        text = once(text, PRIOR_FIELDS, '')
        text = once(text, 'static void IOLockUnlock(',
                    'static bool IOLockTryLock(IOLock *l) { if (!l->try_lock()) return false; ++locksHeld; return true; }\n'
                    'static void IOLockUnlock(')
        text = once(text, '    IOReturn claimAccel();\n', '    IOReturn claimAccel();\n' + OVERRIDE)
        text += '\n'.join(method(driver, signature) for signature in ('bool PhxBringup::exactClaimReadyLocked(',
                           'bool PhxBringup::exactClaimCurrentLocked(', 'IOReturn PhxBringup::callPlatformFunction('))
    start = accel.index(ACCEL_START if prior else '#if defined(NMX_ACCEL) && defined(PHX_FB)\n    bool startClaimedFamily')
    end = accel.index('        ALOG("IOGraphicsAccelerator2::start -> %d", r);', start)
    return text + '\n' + CONSUMER.replace('@START@', accel[start:end]) + (
        '' if prior else '\nstatic constexpr const char *platformName = "' + FUNCTION + '";\n')


def test(out, sdk, kdk):
    out = out.resolve()
    if (os.uname().sysname, os.uname().machine) != ('Darwin', 'x86_64') or out.exists() or ROOT / 'build' not in out.parents:
        raise ValueError('Require fresh private build directory on x86_64 macOS')
    if not out.name.endswith('-private') or git('symbolic-ref', '--short', 'HEAD').strip() != 'upstream34/vram-layout-fix':
        raise ValueError('Require default build34 and a private output')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    protected = git('ls-files', 'src', 'tools/phxctl', 'tools/build_kext.py').splitlines()
    if len(protected) != 172 or git('status', '--porcelain', '--', *protected):
        raise ValueError('Production inputs drifted')
    factory, psp, smu, claim, prior = (json.loads((ROOT / n).read_bytes()) for n in (FACTORY, PSP, SMU, CLAIM, PRIOR))
    pins = (factory['input_sha256'] | psp['frozen_new_input_sha256'] | smu['new_input_sha256'] |
            claim['new_input_sha256'] | prior['new_input_sha256'])
    frozen = {n: (ROOT / n).read_bytes() for n in set(protected) | set(pins) | set(NEW)}
    if any(r['GPU_executed'] for r in (factory, psp, smu, claim, prior)) or any(sha(frozen[n]) != h for n, h in pins.items()):
        raise ValueError('Frozen source drift')
    driver, accel, plist = [frozen[n].decode() for n in (DRIVER, ACCEL, PLIST)]
    prev_driver, next_driver, next_accel, next_plist = previous_stage(driver), stage(driver), stage_accel(accel), stage_plist(plist)
    header = stage_header(frozen['tools/build34_exact_ownership.h'].decode())
    if sha(prev_driver.encode()) != prior['staged_driver_sha256'] or sha(header.encode()) != factory['staged_header_sha256']:
        raise ValueError('Staged predecessor drift')
    configuration = plistlib.loads(next_plist.encode())
    changed = configuration['IOKitPersonalities']['PhxAccel']['IOPropertyMatch']
    original = plistlib.loads(frozen[PLIST])
    if changed != {KEY: True}:
        raise ValueError('Incorrect paired marker')
    configuration['IOKitPersonalities']['PhxAccel']['IOPropertyMatch'] = {'nmxgpu-claimed': True}
    if configuration != original:
        raise ValueError('Other personality changes')

    out.mkdir(mode=0o700)
    for name, blob in frozen.items():
        dest = out / 'frozen' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
    compiler, host_sdk, nm, otool = [xcrun(*args) for args in (('--find', 'clang++'), ('--show-sdk-path',),
                                                             ('--find', 'nm'), ('--find', 'otool'))]
    env = {'PATH': str(compiler.parent) + ':/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
           'TSAN_OPTIONS': 'halt_on_error=1:abort_on_error=0:exitcode=66'}

    def run(label, *args, expected=0):
        result = subprocess.run([str(a) for a in args], cwd=out, env=env, capture_output=True,
                                stdin=subprocess.DEVNULL, timeout=80)
        (out / (label + '.stdout')).write_bytes(result.stdout)
        (out / (label + '.stderr')).write_bytes(result.stderr)
        if result.returncode != expected:
            raise RuntimeError(f'{label} exited {result.returncode}; expected {expected}. See private diagnostics.')
        return result

    def exercise(label, driver, accel, sanitizer, prior=False, broken=False):
        (out / 'paired-fixture.inc').write_text(fixture(driver, accel, frozen, prior))
        binary = out / label
        run(label + '-compile', compiler, '--driver-mode=g++', '-std=c++17', '-arch', 'x86_64', '-isysroot', host_sdk, '-O1', '-g',
            '-Wall', '-Wextra', '-Werror', '-fsanitize=' + sanitizer, '-fno-sanitize-recover=all',
            '-I' + str(out), '-I' + str(out / 'frozen/tools'), '-I' + str(out / 'frozen/src/phxbringup'),
            *(['-DPRIOR'] if prior else []), out / 'frozen' / FIXTURE, '-o', binary)
        if re.search(rb'IOKit|Metal|vulkan|PhxAccel', run(label + '-links', otool, '-L', binary).stdout, re.I):
            raise ValueError('CPU fixture unexpectedly links a device framework')
        result = run(label, binary, expected=86 if broken else 0)
        if broken and result.stderr.startswith(b'failed '):
            return None
        count = re.fullmatch(rb'PASS (\d+) (?:prior|paired) checks\n', result.stdout)
        if broken or not count or result.stderr:
            raise ValueError('Unexpected fixture result: ' + label)
        return int(count[1])

    missed = exercise('prior', prev_driver, accel, 'address,undefined', prior=True)
    asan = exercise('asan', next_driver, next_accel, 'address,undefined')
    tsan = exercise('tsan', next_driver, next_accel, 'thread')
    if asan != tsan:
        raise ValueError('Sanitizer check counts differ')
    mutations = {
        'wrong_pci': (next_driver, next_accel, 'device && pci == device && exactClaimDevice == device', 'device'),
        'wrong_epoch': (next_driver, next_accel, 'exactInvalidationEpoch == exactClaimEpoch && ', ''),
        'wrong_generation': (next_driver, next_accel, 'exactQueueGeneration[1] == exactClaimGeneration[1]', 'exactQueueGeneration[1] != 0'),
        'skip_post_start': (next_accel, next_driver, 'if (started && !current())', 'if (started && false)'),
        'ignore_endpoint_refusal': (next_accel, next_driver, '== kIOReturnSuccess;\n        };', '!= kIOReturnBusy;\n        };'),
    }
    for label, (source, other, old, new) in mutations.items():
        changed = once(source, old, new)
        pair = (other, changed) if source is next_accel else (changed, other)
        exercise(label, *pair, 'address,undefined', broken=True)

    reference = json.loads(frozen[REFERENCE])
    warnings = prior['compiler_warnings']['proposed']
    before = native_check(out / 'prior-native', frozen, prev_driver, prev_driver, header, sdk, kdk,
                          prior['native_import_count'], warnings, reference, compiler)
    after = native_check(out / 'paired-native', frozen, next_driver, next_driver, header, sdk, kdk,
                         prior['native_import_count'] + 1, warnings, reference, compiler)
    old_imports, new_imports = [set((out / name / 'proposed-imports.stdout').read_text().splitlines())
                                for name in ('prior-native', 'paired-native')]
    if old_imports - new_imports or new_imports - old_imports != {'_IOLockTryLock'}:
        raise ValueError('Unexpected native driver imports')
    accel_imports, accel_objects, accel_warnings = {}, {}, {}
    for label, source in [('prior', accel), ('paired', next_accel)]:
        base = out / ('accel-' + label)
        for name, blob in frozen.items():
            if name.startswith('src/phxaccel/'):
                path = base / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(source.encode() if name == ACCEL else blob)
        root = base / 'src/phxaccel'
        flags = shlex.split(frozen['src/phxaccel/build.sh'].decode().split('clang++ ', 1)[1].split('  -c ', 1)[0]
                            .replace('\\\n', '').replace('$MKSDK', str(out / 'paired-native/sdk')).replace('$HERE', str(root)))
        obj, dep = base / 'accel.o', base / 'accel.d'
        result = run('accel-' + label, compiler, *flags, '-MMD', '-MF', dep, '-c', base / ACCEL, '-o', obj)
        deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        if not deps or any(not Path(n).is_relative_to(root) and not Path(n).is_relative_to(out / 'paired-native/sdk') for n in deps):
            raise ValueError('Unfrozen accelerator include')
        blob = obj.read_bytes()
        if struct.unpack_from('<4I', blob) != (0xfeedfacf, 0x1000007, 3, 1):
            raise ValueError('Nonloadable accelerator object required')
        accel_objects[label] = sha(blob)
        accel_warnings[label] = re.findall(r'warning: (.+)', result.stderr.decode())
        accel_imports[label] = set(run('accel-' + label + '-imports', nm, '-arch', 'x86_64', '-uj', obj).stdout.decode().splitlines())
    added = accel_imports['paired'] - accel_imports['prior']
    removed = accel_imports['prior'] - accel_imports['paired']
    expected = {'__ZNK15OSMetaClassBase8metaCastEPK8OSSymbol': 'Libkern', '__ZNK9IOService10isInactiveEv': 'IOKit'}
    if accel_warnings['prior'] != accel_warnings['paired'] or removed or added != set(expected):
        raise ValueError('Unexpected accelerator compiler diagnostics/import delta')
    copied_providers = out / 'paired-native/kdk/System/Library/Extensions/System.kext/PlugIns'
    declared = original['OSBundleLibraries']
    for symbol, provider in expected.items():
        if ('com.apple.kpi.' + provider.lower() not in declared or
                symbol not in interface_exports((copied_providers / (provider + '.kext') / provider).read_bytes())):
            raise ValueError('Accelerator import unavailable in existing declared provider: ' + symbol)
    if any((ROOT / n).read_bytes() != blob or (out / 'frozen' / n).read_bytes() != blob for n, blob in frozen.items()):
        raise ValueError('Input changed during verification')
    report = dict(status='passed-staged-accelerator-claim-admission', kernel_build=34, frozen_input_count=len(frozen),
                  new_input_sha256={n: sha(frozen[n]) for n in NEW}, production_inputs_unchanged=len(protected),
                  preceding_driver_sha256=sha(prev_driver.encode()), staged_driver_sha256=sha(next_driver.encode()),
                  staged_accel_sha256=sha(next_accel.encode()), staged_personality_sha256=sha(next_plist.encode()),
                  old_delayed_match_checks=missed, paired_checks_each_sanitizer=asan, synchronized_scenarios=5,
                  broken_variants_detected=list(mutations), PhxBringup_imports=[len(old_imports), len(new_imports)],
                  added_PhxBringup_imports=sorted(new_imports - old_imports), sdk_commit=after['sdk_commit'],
                  os_version=after['os_version'], os_build=after['os_build'],
                  full_driver_object_sha256=[before['native_object_sha256']['proposed'], after['native_object_sha256']['proposed']],
                  accelerator_object_sha256=accel_objects, accelerator_added_imports=sorted(added),
                  accelerator_added_imports_have_existing_declared_KDK_provider=True,
                  accelerator_compiler_warning_count=len(accel_warnings['paired']),
                  native_object_only=True, IOKit_opened=False, GPU_executed=False, installed=False,
                  attached_accelerator_lifetime_proved=False, external_writer_drain_proved=False,
                  native_reader_bound=False, R3_complete=False)
    (out / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('out', 'sdk', 'kdk'):
        parser.add_argument('--' + flag, type=Path, required=True)
    args = parser.parse_args()
    test(args.out, args.sdk, args.kdk)
