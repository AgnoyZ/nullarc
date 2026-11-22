/* SPDX-License-Identifier: MIT */
#ifndef BUILD34_RADV_RUNTIME_CPU_H
#define BUILD34_RADV_RUNTIME_CPU_H

enum {
   CPU_OK, CPU_OPEN_REFUSED, CPU_SESSION_CAPS, CPU_SESSION_SHORT, CPU_SUBMIT_REFUSED, CPU_EXACT_SUBMIT,
};

struct cpu_exact_trace {
   unsigned submits, zero_polls, positive_waits, prefixes, acks;
};

const struct cpu_exact_trace *phx34_cpu_exact_trace(void);

#endif
