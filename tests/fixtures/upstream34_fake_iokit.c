/* SPDX-License-Identifier: MIT OR GPL-2.0-only
 * Run the actual pinned/patched entrypoints without linking IOKit or touching hardware.
 */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#define main upstream34_main
#include PHX34_SOURCE
#undef main
#undef IOConnectCallScalarMethod
#undef IOConnectCallMethod

const mach_port_t kIOMainPortDefault = 0;
static unsigned calls, writes, defaultWrites, tableWrites, tableErrors, firmwareSubmits;
static uint32_t tableLow, tableHigh, sysLow, sysHigh, sysDefault, faultDefault;
static int firstLow, firstHigh, lastLow, lastHigh;
static const char *fixture;
static int is(const char *s) { return fixture && !strcmp(fixture, s); }

CFMutableDictionaryRef IOServiceMatching(const char *name) {
   assert(!strcmp(name, "PhxBringup"));
   return CFDictionaryCreateMutable(NULL, 0, NULL, NULL);
}
io_service_t IOServiceGetMatchingService(mach_port_t port, CFDictionaryRef dictionary) {
   (void)port; CFRelease(dictionary); return 1;
}
CFTypeRef IORegistryEntryCreateCFProperty(io_registry_entry_t entry, CFStringRef key,
                                         CFAllocatorRef allocator, IOOptionBits options) {
   (void)entry; (void)allocator; (void)options;
   int64_t value = 0;
   if (CFEqual(key, CFSTR("phx-build"))) value = is("build39") ? 39 : 34;
   if (CFEqual(key, CFSTR("phx-fb-mc-base"))) value = is("wrong-mc") ? 0x8100000000ll : 0x8000000000ll;
   if (CFEqual(key, CFSTR("phx-fb-phys"))) {
      if (is("missing")) return NULL;
      if (is("wrong-type")) return CFRetain(CFSTR("32212254720"));
      value = is("reference") ? 0x6a0000000ll : 0x780000000ll;
      if (is("zero")) value = 0;
      if (is("negative")) value = -1;
      if (is("unaligned")) ++value;
      if (is("overflow")) value = 0xfffffe000000ll;
   }
   if (CFEqual(key, CFSTR("phx-fb-size"))) {
      value = is("reference") ? 0x180000000ll : 0x100000000ll;
      if (is("zero-size")) value = 0;
      if (is("small-vram")) value = 0x8000000;
   }
   if (CFEqual(key, CFSTR("phx-fb-aper-len"))) value = is("small-aperture") ? 0x8000000ll : 0x10000000ll;
   return CFNumberCreate(NULL, kCFNumberSInt64Type, &value);
}
kern_return_t IOObjectRelease(io_object_t object) { (void)object; return 0; }
kern_return_t IOServiceOpen(io_service_t service, task_port_t task, uint32_t type, io_connect_t *out) {
   (void)service; (void)task; assert(type == 0x4e34384e); *out = 2; return 0;
}
kern_return_t IOServiceClose(io_connect_t connection) { (void)connection; return 0; }

kern_return_t IOConnectCallScalarMethod(mach_port_t connection, uint32_t selector,
   const uint64_t *in, uint32_t ni, uint64_t *out, uint32_t *no) {
   (void)connection; ++calls;
   if (out && no) memset(out, 0, *no * sizeof(uint64_t));
   if (selector == 0) {
      assert(ni == 2); out[0] = in[1] ? 1 | (12u << 16) : 1; out[1] = 34;
      if (is("hello")) out[1] = 39;
      if (is("hello-size")) *no = 3;
      return 0;
   }
   if (is("transport-scalar")) return kIOReturnError;
   if (selector == 109) {
      assert(ni == 2); ++writes;
      if (in[0] >= 0x2440000 && in[0] < 0x2441000) {
         ++defaultWrites; if (in[1]) ++tableErrors;
      } else if (in[0] >= 0x2400000 && in[0] < 0x2440000) {
         uint64_t index = (in[0] - 0x2400000) / 8;
         uint64_t pte = (0x780000000ull + index * 4096) | 0x71;
         uint32_t expected = (in[0] & 4) ? (uint32_t)(pte >> 32) : (uint32_t)pte;
         if ((uint32_t)in[1] != expected) ++tableErrors;
         ++tableWrites;
         if (index == 0) { if (in[0] & 4) firstHigh = expected == in[1]; else firstLow = expected == in[1]; }
         if (index == 32767) { if (in[0] & 4) lastHigh = expected == in[1]; else lastLow = expected == in[1]; }
      } else assert(!"unexpected VRAM write in tested GART command");
   } else if (selector == 108) {
      assert(ni == 2); ++writes;
      switch (in[0]) {
         case 0x2953: tableLow = (uint32_t)in[1]; break;
         case 0x2954: tableHigh = (uint32_t)in[1]; break;
         case 0x28dd: sysLow = (uint32_t)in[1]; break;
         case 0x28de: sysHigh = (uint32_t)in[1]; break;
         case 0x2808: sysDefault = (uint32_t)in[1]; break;
         case 0x282b: faultDefault = (uint32_t)in[1]; break;
      }
   } else if (selector == 107 || selector == 105 || selector == 106 || selector == 103) {
      ++writes; ++firmwareSubmits;
      if (is("firmware-status")) out[0] = 0xffffffff;
   } else if (selector == 100) {
      ++writes; out[0] = is("SMU-status") ? 0xff : 1;
   } else if (selector == 101 || selector == 113) ++writes;
   else assert(!"unexpected scalar selector");
   return 0;
}

kern_return_t IOConnectCallMethod(mach_port_t connection, uint32_t selector,
   const uint64_t *in, uint32_t ni, const void *input, size_t inputSize,
   uint64_t *out, uint32_t *no, void *output, size_t *outputSize) {
   (void)connection; (void)in; (void)ni; (void)input; (void)inputSize; (void)out; (void)no;
   ++calls;
   if (is("transport-method")) return kIOReturnError;
   if (output && outputSize) memset(output, 0, *outputSize);
   if (is("short-output") && outputSize) *outputSize = 0;
   if (selector == 104) ++writes;
   assert(selector == 2 || selector == 102 || selector == 104);
   return 0;
}

static void report(void) {
   printf("{\"fake_IOKit\":true,\"calls\":%u,\"writes\":%u,\"default_writes\":%u,"
          "\"table_writes\":%u,\"table_errors\":%u,\"firmware_submits\":%u,\"first_last_PTE_match\":%s,"
          "\"table_base_match\":%s,\"system_range_match\":%s,\"default_addresses_match\":%s}\n",
          calls, writes, defaultWrites, tableWrites, tableErrors, firmwareSubmits,
          firstLow && firstHigh && lastLow && lastHigh ? "true":"false",
          tableLow == 0x82400001u && tableHigh == 7 ? "true":"false",
          sysLow == 0x200000u && sysHigh == 0x203fffu ? "true":"false",
          sysDefault == 0x782440u && faultDefault == 0x782440u ? "true":"false");
}
int main(int argc, char **argv) {
   fixture = getenv("PHX34_FIXTURE"); atexit(report);
   return upstream34_main(argc, argv);
}
