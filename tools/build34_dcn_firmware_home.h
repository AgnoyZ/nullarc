#pragma once

#include "build34_dcn_flip_program.h"
#include "build34_dcn_firmware_aperture.h"

#define BUILD34_DCN_SAMPLE_FIRMWARE "phx34DcnSampleFirmwareV2"

namespace build34::dcn {

struct FirmwareScanoutSample {
    HubpAddress scanout;
    ScanoutSurface surface;
    uint64_t barOffset;
    uint64_t backing;
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
        mmioBytes < firmwareAperture::kMmioBytes) return false;
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
    uint64_t backing = 0;
    HubpAddress address{};
    FirmwareLocalAperture before, after;
    if (!read(kFrame, firstFrame) || !unlocked() || !before.sample(read) || !matchHubpFlipGeometry(surface, read) ||
        !HubpFlipReadback::observeQuiescent(read, address, sampledFrame) || !matchHubpFlipGeometry(surface, read) ||
        !after.sample(read) || !before.same(after) || !before.bind(address, offset, bytes, backing) || !unlocked() ||
        !read(kFrame, lastFrame) || (firstFrame & kFrameMask) != sampledFrame ||
        (lastFrame & kFrameMask) != sampledFrame) return false;

    out = {address, surface, offset, backing, sampledFrame};
    return true;
}

}
