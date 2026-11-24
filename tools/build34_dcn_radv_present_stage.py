"""Offer a completed frame through the same negotiated exact connection."""

import build34_dcn_radv_submit_stage as submit
import build34_dcn_radv_writer_stage as writer
from build34_exact_submit import once


INPUTS = writer.INPUTS
PRESENT_HEADER = 'src/amd/common/build34_dcn_present_wire.h'


def stage(inputs):
    sources = writer.stage(inputs)

    def replace(file, old, new):
        sources[file] = once(sources[file], old, new)

    for file, signature, declaration in (
        (submit.KEXT_H, 'int acd_kext_dcn_poll(', 'int acd_kext_dcn_offer(struct acd_kext *, const struct build34_dcn_present_offer *);'),
        (submit.DRM_H, 'int acd_dcn_poll(', 'int acd_dcn_offer(acd_device_handle, const struct build34_dcn_present_offer *);'),
        (submit.RAW_H, 'int ac_drm_dcn_poll(', 'int ac_drm_dcn_offer(ac_drm_device *, const struct build34_dcn_present_offer *);'),
    ):
        replace(file, signature, f'struct build34_dcn_present_offer;\n{declaration}\n{signature}')
    file = submit.KEXT_H
    replace(file, 'struct acd_exact_backend {\n', '''struct build34_dcn_present_offer;
struct acd_exact_backend {
   int (*offer_present)(void *ctx, const struct build34_dcn_present_offer *offer);
''')
    replace(submit.KEXT, '#include "build34_dcn_native_submit.h"\n', '#include "build34_dcn_present_wire.h"\n')
    replace(submit.KEXT, 'static int\nacd_exact_submit_once(struct acd_kext *,', '''int
acd_kext_dcn_offer(struct acd_kext *k, const struct build34_dcn_present_offer *offer)
{
   if (!k || !offer)
      return -EINVAL;
   if (pthread_mutex_trylock(&k->mtx))
      return -EAGAIN;
   struct acd_exact_state *e = k->exact;
   pthread_mutex_unlock(&k->mtx);
   if (!e || !e->be.offer_present)
      return -EOPNOTSUPP;
   if (pthread_mutex_trylock(&e->submit_mtx))
      return -EAGAIN;
   int result = -EAGAIN;
   if (!pthread_mutex_trylock(&k->mtx)) {
      const bool live = !e->poisoned && acd_exact_dcn_matches(e, &offer->native) &&
         (e->dcn_writer->native_waited || e->dcn_writer->acked);
      pthread_mutex_unlock(&k->mtx);
      result = live ? e->be.offer_present(e->be.ctx, offer) : -ENOENT;
   }
   pthread_mutex_unlock(&e->submit_mtx);
   return result;
}

static int
acd_exact_submit_once(struct acd_kext *,''')
    replace(submit.DRM, 'int\nacd_dcn_poll(', '''int
acd_dcn_offer(acd_device_handle dev, const struct build34_dcn_present_offer *offer)
{
   return acd_kext_dcn_offer(dev ? dev->core->kext : NULL, offer);
}

int
acd_dcn_poll(''')
    replace(submit.RAW, 'int\nac_drm_dcn_poll(', '''int
ac_drm_dcn_offer(ac_drm_device *dev, const struct build34_dcn_present_offer *offer)
{
   return acd_dcn_offer(dev && dev->is_darwin ? dev->ddev : NULL, offer);
}

int
ac_drm_dcn_poll(''')
    replace(submit.CS, 'int\nradv_dcn_poll_native(', '''int
radv_dcn_offer_native(const struct radeon_winsys *ws, const struct build34_dcn_present_offer *offer)
{
   if (!ws || ws->cs_submit != radv_amdgpu_winsys_cs_submit || !offer)
      return -EINVAL;
   const struct radv_amdgpu_winsys *amdgpu = (const struct radv_amdgpu_winsys *)ws;
   return ac_drm_dcn_offer(amdgpu->dev, offer);
}

int
radv_dcn_poll_native(''')
    replace(submit.CS, '#include "build34_dcn_radv_submit.h"\n', '#include "build34_dcn_radv_submit.h"\n'
            '#ifdef HAVE_AMDGPU_DARWIN\n#include "build34_dcn_present_wire.h"\n'
            'int radv_dcn_offer_native(const struct radeon_winsys *, const struct build34_dcn_present_offer *);\n#endif\n')
    replace(submit.QUEUE, '#include "build34_dcn_part.h"\n', '#include "build34_dcn_part.h"\n#include "build34_dcn_present_wire.h"\n')
    replace(submit.QUEUE, '#endif\n\nstatic VkResult\nradv_queue_submit_normal(', '''int radv_dcn_offer_native(const struct radeon_winsys *ws, const struct build34_dcn_present_offer *offer);
bool build34_dcn_queue_offer_v1(VkQueue handle, uint32_t surface, const struct build34_dcn_part_writer *writer);
__attribute__((visibility("default"))) bool
build34_dcn_queue_offer_v1(VkQueue handle, uint32_t surface, const struct build34_dcn_part_writer *writer)
{
   if (!handle || !surface || !writer || !writer->recording ||
       !build34_dcn_valid_native_submit(writer->native, writer->native.sequence))
      return false;
   VK_FROM_HANDLE(radv_queue, queue, handle);
   const struct build34_dcn_present_offer offer = {
      .version = BUILD34_DCN_PRESENT_VERSION, .size = sizeof(offer), .native = writer->native,
      .range = {.va = writer->phx_va, .bytes = writer->page_bytes, .bo = writer->bo_handle}, .surface = surface,
   };
   return !radv_dcn_offer_native(radv_queue_device(queue)->ws, &offer);
}
#endif

static VkResult
radv_queue_submit_normal(''')

    file = writer.WIRE
    replace(file, '#include "build34_dcn_writer_wire.h"\n',
            '#include "build34_dcn_writer_wire.h"\n#include "build34_dcn_present_wire.h"\n')
    replace(file, 'wire->flags == PHX34_R3_DCN_FLAGS && writer', 'wire->flags != PHX34_R3_PRESSURE_FLAGS && writer')
    replace(file, '(reply.flags == PHX34_R3_PRESSURE_FLAGS || reply.flags == PHX34_R3_DCN_FLAGS)',
            '(reply.flags == PHX34_R3_PRESSURE_FLAGS || reply.flags == PHX34_R3_DCN_FLAGS ||\n'
            '       reply.flags == PHX34_R3_DCN_PRESENT_FLAGS)')
    replace(file, 'int\nphx34_mesa_wire_backend(', '''static int
wire_offer_present(void *context, const struct build34_dcn_present_offer *offer)
{
   const struct phx34_mesa_wire *wire = context;
   if (!offer || offer->native.owner != wire->owner || !build34_dcn_valid_writer_range(&offer->range))
      return -EINVAL;
   const int result = wire->call(wire->ctx, BUILD34_DCN_SEL_OFFER, offer, sizeof(*offer), NULL, NULL);
   return result ? acd_kr_to_errno(BUILD34_DCN_SEL_OFFER, result) : 0;
}

int
phx34_mesa_wire_backend(''')
    replace(file, '.submit_writer = wire->flags == PHX34_R3_DCN_FLAGS ? wire_submit_impl : NULL,',
            '.submit_writer = wire->flags != PHX34_R3_PRESSURE_FLAGS ? wire_submit_impl : NULL,\n'
            '      .offer_present = wire->flags == PHX34_R3_DCN_PRESENT_FLAGS ? wire_offer_present : NULL,')
    return sources
