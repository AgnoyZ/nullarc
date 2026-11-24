#include <assert.h>
#include <string.h>

#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>

typedef unsigned int mach_port_t;
#include "nvmtl_vk.h"

static char handles[8];
static VkInstance g_inst;
static VkDevice g_dev;
static VkPhysicalDevice g_pdev;
static VkPhysicalDeviceMemoryProperties g_memp = {.memoryTypeCount = 3};
static int g_host_import = 1, g_linmod, fetch;
static enum {
    OK, NO_GET_FORMAT, NO_GET_REQUIREMENTS, NO_GET_LAYOUT, NO_GET_MODIFIERS, QUERY_FAIL,
    NOT_IMPORTABLE, INCOMPATIBLE, FORMAT_DEDICATED, SMALL_FORMAT, MANY_PLANES, TRUNCATED_MODIFIERS,
    CREATE_FAIL, IMAGE_DEDICATED, SIZE, ALIGNMENT, MEMORY_TYPE, OFFSET, PITCH, SHORT_LAYOUT,
    BIND_FAIL, VIEW_FAIL
} fault;
static unsigned queries, modifiers, creates, requirements, layouts, binds, views, destroys, commits;

int nvmtl_vk_init(void) { return 0; }
static int nvmtl_fbfetch_on(void) { return fetch; }

static VkImageUsageFlags expected_usage(void)
{
    return VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT |
        (fetch ? VK_IMAGE_USAGE_INPUT_ATTACHMENT_BIT : 0);
}

static VkResult fake_format(VkPhysicalDevice device, const VkPhysicalDeviceImageFormatInfo2 *query,
    VkImageFormatProperties2 *out)
{
    const VkPhysicalDeviceExternalImageFormatInfo *external = query->pNext;
    const VkPhysicalDeviceImageDrmFormatModifierInfoEXT *modifier = external->pNext;
    assert(device == g_pdev && query->sType == VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_IMAGE_FORMAT_INFO_2);
    assert(query->format == VK_FORMAT_B8G8R8A8_UNORM && query->type == VK_IMAGE_TYPE_2D);
    assert(query->usage == expected_usage() && !query->flags);
    assert(external->sType == VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_EXTERNAL_IMAGE_FORMAT_INFO);
    assert(external->handleType == VK_EXTERNAL_MEMORY_HANDLE_TYPE_HOST_ALLOCATION_BIT_EXT);
    if (g_linmod) {
        assert(query->tiling == VK_IMAGE_TILING_DRM_FORMAT_MODIFIER_EXT);
        assert(modifier && modifier->sType == VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_IMAGE_DRM_FORMAT_MODIFIER_INFO_EXT);
        assert(!modifier->pNext && !modifier->drmFormatModifier && modifier->sharingMode == VK_SHARING_MODE_EXCLUSIVE);
        assert(!modifier->queueFamilyIndexCount && !modifier->pQueueFamilyIndices);
    } else {
        assert(query->tiling == VK_IMAGE_TILING_LINEAR && !modifier);
    }
    queries++;
    if (fault == QUERY_FAIL) return VK_ERROR_FORMAT_NOT_SUPPORTED;
    assert(out->sType == VK_STRUCTURE_TYPE_IMAGE_FORMAT_PROPERTIES_2);
    VkExternalImageFormatProperties *properties = out->pNext;
    assert(properties->sType == VK_STRUCTURE_TYPE_EXTERNAL_IMAGE_FORMAT_PROPERTIES && !properties->pNext);
    properties->externalMemoryProperties = (VkExternalMemoryProperties){
        .compatibleHandleTypes = fault == INCOMPATIBLE ? 0 : external->handleType,
        .externalMemoryFeatures = fault == NOT_IMPORTABLE ? 0 : VK_EXTERNAL_MEMORY_FEATURE_IMPORTABLE_BIT |
            (fault == FORMAT_DEDICATED ? VK_EXTERNAL_MEMORY_FEATURE_DEDICATED_ONLY_BIT : 0),
    };
    out->imageFormatProperties = (VkImageFormatProperties){
        .maxExtent = {256, 256, 1}, .maxMipLevels = 1, .maxArrayLayers = 1,
        .sampleCounts = VK_SAMPLE_COUNT_1_BIT, .maxResourceSize = fault == SMALL_FORMAT ? 4096 : 32768,
    };
    return VK_SUCCESS;
}

static void fake_modifiers(VkPhysicalDevice device, VkFormat format, VkFormatProperties2 *out)
{
    assert(device == g_pdev && format == VK_FORMAT_B8G8R8A8_UNORM && g_linmod);
    assert(out->sType == VK_STRUCTURE_TYPE_FORMAT_PROPERTIES_2);
    VkDrmFormatModifierPropertiesListEXT *list = out->pNext;
    assert(list->sType == VK_STRUCTURE_TYPE_DRM_FORMAT_MODIFIER_PROPERTIES_LIST_EXT && !list->pNext);
    assert(list->drmFormatModifierCount == 64 && list->pDrmFormatModifierProperties);
    const uint32_t capacity = list->drmFormatModifierCount;
    list->pDrmFormatModifierProperties[0] = (VkDrmFormatModifierPropertiesEXT){ 1, 1, 0 };
    list->pDrmFormatModifierProperties[1] = (VkDrmFormatModifierPropertiesEXT){ 0, fault == MANY_PLANES ? 2 : 1, 0 };
    list->drmFormatModifierCount = fault == TRUNCATED_MODIFIERS ? capacity + 1 : 2;
    modifiers++;
}

