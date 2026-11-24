"""Derive a call-scoped association between an exact RADV writer and its caller."""

import build34_dcn_radv_binding_stage as binding
import build34_dcn_radv_complete_stage as complete
import build34_dcn_radv_submit_stage as submit


INPUTS = complete.INPUTS
HEADER = "src/amd/vulkan/build34_dcn_part.h"


def stage(inputs):
    sources = complete.stage(inputs)

    def replace(name, old, new):
        if sources[name].count(old) != 1:
            raise ValueError(f"Build34 RADV part anchor drift: {name}: {old[:75]}")
        sources[name] = sources[name].replace(old, new)

    replace(binding.IMAGE,
            "      image->dcn_render_binding = radv_dcn_bound_image(_device, image, mem, device->ws, bind_idx, offset);\n",
            "      image->dcn_render_binding = radv_dcn_bound_image(_device, image, mem, device->ws, bind_idx, offset);\n"
            "      if (image->dcn_render_binding.map.generation)\n"
            "         image->dcn_render_binding.memory = mem;\n")

    replace(submit.QUEUE, '#include "ac_descriptors.h"\n', '#include "ac_descriptors.h"\n'
            '#ifdef HAVE_AMDGPU_DARWIN\n#include "build34_dcn_part.h"\n'
            '#include "winsys/amdgpu/radv_amdgpu_bo.h"\n#endif\n')
    replace(submit.QUEUE, "static VkResult\nradv_queue_submit_normal(", """#ifdef HAVE_AMDGPU_DARWIN
VkResult build34_dcn_queue_submit_v1(PFN_vkQueueSubmit submit, VkQueue queue, const VkSubmitInfo *info, VkFence fence,
                                    const struct build34_dcn_part_target *target, struct build34_dcn_part_writer *out);
bool build34_dcn_queue_complete_v1(VkQueue handle, const struct build34_dcn_part_target *target,
                                   const struct build34_dcn_part_writer *writer);

struct radv_dcn_part_scope {
   VkQueue queue;
   VkCommandBuffer command;
   const struct build34_dcn_part_target *target;
   struct build34_dcn_part_writer writer;
   unsigned calls;
};

static _Thread_local struct radv_dcn_part_scope *radv_dcn_part_scope;

static void
radv_dcn_note_part_submit(void)
{
   if (radv_dcn_part_scope && radv_dcn_part_scope->calls < 2)
      ++radv_dcn_part_scope->calls;
}

static const struct radv_dcn_render_binding *
radv_dcn_live_part(const struct radv_device *device, const struct radv_image_view *view,
                   const struct build34_dcn_part_target *target)
{
   if (!view || view != target->view ||
       view->vk.base.device != &device->vk)
      return NULL;
   const struct radv_image *image = view->image;
   const struct radv_dcn_render_binding *bound = &image->dcn_render_binding;
   const struct radv_device_memory *memory = bound->memory;
   if (image != target->image || !memory || memory != target->memory ||
       memory->bo != image->bindings[0].bo || memory->user_ptr != target->host ||
       memory->import_handle_type != VK_EXTERNAL_MEMORY_HANDLE_TYPE_HOST_ALLOCATION_BIT_EXT ||
       !bound->map.generation || !target->host || bound->map.host != target->host ||
       bound->map.bytes != target->import_bytes || bound->bind_bytes != target->bind_bytes ||
       bound->width != target->width || bound->height != target->height || bound->pitch != target->pitch ||
       image->bindings[0].addr != bound->map.va || image->bindings[0].range != bound->bind_bytes)
      return NULL;
   const struct radv_dcn_host_map live = radv_amdgpu_dcn_host_map(device->ws, memory->bo);
   return live.generation == bound->map.generation && live.winsys == bound->map.winsys &&
          live.va == bound->map.va && live.handle == bound->map.handle && live.bytes == bound->map.bytes &&
          live.host == bound->map.host ? bound : NULL;
}

static void
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

__attribute__((visibility("default"))) VkResult
build34_dcn_queue_submit_v1(PFN_vkQueueSubmit submit, VkQueue queue, const VkSubmitInfo *info, VkFence fence,
                            const struct build34_dcn_part_target *target, struct build34_dcn_part_writer *out)
{
   *out = (struct build34_dcn_part_writer){0};
   if (radv_dcn_part_scope) {
      radv_dcn_part_scope->calls = 2;
      return submit(queue, 1, info, fence);
   }
   if (info->commandBufferCount != 1 || info->pNext || info->waitSemaphoreCount || info->signalSemaphoreCount)
      return submit(queue, 1, info, fence);
   struct radv_dcn_part_scope scope = {.queue = queue, .command = info->pCommandBuffers[0], .target = target};
   radv_dcn_part_scope = &scope;
   const VkResult result = submit(queue, 1, info, fence);
   radv_dcn_part_scope = NULL;
   if (result == VK_SUCCESS && scope.calls == 1)
      *out = scope.writer;
   return result;
}

__attribute__((visibility("default"))) bool
build34_dcn_queue_complete_v1(VkQueue handle, const struct build34_dcn_part_target *target,
                              const struct build34_dcn_part_writer *writer)
{
   if (!writer->recording || !build34_dcn_valid_native_submit(writer->native, writer->native.sequence))
      return false;
   VK_FROM_HANDLE(radv_queue, queue, handle);
   const struct radv_device *device = radv_queue_device(queue);
   const struct radv_image_view *view = radv_image_view_from_handle((VkImageView)target->view);
   const struct radv_dcn_render_binding *live = radv_dcn_live_part(device, view, target);
   if (!live || live->map.generation != writer->map_generation || live->map.handle != writer->bo_handle ||
       live->phx_va != writer->phx_va || live->scanout_bytes != writer->page_bytes)
      return false;
   bool busy = true;
   return !radv_dcn_poll_native(device->ws, &writer->native, &busy) && !busy;
}
#endif

static VkResult
radv_queue_submit_normal(""")
    replace(submit.QUEUE_H, "#ifdef HAVE_AMDGPU_DARWIN\n   struct radv_dcn_submitted_clear dcn_clear;\n#endif\n", "")
    replace(submit.QUEUE, "   radv_dcn_finish_submit(&queue->dcn_clear, dcn_clear, result == VK_SUCCESS);\n",
            "   struct radv_dcn_submitted_clear accepted;\n"
            "   radv_dcn_finish_submit(&accepted, dcn_clear, result == VK_SUCCESS);\n"
            "   radv_dcn_capture_part(queue, submission, &accepted);\n")
    replace(submit.QUEUE, "   queue->dcn_clear = (struct radv_dcn_submitted_clear){0};\n",
            "   radv_dcn_note_part_submit();\n")
    return sources
