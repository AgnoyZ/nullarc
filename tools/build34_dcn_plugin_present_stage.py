"""Offer a single landed WindowServer attachment before retiring the part."""

import build34_dcn_plugin_part_stage as part
from build34_exact_submit import once


INPUTS = part.INPUTS


def stage(inputs):
    sources = part.stage(inputs)

    def replace(name, old, new):
        sources[name] = once(sources[name], old, new)

    vk, header, events = 'nvmtl_vk.c', 'nvmtl_vk.h', 'NVMTLEventSync.m'
    replace(header, 'uint16_t nvmtl_vk_vendor(void);\n',
            'uint16_t nvmtl_vk_vendor(void);\n'
            'void nvmtl_vk_dcn_offer_present(uint32_t surface, const struct build34_dcn_part_writer *);\n')
    replace(vk, 'static nvmtl_dcn_complete_fn nvmtl_dcn_complete_part;\n',
            'static nvmtl_dcn_complete_fn nvmtl_dcn_complete_part;\n'
            'typedef bool (*nvmtl_dcn_offer_fn)(VkQueue, uint32_t, const struct build34_dcn_part_writer *);\n'
            'static nvmtl_dcn_offer_fn nvmtl_dcn_offer_part;\n')
    anchor = '                nvmtl_dcn_complete_part = (nvmtl_dcn_complete_fn)dlsym(g_lib, "build34_dcn_queue_complete_v1");\n'
    replace(vk, anchor, anchor + '                nvmtl_dcn_offer_part = (nvmtl_dcn_offer_fn)dlsym(g_lib, "build34_dcn_queue_offer_v1");\n')
    anchor = 'int nvmtl_vk_accel_surface_wait(void)\n'
    replace(vk, anchor, '''void nvmtl_vk_dcn_offer_present(uint32_t surface, const struct build34_dcn_part_writer *writer)
{
    if (!surface || !writer || !writer->recording || pthread_mutex_trylock(&nvmtl_submit_mutex))
        return;
    if (g_state == 1 && nvmtl_dcn_offer_part) (void)nvmtl_dcn_offer_part(g_queue, surface, writer);
    pthread_mutex_unlock(&nvmtl_submit_mutex);
}

''' + anchor)
    anchor = '    _parts[_nextPart++] = [NSNull null];\n'
    replace(events, anchor, '''    if (_parts.count == 1 && part->landedWriter.recording &&
        getprogname() && !strcmp(getprogname(), "WindowServer")) {
        NVMTLTexture *attachment = nvmtl_dcn_part_texture(part, &part->landedAttachment.attachment);
        NVMTLTexture *drawable = _present ? (_present->_parent ?: _present) : nil;
        if (attachment && ((_presentations.count == 0 && !drawable) ||
                           (_presentations.count == 1 && attachment == drawable)))
            nvmtl_vk_dcn_offer_present((uint32_t)IOSurfaceGetID(attachment->_surf), &part->landedWriter);
    }
''' + anchor)
    return sources
