// SPDX-License-Identifier: MIT
#include "paired-fixture.inc"

static constexpr uint64_t gfx[6] = {0x20000, 1024, 0x22000, 8, 8, 0x23001};

static void pair(PhxBringup &d) {
    CHECK(d.adoptQueue(queue) == kIOReturnSuccess && d.adoptQueue(gfx) == kIOReturnSuccess);
    d.pciModel.child = &d;
    d.parent = &d.pciModel;
    d.bringupClass = true;
}

static void healthy(PhxBringup &d) {
    NVAccel a;
    CHECK(a.start(&d.pciModel) && a.starts == 1 && !a.stops && a.publishes == 1);
    CHECK(d.refs == 1 && !OSSymbol::count && !d.exactCallbacks.active());
}

static void invalidate(PhxBringup &d) {
    CHECK(d.setPowerState(0, nullptr) == IOPMAckImplied);
    CHECK(d.setPowerState(1, nullptr) == IOPMAckImplied);
    CHECK(!d.isSleeping && d.gpuReady());
}

#ifdef PRIOR
int main() {
    PhxBringup d;
    pair(d);
    CHECK(d.claimAccel() == kIOReturnSuccess && d.pciModel.matches == 1);
    invalidate(d);
    CHECK(d.pciModel.marker == kOSBooleanTrue && !d.exactQueueLive[0] && !d.exactQueueLive[1]);
    healthy(d); // Deferred matching used the old successful marker after sleep/wake.
    std::printf("PASS %u prior checks\n", checks);
}
#else
static void refused(IOService *provider) {
    NVAccel a;
    CHECK(!a.start(provider) && !a.starts && !a.stops && !a.publishes);
    CHECK(!OSSymbol::count);
}

static void deferred() {
    refused(nullptr);
    IOService ordinary;
    refused(&ordinary);
    PhxBringup d;
    pair(d);
    d.pciModel.marker = kOSBooleanTrue;
    refused(&d.pciModel); // Preexisting marker without an issued ticket.
    CHECK(d.claimAccel() == kIOReturnExclusiveAccess && !d.pciModel.matches);
    d.pciModel.marker = nullptr;
    d.pciModel.propertyOK = false;
    CHECK(d.claimAccel() == kIOReturnNoResources && !d.exactClaimDevice);
    d.pciModel.propertyOK = true;
    CHECK(d.claimAccel() == kIOReturnSuccess && d.pciModel.matches == 1);
    healthy(d);
    NVAccel familyFailure;
    familyFailure.familyOK = false;
    CHECK(!familyFailure.start(&d.pciModel) && familyFailure.starts == 1 && !familyFailure.stops && !familyFailure.publishes);
    CHECK(d.refs == 1 && !OSSymbol::count);

    IOPCIDevice other;
    other.child = &d;
    other.marker = kOSBooleanTrue;
    refused(&other); // Even a stale category result from the wrong provider cannot start.
    d.parent = &other;
    refused(&other); // A sibling shape alone cannot substitute for native PCI identity.
    d.parent = &d.pciModel;
    d.bringupClass = false;
    refused(&d.pciModel);
    d.bringupClass = true;
    d.inactive = true;
    refused(&d.pciModel);
    d.inactive = false;
    IOService legacy;
    legacy.parent = &d.pciModel;
    legacy.bringupClass = true;
    d.pciModel.child = &legacy;
    refused(&d.pciModel);
    CHECK(legacy.refs == 1);
    d.pciModel.child = &d;

    const auto *name = OSSymbol::withCStringNoCopy(platformName);
    CHECK(d.callPlatformFunction(name, true, &d.pciModel, nullptr, nullptr, nullptr) == kIOReturnBadArgument);
    CHECK(d.callPlatformFunction(name, false, nullptr, nullptr, nullptr, nullptr) == kIOReturnBadArgument);
    CHECK(d.callPlatformFunction(name, false, &d.pciModel, &other, nullptr, nullptr) == kIOReturnBadArgument);
    CHECK(d.callPlatformFunction(name, false, &other, nullptr, nullptr, nullptr) == kIOReturnNotReady);
    name->release();
    for (uint64_t &generation : d.exactQueueGeneration) {
        ++generation;
        refused(&d.pciModel);
        --generation;
    }
    ++d.exactInvalidationEpoch;
    refused(&d.pciModel);
    CHECK(d.claimAccel() == kIOReturnNotReady && d.pciModel.matches == 1);
    --d.exactInvalidationEpoch;
    d.exactVMFault = true;
    refused(&d.pciModel);
    d.exactVMFault = false;
    invalidate(d);
    CHECK(d.pciModel.marker == kOSBooleanTrue);
    refused(&d.pciModel);
    CHECK(d.refs == 1);
}

static void stopAfterScheduling() {
    PhxBringup d;
    pair(d);
    CHECK(d.claimAccel() == kIOReturnSuccess);
    CHECK(d.exactCallbacks.close()); // Same gate closed by staged stop before metadata invalidation.
    refused(&d.pciModel);
}

static void pauseClaim(bool alreadyArmed) {
    PhxBringup d;
    pair(d);
    Pause pause;
    IOReturn r = -1;
    std::thread writer([&] {
        (alreadyArmed ? duringMatch : duringProperty) = &pause;
        r = d.claimAccel();
    });
    pause.wait();
    CHECK(d.pciModel.marker == kOSBooleanTrue && d.pciModel.refs == 2);
    if (alreadyArmed) CHECK(d.exactCallbacks.close());
    refused(&d.pciModel);
    pause.release();
    writer.join();
    CHECK(d.pciModel.refs == 1 && !d.exactCallbacks.active());
    if (alreadyArmed) {
        CHECK(r == kIOReturnNotReady && !d.pciModel.marker && d.pciModel.removals == 1 && !d.exactClaimArmed);
        d.pciModel.marker = kOSBooleanTrue;
        refused(&d.pciModel);
    } else {
        CHECK(r == kIOReturnSuccess && d.pciModel.matches == 1);
        healthy(d);
    }
}

static void duringStart(bool replaceSibling) {
    PhxBringup d;
    pair(d);
    CHECK(d.claimAccel() == kIOReturnSuccess);
    NVAccel a;
    Pause pause;
    bool started = true;
    std::thread consumer([&] { inFamilyStart = &pause; started = a.start(&d.pciModel); });
    pause.wait();
    CHECK(d.refs == 2);
    PhxBringup replacement;
    if (replaceSibling) {
        pair(replacement);
        replacement.pci = &d.pciModel;
        replacement.parent = &d.pciModel;
        replacement.pciModel.child = nullptr;
        d.parent = nullptr;
        d.pciModel.child = &replacement;
    } else {
        invalidate(d);
    }
    pause.release();
    consumer.join();
    CHECK(!started && a.starts == 1 && a.stops == 1 && !a.publishes && d.refs == 1 && replacement.refs == 1);
}

static void lockContention() {
    PhxBringup d;
    pair(d);
    CHECK(d.claimAccel() == kIOReturnSuccess);
    Pause held;
    std::thread locker([&] { IOLockLock(d.gpuLock); held.arrive(); IOLockUnlock(d.gpuLock); });
    held.wait();
    refused(&d.pciModel);
    held.release();
    locker.join();
    CHECK(d.claimAccel() == kIOReturnSuccess && d.pciModel.matches == 2 && d.pciModel.properties == 1);
    healthy(d);
}

int main() {
    deferred();
    stopAfterScheduling();
    pauseClaim(false);
    pauseClaim(true);
    duringStart(false);
    duringStart(true);
    lockContention();
    std::printf("PASS %u paired checks\n", checks);
}
#endif
