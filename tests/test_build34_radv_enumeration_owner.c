/* SPDX-License-Identifier: MIT */
#include "core-prefix.h"

static unsigned opens, profile_calls, profile_success, create_calls;
static struct fake backends[8];
#define backend backends[opens ? opens-1 : 0]
struct fixture_sync { struct util_sync_provider p; bool live; };
static struct fixture_sync providers[128];
static void sync_finalize(struct util_sync_provider *p) {
   struct fixture_sync *s = (struct fixture_sync *)p;
   CHECK(s->live); s->live = false;
}
static struct util_sync_provider *sync_clone(struct util_sync_provider *p) {
   (void)p;
   for (unsigned i=0;i<128;++i) if (!providers[i].live) {
      providers[i].live=true; providers[i].p.finalize=sync_finalize; providers[i].p.clone=sync_clone;
      return &providers[i].p;
   }
   CHECK(false); return NULL;
}
struct util_sync_provider *acd_sync_provider_create(const struct acd_sync_backend *be) {
   CHECK(be && be->ctx); return sync_clone(NULL);
}
int acd_kext_open_iokit(struct acd_kext **out) { CHECK(opens<8);struct fake *f=&backends[opens++];*out=make(f,false);return 0; }
typedef struct ac_drm_device ac_drm_device;
#define HAVE_AMDGPU_DARWIN 1
#include "wrapper.inc"

typedef int VkResult;
#define VK_SUCCESS 0
#define VK_ERROR_OUT_OF_HOST_MEMORY (-1)
#define VK_ERROR_INITIALIZATION_FAILED (-3)
#define DRM_NODE_MAX 3
#define DRM_BUS_PCI 0
typedef struct { unsigned domain,bus,dev,func; } drmPciBusInfo;
typedef struct { unsigned vendor_id,device_id,subvendor_id,subdevice_id,revision_id; } drmPciDeviceInfo;
typedef struct {
   char **nodes; unsigned available_nodes,bustype;
   union {drmPciBusInfo *pci;} businfo;
   union {drmPciDeviceInfo *pci;} deviceinfo;
} drmDevice;
struct fixture_link {int unused;};
struct fixture_list {unsigned count;};
struct vk_instance {struct {struct fixture_list list;} physical_devices;};
struct radv_instance {struct vk_instance vk;};
struct radv_physical_device {struct {struct fixture_link link;} vk; ac_drm_device *drm_device;};
static struct radv_physical_device *created;
static bool fail_profile, existing_owner;
static VkResult creation_result;
static int fixture_profile(struct phx_topology *out) {
   ++profile_calls;
   if (fail_profile) return -ENODEV;
   int r=acd_profile_identity(out); if (!r) ++profile_success; return r;
}
static VkResult radv_physical_device_try_create(struct radv_instance *instance, drmDevice *drm,
                                               struct radv_physical_device **out) {
   ++create_calls; CHECK(instance && drm->deviceinfo.pci->vendor_id==0x1002 && drm->deviceinfo.pci->device_id==0x1900);
   ac_drm_device *query=NULL; uint32_t major=0,minor=0;
   CHECK(!ac_drm_device_initialize(-1,false,&major,&minor,&query));
   ac_drm_device_deinitialize(query);
   if (creation_result) return creation_result;
   created=calloc(1,sizeof(*created)); CHECK(created);
   if (existing_owner) CHECK(!ac_drm_device_initialize(-1,false,&major,&minor,&created->drm_device));
   *out=created; return VK_SUCCESS;
}
static void list_addtail(struct fixture_link *link,struct fixture_list *list) {CHECK(link);++list->count;}
#define acd_profile_identity fixture_profile
#include "enumeration.inc"
#undef acd_profile_identity

