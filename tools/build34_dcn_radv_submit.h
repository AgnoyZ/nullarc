#pragma once

#include "build34_dcn_radv_clear.h"
#include "build34_dcn_native_submit.h"

struct radv_dcn_submitted_clear {
   struct radv_dcn_recorded_clear clear;
   struct build34_dcn_ib ib;
   struct build34_dcn_native_submit native;
};

static inline void
radv_dcn_finish_submit(struct radv_dcn_submitted_clear *observed, struct radv_dcn_submitted_clear submitted,
                       bool success)
{
   *observed = (struct radv_dcn_submitted_clear){0};
   if (success && submitted.clear.phase == RADV_DCN_CLEAR_CLOSED && submitted.clear.serial &&
       submitted.ib.va && submitted.ib.bytes && build34_dcn_valid_native_submit(submitted.native, submitted.native.sequence))
      *observed = submitted;
}
