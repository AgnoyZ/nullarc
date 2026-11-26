"""Derive the offline build34 plugin attachment observation stage."""

import hashlib


INPUTS = {
    "NVMTLDevice.m": "5cc8292a4f3b335393317ca413c67e723dfd4591c3e9d8d75b77d9a40163b1df",
    "NVMTLObjects.m": "38dc8070cddb8368115ad41aec365a3463f59b27323b5b277238e74a5de50b34",
    "NVMTLEventSync.m": "6b73c8cbf06d84499398355d3d776a0413340d8d49950265420612e9cbe1a95b",
    "nvmtl_vk.c": "436abdc1f9e1435887de871858cfceb62bf1f33abcb46d61840197153c86c86c",
    "nvmtl_vk.h": "bc1eaebd516784f165c580d66780689cb7cbb5c1e5d0be572eeadfb635ee2cb0",
}


def stage(inputs):
    sources = {}
    for name, digest in INPUTS.items():
        data = inputs.get(name, b"")
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"Build34 DCN attachment source drift: {name}")
        sources[name] = data.decode()

    def replace(name, old, new):
        if sources[name].count(old) != 1:
            raise ValueError(f"Build34 DCN attachment anchor drift: {name}: {old[:75]}")
        sources[name] = sources[name].replace(old, new)

    header = "nvmtl_vk.h"
    replace(header, '#include "nvmtl_sample_positions.h"\n',
            '#include "nvmtl_sample_positions.h"\n#include "build34_dcn_render_write.h"\n')
    replace(header, "htype; /* its memory type + 1 when known (0 = unknown) */ } nvk_buffer;",
            "htype; /* its memory type + 1 when known (0 = unknown) */ unsigned dcn_host_allocation; } nvk_buffer;")
    replace(header, "uint64_t up_token; } nvk_image;",
            "uint64_t up_token; nvmtl_dcn_attachment dcn_attachment; } nvk_image;")
    replace(header, "               } nvk_cmdbuf;",
            "                 nvmtl_dcn_recording dcn_recording;\n"
            "                 nvmtl_dcn_observation dcn_completed;\n"
            "               } nvk_cmdbuf;")
    replace(header, "col_layer[NVMTL_NCOL];  } nvk_pass;",
            "col_layer[NVMTL_NCOL]; uint32_t dcn_clear_store; } nvk_pass;")

    replace("NVMTLDevice.m",
            "                    t->_hostBuf = hb; t->_hostOn = YES;",
            """                    nvmtl_dcn_set_surface(&t->_i.dcn_attachment, surf, plane, IOSurfaceGetPlaneCount(surf),
                        IOSurfaceGetPixelFormat(surf), IOSurfaceGetWidth(surf), sh, row, alloc);
                    t->_hostBuf = hb; t->_hostOn = YES;""")
    replace("NVMTLObjects.m", "        MTLStoreAction sa = ca.storeAction;\n",
            """        MTLStoreAction sa = ca.storeAction;
        if (ca.loadAction == MTLLoadActionClear && sa == MTLStoreActionStore && !rx &&
            !ca.level && !ca.slice && !ca.depthPlane && NL == 1)
            _pass.dcn_clear_store |= 1u << i;
""")

    vk = "nvmtl_vk.c"
    replace(vk, "    out->map = ptr; out->alloc = size; out->imported = 1; out->htype = mt + 1;\n",
            "    out->map = ptr; out->alloc = size; out->imported = 1; out->htype = mt + 1;\n"
            "    out->dcn_host_allocation = mr.size && mr.size <= size;\n")
    replace(vk, "typedef struct { size_t off, len; } pool_range;",
            '#include "build34_dcn_external_alias.h"\n\n'
            "typedef struct { size_t off, len; } pool_range;")
    replace(vk, '    VKCK(nvmtl_opaque_CreateImageView(g_dev, &vci, NULL, &out->view), "vkCreateImageView(buffer texture)");\n',
            """    VKCK(nvmtl_opaque_CreateImageView(g_dev, &vci, NULL, &out->view), "vkCreateImageView(buffer texture)");
    if (b->imported && b->map && !b->placed && b->alloc == b->size && !at &&
        !a8 && bpp == 4 && vkfmt == VK_FORMAT_B8G8R8A8_UNORM &&
        (out->usage & VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT)) {
        PFN_vkGetImageSubresourceLayout get_layout = (PFN_vkGetImageSubresourceLayout)
            pvkGetInstanceProcAddr(g_inst, "vkGetImageSubresourceLayout");
        VkImageSubresource subresource = {
            g_linmod ? VK_IMAGE_ASPECT_MEMORY_PLANE_0_BIT_EXT : VK_IMAGE_ASPECT_COLOR_BIT, 0, 0 };
        VkSubresourceLayout actual = {0};
        if (get_layout) {
            get_layout(g_dev, (VkImage)out->img, &subresource, &actual);
            nvmtl_dcn_set_alias(&out->dcn_attachment, out->img, out->view, b->buf, out->mem,
                w, h, row_pitch, b->size, mr.size, actual.rowPitch, actual.offset, actual.size);
        }
    }
""")
    replace(vk, "    c->in_rp = 1;\n    for (uint32_t i = 0; i < NVMTL_NCOL; i++) c->fetchview[i]",
            """    c->in_rp = 1;
    for (uint32_t slot = 0; slot < ncol; ++slot) {
        if (!cf[slot]) continue;
        const nvk_image *image = ps->col[slot];
        if (!(ps->dcn_clear_store & (1u << slot)) || (ps->load & NVMTL_LOAD_COLOUR(slot)) ||
            cf[slot] != VK_FORMAT_B8G8R8A8_UNORM || image->fmt != cf[slot] ||
            !(image->usage & VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT) || p->samples > 1 || image->samples > 1 ||
            ps->layers > 1 || image->mips != 1 || image->layers != 1 || image->mtl_type != 2 ||
            ps->col_level[slot] || ps->col_layer[slot] || ps->res[slot] ||
            ps->colw[slot] != ps->w || ps->colh[slot] != ps->h)
            continue;
        nvmtl_dcn_record_attachment(&c->dcn_recording, &image->dcn_attachment, image->img,
            ps->colview[slot], image->mem, ps->w, ps->h);
    }
    for (uint32_t i = 0; i < NVMTL_NCOL; i++) c->fetchview[i]""")
    replace(vk, "    pvkCmdEndRenderPass(c->cb); c->in_rp = 0;\n",
            "    pvkCmdEndRenderPass(c->cb); c->in_rp = 0;\n"
            "    nvmtl_dcn_end_pass(&c->dcn_recording);\n")
    replace(vk, "static void nvmtl_cmd_retire(nvk_cmdbuf *c)\n{\n",
            "static void nvmtl_cmd_retire(nvk_cmdbuf *c)\n{\n"
            "    c->dcn_recording = (nvmtl_dcn_recording){0};\n"
            "    c->dcn_completed = (nvmtl_dcn_observation){0};\n")
    replace(vk, "struct nvmtl_inflight { nvk_cmdbuf *c; VkFence fence; nvmtl_prologue pre; uint64_t pt[8]; };",
            """struct nvmtl_inflight { nvk_cmdbuf *c; VkFence fence; nvmtl_prologue pre; uint64_t pt[8];
    nvmtl_dcn_observation dcn_submitted;
};
static uint64_t nvmtl_dcn_submit_serial;""")
    replace(vk, "    memset(f, 0, sizeof *f); f->c = c;\n",
            "    memset(f, 0, sizeof *f); f->c = c;\n"
            "    if (c) c->dcn_completed = (nvmtl_dcn_observation){0};\n")
    replace(vk, "    result = g_state == 1 ? pvkQueueSubmit(g_queue, 1, &si, fence) : VK_ERROR_DEVICE_LOST;\n",
            """    result = g_state == 1 ? pvkQueueSubmit(g_queue, 1, &si, fence) : VK_ERROR_DEVICE_LOST;
    if (result == VK_SUCCESS && !c->in_rp && !c->encoding_error && !c->skipped)
        f->dcn_submitted = nvmtl_dcn_submit(&c->dcn_recording, &nvmtl_dcn_submit_serial);
""")
    replace(vk, "    nvmtl_perf_submit(perf_sets, pt);\n    return 0;\n",
            "    nvmtl_perf_submit(perf_sets, pt);\n"
            "    c->dcn_completed = f->dcn_submitted;\n"
            "    f->dcn_submitted = (nvmtl_dcn_observation){0};\n    return 0;\n")

    events = "NVMTLEventSync.m"
    replace(events, "    BOOL copyInputsPrepared, hasHostCopies;\n",
            "    BOOL copyInputsPrepared, hasHostCopies;\n"
            "    nvmtl_dcn_observation landedAttachment;\n")
    replace(events, "static _Atomic unsigned gsub_inflight;",
            """static void nvmtl_dcn_part_landed(NVMTLSubmissionPart *part, BOOL published) {
    const nvmtl_dcn_observation observed = part->commands.dcn_completed;
    part->commands.dcn_completed = (nvmtl_dcn_observation){0};
    part->landedAttachment = (nvmtl_dcn_observation){0};
    if (!published || !observed.serial) return;
    for (NVMTLTexture *texture in part->surfaces) {
        if (texture->_parent || !texture->_surfOwned || !texture->_hostOn || texture->_hostCopy ||
            texture->_vramOn || texture->_plane || texture->_surf != observed.attachment.surface)
            continue;
        if (!nvmtl_dcn_same_attachment(&observed.attachment, &texture->_i.dcn_attachment) ||
            texture->_i.img != observed.attachment.image || texture->_i.view != observed.attachment.view ||
            texture->_i.mem != observed.attachment.memory || texture->_hostBuf.mem != observed.attachment.memory ||
            texture->_hostBuf.buf != observed.attachment.buffer || !texture->_hostBuf.imported ||
            texture->_hostBuf.moff || texture->_hostBuf.size != observed.attachment.import_bytes ||
            texture->_hostBuf.map != IOSurfaceGetBaseAddress(texture->_surf))
            continue;
        if (part->landedAttachment.serial) { part->landedAttachment = (nvmtl_dcn_observation){0}; return; }
        part->landedAttachment = observed;
    }
}
static _Atomic unsigned gsub_inflight;""")
    replace(events, "        if (!published) {\n            [self nvmtlFinishExecution:",
            "        nvmtl_dcn_part_landed(part, published);\n"
            "        if (!published) {\n            [self nvmtlFinishExecution:")
    return sources
