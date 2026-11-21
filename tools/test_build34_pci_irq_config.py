# SPDX-License-Identifier: MIT
"""Check actual staged PCI IRQ observation code on CPU and as nonloadable objects."""

import argparse
import json
from pathlib import Path
import platform
import plistlib
import re
import shlex
import struct
import subprocess

from build34_map_observation import stage_baseline
from build34_pci_irq_config import OBSERVER, SERVICE, START_ANCHOR, START_OBSERVER, stage
from upstream34_layout.ring_padding_candidate import DRIVER, SDK_PIN, file_sha, sdk_inputs, sha

ROOT = Path(__file__).resolve().parents[1]
BASE = 'd225adf8607072262c6ec458cf29d3a1383e4a10'
FIXTURE = 'tests/test_build34_pci_irq_config.cpp'
REFERENCE = 'docs/validation/build34-r3-public-timer-offline-20261121.json'
CLOSURE = (DRIVER, 'src/phxbringup/PhxNativeABI.h', 'src/amd/phx_topology.h')
PRODUCTION = ('src', 'tools/phxctl', 'tools/build_kext.py')
PROVIDER = 'System/Library/Extensions/IOPCIFamily.kext/Contents/MacOS/IOPCIFamily'


def platform_command(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True, timeout=15).strip()


