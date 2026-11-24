#include <assert.h>
#include <string.h>

typedef unsigned int mach_port_t;
#include "nvmtl_vk.h"

enum { VK_SUCCESS = 0, VK_ERROR_DEVICE_LOST = -4, VK_SUBPASS_CONTENTS_INLINE = 0,
    VK_FORMAT_B8G8R8A8_UNORM = 44, VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT = 16,
    VK_IMAGE_ASPECT_COLOR_BIT = 1, VK_IMAGE_ASPECT_MEMORY_PLANE_0_BIT_EXT = 128 };
typedef void *VkImage;
typedef struct { unsigned aspect, mip, layer; } VkImageSubresource;
typedef struct { uint64_t offset, size, rowPitch; } VkSubresourceLayout;
typedef void (*PFN_vkGetImageSubresourceLayout)(void *, VkImage, const VkImageSubresource *, VkSubresourceLayout *);

static char handles[16];
static void *g_inst, *g_dev, *g_queue;
static int g_linmod, g_state = 1, queue_result = VK_SUCCESS, provide_layout = 1;
static unsigned begins, ends, layout_aspect;
static VkSubresourceLayout layout = {0, 8192, 256};
static uint64_t nvmtl_dcn_submit_serial;
struct nvmtl_inflight { nvmtl_dcn_observation dcn_submitted; };

static void fake_layout(void *device, VkImage image, const VkImageSubresource *sub, VkSubresourceLayout *out)
{
    assert(device == g_dev && image && !sub->mip && !sub->layer);
    layout_aspect = sub->aspect;
    *out = layout;
}

static PFN_vkGetImageSubresourceLayout pvkGetInstanceProcAddr(void *instance, const char *name)
{
    assert(instance == g_inst && !strcmp(name, "vkGetImageSubresourceLayout"));
    return provide_layout ? fake_layout : 0;
}

static void pvkCmdBeginRenderPass(void *commands, const int *info, int contents)
{
    assert(commands && info && contents == VK_SUBPASS_CONTENTS_INLINE);
    ++begins;
}

static void pvkCmdEndRenderPass(void *commands)
{
    assert(commands);
    ++ends;
}

static int pvkQueueSubmit(void *queue, int count, const int *info, void *fence)
{
    assert(queue == g_queue && count == 1 && info && fence);
    return queue_result;
}

static void bind_alias(nvk_image *out, const nvk_buffer *b, size_t at, int a8, uint64_t required)
{
    const uint32_t w = out->w, h = out->h, vkfmt = out->fmt, bpp = out->bpp;
    const size_t row_pitch = 256;
    const struct { uint64_t size; } mr = {required};
#include "alias.inc"
}

static nvk_buffer host_buffer(unsigned index)
{
    return (nvk_buffer){.buf = &handles[index + 1], .mem = &handles[index + 2], .map = &handles[index + 3],
        .size = 8192, .alloc = 8192, .imported = 1};
}

static nvk_image host_image(unsigned index, const nvk_buffer *buffer, uint32_t usage)
{
    return (nvk_image){.img = &handles[index], .mem = buffer->mem, .view = &handles[index + 4],
        .w = 63, .h = 32, .mips = 1, .fmt = VK_FORMAT_B8G8R8A8_UNORM, .bpp = 4, .mtl_type = 2,
        .layers = 1, .placed = 1, .usage = usage};
}

static nvk_image direct_image(unsigned index)
{
    const nvk_buffer buffer = host_buffer(index);
    nvk_image image = host_image(index, &buffer, VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT);
    bind_alias(&image, &buffer, 0, 0, buffer.alloc);
    nvmtl_dcn_set_surface(&image.dcn_attachment, &handles[index + 5], 0, 0, NVMTL_DCN_BGRA, 63, 32, 256, 8192);
    assert(image.dcn_attachment.surface && image.dcn_attachment.footprint == 8192);
    return image;
}

