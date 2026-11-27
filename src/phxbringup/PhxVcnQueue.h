#pragma once
#include <stddef.h>
#include <stdint.h>

namespace phx_vcn {

constexpr uint32_t kUnifiedNoop = 0x0;
constexpr uint32_t kUnifiedEnd = 0x1;
constexpr uint32_t kUnifiedIndirectBuffer = 0x2;
constexpr uint32_t kUnifiedFence = 0x3;
constexpr uint32_t kUnifiedTrap = 0x4;
constexpr uint32_t kVmidMin = 8;
constexpr uint32_t kVmidMax = 15;
constexpr uint32_t kUnifiedSubmissionDwords = 11;
constexpr uint32_t kUnifiedAlignDwords = 64;
constexpr uint32_t kUnifiedSuffixDwords = kUnifiedAlignDwords - kUnifiedSubmissionDwords;
constexpr uint32_t kUnifiedMaxSubmissionDwords = kUnifiedSubmissionDwords + kUnifiedSuffixDwords;
constexpr uint32_t kUnifiedRingReservedDwords = 1;
constexpr uint32_t kVcn402UnifiedQueueFlag = 1u << 2;
constexpr uint32_t kVcn402DrmKeyInjectFlag = 1u << 4;
constexpr uint32_t kVcn402SmuDpmInterfaceFlag = 1u << 11;
constexpr uint8_t kVcn402DrmKeyWorkaroundMethod = 2;

struct Vcn402UnifiedQueueLayout {
    uint8_t is_enabled;
    uint8_t queue_mode;
    uint8_t queue_status;
    uint8_t padding[5];
};

struct Vcn402FirmwareLoggingLayout {
    uint8_t is_enabled;
    uint8_t alignment_padding[3];
    uint32_t address_low;
    uint32_t address_high;
    uint32_t size;
};

struct Vcn402RingSetupLayout {
    uint32_t enabled_flags;
    uint8_t ring_info[48];
};

struct Vcn402SmuInterfaceLayout {
    uint8_t interface_type;
    uint8_t padding[3];
};

struct Vcn402DrmKeyWorkaroundLayout {
    uint8_t method;
    uint8_t reserved[3];
};

struct Vcn402QueueDecoupleLayout {
    uint8_t is_enabled;
    uint8_t reserved[7];
};

struct Vcn402FirmwareSharedLayout {
    uint32_t present_flags;
    uint8_t padding[12];
    Vcn402UnifiedQueueLayout unified_queue;
    uint8_t padding1[8];
    Vcn402FirmwareLoggingLayout firmware_logging;
    uint8_t padding2[20];
    Vcn402RingSetupLayout ring_setup;
    Vcn402SmuInterfaceLayout smu_interface;
    Vcn402DrmKeyWorkaroundLayout drm_key_workaround;
    uint8_t padding3[9];
    Vcn402QueueDecoupleLayout queue_decouple;
    uint8_t alignment_padding[3];
};

constexpr uint32_t kVcn402FwSharedSize = sizeof(Vcn402FirmwareSharedLayout);
constexpr uint32_t kVcn402UnifiedQueueOffset = offsetof(Vcn402FirmwareSharedLayout, unified_queue);
constexpr uint32_t kVcn402SmuDpmInterfaceOffset = offsetof(Vcn402FirmwareSharedLayout, smu_interface);
constexpr uint32_t kVcn402DrmKeyWorkaroundOffset = offsetof(Vcn402FirmwareSharedLayout, drm_key_workaround);
static_assert(kVcn402FwSharedSize == 148);
static_assert(kVcn402UnifiedQueueOffset == 16);
static_assert(kVcn402SmuDpmInterfaceOffset == 120);
static_assert(kVcn402DrmKeyWorkaroundOffset == 124);

inline bool encode_vcn402_fw_shared(uint8_t *output, uint32_t output_capacity_bytes, bool is_apu) {
    if (!output || output_capacity_bytes < kVcn402FwSharedSize)
        return false;

    for (uint32_t index = 0; index < kVcn402FwSharedSize; ++index)
        output[index] = 0;

    const uint32_t flags = kVcn402UnifiedQueueFlag | kVcn402DrmKeyInjectFlag | kVcn402SmuDpmInterfaceFlag;
    output[0] = static_cast<uint8_t>(flags);
    output[1] = static_cast<uint8_t>(flags >> 8);
    output[2] = static_cast<uint8_t>(flags >> 16);
    output[3] = static_cast<uint8_t>(flags >> 24);
    output[kVcn402UnifiedQueueOffset] = 1;
    output[kVcn402SmuDpmInterfaceOffset] = is_apu ? 1 : 0;
    output[kVcn402DrmKeyWorkaroundOffset] = kVcn402DrmKeyWorkaroundMethod;
    return true;
}

inline bool encode_unified_submission(uint32_t *output,
                                      uint32_t output_capacity_dw,
                                      uint64_t wptr_dw,
                                      uint32_t ring_dw,
                                      uint32_t vmid,
                                      uint64_t ib_gpu_va,
                                      uint32_t ib_dw,
                                      uint32_t ib_alignment,
                                      uint64_t fence_gpu_va,
                                      uint32_t fence_sequence,
                                      uint32_t *output_dw,
                                      uint64_t *next_wptr_dw) {
    if (!output || !output_dw || !next_wptr_dw || (wptr_dw & (kUnifiedAlignDwords - 1)) ||
        ring_dw < kUnifiedAlignDwords ||
        (ring_dw & (ring_dw - 1)) || vmid < kVmidMin || vmid > kVmidMax || ib_dw == 0 ||
        ib_alignment < 4 || (ib_alignment & (ib_alignment - 1)) || (ib_gpu_va & (ib_alignment - 1)) ||
        (fence_gpu_va & 3) || ib_gpu_va > UINT64_MAX - (static_cast<uint64_t>(ib_dw) * 4 - 1))
        return false;

    const uint32_t suffix_dw = kUnifiedSuffixDwords;
    const uint32_t total_dw = kUnifiedSubmissionDwords + suffix_dw;
    if (total_dw > output_capacity_dw || wptr_dw > UINT64_MAX - total_dw)
        return false;

    uint32_t cursor = 0;
    output[cursor++] = kUnifiedIndirectBuffer;
    output[cursor++] = vmid;
    output[cursor++] = static_cast<uint32_t>(ib_gpu_va);
    output[cursor++] = static_cast<uint32_t>(ib_gpu_va >> 32);
    output[cursor++] = ib_dw;
    output[cursor++] = kUnifiedFence;
    output[cursor++] = static_cast<uint32_t>(fence_gpu_va);
    output[cursor++] = static_cast<uint32_t>(fence_gpu_va >> 32);
    output[cursor++] = fence_sequence;
    output[cursor++] = kUnifiedTrap;
    output[cursor++] = kUnifiedEnd;
    for (uint32_t index = 0; index < suffix_dw; ++index)
        output[cursor++] = kUnifiedNoop;

    *output_dw = cursor;
    *next_wptr_dw = wptr_dw + cursor;
    return true;
}

inline bool place_unified_submission(uint32_t *ring,
                                     uint32_t ring_dw,
                                     uint64_t wptr_dw,
                                     uint64_t rptr_dw,
                                     uint32_t vmid,
                                     uint64_t ib_gpu_va,
                                     uint32_t ib_dw,
                                     uint32_t ib_alignment,
                                     uint64_t fence_gpu_va,
                                     uint32_t fence_sequence,
                                     uint32_t *submitted_dw,
                                     uint64_t *next_wptr_dw) {
    if (!ring || !submitted_dw || !next_wptr_dw || (wptr_dw & (kUnifiedAlignDwords - 1)) ||
        ring_dw < kUnifiedMaxSubmissionDwords + kUnifiedRingReservedDwords ||
        (ring_dw & (ring_dw - 1)) || wptr_dw < rptr_dw ||
        wptr_dw - rptr_dw > ring_dw - kUnifiedRingReservedDwords)
        return false;

    uint32_t encoded[kUnifiedMaxSubmissionDwords];
    uint32_t encoded_dw = 0;
    uint64_t new_wptr_dw = 0;
    if (!encode_unified_submission(encoded, kUnifiedMaxSubmissionDwords, wptr_dw, ring_dw, vmid, ib_gpu_va,
                                   ib_dw, ib_alignment, fence_gpu_va, fence_sequence, &encoded_dw, &new_wptr_dw) ||
        new_wptr_dw - rptr_dw > ring_dw - kUnifiedRingReservedDwords)
        return false;

    for (uint32_t index = 0; index < encoded_dw; ++index)
        ring[(wptr_dw + index) & (ring_dw - 1)] = encoded[index];
    *submitted_dw = encoded_dw;
    *next_wptr_dw = new_wptr_dw;
    return true;
}

}
