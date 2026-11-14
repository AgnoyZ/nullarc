/* Actual collector entrypoint, fake IOKit only. Unexpected calls assert-fail. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <sys/types.h>
#define IORegistryEntryCreateCFProperty unused_default_property
#include <IOKit/IOKitLib.h>
#undef IORegistryEntryCreateCFProperty
static CFTypeRef IORegistryEntryCreateCFProperty(io_registry_entry_t, CFStringRef, CFAllocatorRef, uint32_t);
static uid_t fake_uid(void);
#define geteuid fake_uid
#define PHX_GC_OBSERVATION_TEST
#include "../tools/phxctl/gc_state_observe.c"
#undef geteuid
static const char *fault, *variant;
static int tmr_mode;
static unsigned lookups, opens, hellos, snapshots, reads, closes;
static int is(const char *name) { return !strcmp(fault, name); }
static int number(const char *prefix, unsigned value)
{
   char text[64]; snprintf(text, sizeof(text), "%s-%u", prefix, value); return is(text);
}
static uint64_t fake_mc(void) { return !strcmp(variant, "relocated") ? 0x6000000000ull : 0x8000000000ull; }
static uint64_t fake_phys(void) { return !strcmp(variant, "relocated") ? 0x300000000ull : 0x6a0000000ull; }
static uid_t fake_uid(void) { return is("not-root") ? 501 : 0; }
static void summary(void)
{
   fprintf(stderr, "fake-gc-observation-summary {\"lookups\":%u,\"opens\":%u,\"hellos\":%u,\"snapshots\":%u,"
                   "\"reads\":%u,\"writes\":0,\"closes\":%u}\n", lookups, opens, hellos, snapshots, reads, closes);
}
static CFTypeRef IORegistryEntryCreateCFProperty(io_registry_entry_t service, CFStringRef key,
                                                CFAllocatorRef allocator, uint32_t options)
{
   assert(service == 1 && allocator == kCFAllocatorDefault && options == 0);
   if (is("property-missing")) return NULL;
   if (!strcmp(key, "phx-build")) return phxFakePropertyNumber(39);
   if (!strcmp(key, "phx-fb-mc-base")) return phxFakePropertyNumber((long long)fake_mc());
   if (!strcmp(key, "phx-fb-phys")) return phxFakePropertyNumber((long long)fake_phys());
   if (!strcmp(key, "phx-fb-size")) return phxFakePropertyNumber(0x180000000ull);
   assert(0); return NULL;
}
void *IOServiceMatching(const char *name) { assert(name && *name); return (void *)1; }
io_service_t IOServiceGetMatchingService(mach_port_t port, void *matching)
{ assert(!port && matching); ++lookups; return is("no-service") ? 0 : 1; }
mach_port_t mach_task_self(void) { return 42; }
kern_return_t IOServiceOpen(io_service_t service, mach_port_t task, uint32_t type, io_connect_t *connection)
{ assert(service == 1 && task == 42 && type == UC_TYPE); ++opens; *connection = 7; return is("open-fail") ? 5 : 0; }
kern_return_t IOObjectRelease(io_service_t service) { assert(service == 1); return 0; }
kern_return_t IOServiceClose(io_connect_t connection)
{ assert(connection == 7); ++closes; return is("close-fail") ? 5 : 0; }
kern_return_t IOConnectCallScalarMethod(io_connect_t connection, uint32_t selector,
   const uint64_t *input, uint32_t count, uint64_t *output, uint32_t *output_count)
{
   assert(connection == 7 && selector == SEL_HELLO && input && count == 2 && input[0] == 1 &&
          output && output_count && *output_count == 4 && !snapshots && !reads);
   ++hellos; memset(output, 0, 4 * sizeof(*output)); output[0] = is("hello-abi") ? 2 : 1;
   if (is("hello-short")) --*output_count;
   if (is("hello-long")) ++*output_count;
   return is("hello-fail") ? 5 : 0;
}
kern_return_t IOConnectCallMethod(io_connect_t connection, uint32_t selector, const uint64_t *input,
   uint32_t count, const void *data, size_t data_size, uint64_t *output, uint32_t *output_count,
   void *reply, size_t *reply_size)
{
   assert(connection == 7 && !data && !data_size && !output && !output_count && reply && reply_size);
   if (selector == PHX_BOOT_MEMORY_SELECTOR) {
      assert(!input && !count && *reply_size == sizeof(struct PhxBootMemory)); ++snapshots;
      assert(snapshots <= 2 && (snapshots == 1 ? reads == 0 : reads == 19));
      struct PhxBootMemory memory = {0};
      memory.version = 1; memory.flags = 1; memory.mcBase = fake_mc(); memory.physicalBase = fake_phys();
      memory.vramBytes = 0x180000000ull; memory.apertureBytes = 0x10000000;
      memory.psp = (struct PhxPspLayout){1, 0x100000, 0x4000000, 0x4000000, 0x200000, 0x100000, {0, 0}};
      if (tmr_mode) { memory.flags = 7; memory.tmrBytes = 64ull << 20; }
      if (is("tmr-zero")) memory.tmrBytes = 0;
      if (is("tmr-too-large")) memory.tmrBytes = memory.psp.tmrCapacity + 1;
      if (is("missing-ring")) memory.flags &= ~2ull;
      if (is("missing-tmr")) memory.flags &= ~4ull;
      if (is("configured-only")) memory.flags = 1;
      if (is("ring-active")) memory.flags |= 2;
      if (is("tmr-active")) memory.flags |= 4;
      if (is("gpu-active")) memory.flags |= 8;
      if (is("faulted")) memory.flags |= 16;
      if (is("unknown-flag")) memory.flags |= 32;
      if (is("snapshot-version")) memory.version = 2;
      if (is("snapshot-reserved")) memory.reserved = 1;
      if (is("snapshot-tmr")) memory.tmrBytes = 0x100000;
      if (is("snapshot-geometry")) memory.physicalBase += 0x1000;
      if (is("snapshot-unaligned")) memory.vramBytes++;
      if (is("snapshot-too-large")) memory.vramBytes = 1ull << 41;
      if (is("snapshot-layout")) memory.psp.version = 2;
      if (is("layout-reserved")) memory.psp.reserved[1] = 1;
      if (is("layout-overlap")) memory.psp.stagingOffset = memory.psp.ringOffset;
      if (is("layout-outside")) memory.psp.tmrOffset = memory.apertureBytes;
      if (is("aperture-zero")) memory.apertureBytes = 0;
      if (is("aperture-too-large")) memory.apertureBytes = memory.vramBytes + 1;
      if (is("changed-after") && snapshots == 2) memory.psp.ringOffset += 4096;
      if (is("flag-after") && snapshots == 2) memory.flags ^= 2;
      memcpy(reply, &memory, sizeof(memory));
      if (number("snapshot-short", snapshots)) --*reply_size;
      if (number("snapshot-long", snapshots)) ++*reply_size;
      return number("snapshot-fail", snapshots) ? 5 : 0;
   }
   static const uint32_t expected[] = {0x16061, 0xde3, 0x2004, 0x2002, 0x263e, 0x21a0, 0xa900,
      0xc807, 0xec00, 0xec04, 0xec43, 0xec49, 0xee6b, 0xee7e, 0xe068, 0x2008, 0xa803, 0x31b9, 0x2000};
   assert(selector == SEL_READREGS && snapshots == 1 && count == 3 && input &&
          input[1] == 1 && input[2] == UINT32_MAX && *reply_size == 4 && reads < 19);
   assert(input[0] == expected[reads]); ++reads;
   uint32_t value = is("all-zero-gc") ? 0 : number("all-ones", reads) ? UINT32_MAX : 0x12340000u + reads;
   if (reads == 1 && !number("all-ones", reads)) value = is("control-not-ready") ? 0 : 0x80000000u;
   if (reads == 2 && !number("all-ones", reads))
      value = is("control-zero-size") ? 0 : is("control-size-mismatch") ? 4096 : 6144;
   memcpy(reply, &value, 4);
   if (number("read-short", reads)) --*reply_size;
   if (number("read-long", reads)) ++*reply_size;
   return number("read-fail", reads) ? 5 : 0;
}
int main(int argc, char **argv)
{
   assert(argc == 4); variant = argv[1]; fault = argv[2];
   assert(!strcmp(variant, "reference") || !strcmp(variant, "relocated"));
   if (!strncmp(fault, "tmr:", 4)) { tmr_mode = 1; fault += 4; }
   assert(atexit(summary) == 0);
   char *arguments[] = {"gc-state-observe", tmr_mode ? "tmr-ready" : "configured", argv[3]};
   if (is("bad-mode")) arguments[1] = "auto";
   if (is("relative-path")) arguments[2] = "relative.partial";
   if (is("bad-suffix")) arguments[2] = "/no-output.bin";
   return observation_main(is("arg-count") ? 1 : 3, arguments);
}
