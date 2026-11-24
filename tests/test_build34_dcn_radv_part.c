#include <assert.h>
#include <vulkan/vulkan.h>

#include "build34_dcn_part.h"
#include "build34_dcn_radv_submit.h"

enum { VK_QUEUE_SUBMIT_MODE_IMMEDIATE, TEST_THREADED };
struct radeon_winsys { unsigned token; };
struct radv_device { struct radeon_winsys *ws; unsigned vk; };
struct radv_queue {
    struct { struct { unsigned mode; } submit; } vk;
    struct radv_device *device;
};
struct radv_device_memory {
    const void *bo, *user_ptr;
    VkExternalMemoryHandleTypeFlagBits import_handle_type;
};
struct radv_image {
    struct radv_dcn_render_binding dcn_render_binding;
    struct { const void *bo; uint64_t addr, range; } bindings[1];
};
struct radv_image_view { struct { struct { const unsigned *device; } base; } vk; struct radv_image *image; };
struct vk_queue_submit { unsigned command_buffer_count; void *command_buffers[2]; };

#define VK_FROM_HANDLE(type, name, handle) struct type *name = (struct type *)(handle)
#define radv_image_view_from_handle(handle) ((struct radv_image_view *)(handle))
#define radv_queue_device(queue) ((queue)->device)

static char host, bo, command, other_command, fence_token;
static struct radeon_winsys winsys;
static struct radv_device device = {.ws = &winsys};
static struct radv_queue queue = {.device = &device}, other_queue = {.device = &device};
static struct radv_device_memory memory = {&bo, &host, VK_EXTERNAL_MEMORY_HANDLE_TYPE_HOST_ALLOCATION_BIT_EXT};
static struct radv_image image = {
    .dcn_render_binding = {{&winsys, &host, 5, 0x10000, 8192, 7}, 0x10000, 8192, 256, 8192, 63, 32, &memory},
    .bindings = {{&bo, 0x10000, 8192}},
};
static struct radv_image_view view = {.vk.base.device = &device.vk, .image = &image};
static struct radv_dcn_host_map current_map;
static struct radv_dcn_submitted_clear submitted;
static struct build34_dcn_part_target target = {&image, &view, &memory, &host, 8192, 8192, 256, 63, 32};
static unsigned dispatches, polls, scenario;
static bool pending;
static int poll_result;

static struct radv_dcn_host_map radv_amdgpu_dcn_host_map(const struct radeon_winsys *ws, const void *handle)
{
    assert(ws == &winsys && handle == &bo);
    return current_map;
}

static int radv_dcn_poll_native(const struct radeon_winsys *ws, const struct build34_dcn_native_submit *receipt, bool *busy)
{
    const struct build34_dcn_native_submit accepted = submitted.native;
    assert(ws == &winsys);
    assert(receipt->owner == accepted.owner && receipt->serial == accepted.serial &&
           receipt->sequence == accepted.sequence && receipt->generation == accepted.generation &&
           receipt->context == accepted.context && receipt->queue == accepted.queue && receipt->slot == accepted.slot);
    ++polls;
    *busy = pending;
    return poll_result;
}

#include "staged_radv_part.inc"

static VkResult dispatch(VkQueue handle, uint32_t count, const VkSubmitInfo *info, VkFence fence)
{
    assert(handle == (VkQueue)&queue && count == 1 && fence == (VkFence)&fence_token);
    ++dispatches;
    struct vk_queue_submit submission = {info->commandBufferCount, {(void *)info->pCommandBuffers[0]}};
    if (scenario == 1) return VK_SUCCESS;
    if (scenario == 2) submission.command_buffers[0] = &other_command;
    if (scenario == 3) submission.command_buffer_count = 2;
    radv_dcn_note_part_submit();
    radv_dcn_capture_part(scenario == 4 ? &other_queue : &queue, &submission, &submitted);
    if (scenario == 5) radv_dcn_note_part_submit();
    if (scenario == 6) return VK_ERROR_DEVICE_LOST;
    return VK_SUCCESS;
}

int main(void)
{
    VkCommandBuffer cb = (VkCommandBuffer)&command;
    VkSubmitInfo info = {.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO, .commandBufferCount = 1, .pCommandBuffers = &cb};
    struct build34_dcn_part_writer writer;
    current_map = image.dcn_render_binding.map;
    submitted.clear.binding = image.dcn_render_binding;
    submitted.clear.view = &view;
    submitted.clear.bo = &bo;
    submitted.clear.serial = 11;
    submitted.native = (struct build34_dcn_native_submit){33, 27, 3, 9, 4, 1, 51};

    for (scenario = 0; scenario != 7; ++scenario) {
        writer.recording = UINT64_MAX;
        VkResult result = build34_dcn_queue_submit_v1(dispatch, (VkQueue)&queue, &info, (VkFence)&fence_token, &target, &writer);
        assert(result == (scenario == 6 ? VK_ERROR_DEVICE_LOST : VK_SUCCESS));
        assert(dispatches == scenario + 1 && !radv_dcn_part_scope);
        assert(writer.recording == (scenario ? 0 : 11));
    }
    scenario = 0;
    for (unsigned variant = 0; variant != 13; ++variant) {
        struct build34_dcn_part_target probe = target;
        const struct radv_dcn_render_binding recorded = submitted.clear.binding;
        const struct radv_dcn_host_map map = current_map;
        switch (variant) {
        case 1: probe.image = &other_command; break;
        case 2: probe.view = &other_command; break;
        case 3: probe.memory = &other_command; break;
        case 4: probe.host = &other_command; break;
        case 5: probe.bind_bytes /= 2; break;
        case 6: probe.import_bytes *= 2; break;
        case 7: probe.pitch *= 2; break;
        case 8: ++current_map.generation; break;
        case 9: ++current_map.handle; break;
        case 10: submitted.clear.binding.memory = &other_command; break;
        case 11: queue.vk.submit.mode = TEST_THREADED; break;
        case 12: info.commandBufferCount = 2; break;
        }
        assert(!build34_dcn_queue_submit_v1(dispatch, (VkQueue)&queue, &info, (VkFence)&fence_token, &probe, &writer));
        assert((writer.recording != 0) == (variant == 0));
        current_map = map;
        submitted.clear.binding = recorded;
        queue.vk.submit.mode = VK_QUEUE_SUBMIT_MODE_IMMEDIATE;
        info.commandBufferCount = 1;
    }
    assert(!build34_dcn_queue_submit_v1(dispatch, (VkQueue)&queue, &info, (VkFence)&fence_token, &target, &writer));
    assert(writer.map_generation == 5 && writer.phx_va == 0x10000 && writer.bo_handle == 7 && writer.page_bytes == 8192);
    pending = true;
    assert(!build34_dcn_queue_complete_v1((VkQueue)&queue, &target, &writer) && polls == 1);
    pending = false;
    poll_result = -1;
    assert(!build34_dcn_queue_complete_v1((VkQueue)&queue, &target, &writer) && polls == 2);
    poll_result = 0;
    assert(build34_dcn_queue_complete_v1((VkQueue)&queue, &target, &writer) && polls == 3);
    ++current_map.generation;
    assert(!build34_dcn_queue_complete_v1((VkQueue)&queue, &target, &writer) && polls == 3);
    return 0;
}
