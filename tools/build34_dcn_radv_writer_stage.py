"""Pair the retained RADV part with the staged exact native writer protocol."""

import hashlib

import build34_dcn_radv_part_stage as part
import build34_dcn_radv_submit_stage as submit


WIRE = 'src/amd/common/darwin/build34_r3_mesa_wire.c'
WIRE_H = 'src/amd/common/darwin/build34_r3_mesa_wire.h'
WIRE_HEADER = 'src/amd/common/darwin/build34_dcn_writer_wire.h'
PINS = {
    WIRE: '1938a2ec3c4a16574a68b82201fb8b0e40ff81892d899acfe350c23986915836',
    WIRE_H: '6de4389a3ee3c6fd29dfb4eeba9ee05e6b361ad78145ac91e08fcdfabd98ea7d',
}
INPUTS = {**part.INPUTS, **PINS}


def stage(inputs):
    sources = part.stage(inputs)
    for name, digest in PINS.items():
        data = inputs.get(name, b'')
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f'Build34 RADV writer source drift: {name}')
        sources[name] = data.decode()

    def replace(name, old, new, count=1):
        if sources[name].count(old) != count:
            raise ValueError(f'Build34 RADV writer anchor drift: {name}: {old[:75]}')
        sources[name] = sources[name].replace(old, new)

    replace(submit.QUEUE, '''static void
radv_dcn_capture_part(struct radv_queue *queue, const struct vk_queue_submit *submission,
                      const struct radv_dcn_submitted_clear *writer)
{
   struct radv_dcn_part_scope *scope = radv_dcn_part_scope;
   if (!scope || scope->calls != 1 || queue->vk.submit.mode != VK_QUEUE_SUBMIT_MODE_IMMEDIATE ||
       (VkQueue)&queue->vk != scope->queue || submission->command_buffer_count != 1 ||
       (VkCommandBuffer)submission->command_buffers[0] != scope->command || !writer->clear.serial)
      return;

   const struct radv_image_view *view = writer->clear.view;
   const struct radv_dcn_render_binding *live = radv_dcn_live_part(radv_queue_device(queue), view, scope->target);
   if (live && live->map.generation == writer->clear.binding.map.generation &&
       live->memory == writer->clear.binding.memory &&
       view->image->bindings[0].bo == writer->clear.bo) {
      scope->writer = (struct build34_dcn_part_writer){writer->native, writer->clear.serial,
         live->map.generation, live->phx_va, live->scanout_bytes, live->map.handle};
   }
}
''', '''static const struct radv_dcn_render_binding *
radv_dcn_part_writer_binding(struct radv_queue *queue, const struct vk_queue_submit *submission,
                             const struct radv_dcn_recorded_clear *clear)
{
   const struct radv_dcn_part_scope *scope = radv_dcn_part_scope;
   if (!scope || scope->calls != 1 || queue->vk.submit.mode != VK_QUEUE_SUBMIT_MODE_IMMEDIATE ||
       (VkQueue)&queue->vk != scope->queue || submission->command_buffer_count != 1 ||
       (VkCommandBuffer)submission->command_buffers[0] != scope->command || !clear->serial)
      return NULL;

   const struct radv_image_view *view = clear->view;
   const struct radv_dcn_render_binding *live = radv_dcn_live_part(radv_queue_device(queue), view, scope->target);
   return live && live->map.generation == clear->binding.map.generation && live->memory == clear->binding.memory &&
          view->image->bindings[0].bo == clear->bo && live->phx_va == clear->binding.phx_va &&
          live->scanout_bytes == clear->binding.scanout_bytes && live->map.handle == clear->binding.map.handle ? live : NULL;
}

static void
radv_dcn_capture_part(struct radv_queue *queue, const struct vk_queue_submit *submission,
                      const struct radv_dcn_submitted_clear *writer)
{
   const struct radv_dcn_render_binding *live = radv_dcn_part_writer_binding(queue, submission, &writer->clear);
   if (live)
      radv_dcn_part_scope->writer = (struct build34_dcn_part_writer){writer->native, writer->clear.serial,
         live->map.generation, live->phx_va, live->scanout_bytes, live->map.handle};
}
''')
    replace(submit.QUEUE, '          writer->dcn_clear.stream == writer->cs->b) {',
            '          writer->dcn_clear.stream == writer->cs->b &&\n'
            '          radv_dcn_part_writer_binding(queue, submission, &writer->dcn_clear)) {')
    replace(submit.CS, '''      if (request->dcn_clear)
         r = ac_drm_dcn_cs_submit(ctx->ws->dev, ctx->ctx_handle, 0, num_chunks, chunks, &request->seq_no,
                                  &request->dcn_clear->ib, &request->dcn_clear->native);
      else''', '''      if (request->dcn_clear) {
         const struct radv_dcn_render_binding *bound = &request->dcn_clear->clear.binding;
         const struct build34_dcn_writer_nomination writer = {
            .ib = request->dcn_clear->ib,
            .range = {.va = bound->phx_va, .bytes = bound->scanout_bytes, .bo = bound->map.handle},
         };
         r = ac_drm_dcn_cs_submit(ctx->ws->dev, ctx->ctx_handle, 0, num_chunks, chunks, &request->seq_no,
                                  &writer, &request->dcn_clear->native);
      } else''')
    for name, count in ((submit.RAW, 2), (submit.RAW_H, 1), (submit.DRM, 2), (submit.DRM_H, 1)):
        replace(name, 'struct build34_dcn_ib *writer,', 'struct build34_dcn_writer_nomination *writer,', count)
    for name in (submit.RAW_H, submit.DRM_H):
        replace(name, 'struct build34_dcn_ib;\n', 'struct build34_dcn_writer_nomination;\n')
    replace(submit.DRM, '''   if (exact && out && acd_dcn_matches_plan(&plan, writer))
      plan.receipt_out = &accepted;''', '''   if (exact && out && writer && acd_dcn_matches_plan(&plan, &writer->ib)) {
      plan.receipt_out = &accepted;
      plan.dcn_nomination = writer;
   }''')

    replace(submit.KEXT_H, 'struct acd_cs_plan {\n',
            'struct acd_cs_plan {\n   const struct build34_dcn_writer_nomination *dcn_nomination;\n')
    replace(submit.KEXT_H, 'struct acd_exact_backend {\n', '''struct build34_dcn_writer_nomination;
struct acd_exact_backend {
   int (*submit_writer)(void *ctx, const void *packet, size_t size,
                        const struct build34_dcn_writer_nomination *writer, struct acd_exact_receipt *out,
                        bool *no_dispatch, bool *nominated);
''')
    replace(submit.KEXT, '''      result = e->be.submit(e->be.ctx, buf, sizeof(h) + plan->n_ibs * sizeof(*plan->ibs),
                            &receipt, &no_dispatch);''', '''      const size_t packet_size = sizeof(h) + plan->n_ibs * sizeof(*plan->ibs);
      bool nominated = false;
      if (e->be.submit_writer && plan->dcn_nomination && plan->receipt_out)
         result = e->be.submit_writer(e->be.ctx, buf, packet_size, plan->dcn_nomination, &receipt,
                                      &no_dispatch, &nominated);
      else
         result = e->be.submit(e->be.ctx, buf, packet_size, &receipt, &no_dispatch);''')
    replace(submit.KEXT, '         if (plan->receipt_out && receipt.queue == 1) {',
            '         if (nominated && plan->receipt_out && receipt.queue == 1) {')
    replace(submit.KEXT, '   bool acked, acknowledging;\n', '   bool acked, acknowledging, native_waited;\n')
    replace(submit.KEXT, '      r = e->dcn_writer;\n', '''      r = e->dcn_writer;
      if (r->acknowledging) {
         pthread_mutex_unlock(&k->mtx);
         return -EAGAIN;
      }
''')
    replace(submit.KEXT, '   if (r && r->phase == ACD_EXACT_PENDING) {',
            '   if (r && (r->phase == ACD_EXACT_PENDING || (writer && !r->acked && !r->native_waited))) {')
    replace(submit.KEXT, '      if (!result && acd_exact_snapshot(e, &s) && !pending)\n'
                         '         r->phase = ACD_EXACT_COMPLETE;\n',
            '      if (!result && acd_exact_snapshot(e, &s) && !pending) {\n'
            '         r->phase = ACD_EXACT_COMPLETE;\n'
            '         r->native_waited = true;\n'
            '      }\n')
    replace(submit.KEXT, '      *busy = pending;\n      pthread_mutex_unlock(&k->mtx);',
            '      *busy = pending || (!r->acked && !r->native_waited);\n      pthread_mutex_unlock(&k->mtx);')

    replace(WIRE_H, '   uint64_t owner;\n', '   uint64_t owner;\n   uint32_t flags;\n')
    replace(WIRE, '#include "build34_exact_submit_wire.h"\n', '#include "build34_dcn_writer_wire.h"\n')
    replace(WIRE, '''wire_submit(void *context, const void *packet, size_t size, struct acd_exact_receipt *out, bool *no_dispatch)
{
   const struct phx34_mesa_wire *wire = context;
   struct phx34_r3_submit_request request = {.version = PHX34_R3_WIRE_VERSION,
      .size = sizeof(request), .owner = wire->owner};
   *no_dispatch = true;
''', '''wire_submit_impl(void *context, const void *packet, size_t size, const struct build34_dcn_writer_nomination *writer,
                 struct acd_exact_receipt *out, bool *no_dispatch, bool *nominated)
{
   const struct phx34_mesa_wire *wire = context;
   struct build34_dcn_writer_request envelope = {.submit = {.version = PHX34_R3_WIRE_VERSION,
      .size = sizeof(envelope.submit), .owner = wire->owner}};
   struct phx34_r3_submit_request *request = &envelope.submit;
   *no_dispatch = true;
   if (nominated)
      *nominated = false;
''')
    start = sources[WIRE].index('   if (!packet || size < sizeof(request.submit)')
    end = sources[WIRE].index('\nstatic int\nwire_receipt(', start)
    replace(WIRE, sources[WIRE][start:end], '''   if (!packet || size < sizeof(request->submit) || size > sizeof(request->submit) + sizeof(request->ibs))
      return -EINVAL;
   memcpy(&request->submit, packet, sizeof(request->submit));
   if (request->submit.abi != PHXN_ABI_VERSION || request->submit.reserved ||
       !request->submit.num_ibs || request->submit.num_ibs > PHXN_MAX_IBS ||
       size != sizeof(request->submit) + request->submit.num_ibs * sizeof(request->ibs[0]))
      return -EINVAL;
   if (request->submit.flags || request->submit.fence_handle || request->submit.fence_offset)
      return -EOPNOTSUPP;
   memcpy(request->ibs, (const unsigned char *)packet + sizeof(request->submit), size - sizeof(request->submit));
   if (wire->flags == PHX34_R3_DCN_FLAGS && writer && nominated && build34_dcn_matches_writer_ib(request, writer)) {
      envelope.writer = *writer;
      request->size = sizeof(envelope);
   }

   struct phx34_r3_reply reply;
   struct acd_exact_receipt receipt;
   *no_dispatch = false;
   int result = wire_call(wire, PHX34_R3_SEL_SUBMIT_RECEIPT, &envelope, request->size, &reply, &receipt, no_dispatch);
   if (result)
      return result;
   if (reply.status == PHX34_R3_REPLY_WRITER_SUBMITTED) {
      if (request->size != sizeof(envelope) || receipt.queue != 1)
         return -EPROTO;
      *nominated = true;
   } else if (reply.status != PHX34_R3_REPLY_SUBMITTED) {
      return -EPROTO;
   }
   *out = receipt;
   return 0;
}

static int
wire_submit(void *context, const void *packet, size_t size, struct acd_exact_receipt *out, bool *no_dispatch)
{
   return wire_submit_impl(context, packet, size, NULL, out, no_dispatch, NULL);
}
''')
    replace(WIRE, '              uint64_t timeout_ns, struct acd_exact_snapshot *out)\n',
            '              uint64_t timeout_ns, struct acd_exact_snapshot *out, uint32_t *session_flags)\n')
    replace(WIRE, '''   if (output_size != sizeof(reply) || reply.version != PHX34_R3_WIRE_VERSION ||
       reply.size != sizeof(reply) || reply.build != PHX34_R3_PROGRESS_BUILD ||
       reply.flags != PHX34_R3_PRESSURE_FLAGS || reply.target != target || reply.reserved ||''', '''   const bool flags_valid = session_flags ?
      (reply.flags == PHX34_R3_PRESSURE_FLAGS || reply.flags == PHX34_R3_DCN_FLAGS) : reply.flags == wire->flags;
   if (output_size != sizeof(reply) || reply.version != PHX34_R3_WIRE_VERSION ||
       reply.size != sizeof(reply) || reply.build != PHX34_R3_PROGRESS_BUILD ||
       !flags_valid || reply.target != target || reply.reserved ||''')
    replace(WIRE, '   *out = (struct acd_exact_snapshot){.owner = reply.owner, .retired = reply.retired};\n',
            '   if (session_flags)\n      *session_flags = reply.flags;\n'
            '   *out = (struct acd_exact_snapshot){.owner = reply.owner, .retired = reply.retired};\n')
    replace(WIRE, 'return wire_progress(context, PHX34_R3_SEL_PREFIX, target, timeout_ns, out);',
            'return wire_progress(context, PHX34_R3_SEL_PREFIX, target, timeout_ns, out, NULL);')
    replace(WIRE, 'wire_progress(wire, PHX34_R3_SEL_SESSION, 0, 0, &snapshot);',
            'wire_progress(wire, PHX34_R3_SEL_SESSION, 0, 0, &snapshot, &wire->flags);')
    replace(WIRE, '      .wait = wire_wait, .ack = wire_ack, .wait_prefix = wire_prefix};',
            '      .submit_writer = wire->flags == PHX34_R3_DCN_FLAGS ? wire_submit_impl : NULL,\n'
            '      .wait = wire_wait, .ack = wire_ack, .wait_prefix = wire_prefix};')
    return sources
