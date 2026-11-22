#include "build34_r3_radv_entry.h"
#include "util/u_sync_provider.h"

#include <errno.h>
#include <stdlib.h>

extern void phx34_fixture_assert(bool passed);
#define CHECK(expr) phx34_fixture_assert(expr)

typedef struct ac_drm_device ac_drm_device;
#define HAVE_AMDGPU_DARWIN 1
#define amdgpu_device_initialize(...) (abort(), -1)
#define amdgpu_get_fd(...) (abort(), -1)
#define util_sync_provider_drm(...) (abort(), NULL)
#include "radv-entry-wrapper.inc"

typedef int VkResult;
#define VK_SUCCESS 0
#define VK_ERROR_OUT_OF_HOST_MEMORY (-1)
#define VK_ERROR_INITIALIZATION_FAILED (-3)
#define DRM_NODE_MAX 3
#define DRM_BUS_PCI 0
typedef struct { unsigned domain, bus, dev, func; } drmPciBusInfo;
typedef struct { unsigned vendor_id, device_id, subvendor_id, subdevice_id, revision_id; } drmPciDeviceInfo;
typedef struct {
   char **nodes;
   unsigned available_nodes, bustype;
   union { drmPciBusInfo *pci; } businfo;
   union { drmPciDeviceInfo *pci; } deviceinfo;
} drmDevice;
struct fixture_link { int unused; };
struct fixture_list { unsigned count; };
struct vk_instance { struct { struct fixture_list list; } physical_devices; };
struct radv_instance { struct vk_instance vk; };
struct radv_physical_device { struct { struct fixture_link link; } vk; ac_drm_device *drm_device; };

static struct radv_physical_device *published;
static ac_drm_device *logical_device;
static VkResult creation_result;
static bool existing_owner;

static ac_drm_device *acquire(void)
{
   ac_drm_device *dev = NULL;
   uint32_t major, minor;
   CHECK(ac_drm_device_initialize(-1, false, &major, &minor, &dev) == 0 && dev);
   CHECK(acd_sync_has_exact_completion(ac_drm_device_get_sync_provider(dev)));
   return dev;
}

static VkResult
radv_physical_device_try_create(struct radv_instance *instance, drmDevice *drm,
                               struct radv_physical_device **out)
{
   CHECK(instance && drm->deviceinfo.pci->vendor_id == 0x1002 && drm->deviceinfo.pci->device_id == 0x1900);
   CHECK(drm->deviceinfo.pci->revision_id == 0xbb);
   ac_drm_device *query = acquire();
   struct phx_topology profile = {0};
   CHECK(ac_drm_darwin_exact_profile(query, &profile) == 0 && profile.revision == 0xbb);
   ac_drm_device_deinitialize(query);
   if (creation_result)
      return creation_result;
   published = calloc(1, sizeof(*published));
   CHECK(published != NULL);
   if (existing_owner)
      published->drm_device = acquire();
   *out = published;
   return VK_SUCCESS;
}

static void list_addtail(struct fixture_link *link, struct fixture_list *list)
{
   CHECK(published && link == &published->vk.link && published->drm_device && !list->count);
   list->count++;
}

#include "radv-entry-physical.inc"

int phx34_fixture_radv_enumerate(int creation_status, bool preowned, bool expect_device)
{
   CHECK(!published && !logical_device);
   creation_result = creation_status;
   existing_owner = preowned;
   struct radv_instance instance = {0};
   const VkResult result = radv_darwin_enumerate_physical_devices(&instance.vk);
   CHECK(instance.vk.physical_devices.list.count == expect_device && (published != NULL) == expect_device);
   return result;
}

void phx34_fixture_radv_logical_open(void)
{
   CHECK(published && published->drm_device && !logical_device);
   logical_device = acquire();
   CHECK(acd_device_kext(logical_device->ddev, NULL) == acd_device_kext(published->drm_device->ddev, NULL));
}

void phx34_fixture_radv_logical_close(void)
{
   CHECK(logical_device != NULL);
   ac_drm_device_deinitialize(logical_device);
   logical_device = NULL;
}

void phx34_fixture_radv_physical_close(void)
{
   CHECK(published && published->drm_device);
   ac_drm_device_deinitialize(published->drm_device);
   free(published);
   published = NULL;
}
