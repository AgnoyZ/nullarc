#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Summarize 780M PCI interrupt registry metadata without resolving interrupts."""
import json
import platform
import plistlib
import re
import subprocess

REGISTRY_ID = 'IORegistryEntryID'
CLASS = 'IOObjectClass'
CHILDREN = 'IORegistryEntryChildren'
CONTROLLERS = 'IOInterruptControllers'
SPECIFIERS = 'IOInterruptSpecifiers'
MESSAGED = 'IOPCIMessagedInterruptController'
MSI_MARKER = 'IOPCIMSIMode'
REPORT_LEGEND = 'IOReportLegend'
REPORT_GROUP = 'IOReportGroupName'
IRQ_ACCOUNTING = 'Interrupt Statistics (by index)'
START_CONFIG = 'phx-pci-irq-start-v1'
START_CLASSES = {'both-message-enables-clear', 'msi-enable-set',
                 'msix-enable-set-function-mask-clear', 'msix-enable-set-function-mask-set'}
# At depth two, ioreg omits child properties unless -l is set.
PCI_QUERY = ['/usr/sbin/ioreg', '-a', '-l', '-r', '-d', '2', '-c', 'IOPCIDevice']
PHX_QUERY = ['/usr/sbin/ioreg', '-a', '-r', '-d', '2', '-c', 'PhxBringup']


def entries(value):
    if type(value) is not list or not all(type(item) is dict for item in value):
        raise ValueError('Unexpected registry collection')
    return value


def roots(blob):
    if len(blob) > 8 * 1024 * 1024:
        raise ValueError('Registry snapshot too large')
    return entries(plistlib.loads(blob))


def only(items):
    if len(items) != 1:
        raise ValueError('Expected one registry match')
    return items[0]


def entry_id(entry):
    value = entry.get(REGISTRY_ID)
    if type(value) is not int or not 0 < value < (1 << 64):
        raise ValueError('Invalid registry entry identity')
    return value


def start_config(entry):
    if START_CONFIG not in entry:
        return None
    mode = entry[START_CONFIG]
    if type(mode) is not str or mode not in START_CLASSES:
        raise ValueError('Unknown start-time interrupt classification')
    return mode


def pci_snapshot(blob):
    pci = only([p for p in roots(blob) if p.get(CLASS) == 'IOPCIDevice' and
                p.get('vendor-id') == b'\x02\x10\x00\x00' and p.get('device-id') == b'\x00\x19\x00\x00'])
    child = only([c for c in entries(pci.get(CHILDREN)) if c.get(CLASS) == 'PhxBringup'])
    provider_id, child_id = entry_id(pci), entry_id(child)
    if provider_id == child_id:
        raise ValueError('PCI provider and driver identities overlap')
    if (CONTROLLERS in pci) != (SPECIFIERS in pci):
        raise ValueError('Partial interrupt descriptor pair')
    names, specifiers = pci.get(CONTROLLERS, []), pci.get(SPECIFIERS, [])
    if (type(names) is not list or type(specifiers) is not list or len(names) != len(specifiers) or
            not all(type(n) is str and n for n in names) or not all(type(s) is bytes and s for s in specifiers)):
        raise ValueError('Malformed interrupt descriptor pair')
    marker = pci.get(MSI_MARKER, None)
    if MSI_MARKER in pci and type(marker) is not bool:
        raise ValueError('Malformed PCI MSI marker')
    irq_legend_count = sum(item.get(REPORT_GROUP) == IRQ_ACCOUNTING
                           for item in entries(pci.get(REPORT_LEGEND, [])))
    # Compare raw identities and specifiers only in memory, never in the report.
    return provider_id, child_id, names, specifiers, marker, irq_legend_count, start_config(child)


def summarize(before, service, after, version, build):
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,2}', version) or not re.fullmatch(r'[0-9]+[A-Z][0-9]+[a-z]?', build):
        raise ValueError('Invalid OS build metadata')
    first = pci_snapshot(before)
    if first != pci_snapshot(after):
        raise ValueError('PCI snapshot changed around service observation')
    phx = only(roots(service))
    _, child_id, names, _, marker, irq_legend_count, start_mode = first
    if (entry_id(phx) != child_id or phx.get(CLASS) != 'PhxBringup' or
            type(phx.get('phx-build')) is not int or phx['phx-build'] != 34):
        raise ValueError('Build34 service is not the observed PCI child')
    if start_config(phx) != start_mode:
        raise ValueError('Start-time classification changed around service observation')
    messaged = names.count(MESSAGED)
    status = ('start-time-pci-config-classification' if start_mode else
              'cached-pci-interrupt-descriptors-only' if names else 'no-cached-descriptors-visible')
    return dict(status=status,
                os_version=version, os_build=build, pci='1002:1900', PhxBringup_build=34,
                direct_pci_provider_matched=True, descriptor_count=len(names),
                messaged_controller_count=messaged, other_controller_count=len(names) - messaged,
                msi_registry_marker='absent' if marker is None else 'true' if marker else 'false',
                irq_accounting_legend_count=irq_legend_count,
                start_time_config_classification=start_mode or 'unavailable', loaded_image_identity_checked=False,
                active_interrupt_mode_proved=False, active_isr_proved=False, eop_delivery_proved=False,
                ih_consumer_ownership_proved=False, fence_visibility_proved=False,
                device_opened=False, raw_registry_saved=False)


def collect():
    if platform.system() != 'Darwin':
        raise ValueError('Requires macOS')
    env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C'}

    def read(args):
        return subprocess.run(args, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              check=True, timeout=6).stdout

    version = read(['/usr/bin/sw_vers', '-productVersion']).decode().strip()
    build = read(['/usr/bin/sw_vers', '-buildVersion']).decode().strip()
    return summarize(read(PCI_QUERY), read(PHX_QUERY), read(PCI_QUERY), version, build)


if __name__ == '__main__':
    try:
        print(json.dumps(collect(), sort_keys=True))
    except Exception as error:
        print(json.dumps({'status': 'passive-pci-observation-refused', 'error_type': type(error).__name__}))
        raise SystemExit(1)
