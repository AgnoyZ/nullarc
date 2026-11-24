#include "../tools/build34_dcn_firmware_home.h"
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
    HubpFlipReader reader{this, (uint64_t{0x0500c} + 1) * 4, current, read, clock, this};

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

enum class FirmwareFault { None, DisjointGart, WrongVmid, BadLength, BarOffset, ConsoleMap, Geometry, ChangedGeometry, Lock,
                           LockSelect, Stereo, Pending, TornAddress, CrossedFrame, ReadFailed, AllOnes,
                           MisboundBar, DifferentBase, DifferentTop, DifferentOffset, ChangedAperture, CrossingAperture,
                           AgpOverlap, GartOverlap, GartInvalid, PhysicalOverflow };

static void testFirmwareSample(FirmwareFault fault) {
    Fixture fixture;
    constexpr uint32_t fbBase = 0x9000, fbTop = fbBase + 1;
    uint32_t physicalBase = fault == FirmwareFault::PhysicalOverflow ? 0xffffff : 0x18;
    const auto offset = fault == FirmwareFault::CrossingAperture ? (2ull << 24) - kPageBytes :
        fault == FirmwareFault::PhysicalOverflow ? 1ull << 24 : 0x4000;
    const auto scanout = (uint64_t{fbBase} << 24) + offset;
    fixture.programmed = fixture.inUse = fixture.earliest = {scanout, fault == FirmwareFault::WrongVmid ? 3u : 0u};
    if (fault == FirmwareFault::Pending) fixture.flip = hubp0::kPending;
    if (fault == FirmwareFault::Stereo) fixture.flip = hubp0::kStereoFlip;
    const bool gart = fault == FirmwareFault::DisjointGart || fault == FirmwareFault::GartOverlap || fault == FirmwareFault::GartInvalid;
    const auto gartStart = !gart ? 0u : static_cast<uint32_t>(scanout / kPageBytes + (fault == FirmwareFault::GartOverlap ? 1 : 0x2000));
    uint32_t agpBottom = fault == FirmwareFault::AgpOverlap ? fbBase : 0xffffff;
    uint32_t agpTop = fault == FirmwareFault::AgpOverlap ? fbBase : 0;
    unsigned reads = 0, pitchReads = 0, frameReads = 0, offsetReads = 0, addressReads = 0;
    uint32_t pitch = 63;
    bool updateLocked = false, crossCheckFrame = false;
    const auto read = [&](uint32_t reg, uint32_t &value) {
        ++reads;
        switch (reg) {
        case 0x03935: value = fbBase; return true;
        case 0x03936: value = fbTop; return true;
        case 0x03937:
            value = physicalBase + (++offsetReads == 2 && fault == FirmwareFault::ChangedAperture);
            return true;
        case 0x03938: value = agpBottom; return true;
        case 0x03939: value = agpTop; return true;
        case 0x1a8ec: value = fbBase + (fault == FirmwareFault::DifferentBase); return true;
        case 0x1a8ed: value = fbTop + (fault == FirmwareFault::DifferentTop); return true;
        case 0x1a8d7: value = physicalBase + (fault == FirmwareFault::DifferentOffset); return true;
        case 0x03a19: case 0x03a1a: case 0x03a1c: case 0x03a1e: value = 0; return true;
        case 0x03a1b: value = !gart ? 0 : fault == FirmwareFault::GartInvalid ? 0x1000 : 0x1001; return true;
        case 0x03a1d: value = gartStart; return true;
        case 0x03a1f: value = gartStart + (gart ? 8 : 0); return true;
        case 0x03aa5: value = 8; return true;
        case 0x03aa7: case 0x03aa9: case 0x03ada: value = 0; return true;
        case 0x03aaa: value = (17u << 16) | 64; return true;
        case 0x03ac7:
            ++pitchReads;
            value = pitch + (fault == FirmwareFault::Geometry || (fault == FirmwareFault::ChangedGeometry && pitchReads == 2));
            return true;
        case 0x03b2c: value = 0x00e00000; return true;
        case 0x04f8b: value = 0xfff00000; return true;
        case 0x05001: value = 0x00010001; return true;
        case 0x0504a: value = fault == FirmwareFault::Lock || updateLocked ? 0x100 : 0; return true;
        case 0x05051: value = fault == FirmwareFault::LockSelect ? 1u << 25 : 0; return true;
        default:
            if (reg == 0x0500c) {
                ++frameReads;
                if ((frameReads == 4 && fault == FirmwareFault::CrossedFrame) || (crossCheckFrame && frameReads == 2))
                    ++fixture.frame;
            }
            if (reg == hubp0::kVmid || reg == hubp0::kProgrammedLow || reg == hubp0::kProgrammedHigh ||
                reg == hubp0::kInUseLow || reg == hubp0::kInUseHigh || reg == hubp0::kEarliestLow || reg == hubp0::kEarliestHigh)
                ++addressReads;
            if (reg == 0x03ae5 && fault == FirmwareFault::TornAddress) fixture.earliest.address ^= kPageBytes;
            if (!Fixture::read(&fixture, reg, value)) return false;
            if (reg == 0x03ae2 && fault == FirmwareFault::AllOnes) value = UINT32_MAX;
            return reg != 0x03ae2 || fault != FirmwareFault::ReadFailed;
        }
    };
    constexpr uint64_t bar = 0x800000000, barBytes = 0x10000000, visible = 17 * 256, mmio = 0x80000;
    const bool accepted = fault == FirmwareFault::None || fault == FirmwareFault::DisjointGart;
    FirmwareScanoutSample sample{fixture.oldAddress, {}, UINT64_MAX, UINT64_MAX, UINT32_MAX};
    const auto consoleOffset = fault == FirmwareFault::BarOffset ? barBytes - kPageBytes :
        offset + (fault == FirmwareFault::MisboundBar ? kPageBytes : 0);
    assert(sampleFirmwareScanout(bar + consoleOffset, bar,
        barBytes, fault == FirmwareFault::ConsoleMap ? visible - 1 : visible, 64, 17, 256,
        fault == FirmwareFault::BadLength ? 0x1a8ed * 4 : mmio, read, sample) == accepted);
    if (accepted) {
        assert(sample.scanout == fixture.programmed && sample.surface.width == 64 && sample.surface.height == 17 &&
               sample.surface.pitchPixelsMinusOne == 63 && sample.surface.mappedBytes == 2 * kPageBytes);
        assert(sample.barOffset == 0x4000 && sample.scanout.address != bar + sample.barOffset && sample.frame == 8);
        assert(sample.backing == (uint64_t{physicalBase} << 24) + offset && reads == 80);
    } else {
        assert(!sample.scanout.address && !sample.barOffset && !sample.backing && !sample.surface.mappedBytes && !sample.frame);
        if (fault == FirmwareFault::BarOffset || fault == FirmwareFault::ConsoleMap || fault == FirmwareFault::BadLength)
            assert(!reads);
    }
    if (accepted) {
        const uint64_t fbStart = uint64_t{fbBase} << 24;
        const auto checkWindows = [&](FirmwareFlatWindows windows) {
            FirmwareScanoutSample checked{};
            reads = 0;
            const bool matched = sampleFirmwareScanout(bar + offset, bar, barBytes, visible, 64, 17, 256, mmio,
                read, checked, &sample, &windows);
            assert(reads <= 80 && checked.valid() == matched);
            return matched;
        };
        const FirmwareFlatWindow adjacent{fbStart - kPageBytes, kPageBytes};
        constexpr FirmwareFlatWindow highWindow{kAddressLimit - kPageBytes, kPageBytes};
        assert(checkWindows({adjacent, highWindow}));
        assert(!checkWindows({{adjacent.start, 2 * kPageBytes}, highWindow}));
        assert(!checkWindows({adjacent, {uint64_t{fbTop + 1} << 24, 1}}));
        assert(!checkWindows({adjacent, {highWindow.start, 2 * kPageBytes}}));
        assert(!checkWindows({{adjacent.start, 0}, {}}));
        assert(!checkWindows({{}, {0, kPageBytes}}));
        assert(!checkWindows({{}, {adjacent.start + 1, kPageBytes}}));
        agpBottom = agpTop = fbBase - 1;
        assert(!checkWindows({{}, adjacent}));
        agpBottom = 0xffffff;
        agpTop = 0;
        assert(checkWindows({{}, adjacent}));
        if (gart) {
            const uint64_t gartEnd = (uint64_t{gartStart} + 9) * kPageBytes;
            assert(checkWindows({{}, {gartEnd, kPageBytes}}));
            assert(!checkWindows({{gartEnd - kPageBytes, 2 * kPageBytes}, {}}));
        }
    }
    if (fault != FirmwareFault::None) return;
    assert(sample.valid());
    fixture.setNew();
    ++fixture.frame;
    FirmwareScanoutSample checked{};
    const auto check = [&] {
        addressReads = frameReads = 0;
        return sampleFirmwareScanout(bar + offset, bar, barBytes, visible, 64, 17, 256, mmio, read, checked, &sample);
    };
    assert(!sampleFirmwareScanout(bar + offset, bar, barBytes, visible, 64, 17, 256, mmio, read, checked));
    assert(check() && checked.valid() && !addressReads);
    assert(checked.scanout == sample.scanout && !(checked.scanout == fixture.inUse) && checked.backing == sample.backing &&
           checked.barOffset == sample.barOffset && checked.frame == fixture.frame && sameFlipGeometry(checked.surface, sample.surface));
    ++physicalBase;
    assert(!check() && !checked.backing);
    --physicalBase;
    ++pitch;
    assert(!check() && !checked.backing);
    --pitch;
    updateLocked = true;
    assert(!check() && !checked.backing);
    updateLocked = false;
    crossCheckFrame = true;
    assert(!check() && !checked.backing);
    crossCheckFrame = false;
    assert(check() && checked.backing == sample.backing);
}

