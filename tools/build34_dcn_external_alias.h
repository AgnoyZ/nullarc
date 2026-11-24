#pragma once

static int nvmtl_dcn_single_plane_linear_modifier(VkFormat format)
{
    PFN_vkGetPhysicalDeviceFormatProperties2 get_modifiers = (PFN_vkGetPhysicalDeviceFormatProperties2)
        pvkGetInstanceProcAddr(g_inst, "vkGetPhysicalDeviceFormatProperties2");
    if (!get_modifiers)
        return 0;
    VkDrmFormatModifierPropertiesEXT entries[64] = {0};
    const uint32_t capacity = sizeof entries / sizeof entries[0];
    VkDrmFormatModifierPropertiesListEXT list = { VK_STRUCTURE_TYPE_DRM_FORMAT_MODIFIER_PROPERTIES_LIST_EXT,
        NULL, capacity, entries };
    VkFormatProperties2 properties = { .sType = VK_STRUCTURE_TYPE_FORMAT_PROPERTIES_2, .pNext = &list };
    get_modifiers(g_pdev, format, &properties);
    if (list.drmFormatModifierCount > capacity)
        return 0;
    for (uint32_t index = 0; index < list.drmFormatModifierCount; index++)
        if (!entries[index].drmFormatModifier && entries[index].drmFormatModifierPlaneCount == 1)
            return 1;
    return 0;
}

