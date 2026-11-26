#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Derive an opt-in source-only runtime mapper lookup observer for exact build34."""
import hashlib


DRIVER_SHA256 = '81f45aa2e8166bc6ebed4106129bebebfd70f9b4bbea6dbe389be46263e3c699'
INCLUDE = '#include <IOKit/pci/IOPCIDevice.h>\n'
PROBE_INCLUDE = '#include "PhxDcnMapperProbe.h"\n'
START_ANCHOR = '    pci->retain();\n'
PROBE = '''    int dcnMapperProbeArg = 0;
    const bool dcnMapperProbeRequested = PE_parse_boot_argn("-phx-dcnmapperprobe", &dcnMapperProbeArg,
                                                            sizeof(dcnMapperProbeArg));
    const bool dcnMapperProbeTarget = dcnMapperProbeRequested &&
        pci->configRead32(kIOPCIConfigVendorID) == 0x19001002u;
    const auto dcnMapperProbe = dcnMapperProbeTarget ? build34::dcn::probeDeviceMapperNoWait<IOMapper>(pci) :
        build34::dcn::MapperProbeResult{};
    setProperty("phx-dcn-mapper-probe-requested", dcnMapperProbeRequested);
    setProperty("phx-dcn-mapper-probe-performed", dcnMapperProbe.attempted);
    setProperty("phx-dcn-mapper-resolved", dcnMapperProbe.resolved);
    setProperty("phx-dcn-mapper-active-at-probe", dcnMapperProbe.activeAtProbe);
    setProperty("phx-dcn-address-domain-proven", false);
'''


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('build34 mapper-probe source anchor drift')
    return source.replace(old, new, 1)


def stage(driver):
    if type(driver) is not bytes or hashlib.sha256(driver).hexdigest() != DRIVER_SHA256:
        raise ValueError('build34 mapper-probe driver source drift')
    source = driver.decode('utf-8')
    if '#define PHX_KEXT_BUILD 34u\n' not in source:
        raise ValueError('mapper probe requires exact build34 source')
    source = once(source, INCLUDE, INCLUDE + PROBE_INCLUDE)
    source = once(source, START_ANCHOR, START_ANCHOR + PROBE)
    return source.encode('utf-8')