static void fake_requirements(VkDevice device, const VkImageMemoryRequirementsInfo2 *image,
    VkMemoryRequirements2 *out)
{
    assert(device == g_dev && image->sType == VK_STRUCTURE_TYPE_IMAGE_MEMORY_REQUIREMENTS_INFO_2 && creates);
    assert(image->image == (VkImage)&handles[0] && out->sType == VK_STRUCTURE_TYPE_MEMORY_REQUIREMENTS_2);
    VkMemoryDedicatedRequirements *dedicated = out->pNext;
    assert(dedicated && dedicated->sType == VK_STRUCTURE_TYPE_MEMORY_DEDICATED_REQUIREMENTS);
    dedicated->requiresDedicatedAllocation = fault == IMAGE_DEDICATED;
    out->memoryRequirements = (VkMemoryRequirements){ fault == SIZE ? 8193 : 8192,
        fault == ALIGNMENT ? 0 : 4096, fault == MEMORY_TYPE ? 1 : 2 };
    requirements++;
}

static void fake_layout(VkDevice device, VkImage image, const VkImageSubresource *sub, VkSubresourceLayout *out)
{
    assert(device == g_dev && image == (VkImage)&handles[0] && requirements);
    assert(!sub->mipLevel && !sub->arrayLayer);
    assert(sub->aspectMask == (g_linmod ? VK_IMAGE_ASPECT_MEMORY_PLANE_0_BIT_EXT : VK_IMAGE_ASPECT_COLOR_BIT));
    *out = (VkSubresourceLayout){fault == OFFSET ? 4 : 0, fault == SHORT_LAYOUT ? 8191 : 8192,
        fault == PITCH ? 512 : 256, 0, 0};
    layouts++;
}

static PFN_vkVoidFunction pvkGetInstanceProcAddr(VkInstance instance, const char *name)
{
    assert(instance == g_inst);
    if (!strcmp(name, "vkGetPhysicalDeviceImageFormatProperties2"))
        return fault == NO_GET_FORMAT ? NULL : (PFN_vkVoidFunction)fake_format;
    assert(!strcmp(name, "vkGetPhysicalDeviceFormatProperties2"));
    return fault == NO_GET_MODIFIERS ? NULL : (PFN_vkVoidFunction)fake_modifiers;
}

static PFN_vkVoidFunction pvkGetDeviceProcAddr(VkDevice device, const char *name)
{
    assert(device == g_dev);
    if (!strcmp(name, "vkGetImageMemoryRequirements2"))
        return fault == NO_GET_REQUIREMENTS ? NULL : (PFN_vkVoidFunction)fake_requirements;
    assert(!strcmp(name, "vkGetImageSubresourceLayout"));
    return fault == NO_GET_LAYOUT ? NULL : (PFN_vkVoidFunction)fake_layout;
}

static VkResult nvmtl_opaque_CreateImage(VkDevice device, const VkImageCreateInfo *create,
    const VkAllocationCallbacks *allocator, void **out)
{
    assert(device == g_dev && !allocator && queries && (!g_linmod || modifiers));
    assert(create->sType == VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO && create->usage == expected_usage());
    assert(create->format == VK_FORMAT_B8G8R8A8_UNORM && create->imageType == VK_IMAGE_TYPE_2D);
    assert(create->extent.width == 64 && create->extent.height == 32 && create->extent.depth == 1);
    assert(create->mipLevels == 1 && create->arrayLayers == 1 && create->samples == VK_SAMPLE_COUNT_1_BIT);
    assert(!create->flags && create->sharingMode == VK_SHARING_MODE_EXCLUSIVE);
    assert(create->initialLayout == VK_IMAGE_LAYOUT_UNDEFINED);
    const VkExternalMemoryImageCreateInfo *external = create->pNext;
    assert(external && external->sType == VK_STRUCTURE_TYPE_EXTERNAL_MEMORY_IMAGE_CREATE_INFO);
    assert(external->handleTypes == VK_EXTERNAL_MEMORY_HANDLE_TYPE_HOST_ALLOCATION_BIT_EXT);
    if (g_linmod) {
        const VkImageDrmFormatModifierExplicitCreateInfoEXT *modifier = external->pNext;
        assert(create->tiling == VK_IMAGE_TILING_DRM_FORMAT_MODIFIER_EXT && modifier);
        assert(modifier->sType == VK_STRUCTURE_TYPE_IMAGE_DRM_FORMAT_MODIFIER_EXPLICIT_CREATE_INFO_EXT);
        assert(!modifier->pNext && !modifier->drmFormatModifier && modifier->drmFormatModifierPlaneCount == 1);
        const VkSubresourceLayout *plane = modifier->pPlaneLayouts;
        assert(!plane->offset && !plane->size && plane->rowPitch == 256 && !plane->arrayPitch && !plane->depthPitch);
    } else {
        assert(create->tiling == VK_IMAGE_TILING_LINEAR && !external->pNext);
    }
    creates++;
    if (fault == CREATE_FAIL) return VK_ERROR_FORMAT_NOT_SUPPORTED;
    *out = &handles[0];
    return VK_SUCCESS;
}

