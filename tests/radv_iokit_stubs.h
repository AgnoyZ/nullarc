/* SPDX-License-Identifier: MIT
 * CPU-only IOKit and logging doubles. These functions never open a device.
 */
#ifndef RADV_IOKIT_STUBS_H
#define RADV_IOKIT_STUBS_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define static_assert _Static_assert
#include "PhxNativeABI.h"
#undef static_assert
#define n48n_gem_create_in phxn_gem_create_in
#define n48n_gem_va phxn_gem_va
#define ACD_SEL_BO_CREATE PHXN_SEL_BOCREATE
#define ACD_SEL_BO_IMPORT_HOST PHXN_SEL_BOIMPORTHOST
#define ACD_SEL_GEM_VA PHXN_SEL_GEMVA
#define ACD_SEL_HELLO PHXN_SEL_HELLO
#define N48N_VA_OP_MAP PHX_AMDGPU_VA_OP_MAP
#define N48N_VA_OP_UNMAP PHX_AMDGPU_VA_OP_UNMAP
#define N48N_UC_TYPE PHXN_UC_TYPE
#define ACD_SERVICE_PHOENIX "PhxBringup"
#define ACD_KR_EXCLUSIVE_ACCESS 0xe00002c5u
#define ACD_KR_NOT_PRIVILEGED 0xe00002c1u
#define ACD_KR_NOT_READY 0xe00002d8u
#define kIOReturnSuccess 0
#define KERN_SUCCESS 0
#define KERN_FAILURE 5
#define kIOMainPortDefault 0
#define kIOMapAnywhere 1
typedef uint32_t io_connect_t;
typedef uint32_t io_service_t;
typedef int32_t kern_return_t;
typedef uint64_t mach_vm_address_t;
typedef uint64_t mach_vm_size_t;
struct acd_kext { int unused; };
struct acd_kext_ops {
   int (*call)(void *, uint32_t, const uint64_t *, uint32_t, const void *, size_t,
               uint64_t *, uint32_t *, void *, size_t *);
   int (*map)(void *, uint32_t, void **, size_t *);
   int (*unmap)(void *, uint32_t, void *);
   void (*close)(void *);
};
const char *acd_kext_service_class(void);
struct acd_kext *acd_kext_create(const struct acd_kext_ops *, void *);
int acd_kr_to_errno(uint32_t, int);
uint32_t mach_task_self(void);
void *IOServiceMatching(const char *);
io_service_t IOServiceGetMatchingService(uint32_t, void *);
int IOObjectRelease(io_service_t);
int IOServiceOpen(io_service_t, uint32_t, uint32_t, io_connect_t *);
int IOServiceClose(io_connect_t);
kern_return_t IOConnectCallMethod(io_connect_t, uint32_t, const uint64_t *, uint32_t,
   const void *, size_t, uint64_t *, uint32_t *, void *, size_t *);
kern_return_t IOConnectMapMemory64(io_connect_t, uint32_t, uint32_t,
   mach_vm_address_t *, mach_vm_size_t *, unsigned);
kern_return_t IOConnectUnmapMemory64(io_connect_t, uint32_t, uint32_t, mach_vm_address_t);
void fake_os_log(int, const char *, const char *);
#define OS_LOG_DEFAULT 0
#define os_log_error fake_os_log
#endif
