#include "nvmtl_capabilities.h"
#include <cassert>
#include <cstdint>
#include <iostream>
static constexpr int NO = 0;
static int g_state, translatorReady;
static void *xlate_vrefs, *xlate_link, *xlate_link_rt, *xlate_link_ext;
static int nvmtl_xlate_ready() { return translatorReady; }
#include "capabilities.inc"
int main() {
    unsigned combinations = 0;
    for (int state : {-1, 0, 1}) for (int ready : {0, 1}) for (uint32_t mask = 0; mask < 16; ++mask) {
        ++combinations; g_state = state; translatorReady = ready;
        xlate_vrefs = (mask & 1) ? &mask : nullptr;
        xlate_link = (mask & 2) ? &mask : nullptr;
        xlate_link_rt = (mask & 4) ? &mask : nullptr;
        xlate_link_ext = (mask & 8) ? &mask : nullptr;
        const int pointers = state == 1 && ready && (mask & 7) == 7;
        const int dylibs = state == 1 && ready && (mask & 8);
        assert(nvmtl_vk_backend_ready() == (state == 1));
        assert(nvmtl_translation_capabilities() == (ready ? mask : 0));
        assert(test_supportsFunctionPointers() == pointers);
        assert(test_supportsFunctionPointersFromRender() == pointers);
        assert(test_supportsDynamicLibraries() == dylibs);
        assert(test_supportsRenderDynamicLibraries() == dylibs);
        assert(!test_supportsShaderBarycentricCoordinates() && !test_areBarycentricCoordsSupported());
        assert(!test_hasUnifiedMemory());
        for (int64_t family : {-1, 0, 1001, 2001, 2002, 3001, 3002, 3003, 5001, INT32_MAX})
            assert(!test_supportsFamily(family));
        for (int64_t features : {-1, 0, 9999, 10000, 10005, 10006, INT32_MAX})
            assert(!test_supportsFeatureSet(features));
        assert(!nvmtl_capability_supported(NVMTL_CAP_BARYCENTRICS, 1, mask));
    }
    assert(combinations == 96);
    std::cout << "{\"dependency_combinations\":96,\"hardware_executed\":false}\n";
}
