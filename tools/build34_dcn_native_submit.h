#pragma once

#include <stdbool.h>
#include <stdint.h>

struct build34_dcn_ib {
   uint64_t va;
   uint32_t bytes;
   uint32_t index;
};

struct build34_dcn_native_submit {
   uint64_t sequence, owner, serial, generation;
   uint32_t slot, queue, context;
};

static inline bool
build34_dcn_valid_native_submit(struct build34_dcn_native_submit receipt, uint64_t sequence)
{
   return receipt.sequence == sequence && sequence && sequence != UINT64_MAX &&
          receipt.owner && receipt.serial && receipt.serial != UINT64_MAX &&
          receipt.generation && receipt.generation != UINT64_MAX && receipt.slot < 64 && receipt.queue == 1;
}
