// SPDX-License-Identifier: MIT
#include "firmware-fixture.inc"

static constexpr uint64_t gfx[6] = {0x20000, 1024, 0x22000, 8, 8, 0x23001};

static void pair(PhxBringup &d) {
    CHECK(d.adoptQueue(queue) == kIOReturnSuccess);
    CHECK(d.adoptQueue(gfx) == kIOReturnSuccess);
    d.pciModel.checkLease = &d.exactCallbacks;
}

enum class PauseAt { Lookup, Property, Match };
enum class Invalidate { Close, Sleep, Epoch, ReplaceMarker };

static void race(PauseAt point, Invalidate why, bool prior = false) {
    PhxBringup d;
    pair(d);
    Pause pause;
    IOReturn result = -1;
    std::thread thread([&] {
        switch (point) {
            case PauseAt::Lookup: beforeLookup = &pause; break;
            case PauseAt::Property: duringProperty = &pause; break;
            case PauseAt::Match: duringMatch = &pause; break;
        }
        result = d.claimAccel();
    });
    pause.wait();
    CHECK(d.exactCallbacks.active() == 1 && d.pciModel.refs == 2);
    if (!prior) CHECK(d.claimAccel() == kIOReturnBusy && d.exactCallbacks.active() == 1);
    switch (why) {
        case Invalidate::Close:
            CHECK(d.exactCallbacks.close() && !d.exactCallbacks.drained());
            break;
        case Invalidate::Sleep:
            CHECK(d.setPowerState(0, nullptr) == IOPMAckImplied);
            CHECK(d.setPowerState(1, nullptr) == IOPMAckImplied && !d.isSleeping && d.gpuReady());
            break;
        case Invalidate::Epoch:
            // Isolate the epoch check even if all current readiness flags look healthy.
            IOLockLock(d.gpuLock);
            ++d.exactInvalidationEpoch;
            IOLockUnlock(d.gpuLock);
            break;
        case Invalidate::ReplaceMarker:
            d.pciModel.marker = &foreignProperty;
            break;
    }
    pause.release();
    thread.join();
    CHECK(d.pciModel.refs == 1 && !d.exactCallbacks.active());
    if (prior) {
        CHECK(result == kIOReturnSuccess && d.pciModel.matches == 1 && d.pciModel.marker == kOSBooleanTrue);
        return;
    }
    CHECK(result == kIOReturnNotReady && !d.exactClaimRequested && !d.exactClaimWriters.active());
    CHECK(d.pciModel.properties == (point == PauseAt::Lookup ? 0u : 1u));
    CHECK(d.pciModel.matches == (point == PauseAt::Match ? 1u : 0u));
    CHECK(d.pciModel.removals == (point != PauseAt::Lookup && why != Invalidate::ReplaceMarker ? 1u : 0u));
    CHECK(d.pciModel.marker == (why == Invalidate::ReplaceMarker ? &foreignProperty : nullptr));
}

static void checkedLifecycle() {
    race(PauseAt::Lookup, Invalidate::Sleep);
    race(PauseAt::Property, Invalidate::Close);
    race(PauseAt::Property, Invalidate::Sleep);
    race(PauseAt::Property, Invalidate::Epoch);
    race(PauseAt::Property, Invalidate::ReplaceMarker);
    race(PauseAt::Match, Invalidate::Close);

    for (const auto *marker : {kOSBooleanTrue, &foreignProperty}) {
        PhxBringup foreign;
        pair(foreign);
        foreign.pciModel.marker = marker;
        CHECK(foreign.claimAccel() == kIOReturnExclusiveAccess);
        CHECK(foreign.pciModel.marker == marker && !foreign.pciModel.properties && !foreign.pciModel.matches &&
              !foreign.pciModel.removals && foreign.pciModel.refs == 1);
    }
    PhxBringup live;
    pair(live);
    live.pciModel.propertyOK = false;
    CHECK(live.claimAccel() == kIOReturnNoResources && !live.pciModel.marker && !live.exactClaimRequested);
    CHECK(!live.pciModel.matches && live.pciModel.refs == 1);
    live.pciModel.propertyOK = true;
    CHECK(live.claimAccel() == kIOReturnSuccess && live.exactClaimRequested);
    CHECK(live.claimAccel() == kIOReturnSuccess);
    CHECK(live.pciModel.properties == 2 && live.pciModel.matches == 1 && live.pciModel.refs == 1);
    live.pciModel.marker = nullptr;
    CHECK(live.claimAccel() == kIOReturnNotReady);
    CHECK(live.pciModel.properties == 2 && live.pciModel.matches == 1 && !live.pciModel.removals);
}

int main(int argc, char **argv) {
    if (argc == 2 && !std::strcmp(argv[1], "prior")) race(PauseAt::Property, Invalidate::Close, true);
    else if (argc == 2 && !std::strcmp(argv[1], "smu")) return firmware_fixture_main(1, argv);
    else if (argc == 2 && !std::strcmp(argv[1], "psp")) return firmware_fixture_main(argc, argv);
    else checkedLifecycle();
    std::printf("PASS %u claim lifecycle checks\n", checks);
}
