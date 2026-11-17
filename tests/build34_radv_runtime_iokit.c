/* SPDX-License-Identifier: MIT */
#include <IOKit/IOKitLib.h>
#include <CoreFoundation/CoreFoundation.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "navi48_native_abi.h"

struct cpu_bo { void *data; uint64_t size; unsigned maps; };
static struct cpu_bo bos[N48N_MAX_BOS];
static unsigned opens, closes, creates, calls, blocked, next_handle = 1;
static unsigned contexts;
static uint64_t allocated;
static int armed;

static void fixture_require(int okay, unsigned line)
{
   if (!okay) {
      fprintf(stderr, "FAIL CPU IOKit fixture contract at %u (opens=%u closes=%u creates=%u calls=%u contexts=%u)\n",
              line, opens, closes, creates, calls, contexts);
      exit(77);
   }
}
#define require(okay) fixture_require((okay), __LINE__)
unsigned phx34_cpu_opens(void) { return opens; }
unsigned phx34_cpu_closes(void) { return closes; }
unsigned phx34_cpu_creates(void) { return creates; }
unsigned phx34_cpu_calls(void) { return calls; }
unsigned phx34_cpu_blocked(void) { return blocked; }
void phx34_cpu_arm(void) { require(!armed && blocked == 1 && !opens && !calls); armed = 1; blocked = 0; }

