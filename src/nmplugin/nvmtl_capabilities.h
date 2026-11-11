/* Downstream optional-feature contract. Existing component licence applies. */
#ifndef NVMTL_CAPABILITIES_H
#define NVMTL_CAPABILITIES_H
#include <stdint.h>
enum {
    NVMTL_TRANSLATOR_VISIBLE_REFS = 1u << 0,
    NVMTL_TRANSLATOR_LINK_VISIBLE = 1u << 1,
    NVMTL_TRANSLATOR_LINK_RUNTIME = 1u << 2,
    NVMTL_TRANSLATOR_LINK_EXTERNS = 1u << 3
};
enum nvmtl_optional_feature {
    NVMTL_CAP_FUNCTION_POINTERS, NVMTL_CAP_RENDER_FUNCTION_POINTERS,
    NVMTL_CAP_DYNAMIC_LIBRARIES, NVMTL_CAP_RENDER_DYNAMIC_LIBRARIES,
    NVMTL_CAP_BARYCENTRICS
};
static inline int nvmtl_capability_supported(enum nvmtl_optional_feature feature, int backend_ready, uint32_t translator) {
    if (!backend_ready) return 0;
    uint32_t required;
    switch (feature) {
        case NVMTL_CAP_FUNCTION_POINTERS:
        case NVMTL_CAP_RENDER_FUNCTION_POINTERS:
            required = NVMTL_TRANSLATOR_VISIBLE_REFS | NVMTL_TRANSLATOR_LINK_VISIBLE | NVMTL_TRANSLATOR_LINK_RUNTIME;
            break;
        case NVMTL_CAP_DYNAMIC_LIBRARIES:
        case NVMTL_CAP_RENDER_DYNAMIC_LIBRARIES:
            required = NVMTL_TRANSLATOR_LINK_EXTERNS;
            break;
        // The Vulkan device currently enables no fragment-shader-barycentric feature.
        case NVMTL_CAP_BARYCENTRICS: default: return 0;
    }
    return (translator & required) == required;
}
int nvmtl_vk_backend_ready(void);
uint32_t nvmtl_translation_capabilities(void);
#endif
