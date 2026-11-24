#pragma once

#include "build34_dcn_scanout_pin.h"

namespace build34::dcn {

struct HubpAddress {
    uint64_t address;
    uint32_t vmid;

    bool valid() const { return address && address < kAddressLimit && address % kPageBytes == 0 && vmid < 16; }
    bool operator==(const HubpAddress &other) const { return address == other.address && vmid == other.vmid; }
};

struct HubpFlipRequest {
    const void *routeOwner;
    uint64_t routeGeneration;
    uint64_t flipSerial;
    HubpAddress previous;
    HubpAddress next;
    ScanoutPinToken previousPin;
    ScanoutPinToken nextPin;
};

struct HubpFlipReader {
    void *context;
    uint64_t apertureBytes;
    bool (*current)(void *, const HubpFlipRequest &);
    bool (*readDword)(void *, uint32_t, uint32_t &);
    bool (*readClockNs)(void *, uint64_t &);
};

namespace hubp0 {
inline constexpr uint32_t kControl = 0x03ab3;
inline constexpr uint32_t kVmid = 0x03ac9;
inline constexpr uint32_t kProgrammedLow = 0x03aca, kProgrammedHigh = 0x03acb;
inline constexpr uint32_t kFlip = 0x03adb, kFlip2 = 0x03adc;
inline constexpr uint32_t kInUseLow = 0x03ae1, kInUseHigh = 0x03ae2;
inline constexpr uint32_t kEarliestLow = 0x03ae5, kEarliestHigh = 0x03ae6;
inline constexpr uint32_t kFrame = 0x0500c, kFrameMask = 0x00ffffff;
inline constexpr uint32_t kControlBlank = 1u << 0, kControlReset = 1u << 2, kControlNoRequests = 1u << 12;
inline constexpr uint32_t kControlVtg = 0x000000f0, kControlUnderflow = 0x70000000;
inline constexpr uint32_t kUnsupportedControl = kControlBlank | kControlReset | kControlNoRequests |
    kControlVtg | kControlUnderflow;
inline constexpr uint32_t kImmediate = 1u << 1, kPending = 1u << 8, kUpdateLocked = 1u << 9;
inline constexpr uint32_t kUnsupportedFlip2 = (1u << 8) | (1u << 10);
}

enum class HubpFlipProgress { Idle, Waiting, Latched, OldAddressAbsent, Uncertain };

class HubpFlipReadback {
public:
    HubpFlipReadback() = default;
    HubpFlipReadback(const HubpFlipReadback &) = delete;
    HubpFlipReadback &operator=(const HubpFlipReadback &) = delete;

    template<typename ReadDword>
    static bool observeQuiescent(const ReadDword &read, HubpAddress &address, uint32_t &frame) {
        Sample sample{};
        if (sampleRegisters(read, sample) != Read::Stable || sample.pending || !sample.programmed.valid() ||
            !(sample.programmed == sample.inUse) || !(sample.programmed == sample.earliest)) return false;
        address = sample.programmed;
        frame = sample.frame;
        return true;
    }

    bool begin(HubpFlipRequest request, HubpFlipReader reader) {
        if (progress_ != HubpFlipProgress::Idle || !validRequest(request) ||
            !reader.current || !reader.readDword || !reader.readClockNs ||
            reader.apertureBytes < (uint64_t{hubp0::kFrame} + 1) * sizeof(uint32_t))
            return false;
        Sample baseline{};
        uint64_t start = 0, end = 0;
        if (!reader.readClockNs(reader.context, start) || snapshot(request, reader, baseline) != Read::Stable ||
            !reader.readClockNs(reader.context, end) || end < start || end - start >= kBudgetNs ||
            !reader.current(reader.context, request) || baseline.pending || !(baseline.programmed == request.previous) ||
            !(baseline.inUse == request.previous) || !(baseline.earliest == request.previous))
            return false;
        request_ = request;
        reader_ = reader;
        frame_ = baseline.frame;
        start_ = start;
        lastTime_ = end;
        progress_ = HubpFlipProgress::Waiting;
        return true;
    }

