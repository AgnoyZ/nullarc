/* SPDX-License-Identifier: MIT */
#include <IOKit/IOKitLib.h>
#include <CoreFoundation/CoreFoundation.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "navi48_native_abi.h"

#ifdef PHX34_CPU_R3
#include <errno.h>
#include <time.h>
#include "build34_radv_runtime_cpu.h"
#include "build34_exact_open_wire.h"
#include "build34_exact_progress_wire.h"
#include "build34_exact_submit_wire.h"
#ifdef PHX34_CPU_RETRY
static const uint32_t exact_flags = PHX34_R3_PRESSURE_FLAGS;
#else
static const uint32_t exact_flags = PHX34_R3_PROGRESS_FLAGS;
#endif
static unsigned scenario, attempts, sessions, hellos, releases, matches;
static unsigned match_token;
static struct cpu_exact_trace trace;
static struct phx34_r3_reply receipts[CPU_QUEUE_COUNT];
#ifdef PHX34_CPU_RETRY
static struct phx34_r3_submit_request refused_request;
#endif
static unsigned scheduled_mask, acked_mask;
static int need_prefix;
static const uint64_t owner = 0x10000000bull, first_sequence = 0x200000005ull;
const mach_port_t kIOMainPortDefault = MACH_PORT_NULL;
#define IOKIT_API(mock, symbol) symbol
#define IOKIT_LINKAGE
#else
#define IOKIT_API(mock, symbol) mock
#define IOKIT_LINKAGE static
#endif

struct cpu_bo {
   void *data;
   uint64_t size;
   unsigned maps;
#ifdef PHX34_CPU_R3
   uint64_t va, va_size;
#endif
};
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

#ifdef PHX34_CPU_R3
void phx34_cpu_select(unsigned value) { require(!armed && value < CPU_SCENARIO_COUNT); scenario = value; }
unsigned phx34_cpu_attempts(void) { return attempts; }
unsigned phx34_cpu_sessions(void) { return sessions; }
unsigned phx34_cpu_hellos(void) { return hellos; }
unsigned phx34_cpu_releases(void) { return releases; }
const struct cpu_exact_trace *phx34_cpu_exact_trace(void) { return &trace; }

void phx34_cpu_schedule_completion(unsigned queue)
{
   if (scenario == CPU_RETRY_RECOVERS) {
      require(queue == CPU_GFX && trace.submits == 2 && trace.acks == 1 && !need_prefix);
      scheduled_mask |= 1u << queue;
      return;
   }
   require(scenario == CPU_EXACT_DUAL && trace.submits == 2 && !need_prefix);
   if (queue == CPU_GFX)
      require(!scheduled_mask && !trace.completed_mask && !trace.acks);
   else
      require(queue == CPU_COMPUTE && scheduled_mask == (1u << CPU_GFX) && acked_mask == scheduled_mask &&
              trace.positive_pending);
   scheduled_mask |= 1u << queue;
}

static int mapped_ib(const struct phxn_cs_ib *ib)
{
   for (unsigned handle = 1; handle < next_handle; ++handle) {
      const struct cpu_bo *bo = &bos[handle];
      if (bo->maps && bo->va_size && ib->va_start >= bo->va && ib->ib_bytes <= bo->va_size &&
          ib->va_start - bo->va <= bo->va_size - ib->ib_bytes)
         return 1;
   }
   return 0;
}

CFMutableDictionaryRef IOServiceMatching(const char *name)
{
   require(armed && name && !strcmp(name, "PhxBringup") && matches == releases);
   ++matches;
   return (CFMutableDictionaryRef)&match_token;
}
#endif

