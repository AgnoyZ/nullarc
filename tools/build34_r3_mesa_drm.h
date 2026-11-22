#ifndef BUILD34_R3_MESA_DRM_H
#define BUILD34_R3_MESA_DRM_H

#include "ac_darwin_drm.h"
#include <mach/mach.h>

int acd_device_initialize_exact_iokit(mach_port_t *connection, uint32_t *drm_major,
                                      uint32_t *drm_minor, acd_device_handle *out);
int acd_device_open_exact_iokit(uint32_t *drm_major, uint32_t *drm_minor, acd_device_handle *out);
void acd_sync_detach_backend(struct util_sync_provider *provider);

#endif
