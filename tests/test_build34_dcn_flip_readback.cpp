#include "../tools/build34_dcn_flip_readback.h"
#include "../src/amd/phx_dcn314_prog_regs.h"

#include <cassert>
#include <cstdio>
#include <initializer_list>

using namespace build34::dcn;

static_assert(hubp0::kFrame == phxdcn314::kOtgFrameCount.addr);
static_assert(hubp0::kFrameMask == phxdcn314::kOtgFrameCount.mask);
static_assert(hubp0::kControl == phxdcn314::kHubpVtgSel.addr);
static_assert(hubp0::kControlVtg == phxdcn314::kHubpVtgSel.mask);
static_assert(hubp0::kControlUnderflow == phxdcn314::kHubpUnderflow.mask);

struct Fixture {
    unsigned owner = 0, provider = 0;
    const HubpAddress oldAddress{0x900000020000, 3}, newAddress{0xa00000020000, 6};
    HubpFlipRequest request{&owner, 14, 17, oldAddress, newAddress, {&provider, 20}, {&provider, 21}};
    HubpAddress programmed = oldAddress, inUse = oldAddress, earliest = oldAddress;
    uint32_t frame = 8, control = 0, flip = 0, flip2 = 0;
    uint32_t registersRead = 0, clocksRead = 0, readsInSnapshot = 0;
    uint32_t unstableReadAt = 0, failReadAt = 0, allOnesAt = 0;
    uint64_t now = 1000, endDelay = 0;
    bool clockFails = false, losesRouteDuringRead = false, routeLive = true;
    HubpFlipReader reader{this, (uint64_t{0x0500c} + 1) * 4, current, read, clock};

    static bool current(void *context, const HubpFlipRequest &identity) {
        const auto &self = *static_cast<Fixture *>(context);
        const auto samePin = [](ScanoutPinToken left, ScanoutPinToken right) {
            return left.provider == right.provider && left.serial == right.serial;
        };
        const auto &expected = self.request;
        return self.routeLive && identity.routeOwner == expected.routeOwner &&
            identity.routeGeneration == expected.routeGeneration && identity.flipSerial == expected.flipSerial &&
            identity.previous == expected.previous && identity.next == expected.next &&
            samePin(identity.previousPin, expected.previousPin) && samePin(identity.nextPin, expected.nextPin);
    }

    static bool read(void *context, uint32_t address, uint32_t &value) {
        auto &self = *static_cast<Fixture *>(context);
        ++self.registersRead;
        ++self.readsInSnapshot;
        const auto low = [](HubpAddress surface) { return static_cast<uint32_t>(surface.address); };
        const auto high = [](HubpAddress surface) { return static_cast<uint32_t>(surface.address >> 32); };
        switch (address) {
        case 0x03ab3: value = self.control; break;
        case 0x03ac9: value = self.programmed.vmid; break;
        case 0x03aca: value = low(self.programmed); break;
        case 0x03acb: value = high(self.programmed); break;
        case 0x03adb: value = self.flip; break;
        case 0x03adc: value = self.flip2; break;
        case 0x03ae1: value = low(self.inUse); break;
        case 0x03ae2: value = high(self.inUse) | (self.inUse.vmid << 28); break;
        case 0x03ae5: value = low(self.earliest); break;
        case 0x03ae6: value = high(self.earliest) | (self.earliest.vmid << 28); break;
        case 0x0500c: value = self.frame; break;
        default: assert(false); return false;
        }
        if (self.losesRouteDuringRead) self.routeLive = false;
        if (self.readsInSnapshot == self.unstableReadAt) value ^= 1;
        if (self.readsInSnapshot == self.allOnesAt) value = UINT32_MAX;
        return self.readsInSnapshot != self.failReadAt;
    }

    static bool clock(void *context, uint64_t &ns) {
        auto &self = *static_cast<Fixture *>(context);
        ++self.clocksRead;
        ns = self.now + (self.clocksRead % 2 ? 0 : self.endDelay);
        return !self.clockFails;
    }

    HubpFlipProgress poll(HubpFlipReadback &observation) {
        readsInSnapshot = 0;
        return observation.poll();
    }

    void setNew() { programmed = inUse = earliest = newAddress; }
};

static void testFlipAndOldBacking() {
    Fixture fixture;
    HubpFlipReadback observation;
    assert(observation.poll() == HubpFlipProgress::Idle);
    assert(observation.begin(fixture.request, fixture.reader));
    assert(fixture.registersRead == 22 && !observation.begin(fixture.request, fixture.reader));
    fixture.programmed = fixture.newAddress;
    fixture.flip = hubp0::kPending;
    assert(fixture.poll(observation) == HubpFlipProgress::Waiting);
    ++fixture.frame;
    fixture.inUse = fixture.newAddress;
    assert(fixture.poll(observation) == HubpFlipProgress::Waiting);
    fixture.flip = 0;
    assert(fixture.poll(observation) == HubpFlipProgress::Latched);
    fixture.earliest = fixture.newAddress;
    assert(fixture.poll(observation) == HubpFlipProgress::Latched);
    assert(fixture.poll(observation) == HubpFlipProgress::Latched);
    ++fixture.frame;
    fixture.unstableReadAt = 22;
    assert(fixture.poll(observation) == HubpFlipProgress::Latched);
    fixture.unstableReadAt = 0;
    assert(fixture.poll(observation) == HubpFlipProgress::OldAddressAbsent);
    ++fixture.request.routeGeneration;
    assert(fixture.poll(observation) == HubpFlipProgress::Uncertain);
    const auto stoppedReads = fixture.registersRead;
    assert(fixture.poll(observation) == HubpFlipProgress::Uncertain && fixture.registersRead == stoppedReads);
}

