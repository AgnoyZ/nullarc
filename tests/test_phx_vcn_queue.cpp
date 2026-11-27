#include "../src/phxbringup/PhxVcnQueue.h"
#include <assert.h>
#include <stdint.h>

using namespace phx_vcn;

static void rejected(uint32_t ring_dw,
                     uint32_t vmid,
                     uint64_t ib_gpu_va,
                     uint32_t ib_dw,
                     uint32_t ib_alignment,
                     uint64_t fence_gpu_va,
                     uint32_t output_capacity_dw,
                     uint64_t wptr_dw = 0) {
    uint32_t output[kUnifiedMaxSubmissionDwords];
    for (uint32_t &value : output)
        value = 0xfeedface;
    uint32_t output_dw = 0xabcdef01;
    uint64_t next_wptr_dw = 0x123456789abcdef0ull;
    assert(!encode_unified_submission(output, output_capacity_dw, wptr_dw, ring_dw, vmid, ib_gpu_va, ib_dw,
                                     ib_alignment, fence_gpu_va, 7, &output_dw, &next_wptr_dw));
    assert(output_dw == 0xabcdef01);
    assert(next_wptr_dw == 0x123456789abcdef0ull);
    for (uint32_t value : output)
        assert(value == 0xfeedface);
}

int main() {
    uint8_t fw_shared[kVcn402FwSharedSize];
    for (uint8_t &value : fw_shared)
        value = 0xff;
    assert(encode_vcn402_fw_shared(fw_shared, sizeof(fw_shared), true));
    assert(fw_shared[0] == 0x14);
    assert(fw_shared[1] == 0x08);
    assert(fw_shared[2] == 0);
    assert(fw_shared[3] == 0);
    assert(fw_shared[kVcn402UnifiedQueueOffset] == 1);
    assert(fw_shared[kVcn402UnifiedQueueOffset + 1] == 0);
    assert(fw_shared[kVcn402SmuDpmInterfaceOffset] == 1);
    assert(fw_shared[kVcn402DrmKeyWorkaroundOffset] == kVcn402DrmKeyWorkaroundMethod);
    for (uint32_t index = 0; index < sizeof(fw_shared); ++index) {
        const uint8_t expected = index == 0 ? 0x14 : index == 1 ? 0x08 :
                                 index == kVcn402UnifiedQueueOffset ? 1 :
                                 index == kVcn402SmuDpmInterfaceOffset ? 1 :
                                 index == kVcn402DrmKeyWorkaroundOffset ? kVcn402DrmKeyWorkaroundMethod : 0;
        assert(fw_shared[index] == expected);
    }
    assert(encode_vcn402_fw_shared(fw_shared, sizeof(fw_shared), false));
    assert(fw_shared[kVcn402SmuDpmInterfaceOffset] == 0);
    for (uint32_t index = 0; index < sizeof(fw_shared); ++index) {
        const uint8_t expected = index == 0 ? 0x14 : index == 1 ? 0x08 :
                                 index == kVcn402UnifiedQueueOffset ? 1 :
                                 index == kVcn402DrmKeyWorkaroundOffset ? kVcn402DrmKeyWorkaroundMethod : 0;
        assert(fw_shared[index] == expected);
    }
    for (uint8_t &value : fw_shared)
        value = 0x5a;
    assert(!encode_vcn402_fw_shared(fw_shared, sizeof(fw_shared) - 1, true));
    for (uint8_t value : fw_shared)
        assert(value == 0x5a);

    uint32_t reg_wait[4] = {0xfeedface, 0xfeedface, 0xfeedface, 0xfeedface};
    uint32_t reg_wait_dw = 0xabcdef01;
    assert(encode_reg_wait(reg_wait, 4, 0x1234, 0xffffffff, 0x56789abc, &reg_wait_dw));
    assert(reg_wait_dw == 4);
    assert(reg_wait[0] == kUnifiedRegWait);
    assert(reg_wait[1] == 0x48d0);
    assert(reg_wait[2] == 0xffffffff);
    assert(reg_wait[3] == 0x56789abc);
    for (uint32_t index = 0; index < 4; ++index)
        reg_wait[index] = 0xfeedface;
    reg_wait_dw = 0xabcdef01;
    assert(!encode_reg_wait(reg_wait, 3, 0x1234, 0xffffffff, 0x56789abc, &reg_wait_dw));
    assert(reg_wait_dw == 0xabcdef01);
    for (uint32_t value : reg_wait)
        assert(value == 0xfeedface);
    assert(!encode_reg_wait(reg_wait, 4, (UINT32_MAX >> 2) + 1, 0xffffffff, 0x56789abc, &reg_wait_dw));
    assert(reg_wait_dw == 0xabcdef01);
    for (uint32_t value : reg_wait)
        assert(value == 0xfeedface);
    assert(!encode_reg_wait(nullptr, 4, 0x1234, 0xffffffff, 0x56789abc, &reg_wait_dw));
    assert(!encode_reg_wait(reg_wait, 4, 0x1234, 0xffffffff, 0x56789abc, nullptr));

    uint32_t output[kUnifiedMaxSubmissionDwords]{};
    uint32_t output_dw = 0;
    uint64_t next_wptr_dw = 0;
    constexpr uint64_t ib_gpu_va = 0xffff800012340000ull;
    constexpr uint64_t fence_gpu_va = 0xffff800056780008ull;
    constexpr uint32_t ib_dw = 0x345;
    constexpr uint32_t fence_sequence = 0x89abcdef;

    assert(encode_unified_submission(output, kUnifiedMaxSubmissionDwords, 0, 512, 8, ib_gpu_va, ib_dw, 256,
                                     fence_gpu_va, fence_sequence, &output_dw, &next_wptr_dw));
    assert(output_dw == kUnifiedAlignDwords);
    assert(next_wptr_dw == kUnifiedAlignDwords);
    assert(output[0] == kUnifiedIndirectBuffer);
    assert(output[1] == 8);
    assert(output[2] == 0x12340000);
    assert(output[3] == 0xffff8000);
    assert(output[4] == ib_dw);
    assert(output[5] == kUnifiedFence);
    assert(output[6] == 0x56780008);
    assert(output[7] == 0xffff8000);
    assert(output[8] == fence_sequence);
    assert(output[9] == kUnifiedTrap);
    assert(output[10] == kUnifiedEnd);
    for (uint32_t index = 11; index < output_dw; ++index)
        assert(output[index] == kUnifiedNoop);

    assert(encode_unified_submission(output, kUnifiedMaxSubmissionDwords, 5, 4096, 15, ib_gpu_va, ib_dw, 256,
                                     fence_gpu_va, 1, &output_dw, &next_wptr_dw));
    assert(output_dw == 59);
    assert(next_wptr_dw == 64);
    assert(output[0] == kUnifiedIndirectBuffer);
    assert(output[1] == 15);
    assert(output[9] == kUnifiedTrap);
    assert(output[10] == kUnifiedEnd);
    for (uint32_t index = 11; index < output_dw; ++index)
        assert(output[index] == kUnifiedNoop);

    assert(encode_unified_submission(output, kUnifiedMaxSubmissionDwords, 127, 256, 8, ib_gpu_va, ib_dw, 256,
                                     fence_gpu_va, 2, &output_dw, &next_wptr_dw));
    assert(output_dw == 65);
    assert(next_wptr_dw == 192);
    assert(output[0] == kUnifiedIndirectBuffer);
    assert(output[9] == kUnifiedTrap);
    assert(output[10] == kUnifiedEnd);
    for (uint32_t index = 11; index < output_dw; ++index)
        assert(output[index] == kUnifiedNoop);

    rejected(12, 8, ib_gpu_va, ib_dw, 256, fence_gpu_va, kUnifiedMaxSubmissionDwords);
    rejected(512, 7, ib_gpu_va, ib_dw, 256, fence_gpu_va, kUnifiedMaxSubmissionDwords);
    rejected(512, 16, ib_gpu_va, ib_dw, 256, fence_gpu_va, kUnifiedMaxSubmissionDwords);
    rejected(512, 8, ib_gpu_va + 4, ib_dw, 256, fence_gpu_va, kUnifiedMaxSubmissionDwords);
    rejected(512, 8, ib_gpu_va, 0, 256, fence_gpu_va, kUnifiedMaxSubmissionDwords);
    rejected(512, 8, ib_gpu_va, ib_dw, 0, fence_gpu_va, kUnifiedMaxSubmissionDwords);
    rejected(512, 8, ib_gpu_va, ib_dw, 256, fence_gpu_va + 1, kUnifiedMaxSubmissionDwords);
    rejected(512, 8, ib_gpu_va, ib_dw, 256, fence_gpu_va, kUnifiedSubmissionDwords - 1);
    rejected(512, 8, ib_gpu_va, ib_dw, 256, fence_gpu_va, kUnifiedMaxSubmissionDwords, UINT64_MAX - 63);
    assert(encode_unified_submission(output, kUnifiedMaxSubmissionDwords, UINT64_MAX - 127, 512, 8, ib_gpu_va,
                                    ib_dw, 256, fence_gpu_va, fence_sequence, &output_dw, &next_wptr_dw));
    assert(next_wptr_dw == UINT64_MAX - 63);
    rejected(512, 8, UINT64_MAX - 255, ib_dw, 256, fence_gpu_va, kUnifiedMaxSubmissionDwords);

    uint32_t no_output_dw = 0;
    uint64_t no_next_wptr = 0;
    assert(!encode_unified_submission(nullptr, kUnifiedMaxSubmissionDwords, 0, 512, 8, ib_gpu_va, ib_dw, 256,
                                      fence_gpu_va, fence_sequence, &no_output_dw, &no_next_wptr));
    assert(!encode_unified_submission(output, kUnifiedMaxSubmissionDwords, 0, 512, 8, ib_gpu_va, ib_dw, 256,
                                      fence_gpu_va, fence_sequence, nullptr, &no_next_wptr));

    const uint64_t multi_ib_va[] = {ib_gpu_va, ib_gpu_va + 0x1000, ib_gpu_va + 0x2000};
    const uint32_t multi_ib_dw[] = {ib_dw, 8, 16};
    assert(encode_unified_submission(output, kUnifiedMaxSubmissionDwords, 5, 512, 8, multi_ib_va, multi_ib_dw,
                                     3, 256, fence_gpu_va, fence_sequence, &output_dw, &next_wptr_dw));
    assert(output_dw == 59);
    assert(next_wptr_dw == 64);
    assert(output[0] == kUnifiedIndirectBuffer);
    assert(output[4] == ib_dw);
    assert(output[5] == kUnifiedIndirectBuffer);
    assert(output[9] == 8);
    assert(output[10] == kUnifiedIndirectBuffer);
    assert(output[14] == 16);
    assert(output[15] == kUnifiedFence);
    assert(output[20] == kUnifiedEnd);
    for (uint32_t index = 21; index < output_dw; ++index)
        assert(output[index] == kUnifiedNoop);

    uint64_t max_ib_va[kUnifiedMaxIndirectBuffers];
    uint32_t max_ib_dw[kUnifiedMaxIndirectBuffers];
    for (uint32_t index = 0; index < kUnifiedMaxIndirectBuffers; ++index) {
        max_ib_va[index] = ib_gpu_va + static_cast<uint64_t>(index) * 0x1000;
        max_ib_dw[index] = 1;
    }
    assert(encode_unified_submission(output, kUnifiedMaxSubmissionDwords, 0, 4096, 15, max_ib_va, max_ib_dw,
                                     kUnifiedMaxIndirectBuffers, 256, fence_gpu_va, fence_sequence, &output_dw,
                                     &next_wptr_dw));
    assert(output_dw == 6 * kUnifiedAlignDwords);
    assert(next_wptr_dw == 6 * kUnifiedAlignDwords);
    assert(output[0] == kUnifiedIndirectBuffer);
    assert(output[5 * (kUnifiedMaxIndirectBuffers - 1)] == kUnifiedIndirectBuffer);
    assert(output[5 * (kUnifiedMaxIndirectBuffers - 1) + 4] == 1);
    assert(output[5 * kUnifiedMaxIndirectBuffers] == kUnifiedFence);
    assert(output[5 * kUnifiedMaxIndirectBuffers + 5] == kUnifiedEnd);

    uint32_t short_output[kUnifiedMaxSubmissionDwords];
    for (uint32_t &value : short_output)
        value = 0xfeedface;
    uint32_t short_output_dw = 0xabcdef01;
    uint64_t short_next_wptr = 0x123456789abcdef0ull;
    assert(!encode_unified_submission(short_output, 6 * kUnifiedAlignDwords - 1, 0, 4096, 15, max_ib_va,
                                      max_ib_dw, kUnifiedMaxIndirectBuffers, 256, fence_gpu_va, fence_sequence,
                                      &short_output_dw, &short_next_wptr));
    assert(short_output_dw == 0xabcdef01);
    assert(short_next_wptr == 0x123456789abcdef0ull);
    for (uint32_t value : short_output)
        assert(value == 0xfeedface);

    uint64_t excessive_ib_va[kUnifiedMaxIndirectBuffers + 1];
    uint32_t excessive_ib_dw[kUnifiedMaxIndirectBuffers + 1];
    for (uint32_t index = 0; index < kUnifiedMaxIndirectBuffers + 1; ++index) {
        excessive_ib_va[index] = ib_gpu_va + static_cast<uint64_t>(index) * 0x1000;
        excessive_ib_dw[index] = 1;
    }
    assert(!encode_unified_submission(short_output, kUnifiedMaxSubmissionDwords, 0, 4096, 15, excessive_ib_va,
                                      excessive_ib_dw, kUnifiedMaxIndirectBuffers + 1, 256, fence_gpu_va,
                                      fence_sequence, &short_output_dw, &short_next_wptr));
    assert(short_output_dw == 0xabcdef01);
    assert(short_next_wptr == 0x123456789abcdef0ull);
    for (uint32_t value : short_output)
        assert(value == 0xfeedface);

    const uint64_t overflowing_ib_va[] = {ib_gpu_va, UINT64_MAX - 255};
    const uint32_t overflowing_ib_dw[] = {ib_dw, 128};
    assert(!encode_unified_submission(short_output, kUnifiedMaxSubmissionDwords, 0, 512, 8, overflowing_ib_va,
                                      overflowing_ib_dw, 2, 256, fence_gpu_va, fence_sequence,
                                      &short_output_dw, &short_next_wptr));
    for (uint32_t value : short_output)
        assert(value == 0xfeedface);

    uint32_t multi_output[kUnifiedMaxSubmissionDwords];
    for (uint32_t &value : multi_output)
        value = 0xfeedface;
    uint32_t multi_output_dw = 0xabcdef01;
    uint64_t multi_next_wptr = 0x123456789abcdef0ull;
    const uint64_t bad_multi_ib_va[] = {ib_gpu_va, ib_gpu_va + 4};
    const uint32_t bad_multi_ib_dw[] = {ib_dw, 8};
    assert(!encode_unified_submission(multi_output, kUnifiedMaxSubmissionDwords, 0, 512, 8, bad_multi_ib_va,
                                      bad_multi_ib_dw, 2, 256, fence_gpu_va, fence_sequence, &multi_output_dw,
                                      &multi_next_wptr));
    assert(multi_output_dw == 0xabcdef01);
    assert(multi_next_wptr == 0x123456789abcdef0ull);
    for (uint32_t value : multi_output)
        assert(value == 0xfeedface);

    uint32_t multi_ring[256];
    for (uint32_t &value : multi_ring)
        value = 0xfeedface;
    uint32_t multi_submitted_dw = 0;
    uint64_t multi_ring_next_wptr = 0;
    assert(place_unified_submission(multi_ring, 256, 250, 200, 8, multi_ib_va, multi_ib_dw, 3, 256,
                                    fence_gpu_va, fence_sequence, &multi_submitted_dw, &multi_ring_next_wptr));
    assert(multi_ring_next_wptr == 320);
    assert(multi_ring[250] == kUnifiedIndirectBuffer);
    assert(multi_ring[254] == ib_dw);
    assert(multi_ring[255] == kUnifiedIndirectBuffer);
    assert(multi_ring[4] == kUnifiedIndirectBuffer);
    assert(multi_ring[9] == kUnifiedFence);

    uint32_t ring[256];
    for (uint32_t &value : ring)
        value = 0xfeedface;
    uint32_t submitted_dw = 0;
    uint64_t ring_next_wptr = 0;
    assert(place_unified_submission(ring, 256, 5, 0, 8, ib_gpu_va, ib_dw, 256, fence_gpu_va, fence_sequence,
                                    &submitted_dw, &ring_next_wptr));
    assert(submitted_dw == 59);
    assert(ring_next_wptr == 64);
    assert(ring[5] == kUnifiedIndirectBuffer);
    assert(ring[14] == kUnifiedTrap);
    assert(ring[15] == kUnifiedEnd);
    for (uint32_t index = 16; index < 64; ++index)
        assert(ring[index] == kUnifiedNoop);

    for (uint32_t &value : ring)
        value = 0xfeedface;
    assert(place_unified_submission(ring, 256, 256, 192, 8, ib_gpu_va, ib_dw, 256, fence_gpu_va, fence_sequence,
                                    &submitted_dw, &ring_next_wptr));
    assert(ring_next_wptr == 320);
    assert(ring[0] == kUnifiedIndirectBuffer);
    assert(ring[10] == kUnifiedEnd);
    assert(ring[63] == kUnifiedNoop);

    for (uint32_t &value : ring)
        value = 0xfeedface;
    assert(place_unified_submission(ring, 256, 250, 200, 8, ib_gpu_va, ib_dw, 256, fence_gpu_va, fence_sequence,
                                    &submitted_dw, &ring_next_wptr));
    assert(ring_next_wptr == 320);
    assert(ring[250] == kUnifiedIndirectBuffer);
    assert(ring[255] == kUnifiedFence);
    assert(ring[4] == kUnifiedEnd);
    for (uint32_t index = 5; index < 64; ++index)
        assert(ring[index] == kUnifiedNoop);

    for (uint32_t &value : ring)
        value = 0xfeedface;
    assert(place_unified_submission(ring, 256, 192, 4, 8, ib_gpu_va, ib_dw, 256, fence_gpu_va, fence_sequence,
                                    &submitted_dw, &ring_next_wptr));
    assert(ring_next_wptr == 256);
    for (uint32_t &value : ring)
        value = 0xfeedface;
    assert(!place_unified_submission(ring, 256, 192, 0, 8, ib_gpu_va, ib_dw, 256, fence_gpu_va, fence_sequence,
                                     &submitted_dw, &ring_next_wptr));
    for (uint32_t value : ring)
        assert(value == 0xfeedface);

    for (uint32_t &value : ring)
        value = 0xfeedface;
    submitted_dw = 0xabcdef01;
    ring_next_wptr = 0x123456789abcdef0ull;
    assert(!place_unified_submission(ring, 256, 192, 0, 8, ib_gpu_va, ib_dw, 256, fence_gpu_va, fence_sequence,
                                     &submitted_dw, &ring_next_wptr));
    assert(submitted_dw == 0xabcdef01);
    assert(ring_next_wptr == 0x123456789abcdef0ull);
    for (uint32_t value : ring)
        assert(value == 0xfeedface);
    assert(!place_unified_submission(ring, 256, 64, 128, 8, ib_gpu_va, ib_dw, 256, fence_gpu_va, fence_sequence,
                                     &submitted_dw, &ring_next_wptr));
    assert(!place_unified_submission(ring, 256, 257, 0, 8, ib_gpu_va, ib_dw, 256, fence_gpu_va, fence_sequence,
                                     &submitted_dw, &ring_next_wptr));
    assert(!place_unified_submission(ring, 256, 256, 0, 8, ib_gpu_va, ib_dw, 256, fence_gpu_va, fence_sequence,
                                     &submitted_dw, &ring_next_wptr));
    return 0;
}
