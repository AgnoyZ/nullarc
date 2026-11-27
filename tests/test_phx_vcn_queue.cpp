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

    assert(encode_vcn402_fw_shared(fw_shared, sizeof(fw_shared), true));
    constexpr uint64_t ring_gpu_va = 0x1234567800010000ull;
    constexpr uint32_t ring_dw = 1024;
    constexpr uint32_t rb_enabled_flags = 1;
    assert(encode_vcn402_ring_setup(fw_shared, sizeof(fw_shared), ring_gpu_va, ring_dw, rb_enabled_flags));
    assert(fw_shared[0] == 0x14);
    assert(fw_shared[1] == 0x48);
    assert(fw_shared[kVcn402RingSetupOffset] == rb_enabled_flags);
    assert(fw_shared[kVcn402RingSetupOffset + 1] == 0);
    assert(fw_shared[kVcn402RingSetupOffset + 4] == 0x00);
    assert(fw_shared[kVcn402RingSetupOffset + 5] == 0x00);
    assert(fw_shared[kVcn402RingSetupOffset + 6] == 0x01);
    assert(fw_shared[kVcn402RingSetupOffset + 7] == 0x00);
    assert(fw_shared[kVcn402RingSetupOffset + 8] == 0x78);
    assert(fw_shared[kVcn402RingSetupOffset + 9] == 0x56);
    assert(fw_shared[kVcn402RingSetupOffset + 10] == 0x34);
    assert(fw_shared[kVcn402RingSetupOffset + 11] == 0x12);
    assert(fw_shared[kVcn402RingSetupOffset + 12] == 0x00);
    assert(fw_shared[kVcn402RingSetupOffset + 13] == 0x04);
    assert(fw_shared[kVcn402RingSetupOffset + 14] == 0x00);
    assert(fw_shared[kVcn402RingSetupOffset + 15] == 0x00);

    uint8_t unchanged_shared[kVcn402FwSharedSize];
    for (uint32_t index = 0; index < sizeof(fw_shared); ++index)
        unchanged_shared[index] = fw_shared[index];
    assert(!encode_vcn402_ring_setup(fw_shared, sizeof(fw_shared) - 1, ring_gpu_va, ring_dw, rb_enabled_flags));
    assert(!encode_vcn402_ring_setup(fw_shared, sizeof(fw_shared), ring_gpu_va + 4, ring_dw, rb_enabled_flags));
    assert(!encode_vcn402_ring_setup(fw_shared, sizeof(fw_shared), ring_gpu_va, ring_dw, 0));
    assert(!encode_vcn402_ring_setup(fw_shared, sizeof(fw_shared), ring_gpu_va, 63, rb_enabled_flags));
    assert(!encode_vcn402_ring_setup(fw_shared, sizeof(fw_shared), UINT64_MAX - 255, ring_dw, rb_enabled_flags));
    for (uint32_t index = 0; index < sizeof(fw_shared); ++index)
        assert(fw_shared[index] == unchanged_shared[index]);

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
