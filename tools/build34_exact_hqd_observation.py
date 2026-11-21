# SPDX-License-Identifier: MIT
"""Stage the internal indexed HQD observation transaction without an MMIO backend."""

from build34_exact_claim_consumer import stage as previous_stage, stage_header
from build34_exact_submit import once


FIELDS = '''    enum class HqdBank { Kiq, Scheduler, Compute, Gfx };
    struct HqdAccess {
        // Read the full selector, resolve a fixed bank, and synchronously check device access.
        bool (*selector)(PhxBringup *, uint32_t *);
        bool (*resolve)(PhxBringup *, HqdBank, uint32_t, uint32_t *);
        bool (*select)(PhxBringup *, uint32_t);
        bool (*sample)(PhxBringup *, HqdBank, uint32_t *);
    };
    const HqdAccess *exactHqdAccess{nullptr}; // unbound; never exposed to user clients
    uint32_t exactHqdUncertain{0};
    IOReturn observeInitialHqd(HqdBank bank, uint32_t *sample);
'''

SIGNATURE = 'IOReturn PhxBringup::observeInitialHqd('
METHOD = '''IOReturn PhxBringup::observeInitialHqd(HqdBank bank, uint32_t *sample) {
    if (!sample || (bank != HqdBank::Kiq && bank != HqdBank::Scheduler &&
                    bank != HqdBank::Compute && bank != HqdBank::Gfx)) return kIOReturnBadArgument;
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock) return kIOReturnNotReady;
    phx34_exact::CallbackGate<1>::Lease writer(exactRawWriters);
    if (!writer) return exactRawWriters.closed() ? kIOReturnNotReady : kIOReturnBusy;
    if (!IOLockTryLock(gpuLock)) return kIOReturnBusy;
    const IOReturn result = [&]() -> IOReturn {
        const auto *io = exactHqdAccess;
        if (!io || !io->selector || !io->resolve || !io->select || !io->sample ||
            exactCallbacks.closed() || exactStopped || isSleeping || exactVMFault ||
            exactQueueAdopted[0] || exactQueueAdopted[1]) return kIOReturnNotReady;
        uint32_t saved = 0, selected = 0, value = 0, confirmed = 0;
        if (!io->selector(this, &saved) || !io->resolve(this, bank, saved, &selected) ||
            exactCallbacks.closed()) return kIOReturnNotReady;

        // Once selection was attempted, restore even if the write reported failure.
        const bool switched = io->select(this, selected);
        const bool before = switched && io->selector(this, &confirmed) && confirmed == selected;
        const bool sampled = before && !exactCallbacks.closed() && io->sample(this, bank, &value);
        const bool after = before && io->selector(this, &confirmed) && confirmed == selected;
        const bool restored = io->select(this, saved) && io->selector(this, &confirmed) && confirmed == saved;
        if (!before || !after || !restored) {
            __atomic_store_n(&exactHqdUncertain, 1u, __ATOMIC_RELEASE);
            exactRawWriters.close();
            return kIOReturnNotReady;
        }
        if (!sampled || exactCallbacks.closed()) return kIOReturnNotReady;
        *sample = value; // a diagnostic sample grants no ownership or drain
        return kIOReturnSuccess;
    }();
    IOLockUnlock(gpuLock);
    return result;
}

'''

ADOPTION_CHECK = '    if (__atomic_load_n(&exactFirmwareUncertain, __ATOMIC_ACQUIRE)) {\n'
NEW_ADOPTION_CHECK = ('    if (__atomic_load_n(&exactFirmwareUncertain, __ATOMIC_ACQUIRE) ||\n'
                      '        __atomic_load_n(&exactHqdUncertain, __ATOMIC_ACQUIRE)) {\n')


def stage(source):
    source = previous_stage(source)
    fields_at = '    bool exactQueueAdopted[2]{}; // gpuLock held; no inferred old-writer drain\n'
    source = once(source, fields_at, fields_at + FIELDS)
    source = once(source, 'IOReturn PhxBringup::adoptQueue(', METHOD + 'IOReturn PhxBringup::adoptQueue(')
    return once(source, ADOPTION_CHECK, NEW_ADOPTION_CHECK)
