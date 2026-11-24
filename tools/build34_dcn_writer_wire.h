#pragma once

#include "build34_dcn_native_submit.h"
#include "build34_exact_submit_wire.h"

struct build34_dcn_writer_range {
    uint64_t va, bytes;
    uint32_t bo, reserved;
};

struct build34_dcn_writer_nomination {
    struct build34_dcn_ib ib;
    struct build34_dcn_writer_range range;
};

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