static VkResult pvkBindImageMemory(VkDevice device, VkImage image, VkDeviceMemory memory, VkDeviceSize offset)
{
    assert(device == g_dev && image == (VkImage)&handles[0] && memory == (VkDeviceMemory)&handles[2]);
    assert(!offset && layouts && requirements);
    binds++;
    return fault == BIND_FAIL ? VK_ERROR_OUT_OF_DEVICE_MEMORY : VK_SUCCESS;
}

static VkResult nvmtl_opaque_CreateImageView(VkDevice device, const VkImageViewCreateInfo *view,
    const VkAllocationCallbacks *allocator, void **out)
{
    assert(device == g_dev && !allocator && binds);
    assert(view->sType == VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO && view->image == (VkImage)&handles[0]);
    assert(view->format == VK_FORMAT_B8G8R8A8_UNORM && view->viewType == VK_IMAGE_VIEW_TYPE_2D);
    assert(view->subresourceRange.aspectMask == VK_IMAGE_ASPECT_COLOR_BIT && view->subresourceRange.levelCount == 1);
    views++;
    if (fault == VIEW_FAIL) return VK_ERROR_OUT_OF_HOST_MEMORY;
    *out = &handles[1];
    return VK_SUCCESS;
}

static void nvmtl_failed_image(nvk_image *image)
{
    if (image->img) destroys++;
    assert(!image->mem || (image->placed && image->mem == &handles[2]));
    memset(image, 0, sizeof *image);
}

static void nvmtl_commit_image(nvk_image *image)
{
    assert(image->placed && image->mem == &handles[2] && image->view == &handles[1]);
    commits++;
}

#include "build34_dcn_external_alias.h"

int main(void)
{
    const nvk_buffer host = {.buf = &handles[3], .mem = &handles[2], .map = &handles[4],
        .imported = 1, .dcn_host_allocation = 1, .size = 8192, .alloc = 8192, .htype = 2};
    nvk_image out;
    for (g_linmod = 0; g_linmod <= 1; g_linmod++) {
        fetch = g_linmod;
        fault = OK;
        assert(!nvmtl_dcn_create_render_alias(64, 32, 256, &host, &out));
        assert(out.layout == VK_IMAGE_LAYOUT_UNDEFINED && out.usage == expected_usage() && !out.storage && !out.vpair);
        assert(out.dcn_attachment.external_host && out.dcn_attachment.image == &handles[0]);
        assert(out.dcn_attachment.memory == host.mem && out.dcn_attachment.buffer == host.buf);
        assert(out.dcn_attachment.bind_bytes == host.size && !out.dcn_attachment.surface);
        nvmtl_dcn_set_surface(&out.dcn_attachment, &handles[5], 0, 0, NVMTL_DCN_BGRA, 64, 32, 256, 8192);
        assert(out.dcn_attachment.surface == &handles[5] && out.dcn_attachment.external_host);
    }
    assert(queries == 2 && creates == 2 && modifiers == 1 && commits == 2 && !destroys);

    g_linmod = 1;
    for (fault = NO_GET_FORMAT; fault <= VIEW_FAIL; fault++) {
        const unsigned base_destroys = destroys, base_binds = binds, base_creates = creates;
        assert(nvmtl_dcn_create_render_alias(64, 32, 256, &host, &out) == -1);
        assert(!out.img && !out.mem && !out.view && !out.dcn_attachment.external_host && commits == 2);
        assert(creates == base_creates + (fault >= CREATE_FAIL));
        assert(destroys == base_destroys + (fault > CREATE_FAIL));
        assert(binds == base_binds + (fault >= BIND_FAIL));
    }

    const unsigned base_queries = queries;
    fault = OK;
    nvk_buffer wrong_origin = host;
    wrong_origin.dcn_host_allocation = 0;
    assert(nvmtl_dcn_create_render_alias(64, 32, 256, &wrong_origin, &out) == -1);
    assert(nvmtl_dcn_create_render_alias(64, 32, 224, &host, &out) == -1);
    assert(nvmtl_dcn_create_render_alias(64, 33, 256, &host, &out) == -1);
    assert(nvmtl_dcn_create_render_alias(64, 32, 0, &host, &out) == -1);
    assert(queries == base_queries);
    return 0;
}
