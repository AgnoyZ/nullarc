"""Stage the existing Darwin RADV entrypoints for the exact-only R3 runtime."""

from build34_exact_submit import once


PHYSICAL = 'src/amd/vulkan/radv_physical_device.c'
WRAPPER = 'src/amd/common/ac_linux_drm.c'
WINSYS = 'src/amd/vulkan/winsys/amdgpu/radv_amdgpu_winsys.c'
ENTRY_SHA256 = {
    PHYSICAL: '967de26f3cb4ce7e01bb5534aba815228acdd92aa2cb21e283e690cbac908b02',
    WRAPPER: '13bf82bc43a42e8ee7857c3c5c427e028d26c06c1952ad0b4253614e57e2c3de',
    WINSYS: 'e1a16e10f6df4058ab8efaba700a47f8242ba9fa2d54b49833f54a05168dd722',
}

CORE_PROFILE = '''int
acd_device_exact_profile(acd_device_handle dev, struct phx_topology *out)
{
   if (!dev || !out)
      return -EINVAL;
   if (!acd_sync_has_exact_completion(dev->core->sync))
      return -ENODEV;
   *out = dev->core->topology;
   return 0;
}

'''

WRAPPER_PROFILE = '''int
ac_drm_darwin_exact_profile(struct ac_drm_device *dev, struct phx_topology *out)
{
   if (!dev || !dev->is_darwin)
      return -EINVAL;
   return acd_device_exact_profile(dev->ddev, out);
}

'''


def stage_drm(source):
    source = once(source, '#include "build34_r3_mesa_drm.h"\n',
                  '#include "build34_r3_mesa_drm.h"\n#include "build34_r3_radv_entry.h"\n')
    anchor = '/* Enumeration needs PCI identity before radv_physical_device_try_create. Query\n'
    return once(source, anchor, CORE_PROFILE + anchor)


def stage_wrapper(source):
    source = once(source, '#include "darwin/ac_darwin_drm.h"\n',
                  '#include "darwin/ac_darwin_drm.h"\n#include "build34_r3_radv_entry.h"\n')
    source = once(source, '#include <stdlib.h>\n', '#include <errno.h>\n#include <stdlib.h>\n')
    anchor = '#endif\n\nint ac_drm_device_initialize('
    source = once(source, anchor, WRAPPER_PROFILE + anchor)
    source = once(source, '      acd_device_handle ddev;\n      r = acd_device_initialize(major_version, minor_version, &ddev);\n',
                  '      acd_device_handle ddev = NULL;\n      r = acd_device_open_exact_iokit(major_version, minor_version, &ddev);\n')
    return once(source, '      } else {\n         free(*dev);\n      }\n      return r;\n',
                '      } else {\n         free(*dev);\n         *dev = NULL;\n      }\n      return r;\n')


def stage_physical(source):
    source = once(source, '#include "common/darwin/ac_darwin_drm.h"\n',
                  '#include "common/darwin/ac_darwin_drm.h"\n#include "build34_r3_radv_entry.h"\n')
    source = once(source, '   static drmPciDeviceInfo device_info = {\n', '   drmPciDeviceInfo device_info = {\n')
    source = once(source, '''   int profile_result = acd_profile_identity(&profile);
   if (profile_result) return VK_SUCCESS; /* backend has logged the reason */
''', '''   ac_drm_device *native_owner = NULL;
   uint32_t drm_major, drm_minor;
   if (ac_drm_device_initialize(-1, false, &drm_major, &drm_minor, &native_owner))
      return VK_SUCCESS;
   if (ac_drm_darwin_exact_profile(native_owner, &profile)) {
      ac_drm_device_deinitialize(native_owner);
      return VK_SUCCESS;
   }
''')
    source = once(source, '''   if (result != VK_SUCCESS) {
      /* The backend already said why on stderr (kext missing, Hello refused, ...): no device. */
''', '''   if (result != VK_SUCCESS) {
      ac_drm_device_deinitialize(native_owner);
      /* The backend already said why on stderr (kext missing, Hello refused, ...): no device. */
''')
    return once(source, '''   list_addtail(&pdev->vk.link, &instance->vk.physical_devices.list);
   return VK_SUCCESS;
}
#endif
''', '''   if (!pdev->drm_device)
      pdev->drm_device = native_owner;
   else
      ac_drm_device_deinitialize(native_owner);
   list_addtail(&pdev->vk.link, &instance->vk.physical_devices.list);
   return VK_SUCCESS;
}
#endif
''')
