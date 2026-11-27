#!/usr/bin/env python3
"""Report build34 UMA geometry and missing ownership evidence without retaining raw data."""
import json
import platform
import re
import subprocess

import build34_dcn_mapper_observation as mapper
import build34_dcn_route_observation as route

MIB = 1 << 20
FB_ALIGNMENT = 16 * MIB
BAR_BYTES = 256 * MIB
MC_BASE = 0x8000000000
ADDRESS_LIMIT = 1 << 48
GEOMETRY_KEYS = ('phx-fb-mc-base', 'phx-fb-phys', 'phx-fb-size', 'phx-fb-aper-len')
DISCOVERY_KEYS = ('phx-discovery-offset', 'phx-discovery-signature', 'phx-discovery-bin')
DISCOVERY_SIGNATURE = 0x28211407
VERSION_QUERY = ['/usr/bin/sw_vers', '-productVersion']
BUILD_QUERY = ['/usr/bin/sw_vers', '-buildVersion']


def direct_child(children, name):
    matches = [entry for entry in children if entry.get('IOObjectClass') == name]
    if len(matches) > 1:
        raise ValueError('Ambiguous target PCI child')
    return matches[0] if matches else None


def geometry(service):
    values = [service.get(key) for key in GEOMETRY_KEYS]
    if any(type(value) is not int for value in values):
        raise ValueError('Missing or invalid geometry metadata')
    mc_base, backing_base, size, bar_size = values
    if (mc_base != MC_BASE or not 0 < backing_base < ADDRESS_LIMIT or bar_size != BAR_BYTES or
            not BAR_BYTES <= size <= min(ADDRESS_LIMIT - mc_base, ADDRESS_LIMIT - backing_base) or
            (backing_base | size) & (FB_ALIGNMENT - 1)):
        raise ValueError('Unsupported build34 aperture geometry')
    return size // MIB, bar_size // MIB


def discovery_sample(service, uma_bytes):
    if service is None:
        return 'service-absent'
    present = [key in service for key in DISCOVERY_KEYS]
    if not any(present):
        return 'not-published'
    if not all(present):
        return 'incomplete'
    offset, signature, data = [service[key] for key in DISCOVERY_KEYS]
    if (type(offset) is not int or not 0 <= offset < uma_bytes or offset % 4 or
            type(signature) is not int or signature != DISCOVERY_SIGNATURE or
            type(data) is not bytes or not 4 <= len(data) <= min(64 << 10, uma_bytes - offset) or
            len(data) % 4 or int.from_bytes(data[:4], 'little') != DISCOVERY_SIGNATURE):
        return 'sample-invalid'
    return 'sample-present'


def hubp_sample(service):
    if service is None:
        return 'service-absent'
    present = [key in service for key in route.FIRMWARE_SAMPLE_PROPERTIES]
    if any(present) and not all(present):
        return 'incomplete'
    try:
        return route.classify_firmware_sample(service)['firmware_hubp_sample_state']
    except ValueError:
        return 'sample-invalid'


def decode_snapshot(blob, os_version, os_build):
    if (not re.fullmatch(r'[0-9]{1,3}(?:\.[0-9]{1,3}){1,2}', os_version) or
            not re.fullmatch(r'[0-9]{1,3}[A-Z][0-9]{1,6}[a-z]?', os_build)):
        raise ValueError('Invalid OS build metadata')
    devices = [entry for entry in mapper.roots(blob) if entry.get('IOObjectClass') == 'IOPCIDevice' and
               entry.get('vendor-id') == mapper.TARGET_VENDOR and entry.get('device-id') == mapper.TARGET_DEVICE]
    if len(devices) != 1:
        raise ValueError('Expected one target PCI provider')
    children = devices[0].get('IORegistryEntryChildren')
    if type(children) is not list or any(type(child) is not dict for child in children):
        raise ValueError('Invalid target PCI children')
    service = direct_child(children, 'PhxBringup')
    if service is None or type(service.get('phx-build')) is not int or service['phx-build'] != 34:
        raise ValueError('Expected one build34 PhxBringup child')
    uma_mib, bar0_mib = geometry(service)
    return {
        'status': 'geometry-observed-ownership-unproven',
        'OS_version': os_version,
        'OS_build': os_build,
        'target': '1002:1900',
        'PhxBringup_build': 34,
        'firmware_uma_mib': uma_mib,
        'bar0_mib': bar0_mib,
        'discovery_sample_state': discovery_sample(direct_child(children, 'PhxProbe'), uma_mib * MIB),
        'firmware_hubp_sample_state': hubp_sample(direct_child(children, 'PhxAMDFB')),
        'complete_reservation_map_proven': False,
        'exclusive_ownership_proven': False,
        'pool_admission_permitted': False,
        'raw_registry_saved': False,
    }


def collect():
    if platform.system() != 'Darwin':
        raise ValueError('Passive UMA observation requires macOS')
    env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C'}

    def read(args):
        return subprocess.run(args, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              check=True, timeout=10).stdout

    return decode_snapshot(read(mapper.PCI_QUERY), read(VERSION_QUERY).decode().strip(),
                           read(BUILD_QUERY).decode().strip())


def main():
    try:
        print(json.dumps(collect(), sort_keys=True))
    except Exception:
        print(json.dumps({'status': 'passive-uma-observation-refused', 'pool_admission_permitted': False},
                         sort_keys=True))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
