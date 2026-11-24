#pragma once

#include "build34_dcn_native_submit.h"
#include "build34_exact_submit_wire.h"

#define PHX34_R3_CAP_DCN_WRITER (1u << 3)
#define PHX34_R3_DCN_FLAGS (PHX34_R3_PRESSURE_FLAGS | PHX34_R3_CAP_DCN_WRITER)
#define PHX34_R3_REPLY_WRITER_SUBMITTED 5u

struct build34_dcn_writer_request {
    struct phx34_r3_submit_request submit;
    struct build34_dcn_writer_nomination writer;
};

#ifdef __cplusplus
#define BUILD34_DCN_WRITER_ASSERT static_assert
#else
#define BUILD34_DCN_WRITER_ASSERT _Static_assert
#endif
BUILD34_DCN_WRITER_ASSERT(sizeof(struct build34_dcn_writer_nomination) == 40, "DCN nomination size");
BUILD34_DCN_WRITER_ASSERT(sizeof(struct build34_dcn_writer_request) == 2152, "DCN request size");
BUILD34_DCN_WRITER_ASSERT(offsetof(struct build34_dcn_writer_request, writer) == 2112, "DCN nomination offset");
#undef BUILD34_DCN_WRITER_ASSERT

static inline bool build34_dcn_valid_writer_range(const struct build34_dcn_writer_range *range)
{
    const uint64_t va_limit = 1ull << 48;
    return range->bo && range->bo < PHXN_MAX_BOS && !range->reserved && range->va >= 0x10000 &&
        range->va < va_limit && range->bytes && range->bytes <= (64ull << 20) &&
        range->bytes <= va_limit - range->va && !((range->va | range->bytes) & 4095ull);
}

static inline bool build34_dcn_valid_writer_nomination(const struct build34_dcn_writer_nomination *writer)
{
    return writer->ib.va && writer->ib.bytes && !(writer->ib.bytes & 3u) &&
        writer->ib.index < PHXN_MAX_IBS && build34_dcn_valid_writer_range(&writer->range);
}

static inline bool build34_dcn_matches_writer_ib(const struct phx34_r3_submit_request *submit,
                                                const struct build34_dcn_writer_nomination *writer)
{
    if (!build34_dcn_valid_writer_nomination(writer) || submit->submit.num_ibs > PHXN_MAX_IBS ||
        writer->ib.index >= submit->submit.num_ibs)
        return false;
    const uint64_t va_mask = (1ull << 48) - 1;
    for (uint32_t index = 0; index < submit->submit.num_ibs; ++index) {
        const struct phxn_cs_ib *ib = &submit->ibs[index];
        if (ib->ip_type != PHX_AMDGPU_HW_IP_GFX || ib->ip_instance || ib->ring)
            return false;
        if (index == writer->ib.index) {
            if (ib->va_start != writer->ib.va || ib->ib_bytes != writer->ib.bytes ||
                (ib->flags & PHX_AMDGPU_IB_FLAG_PREAMBLE))
                return false;
        } else if ((ib->va_start & va_mask) == (writer->ib.va & va_mask)) {
            return false;
        }
    }
    return true;
}
