// Narrow x86 primitives for the manual CPU-to-GPU IB publication diagnostic.
// These primitives do not initialize, submit to, or synchronize a GPU.
#ifndef PHX_IB_PUBLICATION_ARCH_H
#define PHX_IB_PUBLICATION_ARCH_H
#include <stdint.h>
#if defined(__x86_64__)
#include <cpuid.h>
#endif

static inline bool phxIbClflushCapability(unsigned *lineBytes) {
    *lineBytes = 0;
#if defined(__x86_64__)
    unsigned eax, ebx, ecx, edx;
    if (!__get_cpuid(1, &eax, &ebx, &ecx, &edx)) return false;
    *lineBytes = ((ebx >> 8) & 0xffu) * 8u;
    return (edx & (1u << 19)) != 0;
#else
    return false;
#endif
}
static inline void phxIbClflushLine(const volatile void *line) {
#if defined(__x86_64__)
    __asm__ __volatile__("clflush (%0)" :: "r"(line) : "memory");
#else
    (void)line; // Capability admission refuses this architecture before device access.
#endif
}
static inline void phxIbPublicationFence() {
#if defined(__x86_64__)
    __asm__ __volatile__("mfence" ::: "memory");
#endif
}
#endif
