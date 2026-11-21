// SPDX-License-Identifier: MIT
#include "firmware-fixture.inc"

static constexpr uint64_t gfx[6] = {0x20000, 1024, 0x22000, 8, 8, 0x23001};
static constexpr uint64_t aliasedGfx[6] = {0x20000, 1024, 0x22000, 0, 8, 0x23001};

static void pair(PhxBringup &d) {
    CHECK(d.adoptQueue(queue) == kIOReturnSuccess);
    CHECK(d.adoptQueue(gfx) == kIOReturnSuccess);
}

static void refused(PhxBringup &d) {
    CHECK(d.claimAccel() == kIOReturnNotReady);
    CHECK(!d.pciModel.properties && !d.pciModel.matches && d.pciModel.refs == 1);
    CHECK(!d.exactCallbacks.active());
}

static void priorClaim() {
    PhxBringup partial;
    CHECK(partial.adoptQueue(queue) == kIOReturnSuccess);
    CHECK(partial.adoptQueue(aliasedGfx) == kIOReturnBadArgument && partial.gpuReady());
    CHECK(partial.claimAccel() == kIOReturnSuccess && partial.pciModel.matches == 1);

    PhxBringup failed;
    pair(failed);
    failed.pciModel.propertyOK = false;
    CHECK(failed.claimAccel() == kIOReturnSuccess && failed.pciModel.matches == 1);
}

static void closeDuringClaim(bool beforeSnapshot) {
    PhxBringup d;
    pair(d);
    Pause pause;
    IOReturn result = -1;
    std::thread claim([&] {
        (beforeSnapshot ? beforeGpuLock : afterGpuUnlock) = &pause;
        result = d.claimAccel();
    });
    pause.wait();
    CHECK(d.exactCallbacks.active() == 1);
    CHECK(d.pciModel.refs == (beforeSnapshot ? 1u : 2u));
    CHECK(d.exactCallbacks.close() && !d.exactCallbacks.drained());
    pause.release();
    claim.join();
    CHECK(result == kIOReturnNotReady && d.exactCallbacks.drained());
    CHECK(!d.pciModel.properties && !d.pciModel.matches && d.pciModel.refs == 1);
}

static void checkedClaim() {
    PhxBringup empty;
    refused(empty);
    CHECK(empty.adoptQueue(queue) == kIOReturnSuccess);
    CHECK(empty.adoptQueue(aliasedGfx) == kIOReturnBadArgument && empty.gpuReady());
    refused(empty);
    PhxBringup graphicsOnly;
    CHECK(graphicsOnly.adoptQueue(gfx) == kIOReturnSuccess && graphicsOnly.gpuReady());
    refused(graphicsOnly);

    for (unsigned unavailable = 0; unavailable < 10; ++unavailable) {
        PhxBringup d;
        pair(d);
        switch (unavailable) {
            case 0: d.gq[0].ready = false; break;
            case 1: d.gq[1].ready = false; break;
            case 2: d.exactQueueLive[0] = false; break;
            case 3: d.exactQueueLive[1] = false; break;
            case 4: d.isSleeping = true; break;
            case 5: d.exactStopped = true; break;
            case 6: d.exactVMFault = true; break;
            case 7: d.exactCallbacks.close(); break;
            case 8: d.pci = nullptr; break;
            case 9: d.gpuLock = nullptr; break;
        }
        CHECK(d.gpuReady()); // discovery cannot reopen the mock fallback
        refused(d);
    }

    PhxBringup live;
    pair(live);
    live.pciModel.checkLease = &live.exactCallbacks;
    live.pciModel.propertyOK = false;
    CHECK(live.claimAccel() == kIOReturnNoResources);
    CHECK(live.pciModel.properties == 1 && !live.pciModel.matches && live.pciModel.refs == 1);
    live.pciModel.propertyOK = true;
    CHECK(live.claimAccel() == kIOReturnSuccess);
    CHECK(live.pciModel.properties == 2 && live.pciModel.matches == 1 && live.pciModel.refs == 1);
    CHECK(!live.exactCallbacks.active());
    closeDuringClaim(true);
    closeDuringClaim(false);
}

int main(int argc, char **argv) {
    if (argc == 2 && !std::strcmp(argv[1], "prior")) priorClaim();
    else if (argc == 2 && !std::strcmp(argv[1], "smu")) return firmware_fixture_main(1, argv);
    else if (argc == 2 && !std::strcmp(argv[1], "psp")) return firmware_fixture_main(argc, argv);
    else checkedClaim();
    std::printf("PASS %u native claim checks\n", checks);
}
