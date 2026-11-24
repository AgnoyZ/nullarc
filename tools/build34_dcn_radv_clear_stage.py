"""Derive a private RADV load-clear record from pinned Mesa and the binding stage."""

import hashlib

import build34_dcn_radv_binding_stage as binding


CMD = "src/amd/vulkan/radv_cmd_buffer.c"
CMD_H = "src/amd/vulkan/radv_cmd_buffer.h"
META = "src/amd/vulkan/meta/radv_meta_clear.c"
HEADER = "src/amd/vulkan/build34_dcn_radv_clear.h"
INPUTS = {
    **binding.INPUTS,
    CMD: "699772e186681afd86c0537f431c4dac998bafd28a38b7b6c29664a46002819d",
    CMD_H: "3527d34cf847ead3825376790ec881deb93977c52a0d9628623e965fb1416298",
    META: "dadba4d819f3f41fcce1622a59bef5ee06fd69d8e58e88498398f3bbab006e41",
}


def stage(inputs):
    sources = binding.stage(inputs)
    for name in (CMD, CMD_H, META):
        data = inputs.get(name, b"")
        if hashlib.sha256(data).hexdigest() != INPUTS[name]:
            raise ValueError(f"Build34 RADV clear source drift: {name}")
        sources[name] = data.decode()

    def replace(name, old, new):
        if sources[name].count(old) != 1:
            raise ValueError(f"Build34 RADV clear anchor drift: {name}: {old[:75]}")
        sources[name] = sources[name].replace(old, new)

    replace(CMD_H, "extern const struct vk_command_buffer_ops radv_cmd_buffer_ops;\n", """#ifdef HAVE_AMDGPU_DARWIN
#include "build34_dcn_radv_clear.h"
#endif

extern const struct vk_command_buffer_ops radv_cmd_buffer_ops;
""")
    replace(CMD_H, "struct radv_cmd_buffer {\n   struct vk_command_buffer vk;\n", """struct radv_cmd_buffer {
   struct vk_command_buffer vk;
#ifdef HAVE_AMDGPU_DARWIN
   struct radv_dcn_recorded_clear dcn_clear;
#endif
""")
    replace(CMD_H, "void radv_get_vbo_info(", """#ifdef HAVE_AMDGPU_DARWIN
void radv_dcn_capture_load_clear(struct radv_cmd_buffer *cmd_buffer, const VkRenderingAttachmentInfo *info);
#endif

void radv_get_vbo_info(""")
    replace(CMD, '#include "util/perf/u_trace.h"\n', '#include "util/perf/u_trace.h"\n'
            '#ifdef HAVE_AMDGPU_DARWIN\n#include "winsys/amdgpu/radv_amdgpu_bo.h"\n#include <stdatomic.h>\n#endif\n')
    replace(CMD, "static void\nradv_reset_cmd_buffer(", """#ifdef HAVE_AMDGPU_DARWIN
static _Atomic uint64_t radv_dcn_clear_serial;

static uint64_t
radv_dcn_next_clear_serial(void)
{
   uint64_t previous = atomic_load_explicit(&radv_dcn_clear_serial, memory_order_relaxed);
   while (previous != UINT64_MAX) {
      if (atomic_compare_exchange_weak_explicit(&radv_dcn_clear_serial, &previous, previous + 1,
                                                memory_order_relaxed, memory_order_relaxed))
         return previous + 1;
   }
   return 0;
}

void
radv_dcn_capture_load_clear(struct radv_cmd_buffer *cmd_buffer, const VkRenderingAttachmentInfo *info)
{
   const struct radv_rendering_state *render = &cmd_buffer->state.render;
   const struct radv_attachment *color = &render->color_att[0];
   const struct radv_image_view *view = color->iview;
   if (cmd_buffer->dcn_clear.phase == RADV_DCN_CLEAR_REJECTED || vk_command_buffer_has_error(&cmd_buffer->vk) ||
       cmd_buffer->vk.level != VK_COMMAND_BUFFER_LEVEL_PRIMARY || cmd_buffer->qf != RADV_QUEUE_GENERAL ||
       cmd_buffer->cs->hw_ip != AMD_IP_GFX || cmd_buffer->gang.cs ||
       (cmd_buffer->vk.render_pass && cmd_buffer->vk.render_pass->subpass_count != 1) ||
       !render->active || !render->has_image_views || render->view_mask || render->layer_count != 1 ||
       render->max_samples != VK_SAMPLE_COUNT_1_BIT || render->color_att_count != 1 ||
       render->ds_att.iview || render->vrs_att.iview || render->area.offset.x || render->area.offset.y ||
       !view || view != radv_image_view_from_handle(info->imageView) || color->flags ||
       color->layout != VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL || color->resolve_mode || color->resolve_iview ||
       info->resolveMode || info->loadOp != VK_ATTACHMENT_LOAD_OP_CLEAR || info->storeOp != VK_ATTACHMENT_STORE_OP_STORE ||
       view->vk.view_type != VK_IMAGE_VIEW_TYPE_2D || view->vk.format != VK_FORMAT_B8G8R8A8_UNORM ||
       view->vk.aspects != VK_IMAGE_ASPECT_COLOR_BIT || view->vk.base_mip_level || view->vk.base_array_layer ||
       view->vk.level_count != 1 || view->vk.layer_count != 1)
      return;

   const struct radv_dcn_render_binding binding = view->image->dcn_render_binding;
   const struct radv_image_binding *bound = &view->image->bindings[0];
   const struct radeon_winsys *ws = radv_cmd_buffer_device(cmd_buffer)->ws;
   if (!binding.map.generation || binding.map.winsys != ws ||
       bound->addr != binding.map.va || bound->range != binding.bind_bytes ||
       binding.width != view->vk.extent.width || binding.height != view->vk.extent.height ||
       binding.width != render->area.extent.width || binding.height != render->area.extent.height)
      return;
   if (radv_amdgpu_dcn_host_map(ws, bound->bo).generation != binding.map.generation)
      return;

   radv_dcn_clear_record(&cmd_buffer->dcn_clear, binding, cmd_buffer->cs->b, view, bound->bo);
}
#endif

static void
radv_reset_cmd_buffer(""")
    replace(CMD, "   vk_command_buffer_reset(&cmd_buffer->vk);\n", """   vk_command_buffer_reset(&cmd_buffer->vk);
#ifdef HAVE_AMDGPU_DARWIN
   cmd_buffer->dcn_clear = (struct radv_dcn_recorded_clear){0};
#endif
""")
    replace(CMD, "   VkResult result = radv_finalize_cmd_stream(device, cs);\n   if (result != VK_SUCCESS)\n"
            "      return vk_error(cmd_buffer, result);\n\n   return vk_command_buffer_end(&cmd_buffer->vk);",
            """   VkResult result = radv_finalize_cmd_stream(device, cs);
   if (result != VK_SUCCESS) {
#ifdef HAVE_AMDGPU_DARWIN
      radv_dcn_clear_reject(&cmd_buffer->dcn_clear);
#endif
      return vk_error(cmd_buffer, result);
   }

#ifdef HAVE_AMDGPU_DARWIN
   result = vk_command_buffer_end(&cmd_buffer->vk);
   uint64_t clear_serial = 0;
   if (result == VK_SUCCESS && !ace_cs && cmd_buffer->dcn_clear.phase == RADV_DCN_CLEAR_CLOSED)
      clear_serial = radv_dcn_next_clear_serial();
   radv_dcn_clear_finalize(&cmd_buffer->dcn_clear, cs->b, clear_serial);
   return result;
#else
   return vk_command_buffer_end(&cmd_buffer->vk);
#endif""")
    replace(CMD, "   assert(commandBufferCount > 0);\n\n   if (is_gfx_or_ace)", """   assert(commandBufferCount > 0);
#ifdef HAVE_AMDGPU_DARWIN
   radv_dcn_clear_reject(&primary->dcn_clear);
#endif

   if (is_gfx_or_ace)""")
    replace(CMD, "   assert(!cmd_buffer->state.render.active);\n\n   const struct VkSampleLocationsInfoEXT",
            """   assert(!cmd_buffer->state.render.active);
#ifdef HAVE_AMDGPU_DARWIN
   if (cmd_buffer->dcn_clear.phase == RADV_DCN_CLEAR_OPEN ||
       (pRenderingInfo->flags & ~VK_RENDERING_LOCAL_READ_CONCURRENT_ACCESS_CONTROL_BIT_KHR))
      radv_dcn_clear_reject(&cmd_buffer->dcn_clear);
#endif

   const struct VkSampleLocationsInfoEXT""")
    replace(CMD, "   radv_cmd_buffer_clear_rendering(cmd_buffer, pRenderingInfo);\n",
            """#ifdef HAVE_AMDGPU_DARWIN
   if (inside_meta_op || msrtss)
      radv_dcn_clear_reject(&cmd_buffer->dcn_clear);
#endif
   radv_cmd_buffer_clear_rendering(cmd_buffer, pRenderingInfo);
""")
    replace(CMD, "   if (render->flags & (VK_RENDERING_SUSPENDING_BIT | VK_RENDERING_CUSTOM_RESOLVE_BIT_EXT))\n",
            """#ifdef HAVE_AMDGPU_DARWIN
   if (need_resolve || vk_command_buffer_has_error(&cmd_buffer->vk))
      radv_dcn_clear_reject(&cmd_buffer->dcn_clear);
   if (cmd_buffer->dcn_clear.phase == RADV_DCN_CLEAR_OPEN) {
      const struct radv_image_view *view = render->active && render->color_att_count == 1 ? render->color_att[0].iview : NULL;
      radv_dcn_clear_close(&cmd_buffer->dcn_clear, cmd_buffer->cs->b, view, view ? view->image->bindings[0].bo : NULL,
                           view ? view->image->dcn_render_binding.map.generation : 0);
   }
#endif

   if (render->flags & (VK_RENDERING_SUSPENDING_BIT | VK_RENDERING_CUSTOM_RESOLVE_BIT_EXT))
""")

    replace(META, "static void\nemit_color_clear(", "static bool\nemit_color_clear(")
    replace(META, "      return;\n   }\n\n   radv_meta_push_constants(cmd_buffer, layout, VK_SHADER_STAGE_FRAGMENT_BIT, 0, 16, &clear_value);",
            "      return false;\n   }\n\n   radv_meta_push_constants(cmd_buffer, layout, VK_SHADER_STAGE_FRAGMENT_BIT, 0, 16, &clear_value);")
    replace(META, "      radv_CmdDraw(cmd_buffer_h, 3, clear_rect->layerCount, 0, clear_rect->baseArrayLayer);\n   }\n}",
            "      radv_CmdDraw(cmd_buffer_h, 3, clear_rect->layerCount, 0, clear_rect->baseArrayLayer);\n   }\n"
            "   return !view_mask && clear_rect->layerCount == 1 && !cmd_buffer->state.cond_render.enabled &&\n"
            "          !vk_command_buffer_has_error(&cmd_buffer->vk);\n}")
    replace(META, "static void\nemit_clear(", "static bool\nemit_clear(")
    replace(META, "      if (color_att->format == VK_FORMAT_UNDEFINED)\n         return;\n",
            "      if (color_att->format == VK_FORMAT_UNDEFINED)\n         return false;\n")
    replace(META, "         emit_color_clear(cmd_buffer, clear_att, clear_rect, view_mask);\n",
            "         return emit_color_clear(cmd_buffer, clear_att, clear_rect, view_mask);\n")
    replace(META, "      if (ds_att->format == VK_FORMAT_UNDEFINED)\n         return;\n",
            "      if (ds_att->format == VK_FORMAT_UNDEFINED)\n         return false;\n")
    replace(META, "   }\n}\n\nstatic bool\nradv_rendering_needs_clear(",
            "   }\n   return false;\n}\n\nstatic bool\nradv_rendering_needs_clear(")
    replace(META, "static void\nradv_subpass_clear_attachment(", "static bool\nradv_subpass_clear_attachment(")
    replace(META, "   emit_clear(cmd_buffer, clear_att, &clear_rect, pre_flush, post_flush, render->view_mask);\n\n"
            "   radv_describe_end_render_pass_clear(cmd_buffer);\n}", """   const bool drew_color = emit_clear(cmd_buffer, clear_att, &clear_rect, pre_flush, post_flush, render->view_mask);

   radv_describe_end_render_pass_clear(cmd_buffer);
   return drew_color;
}""")
    replace(META, "      radv_subpass_clear_attachment(cmd_buffer, &clear_att, &pre_flush, &post_flush);\n   }",
            """      UNUSED const bool drew_color = radv_subpass_clear_attachment(cmd_buffer, &clear_att, &pre_flush, &post_flush);
#ifdef HAVE_AMDGPU_DARWIN
      if (drew_color && i == 0)
         radv_dcn_capture_load_clear(cmd_buffer, &pRenderingInfo->pColorAttachments[i]);
#endif
   }""")
    return sources
