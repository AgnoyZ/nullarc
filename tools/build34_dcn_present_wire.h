#pragma once

#include <stddef.h>

#include "build34_dcn_native_submit.h"

#define BUILD34_DCN_SEL_OFFER 69u
#define BUILD34_DCN_PRESENT_VERSION 1u
#define PHX34_R3_CAP_DCN_PRESENT (1u << 4)
#define PHX34_R3_DCN_PRESENT_FLAGS (PHX34_R3_DCN_FLAGS | PHX34_R3_CAP_DCN_PRESENT)

struct build34_dcn_present_offer {
    uint32_t version, size;
    struct build34_dcn_native_submit native;
    struct build34_dcn_writer_range range;
    uint32_t surface, reserved;
};

#ifdef __cplusplus
#define BUILD34_DCN_PRESENT_ASSERT static_assert
#else
#define BUILD34_DCN_PRESENT_ASSERT _Static_assert
#endif
BUILD34_DCN_PRESENT_ASSERT(sizeof(struct build34_dcn_present_offer) == 88, "DCN present offer size");
BUILD34_DCN_PRESENT_ASSERT(offsetof(struct build34_dcn_present_offer, range) == 56, "DCN range offset");
BUILD34_DCN_PRESENT_ASSERT(offsetof(struct build34_dcn_present_offer, surface) == 80, "DCN surface offset");
#undef BUILD34_DCN_PRESENT_ASSERT
