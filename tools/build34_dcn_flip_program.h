#pragma once

#include "build34_dcn_flip_geometry.h"

namespace build34::dcn {

namespace hubp0 {
inline constexpr uint32_t kStereoFlip = 0x00013000;
inline constexpr uint32_t kOtgUpdateLock = 0x0504a, kOtgLockSelect = 0x05051;
inline constexpr uint32_t kOtgLockRequest = 1u << 0, kOtgLockStatus = 1u << 8;
inline constexpr uint32_t kOtgLockSelectMask = 0x0e000000;
}

struct HubpFlipWriter {
    bool (*writeDword)(void *, uint32_t, uint32_t);
    void (*delayUs)(void *, uint32_t);
};

class HubpFlipProgram {
    friend class ScanoutFlipCommit;

    template<typename IsLive>
    static bool preflight(const HubpFlipRequest &request, const HubpFlipReader &reader, HubpFlipWriter writer,
                          const ScanoutSurface &surface, IsLive live) {
        if (!request.previous.valid() || !request.next.valid() || !reader.current || !reader.readDword ||
            !writer.writeDword || !writer.delayUs || reader.apertureBytes < dcnPeers::kMmioBytes)
            return false;
        Access<IsLive> access{request, reader, writer, live};
        uint32_t vmid = 0;
        return access.baseline(surface, false, vmid) && access.peersIdle();
    }

    template<typename IsLive, typename ContextsCurrent>
    static bool issue(const HubpFlipRequest &request, const HubpFlipReader &reader, HubpFlipWriter writer,
                      const ScanoutSurface &surface, IsLive live, ContextsCurrent contextsCurrent) {
        if (!preflight(request, reader, writer, surface, live)) return false;
        using namespace hubp0;
        Access<IsLive> access{request, reader, writer, live};
        uint32_t vmid = 0;
        if (!access.write(kOtgUpdateLock, kOtgLockRequest, false) || !access.waitLock(true) ||
            !access.baseline(surface, true, vmid) || !contextsCurrent())
            return false;
        if (!access.write(kVmid, (vmid & ~0xfu) | request.next.vmid, true) ||
            !access.write(kProgrammedHigh, static_cast<uint32_t>(request.next.address >> 32), true) ||
            !access.write(kProgrammedLow, static_cast<uint32_t>(request.next.address), true))
            return false;
        return access.write(kOtgUpdateLock, 0, true) && access.waitLock(false);
    }

    template<typename IsLive>
    static bool peersIdle(const HubpFlipRequest &request, const HubpFlipReader &reader, const IsLive &live) {
        return Access<IsLive>{request, reader, {}, live}.peersIdle();
    }

    template<typename IsLive>
    static bool frontCurrent(const HubpFlipRequest &request, const HubpFlipReader &reader,
                             const ScanoutSurface &surface, IsLive live) {
        if (reader.apertureBytes < dcnPeers::kMmioBytes) return false;
        Access<IsLive> access{request, reader, {}, live};
        HubpAddress front{};
        uint32_t frame = 0;
        return access.geometry(surface) && access.peersIdle() && access.lockCurrent(false) &&
            HubpFlipReadback::observeQuiescent([&](uint32_t reg, uint32_t &value) { return access.read(reg, value); },
                front, frame) && front == request.next && access.current();
    }

    template<typename IsLive>
    struct Access {
        const HubpFlipRequest &request;
        const HubpFlipReader &reader;
        HubpFlipWriter writer;
        const IsLive &live;

        bool current() const { return live() && reader.current(reader.context, request) && live(); }

        bool read(uint32_t reg, uint32_t &value) const {
            return current() && reader.readDword(reader.context, reg, value) && value != UINT32_MAX;
        }

        bool write(uint32_t reg, uint32_t value, bool held) const {
            return peersIdle() && lockCurrent(held) && current() && writer.writeDword(reader.context, reg, value);
        }

        bool peersIdle() const {
            return reader.apertureBytes >= dcnPeers::kMmioBytes &&
                matchIdleDcnPeers([&](uint32_t reg, uint32_t &value) { return read(reg, value); }) && current();
        }

        bool geometry(const ScanoutSurface &surface) const {
            return matchHubpFlipGeometry(surface, [&](uint32_t reg, uint32_t &value) { return read(reg, value); });
        }

        bool baseline(const ScanoutSurface &surface, bool held, uint32_t &vmid) const {
            using namespace hubp0;
            uint32_t select = 0, flip = 0, flip2 = 0, lock = 0, high = 0, low = 0;
            if (!read(kOtgLockSelect, select) || (select & kOtgLockSelectMask) ||
                !geometry(surface) ||
                !read(kFlip2, flip2) || (flip2 & kUnsupportedFlip2) ||
                !read(kOtgUpdateLock, lock) || !read(kFlip, flip) || (flip & (kImmediate | kPending | kStereoFlip)) ||
                !lockMatches(lock, flip, held) || !read(kVmid, vmid) || !read(kProgrammedHigh, high) ||
                !read(kProgrammedLow, low))
                return false;
            return (vmid & 0xfu) == request.previous.vmid &&
                ((uint64_t{high & 0xffffu} << 32) | low) == request.previous.address;
        }

        bool lockCurrent(bool held) const {
            uint32_t select = 0;
            uint32_t lock = 0, flip = 0;
            return read(hubp0::kOtgLockSelect, select) && !(select & hubp0::kOtgLockSelectMask) &&
                read(hubp0::kOtgUpdateLock, lock) && read(hubp0::kFlip, flip) && lockMatches(lock, flip, held);
        }

        bool waitLock(bool held) const {
            for (uint32_t attempt = 0; attempt < 10; ++attempt) {
                uint32_t lock = 0, flip = 0;
                if (!read(hubp0::kOtgUpdateLock, lock) || !read(hubp0::kFlip, flip)) return false;
                if (lockMatches(lock, flip, held)) return current();
                if (attempt < 9 && current()) writer.delayUs(reader.context, 1);
            }
            return false;
        }

        static bool lockMatches(uint32_t lock, uint32_t flip, bool held) {
            using namespace hubp0;
            constexpr uint32_t mask = kOtgLockRequest | kOtgLockStatus;
            return (lock & mask) == (held ? mask : 0) && bool(flip & kUpdateLocked) == held;
        }
    };
};

}
