#ifndef BUILD34_R3_RADV_ENTRY_H
#define BUILD34_R3_RADV_ENTRY_H

#include "build34_r3_mesa_drm.h"

struct ac_drm_device;

int acd_device_exact_profile(acd_device_handle dev, struct phx_topology *out);
int ac_drm_darwin_exact_profile(struct ac_drm_device *dev, struct phx_topology *out);

#endif