static io_service_t cpu_match(mach_port_t port, CFDictionaryRef dict)
{
   (void)port;
   require(armed && dict && opens == closes);
   CFTypeRef name = CFDictionaryGetValue(dict, CFSTR("IOProviderClass"));
   require(name && CFEqual(name, CFSTR("PhxBringup")));
   CFRelease(dict);
   return 0x3456;
}
static kern_return_t cpu_matches(mach_port_t port, CFDictionaryRef dict, io_iterator_t *out)
{
   (void)port; (void)out;
   if (dict) CFRelease(dict);
   require(0); return kIOReturnNotPermitted;
}
static kern_return_t cpu_open(io_service_t service, task_port_t task, uint32_t type, io_connect_t *out)
{
   if (!armed) { ++blocked; if (out) *out = 0; return kIOReturnNotPermitted; }
   require(service == 0x3456 && task == mach_task_self() && type == N48N_UC_TYPE && out && opens == closes);
   ++opens; *out = 0x789a; return KERN_SUCCESS;
}
static kern_return_t cpu_release(io_object_t object) { require(object == 0x3456); return KERN_SUCCESS; }
static kern_return_t cpu_close(io_connect_t connection)
{
   require(armed && connection == 0x789a && opens == closes + 1 && !contexts);
   for (unsigned h = 1; h < next_handle; ++h) {
      require(!bos[h].maps); free(bos[h].data); allocated -= bos[h].size; bos[h] = (struct cpu_bo){0};
   }
   require(!allocated); ++closes; return KERN_SUCCESS;
}
static kern_return_t cpu_map(io_connect_t connection, uint32_t h, task_port_t task,
                            mach_vm_address_t *address, mach_vm_size_t *size, IOOptionBits options)
{
   require(armed && connection == 0x789a && opens == closes + 1 && task == mach_task_self() &&
           h && h < next_handle && bos[h].data && !bos[h].maps && options == kIOMapAnywhere && address && size);
   ++bos[h].maps; *address = (uintptr_t)bos[h].data; *size = bos[h].size; return KERN_SUCCESS;
}
static kern_return_t cpu_unmap(io_connect_t connection, uint32_t h, task_port_t task, mach_vm_address_t address)
{
   require(armed && connection == 0x789a && opens == closes + 1 && task == mach_task_self() &&
           h && h < next_handle && bos[h].maps == 1 && address == (uintptr_t)bos[h].data);
   --bos[h].maps; return KERN_SUCCESS;
}
static kern_return_t cpu_call(mach_port_t connection, uint32_t sel,
   const uint64_t *input, uint32_t input_count, const void *structure, size_t structure_size,
   uint64_t *output, uint32_t *output_count, void *result, size_t *result_size)
{
   require(armed && connection == 0x789a && opens == closes + 1 && ++calls < 10000);
   switch (sel) {
   case N48N_SEL_HELLO:
      require(input_count == 2 && input[0] == 1 && input[1] == N48N_HELLO_F_MINOR && *output_count == 4);
      output[0] = 1 | (12u << 16); output[1] = 34; output[2] = 64; output[3] = 8; return KERN_SUCCESS;
   case N48N_SEL_QUERYINFO: {
      require(result_size && *result_size == sizeof(struct n48n_info));
      struct n48n_info info = {0};
      info.abi_version = 1; info.kext_build = 34; info.flags = N48N_INFO_NATIVE_BOOT | N48N_INFO_S1B_POSITIVE;
      info.vmid = 8; info.gb_addr_config = 0x242; info.gc_version = (11u << 16) | 1;
      info.ring_size_dw = 4096; info.max_ibs = 64;
      info.vram_vis_total = info.vram_vis_free = 256ull << 20;
      info.vram_hi_total = info.vram_hi_free = 768ull << 20;
      info.gtt_cap = 512ull << 20; info.gtt_used = allocated; info.gtt_max_bo = 64ull << 20;
      info.pt_cap = 16ull << 20; info.max_bos = N48N_MAX_BOS; info.fence_slots = N48N_FENCE_SLOTS;
      info.va_low_first = 0x10000; info.va_low_last = 0x7fffffffffff;
      info.va_high_first = 0xffff800000000000ull; info.va_high_last = UINT64_MAX; info.reserved[2] = 12;
      memcpy(result, &info, sizeof(info)); return KERN_SUCCESS;
   }
   case 30: return kIOReturnUnsupported;
   case N48N_SEL_BOCREATE: {
      require(structure && structure_size == sizeof(struct n48n_gem_create_in) && output_count && *output_count == 4);
      const struct n48n_gem_create_in *in = structure;
      require(in->bo_size && in->bo_size <= (64ull << 20) && in->domains &&
              !(in->domains & ~(uint64_t)(N48N_GEM_DOMAIN_GTT | N48N_GEM_DOMAIN_VRAM)));
      uint64_t size = (in->bo_size + 4095) & ~4095ull;
      require(allocated + size <= (512ull << 20) && next_handle < N48N_MAX_BOS);
      unsigned h = next_handle++;
      require(!posix_memalign(&bos[h].data, 4096, size));
      memset(bos[h].data, 0, size); bos[h].size = size; allocated += size; ++creates;
      output[0] = h; output[1] = size; output[2] = in->domains & N48N_GEM_DOMAIN_VRAM ? N48N_GEM_DOMAIN_VRAM : N48N_GEM_DOMAIN_GTT;
      output[3] = N48N_PLACED_ZEROED | N48N_PLACED_CPU_MAPPABLE; return KERN_SUCCESS;
   }
   case N48N_SEL_BOFREE: {
      require(input_count == 1 && input[0] && input[0] < next_handle);
      struct cpu_bo *b = &bos[input[0]]; require(b->data && !b->maps);
      free(b->data); allocated -= b->size; *b = (struct cpu_bo){0}; return KERN_SUCCESS;
   }
   case N48N_SEL_GEMVA:
      require(structure && structure_size == sizeof(struct n48n_gem_va)); return KERN_SUCCESS;
   case N48N_SEL_CTX: {
      require(structure_size == sizeof(struct n48n_ctx) && result_size && *result_size == sizeof(struct n48n_ctx));
      const struct n48n_ctx *in = structure; struct n48n_ctx out = {0};
      if (in->op == N48N_CTX_OP_ALLOC) { out.op = ++contexts; require(contexts == 1); }
      else if (in->op == N48N_CTX_OP_FREE) { require(contexts == 1 && in->ctx_id == 1); --contexts; }
      else require(in->op == N48N_CTX_OP_QUERY_STATE2);
      memcpy(result, &out, sizeof(out)); return KERN_SUCCESS;
   }
   default:
      fprintf(stderr, "REFUSED CPU fixture selector %u; no native dispatch or wait is modeled\n", sel);
      require(0); return kIOReturnNotPermitted;
   }
}
#define INTERPOSE(replacement, original) \
   __attribute__((used)) static const struct { const void *replace, *original; } \
   pair_##original __attribute__((section("__DATA,__interpose"))) = \
   { (const void *)(uintptr_t)&replacement, (const void *)(uintptr_t)&original }
INTERPOSE(cpu_match, IOServiceGetMatchingService);
INTERPOSE(cpu_matches, IOServiceGetMatchingServices);
INTERPOSE(cpu_open, IOServiceOpen);
INTERPOSE(cpu_release, IOObjectRelease);
INTERPOSE(cpu_close, IOServiceClose);
INTERPOSE(cpu_map, IOConnectMapMemory64);
INTERPOSE(cpu_unmap, IOConnectUnmapMemory64);
INTERPOSE(cpu_call, IOConnectCallMethod);