    HubpFlipProgress poll() {
        if (progress_ == HubpFlipProgress::Idle || progress_ == HubpFlipProgress::Uncertain)
            return progress_;
        if (progress_ == HubpFlipProgress::OldAddressAbsent)
            progress_ = HubpFlipProgress::Latched;
        uint64_t before = 0, after = 0;
        if (polls_ == kMaxPolls || !reader_.readClockNs(reader_.context, before) || !inBudget(before, lastTime_))
            return fail();
        ++polls_;
        Sample sample{};
        const auto result = snapshot(request_, reader_, sample);
        if (result == Read::Invalid || !reader_.readClockNs(reader_.context, after) || !inBudget(after, before) ||
            !reader_.current(reader_.context, request_))
            return fail();
        lastTime_ = after;
        if (result == Read::Changing)
            return progress_;

        const uint32_t advanced = (sample.frame - frame_) & hubp0::kFrameMask;
        if (advanced > kMaxFrameStep)
            return fail();
        frame_ = sample.frame;
        frameAdvanced_ = frameAdvanced_ || advanced;
        const bool programmedNew = sample.programmed == request_.next;
        const bool inUseNew = sample.inUse == request_.next;
        const bool earliestNew = sample.earliest == request_.next;
        if (!validStep(sample.programmed, programmedNew, programmedNew_) ||
            !validStep(sample.inUse, inUseNew, inUseNew_) || !validStep(sample.earliest, earliestNew, earliestNew_) ||
            (inUseNew && !programmedNew) || (earliestNew && !inUseNew) ||
            (progress_ == HubpFlipProgress::Latched && sample.pending))
            return fail();
        programmedNew_ = programmedNew;
        inUseNew_ = inUseNew;
        earliestNew_ = earliestNew;
        if (!frameAdvanced_ || !inUseNew || sample.pending)
            return progress_;

        progress_ = HubpFlipProgress::Latched;
        if (earliestNew && !drainSeen_) {
            drainFrame_ = frame_;
            drainSeen_ = true;
        } else if (earliestNew && frame_ != drainFrame_) {
            progress_ = HubpFlipProgress::OldAddressAbsent;
        }
        return progress_;
    }

private:
    friend class ScanoutFlipCommit;

    bool stillInBudget() {
        uint64_t now = 0;
        if (!reader_.readClockNs(reader_.context, now) || !inBudget(now, lastTime_)) return false;
        lastTime_ = now;
        return true;
    }

    void recycle() {
        request_ = {};
        reader_ = {};
        progress_ = HubpFlipProgress::Idle;
        polls_ = frame_ = drainFrame_ = 0;
        start_ = lastTime_ = 0;
        frameAdvanced_ = programmedNew_ = inUseNew_ = earliestNew_ = drainSeen_ = false;
    }

    static constexpr uint64_t kBudgetNs = 100000000;
    static constexpr uint32_t kMaxPolls = 64, kMaxFrameStep = 32;

    enum class Read { Stable, Changing, Invalid };

    struct Registers {
        uint32_t control, vmid, programmedLow, programmedHigh, flip, flip2;
        uint32_t inUseLow, inUseHigh, earliestLow, earliestHigh;

        bool operator==(const Registers &other) const {
            return control == other.control && vmid == other.vmid && programmedLow == other.programmedLow &&
                programmedHigh == other.programmedHigh && flip == other.flip && flip2 == other.flip2 &&
                inUseLow == other.inUseLow && inUseHigh == other.inUseHigh && earliestLow == other.earliestLow &&
                earliestHigh == other.earliestHigh;
        }
    };

    struct Sample {
        HubpAddress programmed, inUse, earliest;
        uint32_t frame;
        bool pending;
    };