static void import_cases(void)
{
    nvk_image image = direct_image(0);
    assert(layout_aspect == VK_IMAGE_ASPECT_COLOR_BIT);
    g_linmod = 1;
    image = direct_image(0);
    assert(layout_aspect == VK_IMAGE_ASPECT_MEMORY_PLANE_0_BIT_EXT);
    const nvk_buffer host = host_buffer(0);
    for (unsigned test = 0; test < 11; ++test) {
        nvk_buffer buffer = host;
        nvk_image variant = host_image(0, &buffer, VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT);
        unsigned offset = 0, alpha = 0;
        uint64_t required = 8192;
        layout = (VkSubresourceLayout){0, 8192, 256};
        provide_layout = 1;
        switch (test) {
        case 0: variant.usage = 0; break;
        case 1: buffer.imported = 0; break;
        case 2: buffer.placed = 1; break;
        case 3: offset = 4096; break;
        case 4: layout.offset = 8; break;
        case 5: layout.rowPitch = 512; break;
        case 6: layout.size = 8187; break;
        case 7: required = 8193; break;
        case 8: variant.fmt += 1; break;
        case 9: alpha = 1; break;
        case 10: provide_layout = 0; break;
        }
        bind_alias(&variant, &buffer, offset, alpha, required);
        assert(!variant.dcn_attachment.image);
    }
    for (unsigned test = 0; test < 7; ++test) {
        nvmtl_dcn_attachment alias = image.dcn_attachment;
        nvmtl_dcn_set_surface(&alias, &handles[5], test == 0, test == 1,
            test == 2 ? 0x6c313072u : NVMTL_DCN_BGRA, test == 3 ? 62 : 63,
            test == 4 ? 31 : 32, test == 5 ? 260 : 256, test == 6 ? 8191 : 8192);
        assert(!alias.surface);
    }
}

static nvk_pass make_pass(nvk_image *image, unsigned slot)
{
    nvk_pass pass = {.w = image->w, .h = image->h, .layers = 1, .dcn_clear_store = 1u << slot};
    pass.col[slot] = image;
    pass.colview[slot] = image->view;
    pass.colw[slot] = pass.w;
    pass.colh[slot] = pass.h;
    return pass;
}

static void begin_pass(nvk_cmdbuf *c, const nvk_pass *ps, const nvk_pipeline *p, uint32_t *cf, uint32_t ncol)
{
    const int rbi = 0;
#include "begin.inc"
}

static void end_pass(nvk_cmdbuf *c)
{
#include "end.inc"
}

static int submit(nvk_cmdbuf *c, nvmtl_inflight *f)
{
    int result, si = 0;
    void *fence = &handles[15];
#include "submit.inc"
    return result;
}

static void finish(nvk_cmdbuf *c, nvmtl_inflight *f, int accepted)
{
    c->dcn_recording = (nvmtl_dcn_recording){0};
    c->dcn_completed = (nvmtl_dcn_observation){0};
    if (!accepted) return;
#include "finish.inc"
}

static void record_pass(nvk_cmdbuf *commands, nvk_image *image)
{
    nvk_pass pass = make_pass(image, 2);
    const nvk_pipeline pipeline = {0};
    uint32_t formats[NVMTL_NCOL] = {0, 0, VK_FORMAT_B8G8R8A8_UNORM};
    begin_pass(commands, &pass, &pipeline, formats, 3);
    assert(commands->dcn_recording.open.surface == image->dcn_attachment.surface || commands->dcn_recording.ambiguous);
    end_pass(commands);
}