def replace_one(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Expected one exact source site')
    return text.replace(old, new, 1)


def test(out, sdk, kdk):
    out = out.resolve()
    if (platform.system() != 'Darwin' or platform.machine() != 'x86_64' or out.exists() or
            ROOT / 'build' not in out.parents or not out.name.endswith('-private') or
            platform_command('/usr/bin/git', 'branch', '--show-current') != 'upstream34/vram-layout-fix'):
        raise ValueError('Require default build34 on Intel macOS and a fresh private output')
    subprocess.run(['/usr/bin/git', 'check-ignore', '-q', str(out)], cwd=ROOT, check=True, timeout=15)
    tracked = platform_command('/usr/bin/git', 'ls-files', *PRODUCTION).splitlines()
    if len(tracked) != 172 or platform_command('/usr/bin/git', 'diff', '--name-only', BASE, '--', *PRODUCTION):
        raise ValueError('Production inputs drifted')
    frozen = {n: (ROOT / n).read_bytes() for n in set(tracked) | {FIXTURE, REFERENCE}}
    original = frozen[DRIVER].decode()
    control, observer = stage_baseline(original), stage(original)
    if replace_one(replace_one(observer, OBSERVER + SERVICE, SERVICE),
                   START_OBSERVER + START_ANCHOR, START_ANCHOR) != control:
        raise ValueError('Observer changed unrelated source')
    sdk_blobs = sdk_inputs(sdk)
    compiler, host_sdk, nm, otool = (Path(platform_command('/usr/bin/xcrun', *args)).resolve()
                                    for args in (('--find', 'clang++'), ('--show-sdk-path',),
                                                 ('--find', 'nm'), ('--find', 'otool')))
    tools = {p: file_sha(p) for p in (compiler, host_sdk / 'SDKSettings.json', nm, otool)}
    meta = (kdk / 'System/Library/CoreServices/SystemVersion.plist').read_bytes()
    version = plistlib.loads(meta)
    os_version, os_build = (platform_command('/usr/bin/sw_vers', option) for option in ('-productVersion', '-buildVersion'))
    reference = json.loads(frozen[REFERENCE])
    provider_hash = file_sha(kdk / PROVIDER)
    if (version['ProductVersion'] != os_version or version['ProductBuildVersion'] != os_build or
            sha(meta) != reference['KDK_metadata_sha256'] or
            provider_hash != reference['KDK_declared_provider_sha256']['com.apple.iokit.IOPCIFamily']):
        raise ValueError('Require the matching pinned KDK metadata and PCI provider')

    out.mkdir(mode=0o700)
    tmp = out / 'tmp'
    tmp.mkdir()
    env = {'PATH': str(compiler.parent) + ':/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': str(tmp)}

    def run(label, *args, expected=0):
        proc = subprocess.run([str(a) for a in args], cwd=out, env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_bytes(proc.stdout)
        (out / (label + '.stderr')).write_bytes(proc.stderr)
        if proc.returncode != expected:
            raise RuntimeError(label + ' failed; retained private diagnostics')
        return proc

    fixture = frozen[FIXTURE].decode()

    def cpu(label, source, broken=False):
        begin, end = source.index('namespace {\n\nstruct PhxPciIrqSample '), source.index(SERVICE)
        action = source[source.index('    removeProperty("phx-pci-irq-start-v1");'):source.index(START_ANCHOR)]
        text = replace_one(replace_one(fixture, '// PHX34_PCI_OBSERVER', source[begin:end]),
                           '        // PHX34_PCI_START_OBSERVER', action)
        cpp, binary = out / (label + '.cpp'), out / label
        cpp.write_text(text)
        run(label + '-compile', compiler, '--driver-mode=g++', '-isysroot', host_sdk, '-std=c++17', '-O1', '-g',
            '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', cpp, '-o', binary)
        links = run(label + '-links', otool, '-L', binary).stdout
        if re.search(rb'IOKit|Metal|vulkan', links, re.I):
            raise ValueError('CPU fixture links a device runtime')
        result = run(label, binary, expected=86 if broken else 0)
        if broken:
            if not re.fullmatch(rb'failed line [0-9]+\n', result.stderr):
                raise ValueError('Negative variant did not fail a CPU assertion')
            return 0
        match = re.fullmatch(rb'PASS ([0-9]+) PCI IRQ configuration checks\n', result.stdout)
        if not match or result.stderr:
            raise ValueError('Unexpected PCI observer CPU result')
        return int(match[1])

    count = cpu('observer-cpu', observer)
    mutants = {
        'ignore-non-D0': ('sample.pmcsr == 0xffff || (sample.pmcsr & 3)', 'sample.pmcsr == 0xffff'),
        'ignore-changed-msi': (' || a.controlMsi != b.controlMsi', ''),
        'accept-both-enabled': ('    if (msi && msix) return nullptr;\n', ''),
        'swap-function-mask-bit': ('(a.controlMsix & 0x4000)', '(a.controlMsix & 0x2000)'),
        'skip-dynamic-msi-span': ('((sample.controlMsi & 0x100) ? 8 : 0)', '0'),
    }
    for name, (old, new) in mutants.items():
        cpu(name, replace_one(observer, old, new), broken=True)

    def materialize(directory, files):
        result = set()
        for name, blob in files.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
            result.add(path)
        return result

    headers = materialize(out / 'sdk', {n: b for n, b in sdk_blobs.items() if n.startswith('Headers/')})
    flags = ['-arch', 'x86_64', '-mmacosx-version-min=11.0', '-mkernel', '-fno-builtin', '-fno-common', '-nostdinc',
             '-I' + str(out / 'sdk/Headers'), '-DKERNEL', '-DKERNEL_PRIVATE', '-DDRIVER_PRIVATE', '-DAPPLE', '-DNeXT',
             '-Os', '-Wall', '-std=c++17', '-fapple-kext', '-fno-rtti', '-fno-exceptions']
    imports = {}
    for label, text in [('control', control), ('observer', observer)]:
        source_dir = out / label
        closure = {n: frozen[n] for n in CLOSURE}
        closure[DRIVER] = text.encode()
        allowed = headers | materialize(source_dir, closure)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        result = run(label + '-native-compile', compiler, *flags, '-MMD', '-MF', dep, '-c', source_dir / DRIVER, '-o', obj)
        if re.findall(rb'warning: (.+)', result.stderr) != [b"declaration shadows a field of 'PhxBringup' [-Wshadow]"] * 3:
            raise ValueError('Unexpected complete-object warnings')
        deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        if (struct.unpack_from('<4I', obj.read_bytes()) != (0xfeedfacf, 0x1000007, 3, 1) or
                not deps or any(Path(n).resolve() not in allowed for n in deps)):
            raise ValueError('Require an x86_64 nonloadable object with frozen dependencies')
        imports[label] = set(run(label + '-imports', nm, '-arch', 'x86_64', '-uj', obj).stdout.splitlines())
    pci_exports = set(run('pci-kdk-exports', nm, '-arch', 'x86_64', '-gUj', kdk / PROVIDER).stdout.splitlines())
    if (imports['observer'] != imports['control'] or len(imports['observer']) != 375 or
            b'_thread_call_cancel_wait' not in imports['observer'] or not any(b'11IOPCIDevice' in s for s in pci_exports)):
        raise ValueError('Unexpected observer dependencies or missing inherited admission limitation')
    if (any((ROOT / n).read_bytes() != b for n, b in frozen.items()) or
            sdk_inputs(sdk) != sdk_blobs or file_sha(kdk / PROVIDER) != provider_hash or
            any(file_sha(p) != h for p, h in tools.items())):
        raise ValueError('Input drift during observation preparation')
    print(json.dumps(dict(status='passed-offline-pci-irq-config-observer', branch='upstream34/vram-layout-fix',
                          kernel_build=34, os_version=os_version, os_build=os_build, sdk_commit=SDK_PIN,
                          source_base_commit=BASE, control_source_sha256=sha(control.encode()),
                          observer_source_sha256=sha(observer.encode()), production_inputs_unchanged=len(tracked),
                          asan_ubsan_checks=count, broken_variants_detected=list(mutants),
                          native_objects_compiled=2, native_import_count=len(imports['observer']), new_native_imports=0,
                          inherited_private_import='_thread_call_cancel_wait', native_candidate_admitted=False,
                          live_config_read=False, installed=False, loaded=False, GPU_executed=False,
                          power_actions=0, R3_complete=False), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('out', 'sdk', 'kdk'):
        parser.add_argument('--' + name, required=True, type=Path)
    a = parser.parse_args()
    test(a.out, a.sdk.resolve(), a.kdk.resolve())
