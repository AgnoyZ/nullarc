/*
 * Copyright 2022 Advanced Micro Devices, Inc.
 *
 * Permission is hereby granted, free of charge, to any person obtaining a
 * copy of this software and associated documentation files (the "Software"),
 * to deal in the Software without restriction, including without limitation
 * the rights to use, copy, modify, merge, publish, distribute, sublicense,
 * and/or sell copies of the Software, and to permit persons to whom the
 * Software is furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
 * THE COPYRIGHT HOLDER(S) OR AUTHOR(S) BE LIABLE FOR ANY CLAIM, DAMAGES OR
 * OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
 * ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
 * OTHER DEALINGS IN THE SOFTWARE.
 *
*/

/* Shader array: libdrm 2.4.123, tests/amdgpu/shader_code_gfx11.h.
 * Packet construction below is an independent implementation of reviewed GFX11 state.
 * This is an unverified hardware experiment, not an initialization/ownership grant. */
#ifndef PHX_GFX11_SHADER_PROBE_H
#define PHX_GFX11_SHADER_PROBE_H
#define PHX_SHADER_PROBE_ARENA_BYTES 0x6000ull
#define PHX_SHADER_PROBE_OUTPUT_BYTES 1024u
#define PHX_SHADER_PROBE_PACKET_DWORDS 86u
static const uint32_t phxGfx11ClearShader[] = {
	0xB0802006, 0xBF840003, 0x360000FF, 0x000003FF,
	0x7E020205, 0x7E040206, 0x7E060207, 0xBF870004,
	0xD6460004, 0x04010C08, 0x7E000204, 0xE01C0000,
	0x80800004, 0xBFB60003, 0xBFB00000, 0xBF9F0000,
	0xBF9F0000, 0xBF9F0000, 0xBF9F0000, 0xBF9F0000,
	0xBF9F0000, 0xBF9F0000, 0xBF9F0000, 0xBF9F0000,
	0xBF9F0000, 0xBF9F0000, 0xBF9F0000, 0xBF9F0000,
	0xBF9F0000, 0xBF9F0000, 0xBF9F0000, 0xBF9F0000,
	0xBF9F0000, 0xBF9F0000, 0xBF9F0000, 0xBF9F0000,
	0xBF9F0000, 0xBF9F0000, 0xBF9F0000, 0xBF9F0000,
	0xBF9F0000, 0xBF9F0000, 0xBF9F0000, 0xBF9F0000,
	0xBF9F0000, 0xBF9F0000, 0xBF9F0000, 0xBF9F0000,
	0xBF9F0000, 0xBF9F0000, 0xBF9F0000, 0xBF9F0000,
	0xBF9F0000, 0xBF9F0000, 0xBF9F0000, 0xBF9F0000,
	0xBF9F0000, 0xBF9F0000, 0xBF9F0000, 0xBF9F0000,
	0xBF9F0000, 0xBF9F0000, 0xBF9F0000, 0xBF9F0000,
	0xBF9F0000, 0xBF9F0000, 0xBF9F0000, 0xBF9F0000,
	0xBF9F0000, 0xBF9F0000, 0xBF9F0000, 0xBF9F0000,
	0xBF9F0000, 0xBF9F0000, 0xBF9F0000, 0xBF9F0000,
	0xBF9F0000, 0xBF9F0000, 0xBF9F0000
};
static inline int phxShaderProbeLayoutValid(const struct PhxMesQueueLayout *scheduler,
    const struct PhxMesQueueLayout *work, const struct PhxGartLayout *gart, const struct PhxBootMemory *memory) {
    return phxMesQueueLayoutValid(scheduler, gart, memory) &&
        phxMesArenaLayoutValid(work, gart, memory, PHX_SHADER_PROBE_ARENA_BYTES) &&
        scheduler->doorbellIndex != work->doorbellIndex &&
        phxPspDisjoint(scheduler->arenaOffset, PHX_MES_QUEUE_ARENA_BYTES,
                      work->arenaOffset, PHX_SHADER_PROBE_ARENA_BYTES);
}
static inline unsigned phxGfx11ClearCommands(uint32_t *out, size_t capacity, uint64_t shader,
    uint64_t target, uint64_t fence, uint64_t completion, const uint32_t pattern[4]) {
    const uint64_t limit = 1ull << 48;
    if (!out || !pattern || capacity < PHX_SHADER_PROBE_PACKET_DWORDS || !completion ||
        !shader || (shader & 255) || !phxPspSpanFits(shader, 4096, limit) ||
        !target || (target & 15) || !phxPspSpanFits(target, PHX_SHADER_PROBE_OUTPUT_BYTES, limit) ||
        !fence || (fence & 7) || !phxPspSpanFits(fence, 8, limit) ||
        !phxPspDisjoint(shader, 4096, target, PHX_SHADER_PROBE_OUTPUT_BYTES)) return 0;
    const uint32_t packet[] = {
        /* MEC ACQUIRE_MEM: invalidate instruction/scalar/vector/L1/L2 caches, write back L2. */
        0xc0065800u, 0, 0xffffffffu, 0xff, 0, 0, 10, 0xc381,
        0xc0037602u, 0x204, 0, 0, 0,
        0xc0017602u, 0x218, 0,
        0xc0017602u, 0x222, 0,
        0xc0047602u, 0x224, 0, 0, 0, 0,
        0xc0017900u, 0x22a, 0,
        0xc0029b02u, 0x30000216, 0xffffffffu, 0xffffffffu,
        0xc0029b02u, 0x30000219, 0xffffffffu, 0xffffffffu,
        0xc0027602u, 0x20c, (uint32_t)(shader >> 8), (uint32_t)(shader >> 40),
        0xc0017602u, 0x212, 0x400c0041,
        0xc0017602u, 0x213, 0x90,
        0xc0017602u, 0x207, 64,
        0xc0017602u, 0x208, 1,
        0xc0017602u, 0x209, 1,
        0xc0017602u, 0x228, 0x3f0,
        0xc0047602u, 0x240, (uint32_t)target, (uint32_t)(target >> 32) | 0x100000u, 64, 0x1003dfac,
        0xc0047602u, 0x244, pattern[0], pattern[1], pattern[2], pattern[3],
        0xc0017602u, 0x215, 0,
        0xc0031502u, 1, 1, 1, 1,
        0xc0064900u, 0x06603514u, 0x40000000u, (uint32_t)fence, (uint32_t)(fence >> 32),
        (uint32_t)completion, (uint32_t)(completion >> 32), 0
    };
    if (sizeof(packet) / sizeof(packet[0]) != PHX_SHADER_PROBE_PACKET_DWORDS) return 0;
    memcpy(out, packet, sizeof(packet));
    return PHX_SHADER_PROBE_PACKET_DWORDS;
}
#endif
