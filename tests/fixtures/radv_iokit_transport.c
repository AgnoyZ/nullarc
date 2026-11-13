/*
 * SPDX-License-Identifier: MIT
 *
 * IOKit transport of the native kext ABI: IOServiceOpen of class Navi48Bringup
 * (G6: or Navi48Accelerator, acd_kext_set_service_class) with user-client type
 * 'N48N' (NATIVE-S1C-ABI.md section 1).
 */

#include "ac_darwin_kext.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <unistd.h>

#include <IOKit/IOKitLib.h>
#include <mach/mach.h>

struct iokit_ctx {
   io_connect_t conn;
   bool proxy; /* opened through NMXAccel: BO_CREATE and BO_IMPORT_HOST go as 15 and 16 */
};

/* PhxAccel's accelerator hands RADV a proxy of the PhxBringup client (type 'N48N'): a sandbox that admits only
 * IOAccelerator connections (WebKit's GPU process) cannot open PhxBringup, and its message filter passes neither
 * selector 3 nor 21, so those travel as 15 and 16. */
#define ACD_PROXY_SERVICE "NMXAccel"

static int
iokit_call(void *ctx, uint32_t sel, const uint64_t *sin, uint32_t nsin, const void *stin, size_t stinsz,
           uint64_t *sout, uint32_t *nsout, void *stout, size_t *stoutsz)
{
   struct iokit_ctx *c = ctx;
   if (c->proxy)
      sel = sel == ACD_SEL_BO_CREATE ? 15 : sel == ACD_SEL_BO_IMPORT_HOST ? 16 : sel;
   uint32_t cnt = nsout ? *nsout : 0;
   size_t osz = stoutsz ? *stoutsz : 0;
   kern_return_t kr = IOConnectCallMethod(c->conn, sel, sin, nsin, stin, stinsz, sout, nsout ? &cnt : NULL,
                                          stout, stoutsz ? &osz : NULL);
   if (nsout)
      *nsout = cnt;
   if (stoutsz)
      *stoutsz = osz;
   return (int)kr;
}

static int
iokit_map(void *ctx, uint32_t handle, void **addr, size_t *size)
{
   struct iokit_ctx *c = ctx;
   mach_vm_address_t a = 0;
   mach_vm_size_t s = 0;
   kern_return_t kr = IOConnectMapMemory64(c->conn, handle, mach_task_self(), &a, &s, kIOMapAnywhere);
   if (kr == kIOReturnSuccess) {
      *addr = (void *)(uintptr_t)a;
      *size = (size_t)s;
   }
   return (int)kr;
}

static int
iokit_unmap(void *ctx, uint32_t handle, void *addr)
{
   struct iokit_ctx *c = ctx;
   return (int)IOConnectUnmapMemory64(c->conn, handle, mach_task_self(), (mach_vm_address_t)(uintptr_t)addr);
}

static void
iokit_close(void *ctx)
{
   struct iokit_ctx *c = ctx;
   IOServiceClose(c->conn);
   free(c);
}

int
acd_kext_open_iokit(struct acd_kext **out)
{
   const char *svc_class = acd_kext_service_class(); /* G6: Navi48Bringup unless the bundle chose the accelerator */
   /* RADV_DARWIN_PROXY=1: straight to the accelerator's proxy (tests the sandboxed path outside a sandbox) */
   const char *force = getenv("RADV_DARWIN_PROXY");
   io_service_t svc = force && force[0] == '1' && !strcmp(svc_class, ACD_SERVICE_PHOENIX)
                         ? 0 : IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching(svc_class));
   if (!svc && strcmp(svc_class, ACD_SERVICE_PHOENIX)) {
      fprintf(stderr, "radv-darwin: IOServiceGetMatchingService(%s) found nothing: the Navi48 kext is "
                      "not loaded (native backend unavailable)\n", svc_class);
      return -ENODEV;
   }

   io_connect_t conn = 0;
   kern_return_t kr = KERN_FAILURE;
   /* A previous client (e.g. RADV's throw-away device used for the physical-device query) may
    * still be closing: retry ExclusiveAccess for up to 2 s. */
   for (int tries = 0; svc && tries < 200; tries++) {
      kr = IOServiceOpen(svc, mach_task_self(), N48N_UC_TYPE, &conn);
      if (kr != (kern_return_t)ACD_KR_EXCLUSIVE_ACCESS)
         break;
      usleep(10000);
   }
   if (svc)
      IOObjectRelease(svc);
   bool proxy = false;
   if (kr != KERN_SUCCESS && !strcmp(svc_class, ACD_SERVICE_PHOENIX)) {
      io_service_t acc = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching(ACD_PROXY_SERVICE));
      if (acc) {
         io_connect_t pc = 0;
         if (IOServiceOpen(acc, mach_task_self(), N48N_UC_TYPE, &pc) == KERN_SUCCESS) {
            conn = pc;
            kr = KERN_SUCCESS;
            proxy = true;
         }
         IOObjectRelease(acc);
      }
   }
   if (kr != KERN_SUCCESS) {
      fprintf(stderr, "radv-darwin: IOServiceOpen(%s, type 'N48N') failed: IOReturn 0x%08x%s\n",
              svc_class, (unsigned)kr,
              (unsigned)kr == ACD_KR_EXCLUSIVE_ACCESS ? " (another native client is open)"
              : (unsigned)kr == ACD_KR_NOT_PRIVILEGED ? " (needs root)"
              : (unsigned)kr == ACD_KR_NOT_READY      ? " (native mode not available this boot)"
                                                      : "");
      return acd_kr_to_errno(ACD_SEL_HELLO, (int)kr);
   }

   struct iokit_ctx *c = calloc(1, sizeof(*c));
   if (!c) {
      IOServiceClose(conn);
      return -ENOMEM;
   }
   c->conn = conn;
   c->proxy = proxy;
   const struct acd_kext_ops ops = {
      .call = iokit_call,
      .map = iokit_map,
      .unmap = iokit_unmap,
      .close = iokit_close,
   };
   *out = acd_kext_create(&ops, c);
   return *out ? 0 : -ENOMEM;
}
