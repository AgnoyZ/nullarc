#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record target PCI child-service counts without retaining registry values."""
import json
import platform
import plistlib
import re
import subprocess

import build34_dcn_mapper_observation as mapper

MAX_REGISTRY_BYTES = 8 * 1024 * 1024
CHILD_CLASSES = ('AMDSupport', 'NMXAccel', 'PhxAMDFB', 'PhxBringup', 'PhxDeviceControl')


def decode_snapshot(blob, os_version, os_build):
    if type(blob) is not bytes or len(blob) > MAX_REGISTRY_BYTES:
        raise ValueError('Invalid or oversized registry snapshot')
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,2}', os_version) or not re.fullmatch(r'[0-9]+[A-Z][0-9]+[a-z]?', os_build):
        raise ValueError('Invalid OS build metadata')
    devices = [entry for entry in mapper.roots(blob) if entry.get('IOObjectClass') == 'IOPCIDevice' and
               entry.get('vendor-id') == mapper.TARGET_VENDOR and entry.get('device-id') == mapper.TARGET_DEVICE]
    if len(devices) != 1:
        raise ValueError('Expected one target PCI provider')
    children = devices[0].get('IORegistryEntryChildren')
    if type(children) is not list:
        raise ValueError('Target PCI child list unavailable')
    build34 = [child for child in children if type(child) is dict and child.get('IOObjectClass') == 'PhxBringup' and
               type(child.get('phx-build')) is int and child.get('phx-build') == 34]
    if len(build34) != 1:
        raise ValueError('Expected one build34 PhxBringup child')
    counts = {name: 0 for name in CHILD_CLASSES}
    for child in children:
        if type(child) is not dict:
            raise ValueError('Unexpected target PCI child')
        name = child.get('IOObjectClass')
        if type(name) is str and name in counts:
            counts[name] += 1
    return {
        'status': 'filtered-dcn-route-topology-observation',
        'OS_version': os_version,
        'OS_build': os_build,
        'target': '1002:1900',
        'PhxBringup_build34_child_count': 1,
        'known_direct_child_class_counts': counts,
        'active_hubp_route_observed': False,
        'route_provider_proven': False,
        'device_dma_domain_proven': False,
        'raw_registry_saved': False,
        'property_values_emitted': False,
    }


def collect():
    if platform.system() != 'Darwin':
        raise ValueError('Passive route observation requires macOS')
    env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C'}

    def read(args):
        return subprocess.run(args, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              check=True, timeout=10).stdout

    version = read(['/usr/bin/sw_vers', '-productVersion']).decode().strip()
    build = read(['/usr/bin/sw_vers', '-buildVersion']).decode().strip()
    return decode_snapshot(read(mapper.PCI_QUERY), version, build)


if __name__ == '__main__':
    try:
        print(json.dumps(collect(), sort_keys=True))
    except Exception as error:
        print(json.dumps({'status': 'passive-dcn-route-observation-refused',
                          'error_type': type(error).__name__}, sort_keys=True))
        raise SystemExit(1)
