#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Classify the target PCI mapper-parent property without retaining registry data."""
import json
import platform
import plistlib
import re
import subprocess

PCI_QUERY = ['/usr/sbin/ioreg', '-a', '-l', '-r', '-d', '2', '-c', 'IOPCIDevice']
MAX_REGISTRY_BYTES = 8 * 1024 * 1024
TARGET_VENDOR = bytes.fromhex('02100000')
TARGET_DEVICE = bytes.fromhex('00190000')
MAPPER_PROBE_PROPERTIES = (
    'phx-dcn-mapper-probe-requested',
    'phx-dcn-mapper-probe-performed',
    'phx-dcn-mapper-resolved',
    'phx-dcn-mapper-active-at-probe',
)


def roots(blob):
    if type(blob) is not bytes or len(blob) > MAX_REGISTRY_BYTES:
        raise ValueError('Invalid or oversized registry snapshot')
    value = plistlib.loads(blob)
    if type(value) is not list or not all(type(item) is dict for item in value):
        raise ValueError('Unexpected registry collection')
    return value


def classify_mapper_probe(service):
    present = [key in service for key in MAPPER_PROBE_PROPERTIES]
    if not any(present):
        return {
            'runtime_mapper_probe_state': 'not-published',
            'runtime_mapper_probe_requested': None,
            'runtime_mapper_probe_performed': None,
            'runtime_mapper_resolved': None,
            'runtime_mapper_active_at_probe': None,
        }
    if not all(present):
        raise ValueError('Incomplete mapper-probe metadata')
    values = [service[key] for key in MAPPER_PROBE_PROPERTIES]
    if any(type(value) is not bool for value in values):
        raise ValueError('Invalid mapper-probe metadata')
    requested, performed, resolved, active = values
    if (performed and not requested) or (resolved and not performed) or (active and not resolved):
        raise ValueError('Inconsistent mapper-probe metadata')
    if not requested:
        state = 'published-disabled'
    elif not performed:
        state = 'requested-not-performed'
    elif not resolved:
        state = 'performed-unresolved'
    elif active:
        state = 'active-at-probe'
    else:
        state = 'resolved-inactive-at-probe'
    return {
        'runtime_mapper_probe_state': state,
        'runtime_mapper_probe_requested': requested,
        'runtime_mapper_probe_performed': performed,
        'runtime_mapper_resolved': resolved if performed else None,
        'runtime_mapper_active_at_probe': active if performed else None,
    }


def decode_snapshot(blob, os_version, os_build):
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,2}', os_version) or not re.fullmatch(r'[0-9]+[A-Z][0-9]+[a-z]?', os_build):
        raise ValueError('Invalid OS build metadata')
    devices = [entry for entry in roots(blob) if entry.get('IOObjectClass') == 'IOPCIDevice' and
               entry.get('vendor-id') == TARGET_VENDOR and entry.get('device-id') == TARGET_DEVICE]
    if len(devices) != 1:
        raise ValueError('Expected one target PCI provider')
    children = devices[0].get('IORegistryEntryChildren')
    if type(children) is not list:
        raise ValueError('Target PCI child list unavailable')
    services = [entry for entry in children if type(entry) is dict and entry.get('IOObjectClass') == 'PhxBringup' and
                type(entry.get('phx-build')) is int and entry.get('phx-build') == 34]
    if len(services) != 1:
        raise ValueError('Expected one build34 PhxBringup child')
    probe = classify_mapper_probe(services[0])
    if 'iommu-parent' not in devices[0]:
        classification = 'absent'
    else:
        value = devices[0]['iommu-parent']
        if type(value) is not str:
            classification = 'present-non-string'
        elif not value.strip():
            classification = 'present-empty-string'
        else:
            classification = 'present-nonempty-string'
    return {
        'status': 'passive-dcn-mapper-observation',
        'OS_version': os_version,
        'OS_build': os_build,
        'target': '1002:1900',
        'PhxBringup_build': 34,
        'iommu_parent_property': classification,
        **probe,
        'device_dma_domain_proven': False,
        'raw_registry_saved': False,
        'property_value_emitted': False,
    }


def collect():
    if platform.system() != 'Darwin':
        raise ValueError('Passive mapper observation requires macOS')
    env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C'}

    def read(args):
        return subprocess.run(args, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              check=True, timeout=10).stdout

    version = read(['/usr/bin/sw_vers', '-productVersion']).decode().strip()
    build = read(['/usr/bin/sw_vers', '-buildVersion']).decode().strip()
    return decode_snapshot(read(PCI_QUERY), version, build)


if __name__ == '__main__':
    try:
        print(json.dumps(collect(), sort_keys=True))
    except Exception as error:
        print(json.dumps({'status': 'passive-dcn-mapper-observation-refused',
                          'error_type': type(error).__name__}, sort_keys=True))
        raise SystemExit(1)