static int nvmtl_dcn_create_render_alias_body(uint32_t width, uint32_t height, size_t pitch,
    const nvk_buffer *host, nvk_image *out)
{
    if (nvmtl_vk_init() || !g_host_import || !host || !host->dcn_host_allocation ||
        !host->buf || !host->mem || !host->map || !host->imported || host->placed || host->moff ||
        host->size != host->alloc || host->size > NVMTL_DCN_MAX_ATTACHMENT_BYTES ||
        (host->size & (NVMTL_DCN_PAGE_BYTES - 1)) || host->htype < 1 ||
        (uint32_t)host->htype > g_memp.memoryTypeCount || host->htype > 32 ||
        !width || !height || pitch < (uint64_t)width * 4 || pitch > UINT32_MAX ||
        (pitch % (g_linmod ? 32 : 4)) || height > host->size / pitch)
        return -1;

    PFN_vkGetPhysicalDeviceImageFormatProperties2 get_format = (PFN_vkGetPhysicalDeviceImageFormatProperties2)
        pvkGetInstanceProcAddr(g_inst, "vkGetPhysicalDeviceImageFormatProperties2");
    PFN_vkGetImageMemoryRequirements2 get_requirements = (PFN_vkGetImageMemoryRequirements2)
        pvkGetDeviceProcAddr(g_dev, "vkGetImageMemoryRequirements2");
    PFN_vkGetImageSubresourceLayout get_layout = (PFN_vkGetImageSubresourceLayout)
        pvkGetDeviceProcAddr(g_dev, "vkGetImageSubresourceLayout");
    if (!get_format || !get_requirements || !get_layout)
        return -1;

    const VkExternalMemoryHandleTypeFlagBits handle = VK_EXTERNAL_MEMORY_HANDLE_TYPE_HOST_ALLOCATION_BIT_EXT;
    const VkImageTiling tiling = g_linmod ? VK_IMAGE_TILING_DRM_FORMAT_MODIFIER_EXT : VK_IMAGE_TILING_LINEAR;
    const VkImageUsageFlags usage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT |
        (nvmtl_fbfetch_on() ? VK_IMAGE_USAGE_INPUT_ATTACHMENT_BIT : 0);
    const VkPhysicalDeviceImageDrmFormatModifierInfoEXT query_modifier = {
        VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_IMAGE_DRM_FORMAT_MODIFIER_INFO_EXT, NULL, 0, VK_SHARING_MODE_EXCLUSIVE, 0, NULL };
    const VkPhysicalDeviceExternalImageFormatInfo query_external = {
        VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_EXTERNAL_IMAGE_FORMAT_INFO, g_linmod ? &query_modifier : NULL, handle };
    const VkPhysicalDeviceImageFormatInfo2 query = { VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_IMAGE_FORMAT_INFO_2,
        &query_external, VK_FORMAT_B8G8R8A8_UNORM, VK_IMAGE_TYPE_2D, tiling, usage, 0 };
    VkExternalImageFormatProperties external_props = { .sType = VK_STRUCTURE_TYPE_EXTERNAL_IMAGE_FORMAT_PROPERTIES };
    VkImageFormatProperties2 format_props = { .sType = VK_STRUCTURE_TYPE_IMAGE_FORMAT_PROPERTIES_2, .pNext = &external_props };
    if (get_format(g_pdev, &query, &format_props) != VK_SUCCESS ||
        (g_linmod && !nvmtl_dcn_single_plane_linear_modifier(query.format)))
        return -1;
    const VkExternalMemoryProperties *external = &external_props.externalMemoryProperties;
    const VkImageFormatProperties *limits = &format_props.imageFormatProperties;
    if (!(external->compatibleHandleTypes & handle) ||
        !(external->externalMemoryFeatures & VK_EXTERNAL_MEMORY_FEATURE_IMPORTABLE_BIT) ||
        (external->externalMemoryFeatures & VK_EXTERNAL_MEMORY_FEATURE_DEDICATED_ONLY_BIT) ||
        width > limits->maxExtent.width || height > limits->maxExtent.height || !limits->maxExtent.depth ||
        !limits->maxMipLevels || !limits->maxArrayLayers || !(limits->sampleCounts & VK_SAMPLE_COUNT_1_BIT) ||
        (uint64_t)height * pitch > limits->maxResourceSize)
        return -1;

    const VkSubresourceLayout plane = { 0, 0, pitch, 0, 0 };
    const VkImageDrmFormatModifierExplicitCreateInfoEXT create_modifier = {
        VK_STRUCTURE_TYPE_IMAGE_DRM_FORMAT_MODIFIER_EXPLICIT_CREATE_INFO_EXT, NULL, 0, 1, &plane };
    const VkExternalMemoryImageCreateInfo create_external = {
        VK_STRUCTURE_TYPE_EXTERNAL_MEMORY_IMAGE_CREATE_INFO, g_linmod ? &create_modifier : NULL, handle };
    const VkImageCreateInfo create = { VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO, &create_external, query.flags,
        query.type, query.format, { width, height, 1 }, 1, 1, VK_SAMPLE_COUNT_1_BIT, query.tiling, query.usage,
        VK_SHARING_MODE_EXCLUSIVE, 0, NULL, VK_IMAGE_LAYOUT_UNDEFINED };
    if (nvmtl_opaque_CreateImage(g_dev, &create, NULL, &out->img) != VK_SUCCESS)
        return -1;

    const VkImageMemoryRequirementsInfo2 image_info = { VK_STRUCTURE_TYPE_IMAGE_MEMORY_REQUIREMENTS_INFO_2,
        NULL, out->img };
    VkMemoryDedicatedRequirements dedicated = { .sType = VK_STRUCTURE_TYPE_MEMORY_DEDICATED_REQUIREMENTS };
    VkMemoryRequirements2 requirements = { .sType = VK_STRUCTURE_TYPE_MEMORY_REQUIREMENTS_2, .pNext = &dedicated };
    get_requirements(g_dev, &image_info, &requirements);
    const VkMemoryRequirements *memory = &requirements.memoryRequirements;
    if (dedicated.requiresDedicatedAllocation || !memory->size || !memory->alignment ||
        memory->size > host->alloc || memory->size > limits->maxResourceSize ||
        !(memory->memoryTypeBits & (1u << (host->htype - 1))))
        return -1;

    const VkImageSubresource subresource = {
        g_linmod ? VK_IMAGE_ASPECT_MEMORY_PLANE_0_BIT_EXT : VK_IMAGE_ASPECT_COLOR_BIT, 0, 0 };
    VkSubresourceLayout layout = {0};
    get_layout(g_dev, out->img, &subresource, &layout);
    if (layout.offset || layout.rowPitch != pitch || layout.size > memory->size ||
        layout.size < (height - 1) * (uint64_t)pitch + (uint64_t)width * 4)
        return -1;

    if (pvkBindImageMemory(g_dev, out->img, host->mem, 0) != VK_SUCCESS)
        return -1;
    out->mem = host->mem;
    out->placed = 1;
    const VkImageViewCreateInfo view = { VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO, NULL, 0, out->img,
        VK_IMAGE_VIEW_TYPE_2D, query.format, {0}, { VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1 } };
    if (nvmtl_opaque_CreateImageView(g_dev, &view, NULL, &out->view) != VK_SUCCESS)
        return -1;

    nvmtl_dcn_set_alias(&out->dcn_attachment, out->img, out->view, host->buf, out->mem,
        width, height, pitch, host->size, memory->size, layout.rowPitch, layout.offset, layout.size);
    if (!out->dcn_attachment.image)
        return -1;
    out->dcn_attachment.external_host = 1;
    out->dcn_attachment.host = host->map;
    out->w = width;
    out->h = height;
    out->fmt = query.format;
    out->bpp = 4;
    out->mips = out->layers = 1;
    out->mtl_type = 2;
    out->usage = usage;
    out->layout = create.initialLayout;
    return 0;
}

static int nvmtl_dcn_create_render_alias(uint32_t width, uint32_t height, size_t pitch,
    const nvk_buffer *host, nvk_image *out)
{
    nvk_image pending = {0};
    if (nvmtl_dcn_create_render_alias_body(width, height, pitch, host, &pending)) {
        nvmtl_failed_image(&pending);
        *out = (nvk_image){0};
        return -1;
    }
    nvmtl_commit_image(&pending);
    *out = pending;
    return 0;
}
