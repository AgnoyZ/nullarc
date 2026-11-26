"""Add a one-shot sanitized firmware-HUBP sample to exact build34 PhxFB."""

import build34_dcn_firmware_home_stage as firmware
from build34_exact_submit import once


SCHEMA = 'phx-dcn-firmware-sample-v1'
ATTEMPTED = 'phx-dcn-firmware-sample-attempted'
VALID = 'phx-dcn-firmware-sample-valid'
ROUTE_PROVEN = 'phx-dcn-route-provider-proven'
DOMAIN_PROVEN = 'phx-dcn-device-dma-domain-proven'

OBSERVER = (
    '\n    bool fDcnFirmwareObservationAttempted = false;\n\n'
    '    void observeDcnFirmwareOnce() {\n'
    '        if (!fDcnFirmwareLock || !IOLockTryLock(fDcnFirmwareLock)) return;\n'
    '        if (!fDcnFirmwareReady || !fDcnFirmwarePower || fDcnFirmwareClosed || fDcnFirmwareObservationAttempted) {\n'
    '            IOLockUnlock(fDcnFirmwareLock);\n'
    '            return;\n'
    '        }\n'
    '        fDcnFirmwareObservationAttempted = true;\n'
    '        const void *expectedPci = fPCI;\n'
    '        IOLockUnlock(fDcnFirmwareLock);\n\n'
    '        build34::dcn::FirmwareScanoutSample sample{};\n'
    '        const IOReturn result = sampleDcnFirmware(expectedPci, sample);\n'
    '        const bool valid = result == kIOReturnSuccess && sample.valid();\n'
    '        setProperty("phx-dcn-firmware-sample-v1", 1u, 32);\n'
    '        setProperty("phx-dcn-firmware-sample-attempted", true);\n'
    '        setProperty("phx-dcn-firmware-sample-valid", valid);\n'
    '        setProperty("phx-dcn-route-provider-proven", false);\n'
    '        setProperty("phx-dcn-device-dma-domain-proven", false);\n'
    '    }\n'
)


def stage(framebuffer):
    source = firmware.stage(framebuffer)
    source = once(source, firmware.FIELDS, firmware.FIELDS + OBSERVER)
    power = (
        '        fDcnFirmwarePower = on;\n'
        '        if (!on && fDcnFirmwareReady) fDcnFirmwareClosed = true;\n'
        '        IOLockUnlock(fDcnFirmwareLock);\n'
    )
    source = once(source, power, power + '        if (on) observeDcnFirmwareOnce();\n')
    ready = (
        '    if (fDcnFirmwareLock) {\n'
        '        IOLockLock(fDcnFirmwareLock);\n'
        '        fDcnFirmwareReady = true;\n'
        '        IOLockUnlock(fDcnFirmwareLock);\n'
        '    }\n'
    )
    source = once(source, ready, ready + '    observeDcnFirmwareOnce();\n')
    return source
