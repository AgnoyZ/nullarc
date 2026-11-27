#pragma once
#include <stddef.h>
#include <stdint.h>

namespace phx_vcn {

constexpr uint32_t kUnifiedNoop = 0x0;
constexpr uint32_t kUnifiedEnd = 0x1;
constexpr uint32_t kUnifiedIndirectBuffer = 0x2;
constexpr uint32_t kUnifiedFence = 0x3;
constexpr uint32_t kUnifiedTrap = 0x4;
constexpr uint32_t kUnifiedRegWrite = 0xb;
constexpr uint32_t kUnifiedRegWait = 0xc;
constexpr uint32_t kVmidMin = 8;
constexpr uint32_t kVmidMax = 15;
constexpr uint32_t kUnifiedSubmissionDwords = 11;
constexpr uint32_t kUnifiedAlignDwords = 64;
constexpr uint32_t kUnifiedMaxSuffixDwords = kUnifiedAlignDwords - 1;
constexpr uint32_t kUnifiedControlDwords = 6;
constexpr uint32_t kUnifiedMaxIndirectBuffers = 64;
constexpr uint32_t kUnifiedMaxSubmissionDwords = kUnifiedMaxIndirectBuffers * 5 + kUnifiedControlDwords +
                                                 kUnifiedMaxSuffixDwords;
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

struct Vcn402VfRingSetupLayout {
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
    Vcn402VfRingSetupLayout vf_ring_setup;
    Vcn402SmuInterfaceLayout smu_interface;
    Vcn402DrmKeyWorkaroundLayout drm_key_workaround;
    uint8_t padding3[9];
    Vcn402QueueDecoupleLayout queue_decouple;
    uint8_t alignment_padding[3];
};

constexpr uint32_t kVcn402FwSharedSize = sizeof(Vcn402FirmwareSharedLayout);
constexpr uint32_t kVcn402UnifiedQueueOffset = offsetof(Vcn402FirmwareSharedLayout, unified_queue);
constexpr uint32_t kVcn402VfRingSetupOffset = offsetof(Vcn402FirmwareSharedLayout, vf_ring_setup);
constexpr uint32_t kVcn402SmuDpmInterfaceOffset = offsetof(Vcn402FirmwareSharedLayout, smu_interface);
constexpr uint32_t kVcn402DrmKeyWorkaroundOffset = offsetof(Vcn402FirmwareSharedLayout, drm_key_workaround);
static_assert(kVcn402FwSharedSize == 148);
static_assert(kVcn402UnifiedQueueOffset == 16);
static_assert(kVcn402VfRingSetupOffset == 68);
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

inline bool encode_reg_wait(uint32_t *output,
                            uint32_t output_capacity_dw,
                            uint32_t register_index,
                            uint32_t mask,
                            uint32_t expected_value,
                            uint32_t *output_dw) {
    constexpr uint32_t command_dw = 4;
    if (!output || !output_dw || output_capacity_dw < command_dw || register_index > (UINT32_MAX >> 2))
        return false;

    output[0] = kUnifiedRegWait;
    output[1] = register_index << 2;
    output[2] = mask;
    output[3] = expected_value;
    *output_dw = command_dw;
    return true;
}

inline bool encode_reg_write(uint32_t *output,
                             uint32_t output_capacity_dw,
                             uint32_t register_index,
                             uint32_t value,
                             uint32_t *output_dw) {
    constexpr uint32_t command_dw = 3;
    if (!output || !output_dw || output_capacity_dw < command_dw || register_index > (UINT32_MAX >> 2))
        return false;

    output[0] = kUnifiedRegWrite;
    output[1] = register_index << 2;
    output[2] = value;
    *output_dw = command_dw;
    return true;
}

inline bool encode_reg_write_reg_wait(uint32_t *output,
                                     uint32_t output_capacity_dw,
                                     uint32_t write_register_index,
                                     uint32_t wait_register_index,
                                     uint32_t reference_value,
                                     uint32_t wait_mask,
                                     uint32_t *output_dw) {
    constexpr uint32_t command_dw = 7;
    if (!output || !output_dw || output_capacity_dw < command_dw || wait_mask == 0 ||
        write_register_index > (UINT32_MAX >> 2) || wait_register_index > (UINT32_MAX >> 2))
        return false;

    uint32_t encoded[command_dw];
    uint32_t write_dw = 0;
    uint32_t wait_dw = 0;
    if (!encode_reg_write(encoded, 3, write_register_index, reference_value, &write_dw) ||
        !encode_reg_wait(encoded + write_dw, 4, wait_register_index, wait_mask, wait_mask, &wait_dw))
        return false;

    for (uint32_t index = 0; index < command_dw; ++index)
        output[index] = encoded[index];
    *output_dw = command_dw;
    return true;
}

inline bool encode_mmhub_vm_flush_core_sequence(uint32_t *output,
                                                uint32_t output_capacity_dw,
                                                uint32_t vmid,
                                                uint64_t page_table_base,
                                                uint32_t invalidate_semaphore_register_index,
                                                uint32_t page_table_low_register_index,
                                                uint32_t page_table_high_register_index,
                                                uint32_t invalidate_request_register_index,
                                                uint32_t invalidate_ack_register_index,
                                                uint32_t invalidate_request,
                                                uint32_t *output_dw) {
    constexpr uint32_t command_dw = 24;
    constexpr uint32_t vmid_limit = 15;
    constexpr uint64_t page_table_alignment = 4096;
    if (!output || !output_dw || output_capacity_dw < command_dw || vmid == 0 || vmid > vmid_limit ||
        (page_table_base & (page_table_alignment - 1)) ||
        invalidate_semaphore_register_index > (UINT32_MAX >> 2) ||
        page_table_low_register_index > (UINT32_MAX >> 2) ||
        page_table_high_register_index > (UINT32_MAX >> 2) ||
        invalidate_request_register_index > (UINT32_MAX >> 2) ||
        invalidate_ack_register_index > (UINT32_MAX >> 2))
        return false;

    uint32_t encoded[command_dw];
    uint32_t cursor = 0;
    uint32_t encoded_dw = 0;
    if (!encode_reg_wait(encoded + cursor, command_dw - cursor, invalidate_semaphore_register_index, 1, 1,
                         &encoded_dw))
        return false;
    cursor += encoded_dw;
    if (!encode_reg_write(encoded + cursor, command_dw - cursor, page_table_low_register_index,
                          static_cast<uint32_t>(page_table_base), &encoded_dw))
        return false;
    cursor += encoded_dw;
    if (!encode_reg_write(encoded + cursor, command_dw - cursor, page_table_high_register_index,
                          static_cast<uint32_t>(page_table_base >> 32), &encoded_dw))
        return false;
    cursor += encoded_dw;
    if (!encode_reg_write_reg_wait(encoded + cursor, command_dw - cursor, invalidate_request_register_index,
                                   invalidate_ack_register_index, invalidate_request, 1u << vmid, &encoded_dw))
        return false;
    cursor += encoded_dw;
    if (!encode_reg_write(encoded + cursor, command_dw - cursor, invalidate_semaphore_register_index, 0,
                          &encoded_dw))
        return false;
    cursor += encoded_dw;
    if (!encode_reg_wait(encoded + cursor, command_dw - cursor, page_table_low_register_index, UINT32_MAX,
                         static_cast<uint32_t>(page_table_base), &encoded_dw))
        return false;
    cursor += encoded_dw;

    for (uint32_t index = 0; index < cursor; ++index)
        output[index] = encoded[index];
    *output_dw = cursor;
    return true;
}

inline bool encode_unified_submission(uint32_t *output,
                                      uint32_t output_capacity_dw,
                                      uint64_t wptr_dw,
                                      uint32_t ring_dw,
                                      uint32_t vmid,
                                      const uint64_t *ib_gpu_va,
                                      const uint32_t *ib_dw,
                                      uint32_t ib_count,
                                      uint32_t ib_alignment,
                                      uint64_t fence_gpu_va,
                                      uint32_t fence_sequence,
                                      uint32_t *output_dw,
                                      uint64_t *next_wptr_dw) {
    if (!output || !output_dw || !next_wptr_dw || !ib_gpu_va || !ib_dw || ib_count == 0 ||
        ib_count > kUnifiedMaxIndirectBuffers || ring_dw < kUnifiedAlignDwords ||
        (ring_dw & (ring_dw - 1)) || vmid < kVmidMin || vmid > kVmidMax ||
        ib_alignment < 4 || (ib_alignment & (ib_alignment - 1)) || (fence_gpu_va & 3) ||
        fence_gpu_va > UINT64_MAX - 3)
        return false;

    for (uint32_t index = 0; index < ib_count; ++index) {
        if (ib_dw[index] == 0 || (ib_gpu_va[index] & (ib_alignment - 1)) ||
            ib_gpu_va[index] > UINT64_MAX - (static_cast<uint64_t>(ib_dw[index]) * 4 - 1))
            return false;
    }

    const uint32_t command_dw = ib_count * 5 + kUnifiedControlDwords;
    if (wptr_dw > UINT64_MAX - command_dw)
        return false;
    const uint32_t suffix_dw = static_cast<uint32_t>(
        (kUnifiedAlignDwords - ((wptr_dw & (kUnifiedAlignDwords - 1)) + command_dw) %
                                   kUnifiedAlignDwords) &
        (kUnifiedAlignDwords - 1));
    const uint32_t total_dw = command_dw + suffix_dw;
    if (total_dw > output_capacity_dw || wptr_dw > UINT64_MAX - total_dw)
        return false;

    uint32_t cursor = 0;
    for (uint32_t index = 0; index < ib_count; ++index) {
        output[cursor++] = kUnifiedIndirectBuffer;
        output[cursor++] = vmid;
        output[cursor++] = static_cast<uint32_t>(ib_gpu_va[index]);
        output[cursor++] = static_cast<uint32_t>(ib_gpu_va[index] >> 32);
        output[cursor++] = ib_dw[index];
    }
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
    return encode_unified_submission(output, output_capacity_dw, wptr_dw, ring_dw, vmid, &ib_gpu_va, &ib_dw, 1,
                                     ib_alignment, fence_gpu_va, fence_sequence, output_dw, next_wptr_dw);
}

inline bool place_unified_submission(uint32_t *ring,
                                     uint32_t ring_dw,
                                     uint64_t wptr_dw,
                                     uint64_t rptr_dw,
                                     uint32_t vmid,
                                     const uint64_t *ib_gpu_va,
                                     const uint32_t *ib_dw,
                                     uint32_t ib_count,
                                     uint32_t ib_alignment,
                                     uint64_t fence_gpu_va,
                                     uint32_t fence_sequence,
                                     uint32_t *submitted_dw,
                                     uint64_t *next_wptr_dw);

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
    return place_unified_submission(ring, ring_dw, wptr_dw, rptr_dw, vmid, &ib_gpu_va, &ib_dw, 1, ib_alignment,
                                    fence_gpu_va, fence_sequence, submitted_dw, next_wptr_dw);
}