static bool baseline;
static void reset_case(const char *policy) {
   CHECK(!g_core && !created); memset(backends,0,sizeof(backends)); memset(providers,0,sizeof(providers));
   opens=profile_calls=profile_success=create_calls=0; fail_profile=existing_owner=false; creation_result=0;
   program_name="enumeration-cpu-test";
   unsetenv("RADV_DARWIN_MOCK");unsetenv("RADV_DARWIN_HOST_BO");unsetenv("RADV_DARWIN_CANNED");
   if (policy) setenv("RADV_DARWIN_BUILD34_IB_TAIL",policy,1);else unsetenv("RADV_DARWIN_BUILD34_IB_TAIL");
}
static void finish_case(void) {
   if (created) {if (created->drm_device) ac_drm_device_deinitialize(created->drm_device);free(created);created=NULL;}
   unsigned closes=0,submits=0;for(unsigned i=0;i<opens;++i){closes+=backends[i].close;submits+=backends[i].submit;}
   CHECK(!g_core && !submits && closes==opens);
   unsigned orphaned=0;for(unsigned i=0;i<128;++i)orphaned+=providers[i].live;
   CHECK(orphaned==profile_success);
}
int main(int argc,char **argv) {
   CHECK(argc==2);baseline=!strcmp(argv[1],"baseline");CHECK(baseline||!strcmp(argv[1],"patched"));
   unsigned cases=0;
   const char *policies[]={NULL,"0","1"};
   for(unsigned iteration=0;iteration<20;++iteration)for(unsigned p=0;p<3;++p)for(unsigned existing=0;existing<2;++existing) {
      reset_case(policies[p]);existing_owner=existing;
      struct radv_instance instance={0};CHECK(radv_darwin_enumerate_physical_devices(&instance.vk)==VK_SUCCESS);
      CHECK(created && instance.vk.physical_devices.list.count==1 && create_calls==1);
      bool retained=p==2&&!baseline;
      CHECK((created->drm_device!=NULL)==(retained||existing));
      CHECK(opens==(retained?1u:2u+existing));
      ac_drm_device *device=NULL;uint32_t major=0,minor=0;
      CHECK(!ac_drm_device_initialize(-1,false,&major,&minor,&device));
      CHECK(opens==(retained?1u:existing?3u:3u));
      ac_drm_device_deinitialize(device);
      if(retained)CHECK(!backend.close&&g_core&&backend.create==1);
      finish_case();++cases;
   }
   for(unsigned p=0;p<3;++p)for(unsigned mode=0;mode<3;++mode) {
      reset_case(policies[p]);fail_profile=mode==0;creation_result=mode==1?VK_ERROR_OUT_OF_HOST_MEMORY:mode==2?VK_ERROR_INITIALIZATION_FAILED:0;
      struct radv_instance instance={0};VkResult result=radv_darwin_enumerate_physical_devices(&instance.vk);
      CHECK(result==(mode==1?VK_ERROR_OUT_OF_HOST_MEMORY:VK_SUCCESS));
      CHECK(!created&&!instance.vk.physical_devices.list.count);finish_case();++cases;
   }
   const char *invalid[]={"","true","01","1extra","2"};
   for(unsigned p=0;p<5;++p) {
      reset_case(invalid[p]);struct radv_instance instance={0};CHECK(radv_darwin_enumerate_physical_devices(&instance.vk)==VK_SUCCESS);
      CHECK(!created&&!create_calls&&opens==1);finish_case();++cases;
   }
   const enum fault faults[]={BAD_BUILD,INFO_HUNG,CREATE_ERROR,MAP_ERROR,GEMVA_ERROR};
   for(unsigned f=0;f<5;++f) {
      reset_case("1");backend.fault=faults[f];struct radv_instance instance={0};CHECK(radv_darwin_enumerate_physical_devices(&instance.vk)==VK_SUCCESS);
      CHECK(!created&&!create_calls&&opens==1);finish_case();++cases;
   }
   reset_case("1");program_name="WindowServer";struct radv_instance instance={0};
   CHECK(radv_darwin_enumerate_physical_devices(&instance.vk)==VK_SUCCESS);CHECK(!created&&!create_calls);finish_case();++cases;
   printf("PASS enumeration owner %s: %u cases, %u checks; real core/VA and wrappers; no GPU; legacy profile-clone orphan unchanged\n",baseline?"baseline":"patched",cases,checks);
   return 0;
}