static void testIdleDcnPeers() {
    constexpr uint32_t otg[]{0x05081, 0x05101, 0x05181};
    constexpr uint32_t power[]{0x03543, 0x03545, 0x03547};
    constexpr uint32_t hubp[]{0x03b8f, 0x03c6b, 0x03d47};
    constexpr uint32_t flip[]{0x03bb7, 0x03c93, 0x03d6f};
    static_assert(dcnPeers::kMmioBytes == (0x05181 + 1) * sizeof(uint32_t));
    for (unsigned peer = 0; peer < 3; ++peer) {
        uint32_t peerOtg = 0, peerPower = 0, peerHubp = 0x1003, peerFlip = 0;
        unsigned frame = 12, frameReads = 0, powerReads = 0, pipeReads = 0;
        unsigned crossedFrames = 0, frameJump = 1;
        bool changedPower = false, failedRead = false;
        const auto read = [&](uint32_t reg, uint32_t &value) {
            if (reg == 0x0500c) {
                if (++frameReads % 2 == 0 && crossedFrames) {
                    --crossedFrames;
                    frame += frameJump;
                }
                value = frame;
                return true;
            }
            for (unsigned index = 0; index < 3; ++index) {
                if (reg == otg[index]) {
                    value = index == peer ? peerOtg : 0;
                    return true;
                }
                if (reg == power[index]) {
                    value = index == peer && !(++powerReads == 2 && changedPower) ? peerPower : 0x80000000;
                    return index != peer || !failedRead;
                }
                if (reg == hubp[index] || reg == flip[index]) {
                    assert(index == peer && !peerPower);
                    ++pipeReads;
                    value = reg == hubp[index] ? peerHubp : peerFlip;
                    return true;
                }
            }
            assert(false);
            return false;
        };
        const auto check = [&] {
            frameReads = powerReads = pipeReads = 0;
            return matchIdleDcnPeers(read);
        };
        assert(check() && pipeReads == 4 && frameReads == 2);
        for (const auto bit : {1u, 2u, 0x1000u}) {
            peerHubp = 0x1003 & ~bit;
            assert(!check());
        }
        peerHubp = 0x1003;
        for (const auto bit : {0x100u, 0x200u}) {
            peerFlip = bit;
            assert(!check());
        }
        peerFlip = 0;
        changedPower = true;
        assert(!check() && pipeReads == 2);
        changedPower = false;
        peerPower = 0x80000000;
        assert(check() && !pipeReads);
        for (const auto value : {1u, 0x10000u, UINT32_MAX}) {
            peerOtg = value;
            assert(!check());
        }
        peerOtg = 0;
        for (const auto value : {0x40000000u, 0xc0000000u, UINT32_MAX}) {
            peerPower = value;
            assert(!check() && !pipeReads);
        }
        peerPower = 0x80000000;
        failedRead = true;
        assert(!check());
        failedRead = false;
        crossedFrames = 1;
        assert(check() && frameReads == 4);
        crossedFrames = 2;
        assert(!check() && frameReads == 4);
        crossedFrames = 1;
        frameJump = 2;
        assert(!check() && frameReads == 2);
    }
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
    testIdleDcnPeers();
    for (const auto fault : {FirmwareFault::None, FirmwareFault::DisjointGart, FirmwareFault::WrongVmid, FirmwareFault::BadLength, FirmwareFault::BarOffset,
            FirmwareFault::ConsoleMap, FirmwareFault::Geometry, FirmwareFault::ChangedGeometry, FirmwareFault::Lock,
            FirmwareFault::LockSelect, FirmwareFault::Stereo, FirmwareFault::Pending, FirmwareFault::TornAddress,
            FirmwareFault::CrossedFrame, FirmwareFault::ReadFailed, FirmwareFault::AllOnes, FirmwareFault::MisboundBar,
            FirmwareFault::DifferentBase, FirmwareFault::DifferentTop, FirmwareFault::DifferentOffset, FirmwareFault::ChangedAperture,
            FirmwareFault::CrossingAperture, FirmwareFault::AgpOverlap, FirmwareFault::GartOverlap, FirmwareFault::GartInvalid,
            FirmwareFault::PhysicalOverflow})
        testFirmwareSample(fault);
    std::puts("[PASS] build34 HUBP flip readback (CPU only)");
}
