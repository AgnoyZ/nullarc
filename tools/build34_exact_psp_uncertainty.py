# SPDX-License-Identifier: MIT
"""Stage a terminal handoff veto for published PSP work without an observed response."""

from build34_exact_factory import stage as previous_stage, stage_header
from build34_exact_submit import once
from test_build34_exact_ownership import method


FIELD = '    uint32_t exactPspUncertain{0}; // sticky; never reset by ring teardown or queue invalidation\n'
HELPER = '''    void quarantinePsp() {
        // Called while owning the exclusive raw writer lease. Closing that
        // gate stops further CPU writes but cannot cancel a published command.
        __atomic_store_n(&exactPspUncertain, 1u, __ATOMIC_RELEASE);
        exactRawWriters.close();
    }
'''
ADOPT = 'IOReturn PhxBringup::adoptQueue('
RING = 'IOReturn PhxBringup::pspRing('
COMMAND = 'IOReturn PhxBringup::pspRunCmd('
SIGNATURES = (ADOPT, RING, COMMAND)


def change(source, signature, *replacements):
    original = method(source, signature)
    updated = original
    for old, new in replacements:
        updated = once(updated, old, new)
    return once(source, original, updated)


def stage(source):
    source = previous_stage(source)
    source = once(source, '    uint64_t exactQueueSubmitted[2]', FIELD + HELPER + '    uint64_t exactQueueSubmitted[2]')
    source = change(source, ADOPT,
                    ('    exactQueueAdopted[qi] = true;',
                     '    if (__atomic_load_n(&exactPspUncertain, __ATOMIC_ACQUIRE)) {\n'
                     '        IOLockUnlock(gpuLock);\n'
                     '        return kIOReturnNotReady;\n'
                     '    }\n'
                     '    exactQueueAdopted[qi] = true;'))
    source = change(source, RING,
                    ('                    ringMc = 0;              // not established: allow destroy + retry',
                     '                    quarantinePsp();        // keep the uncertain ring address reserved'),
                    ('        if (!pspWaitTos(2000))\n            r = kIOReturnTimeout;\n        clearRing();',
                     '        if (!pspWaitTos(2000)) {\n'
                     '            r = kIOReturnTimeout;\n'
                     '            quarantinePsp();\n'
                     '        } else {\n'
                     '            clearRing();\n'
                     '        }'))
    return change(source, COMMAND,
                  ('    uint32_t status = cmd[PHX_PSP_GFX_RESP_OFFSET / 4];\n'
                   '    // Always succeed at the transport level so IOKit delivers the outputs; the PSP result is in out[].\n'
                   '    // out[1] = elapsed us (≈budget on a fence timeout), so userspace distinguishes timeout from a status code.\n'
                   '    out[0] = (observed == fence) ? status : 0xFFFFFFFFu;  // 0xFFFFFFFF = fence never arrived\n'
                   '    out[1] = us;',
                   '    // Preserve the transport/result split, but do not read a response the PSP may still write.\n'
                   '    out[1] = us;\n'
                   '    if (observed != fence) {\n'
                   '        quarantinePsp();\n'
                   '        out[0] = 0xFFFFFFFFu;\n'
                   '        out[2] = out[3] = 0;\n'
                   '        return kIOReturnSuccess;\n'
                   '    }\n'
                   '    out[0] = cmd[PHX_PSP_GFX_RESP_OFFSET / 4];'))
