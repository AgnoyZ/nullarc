"""Carry the exact RADV writer through one retained build34 submission part."""

import build34_dcn_render_write_stage as render


INPUTS = render.INPUTS


def stage(inputs):
    sources = render.stage(inputs)

    def replace(name, old, new):
        if sources[name].count(old) != 1:
            raise ValueError(f"Build34 plugin part anchor drift: {name}: {old[:75]}")
        sources[name] = sources[name].replace(old, new)

    header, vk, events = "nvmtl_vk.h", "nvmtl_vk.c", "NVMTLEventSync.m"
    replace(header, '#include "build34_dcn_render_write.h"\n',
            '#include "build34_dcn_render_write.h"\n#include "build34_dcn_part.h"\n')
    replace(header, "                 nvmtl_dcn_observation dcn_completed;\n",
            "                 nvmtl_dcn_observation dcn_completed;\n"
            "                 unsigned dcn_part_held;\n"
            "                 struct build34_dcn_part_writer dcn_writer;\n")
    replace(vk, "static void *g_lib;\n", """static void *g_lib;
typedef VkResult (*nvmtl_dcn_submit_fn)(PFN_vkQueueSubmit, VkQueue, const VkSubmitInfo *, VkFence,
    const struct build34_dcn_part_target *, struct build34_dcn_part_writer *);
typedef bool (*nvmtl_dcn_complete_fn)(VkQueue, const struct build34_dcn_part_target *,
    const struct build34_dcn_part_writer *);
static nvmtl_dcn_submit_fn nvmtl_dcn_submit_part;
static nvmtl_dcn_complete_fn nvmtl_dcn_complete_part;
""")
    replace(vk, '            pnvk_sparse = (int (*)(void))dlsym(g_lib, "nvmtl_nvk_sparse_bind_v1");\n',
            '            pnvk_sparse = (int (*)(void))dlsym(g_lib, "nvmtl_nvk_sparse_bind_v1");\n'
            "            if (nvmtl_vk_vendor() == 0x1002) {\n"
            '                nvmtl_dcn_submit_part = (nvmtl_dcn_submit_fn)dlsym(g_lib, "build34_dcn_queue_submit_v1");\n'
            '                nvmtl_dcn_complete_part = (nvmtl_dcn_complete_fn)dlsym(g_lib, "build34_dcn_queue_complete_v1");\n'
            "            }\n")
    replace(vk, "    c->dcn_recording = (nvmtl_dcn_recording){0};\n",
            "    c->dcn_recording = (nvmtl_dcn_recording){0};\n"
            "    c->dcn_part_held = 0;\n    c->dcn_writer = (struct build34_dcn_part_writer){0};\n")
    replace(vk, "    nvmtl_dcn_observation dcn_submitted;\n", """    nvmtl_dcn_observation dcn_submitted;
    struct build34_dcn_part_target dcn_target;
    struct build34_dcn_part_writer dcn_writer;
""")
    replace(vk, "    if (c) c->dcn_completed = (nvmtl_dcn_observation){0};\n", """    if (c) {
        c->dcn_completed = (nvmtl_dcn_observation){0};
        c->dcn_writer = (struct build34_dcn_part_writer){0};
    }
""")
    replace(vk, "    result = g_state == 1 ? pvkQueueSubmit(g_queue, 1, &si, fence) : VK_ERROR_DEVICE_LOST;\n",
            """    const nvmtl_dcn_attachment *attachment = &c->dcn_recording.recorded;
    if (g_state == 1 && ncb == 1 && c->dcn_part_held && nvmtl_dcn_submit_part && nvmtl_dcn_complete_part &&
        !c->in_rp && !c->encoding_error && !c->skipped && !c->dcn_recording.open.surface &&
        !c->dcn_recording.ambiguous && nvmtl_dcn_submit_serial != UINT64_MAX &&
        attachment->surface && attachment->external_host && attachment->host) {
        f->dcn_target = (struct build34_dcn_part_target){attachment->image, attachment->view,
            attachment->memory, attachment->host, attachment->import_bytes, attachment->bind_bytes,
            attachment->pitch, attachment->width, attachment->height};
        result = nvmtl_dcn_submit_part(pvkQueueSubmit, g_queue, &si, fence, &f->dcn_target, &f->dcn_writer);
    } else {
        result = g_state == 1 ? pvkQueueSubmit(g_queue, 1, &si, fence) : VK_ERROR_DEVICE_LOST;
    }
""")
    replace(vk, "    nvmtl_cmd_retire(c);\n    pt[7] = nvmtl_perf_now();\n", """    struct build34_dcn_part_writer completed_writer = {0};
    if (f->dcn_submitted.serial && f->dcn_writer.recording && !pthread_mutex_trylock(&nvmtl_submit_mutex)) {
        if (g_state == 1 && nvmtl_dcn_complete_part(g_queue, &f->dcn_target, &f->dcn_writer))
            completed_writer = f->dcn_writer;
        pthread_mutex_unlock(&nvmtl_submit_mutex);
    }
    f->dcn_writer = (struct build34_dcn_part_writer){0};
    f->dcn_target = (struct build34_dcn_part_target){0};
    nvmtl_cmd_retire(c);
    c->dcn_writer = completed_writer;
    pt[7] = nvmtl_perf_now();
""")

    replace(events, "    nvmtl_dcn_observation landedAttachment;\n",
            "    nvmtl_dcn_observation landedAttachment;\n    struct build34_dcn_part_writer landedWriter;\n")
    replace(events, """static void nvmtl_dcn_part_landed(NVMTLSubmissionPart *part, BOOL published) {
    const nvmtl_dcn_observation observed = part->commands.dcn_completed;
    part->commands.dcn_completed = (nvmtl_dcn_observation){0};
    part->landedAttachment = (nvmtl_dcn_observation){0};
    if (!published || !observed.serial) return;
    for (NVMTLTexture *texture in part->surfaces) {""", """static NVMTLTexture *nvmtl_dcn_part_texture(NVMTLSubmissionPart *part, const nvmtl_dcn_attachment *attachment) {
    NVMTLTexture *match = nil;
    for (NVMTLTexture *texture in part->surfaces) {""")
    replace(events, """        if (texture->_parent || !texture->_surfOwned || !texture->_hostOn || texture->_hostCopy ||
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
""", """        if (texture->_parent || !texture->_surfOwned || !texture->_hostOn || texture->_hostCopy ||
            texture->_vramOn || texture->_plane || texture->_surf != attachment->surface)
            continue;
        if (!nvmtl_dcn_same_attachment(attachment, &texture->_i.dcn_attachment) ||
            texture->_i.img != attachment->image || texture->_i.view != attachment->view ||
            texture->_i.mem != attachment->memory || texture->_hostBuf.mem != attachment->memory ||
            texture->_hostBuf.buf != attachment->buffer || !texture->_hostBuf.imported ||
            texture->_hostBuf.moff || texture->_hostBuf.size != attachment->import_bytes ||
            texture->_hostBuf.map != IOSurfaceGetBaseAddress(texture->_surf) ||
            (attachment->external_host && (!texture->_i.placed || !texture->_hostBuf.dcn_host_allocation ||
                                           texture->_hostBuf.map != attachment->host)))
            continue;
        if (match) return nil;
        match = texture;
    }
    return match;
}
static void nvmtl_dcn_part_prepare(NVMTLSubmissionPart *part) {
    const nvmtl_dcn_attachment *attachment = &part->commands.dcn_recording.recorded;
    part->commands.dcn_part_held = attachment->external_host && attachment->host &&
        nvmtl_dcn_part_texture(part, attachment) != nil;
}
static void nvmtl_dcn_part_landed(NVMTLSubmissionPart *part, BOOL published) {
    const nvmtl_dcn_observation observed = part->commands.dcn_completed;
    const struct build34_dcn_part_writer writer = part->commands.dcn_writer;
    part->commands.dcn_completed = (nvmtl_dcn_observation){0};
    part->commands.dcn_writer = (struct build34_dcn_part_writer){0};
    part->landedAttachment = (nvmtl_dcn_observation){0};
    part->landedWriter = (struct build34_dcn_part_writer){0};
    if (!published || !observed.serial || !nvmtl_dcn_part_texture(part, &observed.attachment)) return;
    part->landedAttachment = observed;
    part->landedWriter = writer;
}
""")
    replace(events, "        const int r = nvmtl_vk_submit_begin(&part->commands, f);\n",
            "        nvmtl_dcn_part_prepare(part);\n        const int r = nvmtl_vk_submit_begin(&part->commands, f);\n")
    replace(events, "            result = nvmtl_vk_submit_wait(&part->commands);\n",
            "            nvmtl_dcn_part_prepare(part);\n            result = nvmtl_vk_submit_wait(&part->commands);\n")
    return sources
