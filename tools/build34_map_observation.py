#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage BAR0 map-option metadata or read existing properties passively.

This is observation preparation, never a coherent reader, cache-mode change,
candidate admission, device open, deployment or GPU test. No raw registry data
is printed or saved by the collector.
"""
import hashlib
import json
import platform
import plistlib
import subprocess

BASE_COMMIT = '194ce9098b34c9f48483ff0729a50b21c5ca0401'
BASE_SHA = '81f45aa2e8166bc6ebed4106129bebebfd70f9b4bbea6dbe389be46263e3c699'
FACTORY_SHA = 'ff3ec08c030055d678fcf524e60dd06bdaaa877f9f4a0e840f37ea530f0df6df'
OPTION = 'phx-bar0-map-options'
CACHE = 'phx-bar0-map-cache-option'
VERSION = 'phx-bar0-map-observation-version'
ANCHOR = '''    if (fbAper) {
        fbAperLen = fbAper->getLength();
        fbAperPhys = fbAper->getPhysicalAddress();
    }
'''
OBSERVATION = '''        // Mapping options only: this is NOT effective PAT/coherency proof.
        const IOOptionBits observedBar0MapOptions = fbAper->getMapOptions();
        const bool optionsPublished = setProperty("phx-bar0-map-options", static_cast<uint64_t>(observedBar0MapOptions), 32);
        const bool cachePublished = setProperty("phx-bar0-map-cache-option",
            static_cast<uint64_t>((observedBar0MapOptions & kIOMapCacheMask) >> kIOMapCacheShift), 32);
        if (optionsPublished && cachePublished)
            setProperty("phx-bar0-map-observation-version", static_cast<uint64_t>(1), 32);
'''


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def insert_observation(source):
    if sha(source.encode()) not in (BASE_SHA, FACTORY_SHA) or source.count(ANCHOR) != 1:
        raise ValueError('Require exact accepted R1b or frozen factory source')
    replacement = ANCHOR[:-6] + OBSERVATION + '    }\n'
    result = source.replace(ANCHOR, replacement, 1)
    if result.replace(OBSERVATION, '', 1) != source:
        raise ValueError('Unexpected source delta outside mapping observation')
    return result


def stage_baseline(source):
    if sha(source.encode()) != BASE_SHA:
        raise ValueError('Require exact accepted R1b baseline')
    return insert_observation(source)


def stage_factory(source):
    if sha(source.encode()) != BASE_SHA:
        raise ValueError('Require exact accepted R1b production input')
    from build34_exact_factory import stage
    staged = stage(source)
    if sha(staged.encode()) != FACTORY_SHA:
        raise ValueError('Frozen source-only factory stage changed')
    return insert_observation(staged)


def decode_snapshot(blob, os_version, os_build):
    """Whitelist one root service; missing metadata cannot admit any reader."""
    if not isinstance(blob, bytes) or len(blob) > 8 * 1024 * 1024:
        raise ValueError('Invalid or oversized registry snapshot')
    roots = plistlib.loads(blob)
    if type(roots) is not list or len(roots) != 1 or type(roots[0]) is not dict:
        raise ValueError('Require exactly one root PhxBringup service')
    node = roots[0]

    def uint(name, bits):
        value = node.get(name)
        if type(value) is not int or not 0 <= value < 1 << bits:
            raise ValueError('Missing or invalid admitted registry property')
        return value

    if uint('phx-build', 32) != 34:
        raise ValueError('Require build34 service')
    length = uint('phx-fb-aper-len', 64)
    if not length:
        raise ValueError('Require nonempty BAR0 aperture')
    result = dict(schema_version=1, OS_version=os_version, OS_build=os_build,
                  kernel_build=34, BAR0_bytes=length,
                  status='mapping-metadata-unavailable',
                  effective_cache_proven=False, mapping_coherency_proven=False,
                  loaded_image_identity_checked=False, native_reader_admitted=False,
                  device_opened=False, GPU_submissions=0, power_actions=0,
                  raw_registry_saved=False)
    present = [name in node for name in (OPTION, CACHE, VERSION)]
    if not any(present):
        return result
    if not all(present) or uint(VERSION, 32) != 1:
        raise ValueError('Incomplete or unknown mapping-observation schema')
    options, cache = uint(OPTION, 32), uint(CACHE, 32)
    if cache != (options & 0xf00) >> 8:
        raise ValueError('Map options and cache field disagree')
    result.update(status='mapping-options-observed-not-reader-admitted',
                  observation_version=1, map_options=options, cache_option=cache,
                  default_cache_option=(cache == 0),
                  cache_option_known_to_pinned_SDK=(cache <= 9))
    return result


def collect():
    if platform.system() != 'Darwin':
        raise ValueError('Passive native registry observation requires macOS')
    env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C'}

    def read(args):
        return subprocess.run(args, env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, check=True, timeout=15).stdout

    version = read(['/usr/bin/sw_vers', '-productVersion']).decode().strip()
    build = read(['/usr/bin/sw_vers', '-buildVersion']).decode().strip()
    return decode_snapshot(read(['/usr/sbin/ioreg', '-r', '-c', 'PhxBringup', '-a']), version, build)


if __name__ == '__main__':
    try:
        report = collect()
    except Exception as error:
        # Subprocess/plist errors can contain raw diagnostics. Publish type only.
        print(json.dumps({'status': 'passive-observation-refused', 'error_type': type(error).__name__}))
        raise SystemExit(1)
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(2 if report['status'] == 'mapping-metadata-unavailable' else 0)
