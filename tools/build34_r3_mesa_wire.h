// SPDX-License-Identifier: MIT
#ifndef BUILD34_R3_MESA_WIRE_H
#define BUILD34_R3_MESA_WIRE_H

#include "ac_darwin_kext.h"

struct phx34_mesa_wire {
   uint64_t owner;
   void *ctx;
   int (*call)(void *ctx, uint32_t selector, const void *input, size_t input_size,
               void *output, size_t *output_size);
};

int phx34_mesa_wire_backend(struct phx34_mesa_wire *wire, struct acd_exact_backend *out);

#endif
