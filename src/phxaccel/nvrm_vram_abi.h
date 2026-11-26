/*
 * NullMoth NVIDIA driver for macOS
 * Copyright (c) 2026 NullMoth Systems.
 * SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
 */

#pragma once

#define NVRM_VRAM_ABI_VERSION 2u
#define NVRM_VRAM_FN_ALLOC    "nvAllocVram"
#define NVRM_VRAM_FN_FREE     "nvFreeVram"

#define NVRM_VRAM_FN_SCANOUT  "nvScanoutInfo"

#define PHX_FB_ABI_ZEROCOPY_VERSION 1u
#define PHX_FB_FN_ZEROCOPY_FLIP     "phxZeroCopyFlip"
#define PHX_FB_FN_ZEROCOPY_HOME     "phxZeroCopyHome"

#define NVRM_VRAM_BAR1_BUDGET (192ull * 1024ull * 1024ull)

struct NVRMVramRequest {
    unsigned int       version;
    unsigned int       flags;
    unsigned long long size;
    unsigned long long actualSize;
    unsigned long long phys;
    void              *kva;
    void              *handle;
    unsigned long long mappedTotal;
    unsigned int width, height, pitch;
    unsigned long long allocationCookie;
};

struct PhxZeroCopyFlipRequest {
    unsigned int version;
    unsigned int flags;
    unsigned int surfaceID;
    unsigned int pixelFormat;
    unsigned int width;
    unsigned int height;
    unsigned int pitch;
    int status;
    void *surface;
    void *memoryDescriptor;
};
