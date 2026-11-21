# SPDX-License-Identifier: MIT
"""Extend the staged handoff veto to SMU timeouts and reserve known mailboxes."""

from build34_exact_psp_uncertainty import change, stage as previous_stage, stage_header
from build34_exact_submit import once


WRITE = 'IOReturn PhxBringup::writeReg('
SMU = 'IOReturn PhxBringup::smuMessage('
MAILBOX = '''    // The tracked firmware paths own these mailboxes during bootstrap.
    switch (reg) {
        case PHX_PSP_C2PMSG_64:
        case PHX_PSP_C2PMSG_67:
        case PHX_PSP_C2PMSG_69:
        case PHX_PSP_C2PMSG_70:
        case PHX_PSP_C2PMSG_71:
        case PHX_SMU_MSG_REG:
        case PHX_SMU_ARG_REG:
        case PHX_SMU_RESP_REG:
            return kIOReturnNotPermitted;
    }
'''
RESPONSE = '''    *resp = r;
    if (!r) {
        quarantineFirmware();
        *argAfter = 0; // no acknowledged result to read
        IOLockUnlock(smuLock);
        return kIOReturnTimeout;
    }
    *argAfter = rreg(PHX_SMU_ARG_REG);
    IOLockUnlock(smuLock);
    return kIOReturnSuccess;
'''


def shared_latch(source):
    if source.count('exactPspUncertain') != 3 or source.count('quarantinePsp()') != 4:
        raise ValueError('Unexpected PSP latch use')
    return source.replace('exactPspUncertain', 'exactFirmwareUncertain').replace('quarantinePsp()', 'quarantineFirmware()')


def stage(source):
    source = shared_latch(previous_stage(source))
    source = change(source, WRITE, ('    wreg(reg, value);', MAILBOX + '    wreg(reg, value);'))
    return change(source, SMU,
                  ('    *resp = r;\n    *argAfter = rreg(PHX_SMU_ARG_REG);\n    IOLockUnlock(smuLock);\n'
                   '    return r ? kIOReturnSuccess : kIOReturnTimeout;\n', RESPONSE))
