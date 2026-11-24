#pragma once

#include "build34_dcn_flip_program.h"

#define BUILD34_DCN_SAMPLE_FIRMWARE "phx34DcnSampleFirmwareV1"

namespace build34::dcn {

struct FirmwareScanoutSample {
    HubpAddress scanout;
    ScanoutSurface surface;
    uint64_t barOffset;
    uint32_t frame;
};

template<typename ReadDword>
bool sampleFirmwareScanout(uint64_t consoleBase, uint64_t barBase, uint64_t barBytes, uint64_t mappedBytes,
                           uint32_t width, uint32_t height, uint32_t rowBytes, uint64_t mmioBytes,
                           const ReadDword &readDword, FirmwareScanoutSample &out) {
    using namespace hubp0;
    out = {};
    if (!barBase || barBase % kPageBytes || barBytes > UINT64_MAX - barBase || consoleBase < barBase ||
        consoleBase % kPageBytes || rowBytes < 4 || rowBytes % 4 ||
        mmioBytes < (uint64_t{kOtgLockSelect} + 1) * sizeof(uint32_t)) return false;
    const uint64_t offset = consoleBase - barBase, visible = uint64_t{rowBytes} * height;
    if (offset >= barBytes || visible > mappedBytes || visible > kMaxBackingBytes) return false;
    const auto bytes = (visible + kPageBytes - 1) & ~(kPageBytes - 1);
    if (bytes > barBytes - offset) return false;
    const ScanoutSurface surface{width, height, rowBytes / 4 - 1, kDcnArgb8888, bytes};
    if (!validFlipGeometry(surface)) return false;

    const auto read = [&](uint32_t reg, uint32_t &value) { return readDword(reg, value) && value != UINT32_MAX; };
    const auto unlocked = [&] {
        uint32_t select = 0, lock = 0, flip = 0;
        return read(kOtgLockSelect, select) && !(select & kOtgLockSelectMask) &&
            read(kOtgUpdateLock, lock) && !(lock & (kOtgLockRequest | kOtgLockStatus)) &&
            read(kFlip, flip) && !(flip & (kStereoFlip | kPending | kUpdateLocked | kImmediate));
    };
    uint32_t firstFrame = 0, lastFrame = 0, sampledFrame = 0;
    HubpAddress address{};
    if (!read(kFrame, firstFrame) || !unlocked() || !matchHubpFlipGeometry(surface, read) ||
        !HubpFlipReadback::observeQuiescent(read, address, sampledFrame) || address.vmid ||
        bytes > kAddressLimit - address.address || !matchHubpFlipGeometry(surface, read) || !unlocked() ||
        !read(kFrame, lastFrame) || (firstFrame & kFrameMask) != sampledFrame ||
        (lastFrame & kFrameMask) != sampledFrame) return false;

    out = {address, surface, offset, sampledFrame};
    return true;
}

}
