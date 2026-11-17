/* SPDX-License-Identifier: MIT
 * Execute the real Mesa shared-core / VA allocator lifecycle with CPU-only ops.
 */
#define main transport_fixture_main
#define acd_kext_open_iokit unused_open_iokit
#include "test_build34_radv_ib_tail.c"
#undef main
#undef acd_kext_open_iokit

static const char *program_name = "build34-cpu-test";
static const char *test_program_name(void) { return program_name; }
#define getprogname test_program_name
#include "ac_darwin_drm.c"
#undef getprogname

const struct amdgpu_device amdgpu_devices[] = {{
   .name="phoenix", .mmr_regs={ACD_GB_ADDR_CONFIG_REG,0,ACD_GB_ADDR_CONFIG_GFX1201},
   .dev={ .virtual_address_offset=0x20000, .virtual_address_max=0x1000000,
          .virtual_address_alignment=4096 },
}};
const size_t num_amdgpu_devices=1;
static struct fake backend;
static unsigned sync_finalized, sync_cloned, opens;
static void sync_finalize(struct util_sync_provider *p) { ++sync_finalized; free(p); }
static struct util_sync_provider *sync_clone(struct util_sync_provider *p) {
   (void)p; ++sync_cloned;
   struct util_sync_provider *result=calloc(1,sizeof(*result)); CHECK(result);
   result->finalize=sync_finalize; result->clone=sync_clone; return result;
}
struct util_sync_provider *acd_sync_provider_create(const struct acd_sync_backend *be) {
   CHECK(be && be->ctx); return sync_clone(NULL);
}
int acd_kext_open_iokit(struct acd_kext **out) { ++opens; *out=make(&backend,false); return 0; }
static void release_device(acd_device_handle dev) {
   dev->sync->finalize(dev->sync); acd_device_deinitialize(dev);
}
static int initialize(acd_device_handle *out) {
   uint32_t major=0,minor=0; int r=acd_device_initialize(&major,&minor,out);
   if (!r) CHECK(major==ACD_DRM_MAJOR && minor==ACD_DRM_MINOR); return r;
}
static void reset(void) {
   CHECK(!g_core); memset(&backend,0,sizeof(backend)); sync_finalized=sync_cloned=opens=0;
   program_name="build34-cpu-test"; unsetenv("RADV_DARWIN_BUILD34_IB_TAIL");
   unsetenv("RADV_DARWIN_CANNED"); unsetenv("RADV_DARWIN_MOCK"); unsetenv("RADV_DARWIN_HOST_BO");
}
int main(void) {
   for (unsigned enabled=0;enabled<2;++enabled) {
      reset(); if (enabled) setenv("RADV_DARWIN_BUILD34_IB_TAIL","1",1);
      acd_device_handle first=NULL,second=NULL;
      CHECK(!initialize(&first) && !initialize(&second));
      CHECK(first->core==second->core && first->core->refcount==2 && opens==1);
      CHECK(backend.create==enabled && backend.map==enabled && backend.unmap==enabled && backend.gemva==enabled);
      CHECK(!!first->core->ib_tail_reservation==enabled);
      uint64_t va=0; amdgpu_va_handle range=NULL;
      CHECK(!acd_va_range_alloc(second,amdgpu_gpu_va_range_general,4096,4096,0,&va,&range,0));
      CHECK(va==tail_va+enabled*4096); CHECK(!amdgpu_va_range_free(range));
      if (enabled) {
         CHECK(acd_va_range_alloc(second,amdgpu_gpu_va_range_general,4096,4096,tail_va,&va,&range,0)!=0);
         CHECK(!backend.close);
      }
      release_device(first); CHECK(!backend.close && g_core);
      release_device(second); CHECK(backend.close==1 && !g_core);
      CHECK(sync_finalized==3 && sync_cloned==3);
   }
   const char *invalid[]={"", "true", "01", "1extra", "2"};
   for (unsigned i=0;i<sizeof(invalid)/sizeof(*invalid);++i) {
      reset(); setenv("RADV_DARWIN_BUILD34_IB_TAIL",invalid[i],1);
      acd_device_handle dev=NULL; CHECK(initialize(&dev)==-EINVAL && !dev && !g_core);
      CHECK(!backend.create && !backend.submit && backend.close==1 && sync_finalized==1);
   }
   reset(); setenv("RADV_DARWIN_BUILD34_IB_TAIL","1",1); program_name="WindowServer";
   { acd_device_handle dev=NULL; CHECK(initialize(&dev)==-EINVAL && !dev && !g_core);
     CHECK(!backend.create && !backend.submit && backend.close==1); }
   const enum fault init_failures[]={BAD_BUILD, INFO_HUNG, CREATE_ERROR, MAP_ERROR, GEMVA_ERROR};
   for (unsigned i=0;i<sizeof(init_failures)/sizeof(*init_failures);++i) {
      reset(); setenv("RADV_DARWIN_BUILD34_IB_TAIL","1",1); backend.fault=init_failures[i];
      acd_device_handle dev=NULL; CHECK(initialize(&dev)<0 && !dev && !g_core);
      CHECK(!backend.submit && backend.close==1);
   }
   reset(); setenv("RADV_DARWIN_BUILD34_IB_TAIL","0",1);
   { acd_device_handle dev=NULL; CHECK(!initialize(&dev)); CHECK(!backend.create);
     release_device(dev); CHECK(backend.close==1); }
   printf("PASS real Mesa core and VA allocator: %u checks; shared ownership, reserved VA, fail-closed opt-in\n",checks);
   return 0;
}