    static bool validRequest(const HubpFlipRequest &request) {
        const auto validPin = [](ScanoutPinToken pin) {
            return (!pin.provider && !pin.serial) || (pin.provider && pin.serial && pin.serial != UINT64_MAX);
        };
        const auto old = request.previousPin, next = request.nextPin;
        return request.routeOwner && request.routeGeneration && request.routeGeneration != UINT64_MAX &&
            request.flipSerial && request.flipSerial != UINT64_MAX && request.previous.valid() && request.next.valid() &&
            request.previous.address != request.next.address && validPin(old) && validPin(next) &&
            (old.provider || next.provider) && (!old.provider || !next.provider ||
                (old.provider == next.provider && old.serial != next.serial));
    }

    static bool read(const HubpFlipReader &reader, uint32_t address, uint32_t &value) {
        return reader.readDword(reader.context, address, value) && value != UINT32_MAX;
    }

    template<typename ReadDword>
    static bool readRegisters(const ReadDword &read, Registers &regs) {
        using namespace hubp0;
        return read(kControl, regs.control) && read(kVmid, regs.vmid) &&
            read(kProgrammedLow, regs.programmedLow) && read(kProgrammedHigh, regs.programmedHigh) &&
            read(kFlip, regs.flip) && read(kFlip2, regs.flip2) &&
            read(kInUseLow, regs.inUseLow) && read(kInUseHigh, regs.inUseHigh) &&
            read(kEarliestLow, regs.earliestLow) && read(kEarliestHigh, regs.earliestHigh);
    }

    static Read snapshot(const HubpFlipRequest &request, const HubpFlipReader &reader, Sample &sample) {
        if (!reader.current(reader.context, request)) return Read::Invalid;
        const auto result = sampleRegisters([&](uint32_t reg, uint32_t &value) { return read(reader, reg, value); }, sample);
        return result != Read::Invalid && reader.current(reader.context, request) ? result : Read::Invalid;
    }

    template<typename ReadDword>
    static Read sampleRegisters(const ReadDword &read, Sample &sample) {
        using namespace hubp0;
        uint32_t firstFrame = 0, lastFrame = 0;
        Registers first{}, last{};
        if (!read(kFrame, firstFrame) || !readRegisters(read, first) || !readRegisters(read, last) || !read(kFrame, lastFrame))
            return Read::Invalid;
        if ((firstFrame & kFrameMask) != (lastFrame & kFrameMask) || !(first == last) || (last.flip & kUpdateLocked))
            return Read::Changing;
        if ((last.control & kUnsupportedControl) || (last.flip & kImmediate) || (last.flip2 & kUnsupportedFlip2))
            return Read::Invalid;

        const auto address = [](uint32_t low, uint32_t high) { return (uint64_t{high & 0xffff} << 32) | low; };
        sample = {{address(last.programmedLow, last.programmedHigh), last.vmid & 0xf},
                  {address(last.inUseLow, last.inUseHigh), last.inUseHigh >> 28},
                  {address(last.earliestLow, last.earliestHigh), last.earliestHigh >> 28},
                  lastFrame & kFrameMask, (last.flip & kPending) != 0};
        return Read::Stable;
    }

    bool inBudget(uint64_t now, uint64_t previous) const { return now >= previous && now - start_ < kBudgetNs; }

    bool validStep(const HubpAddress &address, bool isNew, bool wasNew) const {
        return isNew || (!wasNew && address == request_.previous);
    }

    HubpFlipProgress fail() { return progress_ = HubpFlipProgress::Uncertain; }

    HubpFlipRequest request_{};
    HubpFlipReader reader_{};
    HubpFlipProgress progress_{HubpFlipProgress::Idle};
    uint32_t polls_{0}, frame_{0}, drainFrame_{0};
    uint64_t start_{0}, lastTime_{0};
    bool frameAdvanced_{false}, programmedNew_{false}, inUseNew_{false}, earliestNew_{false}, drainSeen_{false};
};

}