static void testNoSyntheticVblOrStalePending() {
    Fixture fixture;
    HubpFlipReadback observation;
    fixture.frame = hubp0::kFrameMask;
    fixture.request.previousPin = {};
    assert(observation.begin(fixture.request, fixture.reader));
    fixture.setNew();
    fixture.now += 1000;
    assert(fixture.poll(observation) == HubpFlipProgress::Waiting);
    fixture.frame = 0;
    assert(fixture.poll(observation) == HubpFlipProgress::Latched);
    fixture.frame = 1;
    assert(fixture.poll(observation) == HubpFlipProgress::OldAddressAbsent);
    fixture.flip = hubp0::kPending;
    assert(fixture.poll(observation) == HubpFlipProgress::Uncertain);
}

static void testBaselineRefusals() {
    Fixture fixture;
    HubpFlipReadback observation;
    --fixture.reader.apertureBytes;
    assert(!observation.begin(fixture.request, fixture.reader) && !fixture.registersRead);
    ++fixture.reader.apertureBytes;
    fixture.request.nextPin = fixture.request.previousPin;
    assert(!observation.begin(fixture.request, fixture.reader) && !fixture.registersRead);
    fixture.request.nextPin.serial++;
    const auto next = fixture.request.next;
    fixture.request.next = fixture.request.previous;
    assert(!observation.begin(fixture.request, fixture.reader) && !fixture.registersRead);
    fixture.request.next = next;
    for (const auto control : {hubp0::kControlBlank, hubp0::kControlReset, hubp0::kControlNoRequests,
                              hubp0::kControlVtg, hubp0::kControlUnderflow}) {
        fixture.control = control;
        assert(!observation.begin(fixture.request, fixture.reader));
    }
    fixture.control = 0;
    for (const auto flip : {hubp0::kPending, hubp0::kUpdateLocked, hubp0::kImmediate}) {
        fixture.flip = flip;
        assert(!observation.begin(fixture.request, fixture.reader));
    }
    fixture.flip = 0;
    fixture.flip2 = hubp0::kUnsupportedFlip2;
    assert(!observation.begin(fixture.request, fixture.reader));
    fixture.flip2 = 0;
    fixture.earliest.vmid++;
    assert(!observation.begin(fixture.request, fixture.reader));
    fixture.earliest = fixture.oldAddress;
    assert(observation.begin(fixture.request, fixture.reader));
}

enum class Fault { WrongVmid, WrongAddress, EarliestAhead, Reverted, BackwardsFrame, ReadFailed,
                   AllOnes, RouteLost, SerialChanged, ClockFailed, BackwardsClock, Late };

static void testFault(Fault fault) {
    Fixture fixture;
    HubpFlipReadback observation;
    assert(observation.begin(fixture.request, fixture.reader));
    fixture.setNew();
    ++fixture.frame;
    switch (fault) {
    case Fault::WrongVmid: ++fixture.inUse.vmid; break;
    case Fault::WrongAddress: fixture.programmed.address += kPageBytes; break;
    case Fault::EarliestAhead: fixture.inUse = fixture.oldAddress; break;
    case Fault::Reverted:
        assert(fixture.poll(observation) == HubpFlipProgress::Latched);
        fixture.earliest = fixture.oldAddress;
        break;
    case Fault::BackwardsFrame: fixture.frame -= 2; break;
    case Fault::ReadFailed: fixture.failReadAt = 8; break;
    case Fault::AllOnes: fixture.allOnesAt = 13; break;
    case Fault::RouteLost: fixture.losesRouteDuringRead = true; break;
    case Fault::SerialChanged: ++fixture.request.flipSerial; break;
    case Fault::ClockFailed: fixture.clockFails = true; break;
    case Fault::BackwardsClock: --fixture.now; break;
    case Fault::Late: fixture.endDelay = 100000000; break;
    }
    assert(fixture.poll(observation) == HubpFlipProgress::Uncertain);
}

static void testPollBoundAndTornRead() {
    Fixture fixture;
    HubpFlipReadback observation;
    assert(observation.begin(fixture.request, fixture.reader));
    fixture.setNew();
    ++fixture.frame;
    fixture.unstableReadAt = 19;
    for (unsigned attempt = 0; attempt < 64; ++attempt)
        assert(fixture.poll(observation) == HubpFlipProgress::Waiting);
    assert(fixture.registersRead == 22 * 65);
    assert(fixture.poll(observation) == HubpFlipProgress::Uncertain);
    assert(fixture.registersRead == 22 * 65);
}

int main() {
    testFlipAndOldBacking();
    testNoSyntheticVblOrStalePending();
    testBaselineRefusals();
    for (const auto fault : {Fault::WrongVmid, Fault::WrongAddress, Fault::EarliestAhead, Fault::Reverted,
                             Fault::BackwardsFrame, Fault::ReadFailed, Fault::AllOnes, Fault::RouteLost,
                             Fault::SerialChanged, Fault::ClockFailed, Fault::BackwardsClock, Fault::Late})
        testFault(fault);
    testPollBoundAndTornRead();
    std::puts("[PASS] build34 HUBP flip readback (CPU only)");
}
