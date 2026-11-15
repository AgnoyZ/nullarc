/* SPDX-License-Identifier: MIT OR GPL-2.0-only
 * Narrow user-tool correction for pinned upstream build 34. No kernel ABI additions.
 */
#ifndef PHX_UPSTREAM34_LAYOUT_H
#define PHX_UPSTREAM34_LAYOUT_H
#include <stdint.h>
#include <string.h>

#define PHX34_GART_BYTES 0x8000000ull
#define PHX34_TABLE_OFFSET 0x2400000ull
#define PHX34_DEFAULT_OFFSET 0x2440000ull
#define PHX34_TOC_OFFSET 0x4000000ull
#define PHX34_TMR_OFFSET 0x8000000ull
#define PHX34_TMR_BYTES 0x4000000ull

struct Phx34Geometry { uint64_t mc, physical, bytes, aperture; };
struct Phx34Plan {
   struct Phx34Geometry geometry;
   uint64_t tablePhysical, defaultPhysical, tocMC, tmrMC, tmrPhysical;
   uint32_t systemLow, systemHigh;
};

static inline int phx34_plan(const struct Phx34Geometry *g, struct Phx34Plan *p)
{
   const uint64_t limit = 1ull << 48;
   memset(p, 0, sizeof(*p));
   if (!g || !g->physical || g->mc != 0x8000000000ull || !g->bytes ||
       ((g->mc | g->physical | g->bytes) & 0xffffffull) ||
       g->mc >= limit || g->physical >= limit || g->bytes > limit - g->mc ||
       g->bytes > limit - g->physical || g->aperture != 0x10000000ull ||
       g->aperture > g->bytes || PHX34_TMR_OFFSET + PHX34_TMR_BYTES > g->aperture ||
       PHX34_DEFAULT_OFFSET + 4096 > PHX34_GART_BYTES)
      return 0;
   p->geometry = *g;
   p->tablePhysical = g->physical + PHX34_TABLE_OFFSET;
   p->defaultPhysical = g->physical + PHX34_DEFAULT_OFFSET;
   p->tocMC = g->mc + PHX34_TOC_OFFSET;
   p->tmrMC = g->mc + PHX34_TMR_OFFSET;
   p->tmrPhysical = g->physical + PHX34_TMR_OFFSET;
   p->systemLow = (uint32_t)(g->mc >> 18);
   p->systemHigh = (uint32_t)((g->mc + g->bytes - 1) >> 18);
   return 1;
}

#ifdef PHX34_WITH_IOKIT
#include <CoreFoundation/CoreFoundation.h>
static struct Phx34Plan phx34_live;
static int phx34_ready;

static int phx34_number(io_service_t service, CFStringRef name, uint64_t *out)
{
   CFTypeRef value = IORegistryEntryCreateCFProperty(service, name, kCFAllocatorDefault, 0);
   if (!value) return 0;
   int64_t number = 0;
   int ok = CFGetTypeID(value) == CFNumberGetTypeID() &&
      CFNumberGetValue(value, kCFNumberSInt64Type, &number) && number > 0;
   CFRelease(value);
   if (ok) *out = (uint64_t)number;
   return ok;
}

static int phx34_geometry(io_service_t service)
{
   struct Phx34Geometry g = {0}; uint64_t build = 0;
   phx34_ready = 0;
   if (!phx34_number(service, CFSTR("phx-build"), &build) || build != 34 ||
       !phx34_number(service, CFSTR("phx-fb-mc-base"), &g.mc) ||
       !phx34_number(service, CFSTR("phx-fb-phys"), &g.physical) ||
       !phx34_number(service, CFSTR("phx-fb-size"), &g.bytes) ||
       !phx34_number(service, CFSTR("phx-fb-aper-len"), &g.aperture) ||
       !phx34_plan(&g, &phx34_live)) {
      fprintf(stderr, "upstream34-layout: valid original build-34 geometry required\n");
      return 0;
   }
   phx34_ready = 1;
   return 1;
}

/* Keep the upstream raw TOC/TMR order, but admit only the geometry-derived words. */
static int phx34_raw_valid(const uint64_t *in, uint32_t count)
{
   if (!phx34_ready || !in || count != 7) return 0;
   uint64_t expected[7] = {0};
   if (in[0] == 0x20) {
      uint64_t mc = phx34_live.tocMC;
      uint64_t words[7] = {0x20, (uint32_t)mc, mc >> 32, 0x900, 0, 0, 0};
      memcpy(expected, words, sizeof(expected));
   } else if (in[0] == 0x5) {
      uint64_t mc = phx34_live.tmrMC, pa = phx34_live.tmrPhysical;
      uint64_t words[7] = {0x5, (uint32_t)mc, mc >> 32, PHX34_TMR_BYTES, 2,
                           (uint32_t)pa, pa >> 32};
      memcpy(expected, words, sizeof(expected));
   } else return 0;
   return memcmp(in, expected, sizeof(expected)) == 0;
}

static kern_return_t phx34_scalar(io_connect_t connection, uint32_t selector,
   const uint64_t *in, uint32_t ni, uint64_t *out, uint32_t *no)
{
   if (!phx34_ready || (selector == 107 && !phx34_raw_valid(in, ni))) {
      fprintf(stderr, "upstream34-layout: unverified geometry or raw PSP words refused\n"); exit(75);
   }
   uint32_t expected = no ? *no : 0;
   kern_return_t kr = IOConnectCallScalarMethod(connection, selector, in, ni, out, no);
   if (kr || (no && *no != expected)) {
      fprintf(stderr, "upstream34-layout: selector %u transport/size failure\n", selector); exit(74);
   }
   if ((selector == 0 && (!out || expected != 4 || out[0] != (1u | (12u << 16)) || out[1] != 34)) ||
       ((selector == 103 || selector == 105 || selector == 106 || selector == 107) &&
        (!out || expected != 4 || out[0] != 0)) ||
       (selector == 100 && (!out || expected != 2 || out[0] != 1))) {
      fprintf(stderr, "upstream34-layout: selector %u ABI/firmware refusal\n", selector); exit(75);
   }
   return kr;
}

static kern_return_t phx34_method(io_connect_t connection, uint32_t selector,
   const uint64_t *in, uint32_t ni, const void *input, size_t inputSize,
   uint64_t *out, uint32_t *no, void *output, size_t *outputSize)
{
   if (!phx34_ready) { fprintf(stderr, "upstream34-layout: geometry not admitted\n"); exit(75); }
   uint32_t expected = no ? *no : 0;
   size_t expectedSize = outputSize ? *outputSize : 0;
   kern_return_t kr = IOConnectCallMethod(connection, selector, in, ni, input, inputSize,
                                         out, no, output, outputSize);
   if (kr || (no && *no != expected) || (outputSize && *outputSize != expectedSize)) {
      fprintf(stderr, "upstream34-layout: selector %u transport/size failure\n", selector); exit(74);
   }
   return kr;
}

#define IOConnectCallScalarMethod phx34_scalar
#define IOConnectCallMethod phx34_method
#endif
#endif