inline bool place_unified_submission(uint32_t *ring,
                                     uint32_t ring_dw,
                                     uint64_t wptr_dw,
                                     uint64_t rptr_dw,
                                     uint32_t vmid,
                                     const uint64_t *ib_gpu_va,
                                     const uint32_t *ib_dw,
                                     uint32_t ib_count,
                                     uint32_t ib_alignment,
                                     uint64_t fence_gpu_va,
                                     uint32_t fence_sequence,
                                     uint32_t *submitted_dw,
                                     uint64_t *next_wptr_dw) {
    if (!ring || !submitted_dw || !next_wptr_dw || ring_dw < kUnifiedAlignDwords + kUnifiedRingReservedDwords ||
        (ring_dw & (ring_dw - 1)) || wptr_dw < rptr_dw ||
        wptr_dw - rptr_dw > ring_dw - kUnifiedRingReservedDwords)
        return false;

    uint32_t encoded[kUnifiedMaxSubmissionDwords];
    uint32_t encoded_dw = 0;
    uint64_t new_wptr_dw = 0;
    if (!encode_unified_submission(encoded, kUnifiedMaxSubmissionDwords, wptr_dw, ring_dw, vmid, ib_gpu_va, ib_dw,
                                   ib_count, ib_alignment, fence_gpu_va, fence_sequence, &encoded_dw, &new_wptr_dw) ||
        new_wptr_dw - rptr_dw > ring_dw - kUnifiedRingReservedDwords)
        return false;

    for (uint32_t index = 0; index < encoded_dw; ++index)
        ring[(wptr_dw + index) & (ring_dw - 1)] = encoded[index];
    *submitted_dw = encoded_dw;
    *next_wptr_dw = new_wptr_dw;
    return true;
}

}