static void pass_cases(void)
{
    nvk_image image = direct_image(0), other = direct_image(6);
    nvk_cmdbuf commands = {.cb = &handles[14]};
    for (unsigned test = 0; test < 15; ++test) {
        nvk_image variant = image;
        nvk_pass pass = make_pass(&variant, 2);
        nvk_pipeline pipeline = {0};
        uint32_t formats[NVMTL_NCOL] = {0, 0, VK_FORMAT_B8G8R8A8_UNORM};
        switch (test) {
        case 0: formats[2] = 0; break;
        case 1: pass.dcn_clear_store = 0; break;
        case 2: pass.load = NVMTL_LOAD_COLOUR(2); break;
        case 3: pass.w = 62; break;
        case 4: pass.colview[2] = other.view; break;
        case 5: pass.col_layer[2] = 1; break;
        case 6: pass.col_level[2] = 1; break;
        case 7: pass.layers = 2; break;
        case 8: pass.res[2] = &other; break;
        case 9: pipeline.samples = 4; break;
        case 10: variant.dcn_attachment.surface = 0; break;
        case 11: variant.usage = 0; break;
        case 12: variant.mem = other.mem; break;
        case 13: variant.img = other.img; break;
        case 14: variant.fmt = 50; break;
        }
        begin_pass(&commands, &pass, &pipeline, formats, 3);
        assert(!commands.dcn_recording.open.surface);
        end_pass(&commands);
        assert(!commands.dcn_recording.recorded.surface);
    }
    record_pass(&commands, &image);
    record_pass(&commands, &image);
    assert(commands.dcn_recording.recorded.surface == image.dcn_attachment.surface && !commands.dcn_recording.ambiguous);
    record_pass(&commands, &other);
    assert(commands.dcn_recording.ambiguous && begins == ends);
    nvmtl_inflight pending = {0};
    assert(!submit(&commands, &pending) && !pending.dcn_submitted.serial);
}

static void submit_cases(void)
{
    nvk_image image = direct_image(0), other = direct_image(6);
    other.dcn_attachment.surface = image.dcn_attachment.surface;
    nvk_cmdbuf first = {.cb = &handles[12]}, second = {.cb = &handles[13]};
    nvmtl_inflight earlier = {0}, later = {0};
    record_pass(&first, &image);
    record_pass(&second, &other);
    assert(!submit(&first, &earlier) && !submit(&second, &later));
    assert(earlier.dcn_submitted.serial == 1 && later.dcn_submitted.serial == 2);
    assert(!first.dcn_completed.serial && !second.dcn_completed.serial);
    finish(&second, &later, 1);
    assert(second.dcn_completed.serial == 2 && second.dcn_completed.attachment.image == other.img);
    assert(second.dcn_completed.attachment.memory == other.mem);
    assert(!first.dcn_completed.serial);
    finish(&first, &earlier, 1);
    assert(first.dcn_completed.serial == 1 && first.dcn_completed.attachment.image == image.img);
    assert(first.dcn_completed.attachment.memory == image.mem);
    assert(first.dcn_completed.attachment.surface == second.dcn_completed.attachment.surface);
    assert(!earlier.dcn_submitted.serial && !later.dcn_submitted.serial);

    record_pass(&first, &other);
    queue_result = VK_ERROR_DEVICE_LOST;
    assert(submit(&first, &earlier) && !earlier.dcn_submitted.serial);
    queue_result = VK_SUCCESS;
    first.skipped = 1;
    assert(!submit(&first, &earlier) && !earlier.dcn_submitted.serial);
    first.skipped = 0;
    first.encoding_error = 1;
    assert(!submit(&first, &earlier) && !earlier.dcn_submitted.serial);
    first.encoding_error = 0;
    first.in_rp = 1;
    assert(!submit(&first, &earlier) && !earlier.dcn_submitted.serial);
    first.in_rp = 0;
    assert(!submit(&first, &earlier) && earlier.dcn_submitted.serial == 3);
    finish(&first, &earlier, 0);
    assert(!first.dcn_completed.serial);
    record_pass(&second, &image);
    nvmtl_dcn_submit_serial = UINT64_MAX;
    assert(!submit(&second, &later) && !later.dcn_submitted.serial);
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    if (!strcmp(argv[1], "import")) import_cases();
    else if (!strcmp(argv[1], "pass")) pass_cases();
    else if (!strcmp(argv[1], "submit")) submit_cases();
    else return 1;
    return 0;
}
