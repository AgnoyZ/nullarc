"""Stage a connection-owning exact constructor in the pinned Mesa IOKit transport."""

from build34_exact_submit import once


IOKIT = 'src/amd/common/darwin/ac_darwin_iokit.c'
IOKIT_SHA256 = '889a65f216025a230d55ae6a0da3eb8509d12f2a65f8e3bd2ec1930b60c4a3f9'

LEGACY_CREATE = '''   struct iokit_ctx *c = calloc(1, sizeof(*c));
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
'''

CREATE = '''static struct acd_kext *
iokit_create(io_connect_t conn, bool proxy, struct iokit_ctx **context)
{
''' + once(once(LEGACY_CREATE, '      return -ENOMEM;\n', '      return NULL;\n'),
           '   *out = acd_kext_create(&ops, c);\n   return *out ? 0 : -ENOMEM;\n',
           '   struct acd_kext *transport = acd_kext_create(&ops, c);\n'
           '   if (transport && context)\n      *context = c;\n   return transport;\n') + '''}

static int
iokit_exact_call(void *context, uint32_t selector, const void *input, size_t input_size,
                 void *output, size_t *output_size)
{
   return iokit_call(context, selector, NULL, 0, input, input_size, NULL, NULL, output, output_size);
}

int
acd_kext_adopt_exact_iokit(mach_port_t *connection, struct acd_kext **out)
{
   if (!connection || !MACH_PORT_VALID(*connection) || !out || *out)
      return -EINVAL;
   const io_connect_t conn = *connection;
   *connection = IO_OBJECT_NULL;
   struct iokit_ctx *context = NULL;
   struct acd_kext *transport = iokit_create(conn, false, &context);
   if (!transport)
      return -ENOMEM;

   struct acd_hello hello;
   int result = acd_kext_hello(transport, &hello);
   if (!result && (hello.abi != N48N_ABI_VERSION || hello.build != PHX34_R3_PROGRESS_BUILD ||
                   hello.max_ibs != N48N_MAX_IBS || hello.vmid != PHXN_VMID))
      result = -EPROTO;
   if (!result) {
      context->exact_wire = (struct phx34_mesa_wire){.ctx = context, .call = iokit_exact_call};
      struct acd_exact_backend backend;
      result = phx34_mesa_wire_backend(&context->exact_wire, &backend);
      if (!result)
         result = acd_kext_set_exact_backend(transport, &backend);
   }
   if (result) {
      acd_kext_destroy(transport);
      return result;
   }
   *out = transport;
   return 0;
}

'''


def stage(source):
    source = once(source, '#include "ac_darwin_kext.h"\n',
                  '#include "ac_darwin_kext.h"\n#include "build34_r3_mesa_iokit.h"\n'
                  '#include "build34_exact_progress_wire.h"\n#include "build34_exact_submit_wire.h"\n'
                  '#include "build34_r3_mesa_wire.h"\n')
    source = once(source, '   io_connect_t conn;\n',
                  '   io_connect_t conn;\n   struct phx34_mesa_wire exact_wire;\n')
    source = once(source, LEGACY_CREATE, '   *out = iokit_create(conn, proxy, NULL);\n   return *out ? 0 : -ENOMEM;\n')
    anchor = 'int\nacd_kext_open_iokit(struct acd_kext **out)\n'
    return once(source, anchor, CREATE + anchor)
