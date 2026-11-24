#include <assert.h>
#include <pthread.h>

typedef unsigned int mach_port_t;
#include "nvmtl_vk.h"

typedef void *VkQueue;
typedef void *VkFence;
typedef int VkResult;
typedef unsigned VkSubmitInfo;
typedef VkResult (*PFN_vkQueueSubmit)(VkQueue, unsigned, const VkSubmitInfo *, VkFence);
typedef struct { unsigned begun; } nvmtl_prologue;
#include "inflight.inc"

enum { VK_SUCCESS, VK_ERROR_DEVICE_LOST = -4 };
static int g_state = 1;
static char handles[5];
static VkQueue g_queue = &handles[0];
static unsigned submissions, completions;
static uint64_t expected_writer;
static bool complete;
static pthread_mutex_t nvmtl_submit_mutex = PTHREAD_MUTEX_INITIALIZER;

static VkResult pvkQueueSubmit(VkQueue queue, unsigned count, const VkSubmitInfo *info, VkFence fence)
{
    assert(queue == g_queue && count == 1 && info && fence == &handles[1]);
    ++submissions;
    return VK_SUCCESS;
}

static VkResult submit_part(PFN_vkQueueSubmit submit, VkQueue queue, const VkSubmitInfo *info, VkFence fence,
                             const struct build34_dcn_part_target *target, struct build34_dcn_part_writer *writer)
{
    assert(target->host == &handles[2] && target->image && target->view && target->memory);
    assert(target->import_bytes == 8192 && target->bind_bytes == 8192 && target->pitch == 256);
    assert(target->width == 63 && target->height == 32);
    writer->recording = expected_writer;
    return submit(queue, 1, info, fence);
}

static bool complete_part(VkQueue queue, const struct build34_dcn_part_target *target,
                          const struct build34_dcn_part_writer *writer)
{
    assert(queue == g_queue && target->host == &handles[2] && writer->recording == expected_writer);
    ++completions;
    return complete;
}

static __typeof__(submit_part) *nvmtl_dcn_submit_part = submit_part;
static __typeof__(complete_part) *nvmtl_dcn_complete_part = complete_part;

static void nvmtl_cmd_retire(nvk_cmdbuf *command)
{
    command->cb = NULL;
    command->dcn_part_held = 0;
    command->dcn_writer = (struct build34_dcn_part_writer){0};
}

static VkResult submit(nvk_cmdbuf *c, nvmtl_inflight *f, unsigned ncb)
{
    const VkSubmitInfo si = ncb;
    const VkFence fence = &handles[1];
    VkResult result;
#include "part_submit.inc"
    return result;
}

static void finish(nvk_cmdbuf *c, nvmtl_inflight *f)
{
#include "part_finish.inc"
}

int main(void)
{
    const nvmtl_dcn_attachment attachment = {
        .surface = &handles[0], .image = &handles[1], .host = &handles[2], .view = &handles[3], .memory = &handles[4],
        .import_bytes = 8192, .bind_bytes = 8192, .pitch = 256, .width = 63, .height = 32, .external_host = 1,
    };
    const nvk_cmdbuf command = {.cb = &handles[0], .dcn_part_held = 1, .dcn_recording.recorded = attachment};
    for (unsigned variant = 0; variant < 9; ++variant) {
        nvk_cmdbuf current = command;
        nvmtl_inflight inflight = {0};
        expected_writer = 17;
        switch (variant) {
        case 1: current.dcn_part_held = 0; break;
        case 2: current.dcn_recording.recorded.external_host = 0; break;
        case 3: current.dcn_recording.ambiguous = 1; break;
        case 4: current.dcn_recording.open = attachment; break;
        case 5: current.encoding_error = 1; break;
        case 6: current.skipped = 1; break;
        case 7: nvmtl_dcn_complete_part = NULL; break;
        }
        assert(submit(&current, &inflight, variant == 8 ? 2 : 1) == VK_SUCCESS);
        assert(inflight.dcn_writer.recording == (variant ? 0 : 17));
        nvmtl_dcn_complete_part = complete_part;
    }
    nvk_cmdbuf first = command, second = command;
    nvmtl_inflight earlier = {0}, later = {0};
    expected_writer = 21;
    assert(submit(&first, &earlier, 1) == VK_SUCCESS);
    expected_writer = 22;
    assert(submit(&second, &later, 1) == VK_SUCCESS);
    complete = true;
    finish(&second, &later);
    assert(!second.cb && second.dcn_writer.recording == 22 && !later.dcn_writer.recording && !later.dcn_target.host);
    expected_writer = 21;
    complete = false;
    finish(&first, &earlier);
    assert(!first.cb && !first.dcn_writer.recording && !earlier.dcn_writer.recording);
    assert(submissions == 11 && completions == 2);
    first = command;
    assert(submit(&first, &earlier, 1) == VK_SUCCESS);
    assert(!pthread_mutex_lock(&nvmtl_submit_mutex));
    finish(&first, &earlier);
    assert(!pthread_mutex_unlock(&nvmtl_submit_mutex));
    assert(!first.dcn_writer.recording && completions == 2);
    return 0;
}