IOKIT_LINKAGE io_service_t IOKIT_API(cpu_match, IOServiceGetMatchingService)(mach_port_t port, CFDictionaryRef dict)
{
#ifdef PHX34_CPU_R3
   require(armed && port == kIOMainPortDefault && dict == (CFDictionaryRef)&match_token &&
           matches == attempts + 1 && opens == closes);
#else
   (void)port;
   require(armed && dict && opens == closes);
   CFTypeRef name = CFDictionaryGetValue(dict, CFSTR("IOProviderClass"));
   require(name && CFEqual(name, CFSTR("PhxBringup")));
   CFRelease(dict);
#endif
   return 0x3456;
}
#ifndef PHX34_CPU_R3
static kern_return_t cpu_matches(mach_port_t port, CFDictionaryRef dict, io_iterator_t *out)
{
   (void)port; (void)out;
   if (dict) CFRelease(dict);
   require(0); return kIOReturnNotPermitted;
}
#endif
IOKIT_LINKAGE kern_return_t IOKIT_API(cpu_open, IOServiceOpen)(io_service_t service, task_port_t task,
                                                             uint32_t type, io_connect_t *out)
{
   if (!armed) { ++blocked; if (out) *out = 0; return kIOReturnNotPermitted; }
#ifdef PHX34_CPU_R3
   require(service == 0x3456 && task == mach_task_self() && type == PHX34_R3_UC_TYPE &&
           out && *out == MACH_PORT_NULL && opens == closes && ++attempts == matches);
   if (scenario == CPU_OPEN_REFUSED)
      return kIOReturnNotReady;
#else
   require(service == 0x3456 && task == mach_task_self() && type == N48N_UC_TYPE && out && opens == closes);
#endif
   ++opens; *out = 0x789a; return KERN_SUCCESS;
}
IOKIT_LINKAGE kern_return_t IOKIT_API(cpu_release, IOObjectRelease)(io_object_t object)
{
   require(object == 0x3456);
#ifdef PHX34_CPU_R3
   require(++releases == attempts);
#endif
   return KERN_SUCCESS;
}
IOKIT_LINKAGE kern_return_t IOKIT_API(cpu_close, IOServiceClose)(io_connect_t connection)
{
   require(armed && connection == 0x789a && opens == closes + 1 && !contexts);
#ifdef PHX34_CPU_R3
   require(!need_prefix && trace.submits == trace.acks + trace.short_submit_replies +
           (scenario == CPU_RETRY_NO_PROGRESS));
#endif
   for (unsigned h = 1; h < next_handle; ++h) {
      require(!bos[h].maps); free(bos[h].data); allocated -= bos[h].size; bos[h] = (struct cpu_bo){0};
   }
   require(!allocated); ++closes; return KERN_SUCCESS;
}
IOKIT_LINKAGE kern_return_t IOKIT_API(cpu_map, IOConnectMapMemory64)(io_connect_t connection, uint32_t h,
   task_port_t task, mach_vm_address_t *address, mach_vm_size_t *size, IOOptionBits options)
{
   require(armed && connection == 0x789a && opens == closes + 1 && task == mach_task_self() &&
           h && h < next_handle && bos[h].data && !bos[h].maps && options == kIOMapAnywhere && address && size);
   ++bos[h].maps; *address = (uintptr_t)bos[h].data; *size = bos[h].size; return KERN_SUCCESS;
}
IOKIT_LINKAGE kern_return_t IOKIT_API(cpu_unmap, IOConnectUnmapMemory64)(io_connect_t connection, uint32_t h,
   task_port_t task, mach_vm_address_t address)
{
   require(armed && connection == 0x789a && opens == closes + 1 && task == mach_task_self() &&
           h && h < next_handle && bos[h].maps == 1 && address == (uintptr_t)bos[h].data);
   --bos[h].maps; return KERN_SUCCESS;
}
IOKIT_LINKAGE kern_return_t IOKIT_API(cpu_call, IOConnectCallMethod)(mach_port_t connection, uint32_t sel,
   const uint64_t *input, uint32_t input_count, const void *structure, size_t structure_size,
   uint64_t *output, uint32_t *output_count, void *result, size_t *result_size)
{
   require(armed && connection == 0x789a && opens == closes + 1 && ++calls < 10000);
   switch (sel) {
#ifdef PHX34_CPU_R3
   case PHX34_R3_SEL_SESSION: {
      require(releases == attempts && hellos == 1 && ++sessions == 1);
      require(!input && !input_count && !output && !output_count && structure &&
              structure_size == sizeof(struct phx34_r3_progress_request) && result && result_size &&
              *result_size == sizeof(struct phx34_r3_progress_reply));
      const struct phx34_r3_progress_request *request = structure;
      require(request->version == PHX34_R3_WIRE_VERSION && request->size == sizeof(*request) &&
              !request->owner && !request->target && !request->timeout_ns);
      const struct phx34_r3_progress_reply reply = {
         .version = PHX34_R3_WIRE_VERSION, .size = sizeof(reply), .build = PHX34_R3_PROGRESS_BUILD,
         .flags = scenario == CPU_SESSION_CAPS ? PHX34_R3_CAP_EXACT_RECEIPTS :
                  scenario == CPU_RETRY_OLD_FLAGS ? PHX34_R3_PROGRESS_FLAGS : exact_flags,
         .owner = owner,
      };
      if (scenario == CPU_SESSION_SHORT)
         --*result_size;
      memcpy(result, &reply, *result_size);
      return KERN_SUCCESS;
   }
   case PHX34_R3_SEL_SUBMIT_RECEIPT: {
      const bool capacity_case = cpu_is_capacity_case(scenario);
      require(scenario >= CPU_EXACT_SUBMIT && sessions == 1 && hellos == 2 &&
              contexts == 1 && !need_prefix && trace.submits < (scenario == CPU_EXACT_DUAL || capacity_case ? 2u : 1u));
      const unsigned queue = trace.submits ? CPU_GFX : CPU_COMPUTE;
      struct phx34_r3_reply *receipt = &receipts[queue];
      require(!input && !input_count && !output && !output_count && structure &&
              structure_size == sizeof(struct phx34_r3_submit_request) && result && result_size &&
              *result_size == sizeof(*receipt));
      const struct phx34_r3_submit_request *request = structure;
      const struct phxn_cs_in *submit = &request->submit;
      require(request->version == PHX34_R3_WIRE_VERSION && request->size == sizeof(*request) &&
              request->owner == owner && !request->reserved[0] && !request->reserved[1] &&
              submit->abi == PHXN_ABI_VERSION && submit->ctx_id == 1 && submit->num_ibs &&
              submit->num_ibs <= PHXN_MAX_IBS && !submit->reserved && !submit->flags &&
              !submit->fence_handle && !submit->fence_offset);
      const struct phxn_cs_ib zero = {0};
      const uint32_t supported_ib_flags = N48N_IB_FLAG_PREAMBLE | N48N_IB_FLAG_PREEMPT |
                                          N48N_IB_FLAG_TC_WB_NOT_INVALIDATE;
      for (unsigned index = 0; index < PHXN_MAX_IBS; ++index) {
         const struct phxn_cs_ib *ib = &request->ibs[index];
         if (index >= submit->num_ibs) {
            require(!memcmp(ib, &zero, sizeof(zero)));
            continue;
         }
         require(!ib->_pad && !(ib->flags & ~supported_ib_flags) && ib->ip_type == queue && !ib->ip_instance && !ib->ring &&
                 ib->ib_bytes && !(ib->ib_bytes & 3) && ib->ib_bytes <= 0xfffffu * 4 &&
                 !(ib->va_start & 3) && mapped_ib(ib));
      }
      ++trace.submit_attempts;
#ifdef PHX34_CPU_RETRY
      if (scenario == CPU_RETRY_RAW_OOM) {
         ++trace.submit_refusals;
         return kIOReturnNoMemory;
      }
      if (capacity_case && queue == CPU_GFX) {
         if (trace.capacity_replies) {
            require(trace.acks == 1 && trace.ack_order[0] == CPU_COMPUTE && !trace.capacity_replays &&
                    scenario != CPU_RETRY_NO_PROGRESS && scenario != CPU_RETRY_LATE_PROGRESS &&
                    !memcmp(request, &refused_request, sizeof(*request)));
            ++trace.capacity_replays;
         }
         if (!trace.capacity_replies || scenario == CPU_RETRY_FULL_AGAIN) {
            refused_request = *request;
            const struct phx34_r3_reply pressure = {.version = PHX34_R3_WIRE_VERSION, .size = sizeof(pressure),
               .status = PHX34_R3_REPLY_RECEIPT_FULL, .owner = owner};
            ++trace.capacity_replies;
            memcpy(result, &pressure, sizeof(pressure));
            return KERN_SUCCESS;
         }
      }
#endif
      if (scenario == CPU_EXACT_BUSY_ONCE && trace.submit_attempts == 1) {
         ++trace.submit_refusals;
         return kIOReturnBusy;
      }
      if (scenario == CPU_EXACT_NO_RESOURCES) {
         ++trace.submit_refusals;
         return kIOReturnNoResources;
      }
      *receipt = (struct phx34_r3_reply){.version = PHX34_R3_WIRE_VERSION, .size = sizeof(*receipt),
         .status = PHX34_R3_REPLY_SUBMITTED, .owner = owner, .serial = 0x300000019ull + trace.submits,
         .sequence = first_sequence + trace.submits, .generation = 0x400000023ull + queue,
         .slot = 63 - trace.submits, .queue = queue};
      ++trace.submits;
      if (scenario == CPU_EXACT_SHORT_SUBMIT || (scenario == CPU_RETRY_SHORT_REPLY && queue == CPU_GFX)) {
         --*result_size;
         ++trace.short_submit_replies;
      }
      memcpy(result, receipt, *result_size);
      return KERN_SUCCESS;
   }
   case PHX34_R3_SEL_WAIT_RECEIPT:
   case PHX34_R3_SEL_ACK_RECEIPT: {
      const bool capacity_case = cpu_is_capacity_case(scenario);
      require((scenario == CPU_EXACT_SUBMIT || scenario == CPU_EXACT_DUAL || capacity_case) &&
              trace.submits && !need_prefix);
      require(!input && !input_count && !output && !output_count && structure &&
              structure_size == sizeof(struct phx34_r3_request) && result && result_size &&
              *result_size == sizeof(receipts[0]));
      const struct phx34_r3_request *request = structure;
      require(request->queue < CPU_QUEUE_COUNT);
      const struct phx34_r3_reply receipt = receipts[request->queue];
      const unsigned queue_mask = 1u << request->queue;
      require(receipt.sequence && !(acked_mask & queue_mask));
      require(request->version == PHX34_R3_WIRE_VERSION && request->size == sizeof(*request) &&
              request->owner == receipt.owner && request->serial == receipt.serial &&
              request->sequence == receipt.sequence && request->generation == receipt.generation &&
              request->slot == receipt.slot && request->queue == receipt.queue && !request->reserved &&
              request->timeout_ns <= 20000000ull);
      struct phx34_r3_reply reply = receipt;
      if (sel == PHX34_R3_SEL_ACK_RECEIPT) {
         require((trace.zero_polls || trace.recovery_waits) && trace.acks < trace.submits && !request->timeout_ns &&
                 (trace.completed_mask & queue_mask));
         if (scenario == CPU_EXACT_DUAL) {
            require(request->queue == (trace.acks ? CPU_COMPUTE : CPU_GFX));
            require(trace.acks ? trace.closed_prefixes : trace.gap_prefixes);
         }
         trace.ack_order[trace.acks++] = request->queue;
         acked_mask |= queue_mask;
         reply.status = PHX34_R3_REPLY_ACKED;
      } else {
         require(!(trace.completed_mask & queue_mask) && trace.zero_polls < 24 && trace.positive_waits < 8);
         if (request->timeout_ns) {
            ++trace.positive_waits;
            if (capacity_case) {
               require(request->queue == CPU_COMPUTE && trace.capacity_replies == 1 && !trace.capacity_replays &&
                       ++trace.recovery_waits == 1 && request->timeout_ns <= 5000000ull);
               if (scenario == CPU_RETRY_LATE_PROGRESS) {
                  struct timespec remaining = {.tv_nsec = 25000000};
                  while (nanosleep(&remaining, &remaining) != 0)
                     require(errno == EINTR);
               }
            } else {
               require(trace.zero_polls && request->queue == CPU_COMPUTE);
            }
            if (scenario == CPU_EXACT_SUBMIT || (capacity_case && scenario != CPU_RETRY_NO_PROGRESS) ||
                (scheduled_mask & queue_mask)) {
               trace.completed_mask |= queue_mask;
            } else {
               require(capacity_case || (trace.acks == 1 && acked_mask == (1u << CPU_GFX)));
               struct timespec remaining = {.tv_nsec = (long)request->timeout_ns};
               while (nanosleep(&remaining, &remaining) != 0)
                  require(errno == EINTR);
               ++trace.positive_pending;
            }
         } else {
            ++trace.zero_polls;
            if ((scenario == CPU_EXACT_DUAL || capacity_case) && request->queue == CPU_GFX &&
                (scheduled_mask & queue_mask))
               trace.completed_mask |= queue_mask;
         }
         reply.status = (trace.completed_mask & queue_mask) ? PHX34_R3_REPLY_COMPLETE : PHX34_R3_REPLY_PENDING;
         need_prefix = 1;
      }
      memcpy(result, &reply, sizeof(reply));
      return KERN_SUCCESS;
   }
   case PHX34_R3_SEL_PREFIX: {
      const bool capacity_case = cpu_is_capacity_case(scenario);
      require((scenario == CPU_EXACT_SUBMIT || scenario == CPU_EXACT_DUAL || capacity_case) && need_prefix);
      require(!input && !input_count && !output && !output_count && structure &&
              structure_size == sizeof(struct phx34_r3_progress_request) && result && result_size &&
              *result_size == sizeof(struct phx34_r3_progress_reply));
      const struct phx34_r3_progress_request *request = structure;
      require(request->version == PHX34_R3_WIRE_VERSION && request->size == sizeof(*request) &&
              request->owner == owner && !request->target && !request->timeout_ns);
      uint64_t retired = first_sequence - 2;
      if (scenario == CPU_EXACT_DUAL) {
         retired = first_sequence - 1;
         if (trace.completed_mask == (1u << CPU_GFX)) {
            ++trace.gap_prefixes;
         } else if (trace.completed_mask == ((1u << CPU_GFX) | (1u << CPU_COMPUTE))) {
            require(trace.acks == 1);
            retired = first_sequence + 1;
            ++trace.closed_prefixes;
         }
      } else if (capacity_case) {
         retired = first_sequence - 1;
         if (trace.completed_mask & (1u << CPU_COMPUTE))
            retired = first_sequence + !!(trace.completed_mask & (1u << CPU_GFX));
      }
      const struct phx34_r3_progress_reply reply = {
         .version = PHX34_R3_WIRE_VERSION, .size = sizeof(reply), .build = PHX34_R3_PROGRESS_BUILD,
         .flags = exact_flags, .owner = owner, .retired = retired,
      };
      need_prefix = 0;
      ++trace.prefixes;
      memcpy(result, &reply, sizeof(reply));
      return KERN_SUCCESS;
   }
#endif
   case N48N_SEL_HELLO:
      require(input_count == 2 && input[0] == 1 && input[1] == N48N_HELLO_F_MINOR && *output_count == 4);
#ifdef PHX34_CPU_R3
      require(releases == attempts && ++hellos == 1 + sessions && hellos <= 2);
#endif
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
      require(structure && structure_size == sizeof(struct n48n_gem_va));
#ifdef PHX34_CPU_R3
      if (scenario >= CPU_EXACT_SUBMIT) {
         const struct n48n_gem_va *request = structure;
         require(request->handle && request->handle < next_handle && !request->_pad &&
                 !request->vm_timeline_point && !request->vm_timeline_syncobj_out &&
                 !request->num_syncobj_handles && !request->input_fence_syncobj_handles);
         struct cpu_bo *bo = &bos[request->handle];
         require(bo->data && request->map_size && request->map_size <= bo->size &&
                 request->offset_in_bo <= bo->size - request->map_size && request->va_address);
         if (request->operation == N48N_VA_OP_MAP) {
            require(!bo->va_size);
            bo->va = request->va_address;
            bo->va_size = request->map_size;
         } else {
            require(request->operation == N48N_VA_OP_UNMAP && bo->va == request->va_address &&
                    bo->va_size == request->map_size);
            bo->va_size = 0;
         }
      }
#endif
      return KERN_SUCCESS;
   case N48N_SEL_CTX: {
      require(structure_size == sizeof(struct n48n_ctx) && result_size && *result_size == sizeof(struct n48n_ctx));
      const struct n48n_ctx *in = structure; struct n48n_ctx out = {0};
      if (in->op == N48N_CTX_OP_ALLOC) { out.op = ++contexts; require(contexts == 1); }
      else if (in->op == N48N_CTX_OP_FREE) { require(contexts == 1 && in->ctx_id == 1); --contexts; }
      else require(in->op == N48N_CTX_OP_QUERY_STATE2);
      memcpy(result, &out, sizeof(out)); return KERN_SUCCESS;
   }
   default:
      fprintf(stderr, "REFUSED unexpected CPU fixture selector %u\n", sel);
      require(0); return kIOReturnNotPermitted;
   }
}
#ifndef PHX34_CPU_R3
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
#endif
