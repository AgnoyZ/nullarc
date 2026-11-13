/* SPDX-License-Identifier: MIT
 * Execute the patched pinned transport with fake IOKit, not the installed driver.
 */
#include "radv_iokit_stubs.h"
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned call_count, map_count, service_calls, log_count, observed_selector;
static int injected_status;
static char messages[8][384];
static pthread_mutex_t log_lock = PTHREAD_MUTEX_INITIALIZER;

void fake_os_log(int log, const char *format, const char *line) {
   assert(log == OS_LOG_DEFAULT && !strcmp(format, "%{public}s"));
   pthread_mutex_lock(&log_lock);
   assert(log_count < 8 && strlen(line) < sizeof(messages[0]));
   strcpy(messages[log_count++], line);
   pthread_mutex_unlock(&log_lock);
   errno = EIO; /* The diagnostic must preserve the caller's errno. */
}
kern_return_t IOConnectCallMethod(io_connect_t conn, uint32_t selector, const uint64_t *sin,
   uint32_t nsin, const void *stin, size_t stinsz, uint64_t *sout, uint32_t *nsout,
   void *stout, size_t *stoutsz) {
   assert(conn == 88);
   __atomic_fetch_add(&call_count, 1, __ATOMIC_RELAXED);
   if (selector != PHXN_SEL_BOCREATE) observed_selector = selector;
   (void)sin; (void)nsin; (void)stin; (void)stinsz;
   if (sout) sout[0] = 73;
   if (nsout) *nsout = 1;
   if (stout) *(unsigned char *)stout = 29;
   if (stoutsz) *stoutsz = 1;
   return injected_status;
}
kern_return_t IOConnectMapMemory64(io_connect_t conn, uint32_t handle, uint32_t task,
   mach_vm_address_t *address, mach_vm_size_t *size, unsigned flags) {
   assert(conn == 88 && handle == 37 && task == 19 && flags == kIOMapAnywhere);
   ++map_count; *address = 0x13579000ull; *size = 8192;
   return injected_status;
}
kern_return_t IOConnectUnmapMemory64(io_connect_t a, uint32_t b, uint32_t c, mach_vm_address_t d) {
   (void)a; (void)b; (void)c; (void)d; assert(!"unexpected unmap"); return 0;
}
uint32_t mach_task_self(void) { return 19; }
const char *acd_kext_service_class(void) { ++service_calls; return ACD_SERVICE_PHOENIX; }
struct acd_kext *acd_kext_create(const struct acd_kext_ops *a, void *b) {
   (void)a; (void)b; ++service_calls; return NULL;
}
int acd_kr_to_errno(uint32_t a, int b) { (void)a; (void)b; ++service_calls; return -EIO; }
void *IOServiceMatching(const char *s) { (void)s; ++service_calls; return NULL; }
io_service_t IOServiceGetMatchingService(uint32_t p, void *s) { (void)p; (void)s; ++service_calls; return 0; }
int IOObjectRelease(io_service_t s) { (void)s; ++service_calls; return 0; }
int IOServiceOpen(io_service_t s, uint32_t t, uint32_t u, io_connect_t *c) {
   (void)s; (void)t; (void)u; (void)c; ++service_calls; return KERN_FAILURE;
}
int IOServiceClose(io_connect_t c) { (void)c; ++service_calls; return 0; }

#include "radv_iokit_patched.inc"

static void reset(void) {
   call_count = map_count = log_count = observed_selector = 0;
   memset(messages, 0, sizeof(messages));
   memset(acd_alloc_failures, 0, sizeof(acd_alloc_failures));
}

