#pragma once

#include <stdint.h>

#define NVMTL_DCN_MAX_ATTACHMENT_BYTES (64ull * 1024 * 1024)
#define NVMTL_DCN_PAGE_BYTES 4096ull
#define NVMTL_DCN_BGRA 0x42475241u

typedef struct {
    const void *surface, *image, *view, *buffer, *memory;
    uint32_t width, height;
    uint64_t pitch, footprint, import_bytes, bind_bytes;
    unsigned external_host;
} nvmtl_dcn_attachment;

typedef struct {
    nvmtl_dcn_attachment open, recorded;
    unsigned ambiguous;
} nvmtl_dcn_recording;

typedef struct {
    nvmtl_dcn_attachment attachment;
    uint64_t serial;
} nvmtl_dcn_observation;

static inline void nvmtl_dcn_set_alias(nvmtl_dcn_attachment *out,
    const void *image, const void *view, const void *buffer, const void *memory,
    uint32_t width, uint32_t height, uint64_t pitch, uint64_t import_bytes,
    uint64_t bind_bytes, uint64_t actual_pitch, uint64_t actual_offset, uint64_t actual_bytes)
{
    *out = (nvmtl_dcn_attachment){0};
    const uint64_t pixel_bytes = (uint64_t)width * 4;
    if (!image || !view || !buffer || !memory || !width || !height ||
        pitch < pixel_bytes || (pitch & 3) || pitch != actual_pitch || actual_offset ||
        import_bytes > NVMTL_DCN_MAX_ATTACHMENT_BYTES || (import_bytes & (NVMTL_DCN_PAGE_BYTES - 1)) ||
        height > import_bytes / pitch || bind_bytes > import_bytes)
        return;
    const uint64_t footprint = pitch * height;
    if (actual_bytes > bind_bytes || actual_bytes < footprint - pitch + pixel_bytes)
        return;
    *out = (nvmtl_dcn_attachment){0, image, view, buffer, memory,
        width, height, pitch, footprint, import_bytes, bind_bytes, 0};
}

static inline void nvmtl_dcn_set_surface(nvmtl_dcn_attachment *alias, const void *surface,
    uint64_t plane, uint64_t planes, uint32_t format, uint64_t width, uint64_t height,
    uint64_t pitch, uint64_t bytes)
{
    alias->surface = 0;
    if (!alias->image || !surface || plane || planes || format != NVMTL_DCN_BGRA ||
        width != alias->width || height != alias->height || pitch != alias->pitch ||
        bytes > alias->import_bytes || alias->bind_bytes > bytes)
        return;
    const uint64_t rounded = (alias->footprint + NVMTL_DCN_PAGE_BYTES - 1) & ~(NVMTL_DCN_PAGE_BYTES - 1);
    if (rounded <= bytes)
        alias->surface = surface;
}

static inline int nvmtl_dcn_same_attachment(const nvmtl_dcn_attachment *first,
    const nvmtl_dcn_attachment *second)
{
    return first->surface == second->surface && first->image == second->image &&
        first->view == second->view && first->buffer == second->buffer && first->memory == second->memory &&
        first->width == second->width && first->height == second->height && first->pitch == second->pitch &&
        first->footprint == second->footprint && first->import_bytes == second->import_bytes &&
        first->bind_bytes == second->bind_bytes && first->external_host == second->external_host;
}

static inline void nvmtl_dcn_record_attachment(nvmtl_dcn_recording *recording,
    const nvmtl_dcn_attachment *alias, const void *image, const void *view, const void *memory,
    uint32_t width, uint32_t height)
{
    if (recording->ambiguous || !alias->surface || alias->image != image || alias->view != view ||
        alias->memory != memory || width != alias->width || height != alias->height)
        return;
    if (recording->open.surface) {
        recording->ambiguous = 1;
        return;
    }
    recording->open = *alias;
}

static inline void nvmtl_dcn_end_pass(nvmtl_dcn_recording *recording)
{
    if (recording->open.surface && !recording->ambiguous) {
        if (recording->recorded.surface && !nvmtl_dcn_same_attachment(&recording->recorded, &recording->open))
            recording->ambiguous = 1;
        else
            recording->recorded = recording->open;
    }
    recording->open = (nvmtl_dcn_attachment){0};
}

static inline nvmtl_dcn_observation nvmtl_dcn_submit(const nvmtl_dcn_recording *recording,
    uint64_t *serial)
{
    if (recording->ambiguous || recording->open.surface || !recording->recorded.surface || *serial == UINT64_MAX)
        return (nvmtl_dcn_observation){0};
    return (nvmtl_dcn_observation){recording->recorded, ++*serial};
}
