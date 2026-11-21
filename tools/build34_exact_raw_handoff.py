#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage a one-way handoff from raw debug writers to adopted R3 queues.

Source/CPU/native-object prerequisite only. Initial external queue ownership,
device coherency and healthy teardown are not established by this handoff.
"""
from build34_exact_public_timer import stage as previous_stage, stage_header
from build34_exact_submit import once
from test_build34_exact_ownership import method

WRITERS = ('writeReg', 'vramWrite', 'doorbellWrite', 'sysMem', 'smuMessage',
           'pspRing', 'pspSubmit', 'fwStage', 'loadIpFw', 'pspCtl', 'pspRaw')
READERS = ('readRegs', 'vramRead')
SERVICE_LEASE = '''    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback) return kIOReturnNotReady;
'''
WRITER_LEASE = SERVICE_LEASE + '''    phx34_exact::CallbackGate<1>::Lease rawWriter(exactRawWriters);
    if (!rawWriter) return exactRawWriters.closed() ? kIOReturnNotReady : kIOReturnBusy;
    if (exactCallbacks.closed()) return kIOReturnNotReady;
'''
HANDOFF = '''    // Neither a new generation nor an adoption seed proves old writers drained.
    if (exactQueueAdopted[qi]) {
        IOLockUnlock(gpuLock);
        return kIOReturnExclusiveAccess;
    }
    exactRawWriters.close(); // irreversible; no wait while holding gpuLock
    if (!exactRawWriters.drained()) {
        IOLockUnlock(gpuLock);
        return kIOReturnBusy; // admitted debug writer owns its service lease until return
    }
    if (exactCallbacks.closed()) {
        IOLockUnlock(gpuLock);
        return kIOReturnNotReady;
    }
    exactQueueAdopted[qi] = true; // never reset by invalidation, sleep, fault or stop
'''
RANGES = '''    const uint64_t starts[3] = {ringOff, wbOff, fenceOff};
    const uint64_t sizes[3] = {ringDw * 4, 32, 8};
    const auto overlaps = [](uint64_t a, uint64_t n, uint64_t b, uint64_t m) {
        return a <= b ? b - a < n : a - b < m;
    };
    for (uint32_t i = 0; i < 3; ++i)
        for (uint32_t j = 0; j < i; ++j)
            if (overlaps(starts[i], sizes[i], starts[j], sizes[j])) return kIOReturnBadArgument;
'''
PEER = '''    if (exactQueueAdopted[qi ^ 1u]) {
        const GpuQueue &peer = gq[qi ^ 1u];
        const uint64_t peerStarts[3] = {peer.ringOff, peer.wbOff, peer.fenceOff};
        const uint64_t peerSizes[3] = {uint64_t(peer.ringDw) * 4, 32, 8};
        bool alias = dbByte == peer.dbByte;
        for (uint32_t i = 0; i < 3; ++i)
            for (uint32_t j = 0; j < 3; ++j)
                alias = alias || overlaps(starts[i], sizes[i], peerStarts[j], peerSizes[j]);
        if (alias) {
            IOLockUnlock(gpuLock);
            return kIOReturnBadArgument;
        }
    }
'''
BOOTSTRAP = '''// R3: finish every raw setup operation before the first one-way queue handoff.
static uint64_t phx34Adoption[2][6];
static unsigned phx34AdoptionPending, phx34AdoptionFault;
static void phx34DeferAdoption(const uint64_t in[6])
{
   const unsigned qi = in[5] & 1u;
   if (phx34AdoptionFault || (phx34AdoptionPending & (1u << qi))) {
      phx34AdoptionFault = 1;
      return;
   }
   memcpy(phx34Adoption[qi], in, sizeof(phx34Adoption[qi]));
   phx34AdoptionPending |= 1u << qi;
}
static int phx34CommitAdoptions(void)
{
   if (phx34AdoptionFault) return 74;
   for (unsigned qi = 0; qi < 2; ++qi) {
      if (!(phx34AdoptionPending & (1u << qi))) continue;
      kern_return_t kr = IOConnectCallScalarMethod(conn, SEL_DBG_ADOPTQ, phx34Adoption[qi], 6, NULL, NULL);
      printf(qi ? "adopt gfx queue -> kr 0x%x\\n" : "adopt queue -> kr 0x%x\\n", kr);
      if (kr) {
         phx34AdoptionFault = 1; // no retry/reopen/rollback of an earlier successful handoff
         return 74;
      }
      phx34AdoptionPending &= ~(1u << qi);
   }
   return 0;
}

'''


def stage(source):
    source = previous_stage(source)
    source = once(source, '    mutable phx34_exact::CallbackGate<> exactCallbacks;\n',
                  '    mutable phx34_exact::CallbackGate<> exactCallbacks;\n'
                  '    phx34_exact::CallbackGate<1> exactRawWriters; // exclusive raw transaction, one-way close\n'
                  '    bool exactQueueAdopted[2]{}; // gpuLock held; no inferred old-writer drain\n')
    for name in WRITERS + READERS:
        old = method(source, 'IOReturn PhxBringup::' + name + '(')
        guard = WRITER_LEASE if name in WRITERS else SERVICE_LEASE
        brace = old.index('{\n') + 2
        source = once(source, old, old[:brace] + guard + old[brace:])
    old = method(source, 'IOReturn PhxBringup::adoptQueue(')
    new = once(old, '    exactFenceWindow[qi].invalidate();\n', HANDOFF + '    exactFenceWindow[qi].invalidate();\n')
    # User scalars are 64-bit. Reject wrap before any ownership or mapping mutation.
    new = once(new,
               '        ringOff + ringDw * 4 > fbAperLen || (wbOff & 7) || wbOff + 32 > fbAperLen || (fenceOff & 7) ||\n'
               '        fenceOff + 8 > fbAperLen || (dbByte & 7) || dbByte + 8 > doorbellMap->getLength())\n',
               '        ringOff > fbAperLen || ringDw * 4 > fbAperLen - ringOff || (wbOff & 7) ||\n'
               '        wbOff > fbAperLen || 32 > fbAperLen - wbOff || (fenceOff & 7) ||\n'
               '        fenceOff > fbAperLen || 8 > fbAperLen - fenceOff || (dbByte & 7) ||\n'
               '        dbByte > doorbellMap->getLength() || 8 > doorbellMap->getLength() - dbByte)\n')
    new = once(new, '    IOLockLock(gpuLock);\n', RANGES + '    IOLockLock(gpuLock);\n')
    new = once(new, '    exactRawWriters.close();', PEER + '    exactRawWriters.close();')
    return once(source, old, new)


def stage_bootstrap(source):
    source = once(source, 'static io_connect_t conn;\n', 'static io_connect_t conn;\n\n' + BOOTSTRAP)
    for text in [
        '      kern_return_t kr = IOConnectCallScalarMethod(conn, SEL_DBG_ADOPTQ, in, 6, NULL, NULL);\n'
        '      printf("adopt queue -> kr 0x%x\\n", kr);\n',
        '      kern_return_t kr = IOConnectCallScalarMethod(conn, SEL_DBG_ADOPTQ, in, 6, NULL, NULL);\n'
        '      printf("adopt gfx queue -> kr 0x%x\\n", kr);\n',
    ]:
        source = once(source, text, '      phx34DeferAdoption(in);\n')
    return once(source, '   if (all || !strcmp(argv[1], "kiq")) kiq_test();\n   return 0;\n',
                '   if (all || !strcmp(argv[1], "kiq")) kiq_test();\n   return phx34CommitAdoptions();\n')
