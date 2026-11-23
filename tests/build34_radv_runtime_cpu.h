/* SPDX-License-Identifier: MIT */
#ifndef BUILD34_RADV_RUNTIME_CPU_H
#define BUILD34_RADV_RUNTIME_CPU_H

enum {
   CPU_OK, CPU_OPEN_REFUSED, CPU_SESSION_CAPS, CPU_SESSION_SHORT, CPU_SUBMIT_REFUSED, CPU_EXACT_SUBMIT, CPU_EXACT_DUAL,
   CPU_EXACT_BUSY_ONCE, CPU_EXACT_NO_RESOURCES, CPU_EXACT_SHORT_SUBMIT,
   CPU_RETRY_RECOVERS, CPU_RETRY_NO_PROGRESS, CPU_RETRY_FULL_AGAIN, CPU_RETRY_SHORT_REPLY,
   CPU_RETRY_LATE_PROGRESS, CPU_RETRY_RAW_OOM, CPU_RETRY_OLD_FLAGS,
   CPU_SCENARIO_COUNT,
};

enum { CPU_GFX, CPU_COMPUTE, CPU_QUEUE_COUNT };

struct cpu_exact_trace {
   unsigned submit_attempts, submit_refusals, short_submit_replies;
   unsigned capacity_replies, recovery_waits, capacity_replays;
   unsigned submits, zero_polls, positive_waits, positive_pending, prefixes, acks;
   unsigned completed_mask, ack_order[CPU_QUEUE_COUNT], gap_prefixes, closed_prefixes;
};

static inline int cpu_is_capacity_case(unsigned scenario)
{
   return scenario >= CPU_RETRY_RECOVERS && scenario <= CPU_RETRY_LATE_PROGRESS;
}

const struct cpu_exact_trace *phx34_cpu_exact_trace(void);
void phx34_cpu_schedule_completion(unsigned queue);

#endif
