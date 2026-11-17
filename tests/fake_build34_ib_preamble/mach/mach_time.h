#ifndef PHX_TEST_MACH_TIME_H
#define PHX_TEST_MACH_TIME_H
#include <stdint.h>
struct mach_timebase_info_data_t { uint32_t numer, denom; };
static inline int mach_timebase_info(mach_timebase_info_data_t *value) {
    value->numer = 1; value->denom = 1; return 0;
}
static uint64_t phx_fake_ticks = 12345678000ull;
static inline uint64_t mach_absolute_time() { return phx_fake_ticks += 4000; }
#endif