static int invoke(unsigned operation, bool proxy, bool malformed) {
   struct iokit_ctx context = {.conn = 88, .proxy = proxy};
   struct n48n_gem_create_in create = {8192, 65536, 6, 9};
   struct n48n_gem_va va = {.handle = 37, .operation = N48N_VA_OP_MAP,
      .flags = 7, .va_address = 0x13579000ull, .offset_in_bo = 4096, .map_size = 8192};
   uint64_t sin[4] = {0x13579000ull, 8192, 0, 0}, sout[4] = {0};
   uint32_t count = 4;
   unsigned char output = 0;
   size_t output_size = 8;
   uint32_t selector = ACD_SEL_BO_CREATE;
   const void *input = &create;
   size_t bytes = sizeof(create);
   if (operation == ACD_ALLOC_IMPORT) { selector = ACD_SEL_BO_IMPORT_HOST; input = NULL; bytes = 0; }
   if (operation == ACD_ALLOC_GPU_MAP || operation == ACD_ALLOC_GPU_UNMAP) {
      selector = ACD_SEL_GEM_VA; input = &va; bytes = sizeof(va);
      if (operation == ACD_ALLOC_GPU_UNMAP) va.operation = N48N_VA_OP_UNMAP;
   }
   if (operation == ACD_ALLOC_CPU_MAP) {
      void *address = (void *)(uintptr_t)0xabcdef;
      size_t mapped = 7;
      int status = iokit_map(&context, 37, &address, &mapped);
      assert(status == injected_status);
      if (!status) assert((uintptr_t)address == 0x13579000ull && mapped == 8192);
      else assert((uintptr_t)address == 0xabcdef && mapped == 7);
      return status;
   }
   if (operation == ACD_ALLOC_OPERATION_COUNT) selector = ACD_SEL_HELLO;
   if (malformed) { input = NULL; bytes = 1; }
   int status = iokit_call(&context, selector, sin, 4, input, bytes,
                           sout, &count, &output, &output_size);
   assert(status == injected_status && count == 1 && output_size == 1 && sout[0] == 73 && output == 29);
   return status;
}

static void *concurrent_failure(void *unused) {
   (void)unused;
   for (unsigned i = 0; i < 50; ++i) invoke(ACD_ALLOC_CREATE, false, false);
   return NULL;
}

int main(void) {
   const uint32_t errors[] = {0xe00002bdu, 0xe00002beu, 0xe00002c1u, 0xe00002d6u};
   const char *names[] = {"BO_CREATE", "BO_IMPORT_HOST", "GPU_MAP", "GPU_UNMAP", "CPU_MAP"};
   unsigned cases = 0;
   for (unsigned op = 0; op < ACD_ALLOC_OPERATION_COUNT; ++op)
      for (unsigned proxy = 0; proxy < 2; ++proxy)
         for (unsigned error = 0; error <= 4; ++error) {
            reset();
            injected_status = error == 4 ? KERN_SUCCESS : (int)errors[error];
            errno = ERANGE;
            invoke(op, proxy, false);
            assert(errno == ERANGE && call_count + map_count == 1 && !service_calls);
            assert(log_count == (error == 4 ? 0u : 1u));
            if (error != 4) {
               char status[40]; snprintf(status, sizeof(status), "IOReturn=0x%08x", errors[error]);
               assert(strstr(messages[0], status) && strstr(messages[0], names[op]));
               assert(strstr(messages[0], proxy ? "route=proxy" : "route=direct"));
               assert(strstr(messages[0], "sample=1/8") && !strstr(messages[0], "13579000"));
               if (op != ACD_ALLOC_CPU_MAP) assert(strstr(messages[0], "bytes=8192"));
               if (op == ACD_ALLOC_CREATE) {
                  assert(strstr(messages[0], "alignment=65536 domains=0x6 flags=0x9"));
                  assert(strstr(messages[0], proxy ? "selector=15 " : "selector=3 "));
               }
               if (op == ACD_ALLOC_IMPORT) assert(strstr(messages[0], proxy ? "selector=16 " : "selector=21 "));
               if (op == ACD_ALLOC_CPU_MAP) assert(strstr(messages[0], "handle=37"));
            }
            ++cases;
         }
   reset(); injected_status = (int)errors[0];
   invoke(ACD_ALLOC_CREATE, false, true);
   invoke(ACD_ALLOC_OPERATION_COUNT, false, false);
   assert(call_count == 2 && !log_count); cases += 2;
   reset();
   for (unsigned i = 0; i < 100; ++i) invoke(ACD_ALLOC_CREATE, false, false);
   assert(call_count == 100 && log_count == 8 && acd_alloc_failures[ACD_ALLOC_CREATE] == 8);
   assert(strstr(messages[7], "sample=8/8")); ++cases;
   reset();
   pthread_t threads[24];
   for (unsigned i = 0; i < 24; ++i) assert(!pthread_create(&threads[i], NULL, concurrent_failure, NULL));
   for (unsigned i = 0; i < 24; ++i) assert(!pthread_join(threads[i], NULL));
   assert(call_count == 1200 && log_count == 8 && acd_alloc_failures[ACD_ALLOC_CREATE] == 8);
   assert(!service_calls); ++cases;
   printf("{\"cases\":%u,\"concurrent_calls\":1200,\"hardware_executed\":false,\"real_iokit_linked\":false}\n", cases);
}
