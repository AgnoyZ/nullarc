"""Derive the explicit exact open path from the reviewed DRM and IOKit stages."""

from build34_exact_submit import once
from build34_r3_mesa_drm import WRAPPERS


OPEN = '''int
acd_kext_open_exact_iokit(struct acd_kext **out)
{
   if (!out || *out)
      return -EINVAL;
   CFMutableDictionaryRef match = IOServiceMatching(ACD_SERVICE_PHOENIX);
   if (!match)
      return -ENOMEM;
   io_service_t service = IOServiceGetMatchingService(kIOMainPortDefault, match);
   if (!MACH_PORT_VALID(service))
      return -ENODEV;

   io_connect_t connection = IO_OBJECT_NULL;
   kern_return_t status = IOServiceOpen(service, mach_task_self(), PHX34_R3_UC_TYPE, &connection);
   IOObjectRelease(service);
   if (status != KERN_SUCCESS)
      return acd_kr_to_errno(ACD_SEL_HELLO, status);
   if (!MACH_PORT_VALID(connection))
      return -EIO;
   return acd_kext_adopt_exact_iokit(&connection, out);
}

'''


def stage_iokit(source):
    source = once(source, '#include "build34_r3_mesa_iokit.h"\n',
                  '#include "build34_r3_mesa_iokit.h"\n#include "build34_exact_open_wire.h"\n')
    anchor = 'int\nacd_kext_open_iokit(struct acd_kext **out)\n'
    return once(source, anchor, OPEN + anchor)


def stage_drm(source):
    source = once(source, 'bool host_bo, mach_port_t *connection,\n',
                  'bool host_bo, bool exact, mach_port_t *connection,\n')
    source = once(source,
                  '      int r = connection ? acd_kext_adopt_exact_iokit(connection, &c->kext) : acd_kext_open(&c->kext);\n',
                  '''      int r;
      if (connection)
         r = acd_kext_adopt_exact_iokit(connection, &c->kext);
      else if (exact)
         r = acd_kext_open_exact_iokit(&c->kext);
      else
         r = acd_kext_open(&c->kext);
''')
    source = once(source, '.exact_completion = connection != NULL', '.exact_completion = exact')
    source = once(source, 'acd_device_initialize_mode(bool exact, mach_port_t *connection, uint32_t *drm_major,',
                  'acd_device_initialize_mode(bool exact, bool open_exact, mach_port_t *connection, uint32_t *drm_major,')
    source = once(source, '   } else if (exact && !connection) {\n',
                  '   } else if (exact && !connection && !open_exact) {\n')
    source = once(source, 'acd_core_create(dev->canned, false, connection, &unpublished)',
                  'acd_core_create(dev->canned, false, exact, connection, &unpublished)')
    wrappers = once(WRAPPERS, 'initialize_mode(false, NULL,', 'initialize_mode(false, false, NULL,')
    wrappers = once(wrappers, 'initialize_mode(true, connection,', 'initialize_mode(true, false, connection,')
    return once(source, WRAPPERS, wrappers + '''int
acd_device_open_exact_iokit(uint32_t *drm_major, uint32_t *drm_minor, acd_device_handle *out)
{
   if (!out || *out)
      return -EINVAL;
   return acd_device_initialize_mode(true, true, NULL, drm_major, drm_minor, out);
}

''')
