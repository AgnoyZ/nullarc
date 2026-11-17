/* SPDX-License-Identifier: MIT */
#ifndef PHX34_RADV_RUNTIME_GUARD_H
#define PHX34_RADV_RUNTIME_GUARD_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
struct phx34_runtime_counts {
    uint32_t blocked, opens, closes, submits, arena_passes, tail_published, reused_changed_IB, CPU_platform;
    uint32_t first_reused_IB_bytes, second_reused_IB_bytes;
    uint64_t last_sequence, retired_sequence;
};
void phx34_runtime_counts(struct phx34_runtime_counts *out);
int phx34_runtime_platform_selftest(void);
void phx34_runtime_arm(void);
void phx34_runtime_bind_arena(void *address, size_t bytes);
void phx34_runtime_verify_pass(unsigned pass);
void phx34_runtime_finish(void);
#if defined(__GNUC__)
__attribute__((noreturn))
#endif
void phx34_runtime_hold(const char *reason);
#ifdef __cplusplus
}
#endif
#endif
