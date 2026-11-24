"""Stage build34 host-map and GPUVM identities for CPU tests."""

import hashlib


DRIVER = "src/phxbringup/PhxBringup.cpp"
DRIVER_SHA256 = "81f45aa2e8166bc6ebed4106129bebebfd70f9b4bbea6dbe389be46263e3c699"
ABI = "src/phxbringup/PhxNativeABI.h"
ABI_SHA256 = "cb37e93dcab4faf8c9e672ad04793f2e363ae1e815c9913251cebcff5cd42c90"


def stage(driver, abi):
    if (hashlib.sha256(driver).hexdigest() != DRIVER_SHA256 or
            hashlib.sha256(abi).hexdigest() != ABI_SHA256):
        raise ValueError("Build34 DCN render-map source or ABI drift")
    source = driver.decode()

    def replace(old, new, count=1):
        nonlocal source
        if source.count(old) != count:
            raise ValueError("Build34 DCN render-map anchor drift: " + old[:100])
        source = source.replace(old, new, count)

    replace("        uint64_t va, size, off;\n        uint32_t flags;\n",
            "        uint64_t va, size, off;\n        uint32_t flags;\n        uint64_t softwareGeneration;\n")
    replace("    Map *maps{nullptr};    // kMaxMaps entries\n",
            "    Map *maps{nullptr};    // kMaxMaps entries\n"
            "    uint64_t renderMapGeneration{0};\n"
            "    bool renderMapsClosed{false};\n"
            "    uint64_t softwareMappedHostGenerationLocked(uint64_t va, uint64_t bytes) const;\n")
    replace("void IOAccelPhxNativeClient::freeAll() {\n",
            "void IOAccelPhxNativeClient::freeAll() {\n"
            "    renderMapsClosed = true;\n"
            "    if (maps)\n"
            "        for (int i = 0; i < kMaxMaps; ++i)\n"
            "            maps[i].softwareGeneration = 0;\n")
    replace("        if (maps[i].used && maps[i].handle == h)\n            maps[i].used = false;\n",
            "        if (maps[i].used && maps[i].handle == h) {\n"
            "            maps[i].softwareGeneration = 0;\n"
            "            maps[i].used = false;\n"
            "        }\n")
    replace("    if (va < 0x10000 || va + v->map_size > (1ull << 48))\n",
            "    if (va < 0x10000 || v->map_size > (1ull << 48) - va)\n")
    replace("    if (v->offset_in_bo + v->map_size > b->size)\n",
            "    if (v->offset_in_bo > b->size || v->map_size > b->size - v->offset_in_bo)\n")
    replace("maps[freei] = Map{true, v->handle, va, v->map_size, v->offset_in_bo, v->flags};",
            "maps[freei] = Map{true, v->handle, va, v->map_size, v->offset_in_bo, v->flags, 0};")
    replace("                maps[freei].used = false;\n                return r;\n            }\n",
            "                maps[freei].used = false;\n                return r;\n            }\n"
            "            if (b->host && !renderMapsClosed && renderMapGeneration < UINT64_MAX - 1)\n"
            "                maps[freei].softwareGeneration = ++renderMapGeneration;\n")
    replace("            maps[i].used = false;\n            if (vmid)\n",
            "            maps[i].softwareGeneration = 0;\n"
            "            maps[i].used = false;\n            if (vmid)\n")
    anchor = "IOReturn IOAccelPhxNativeClient::doCtx(IOExternalMethodArguments *a) {"
    replace(anchor, """uint64_t IOAccelPhxNativeClient::softwareMappedHostGenerationLocked(uint64_t va, uint64_t bytes) const {
    if (renderMapsClosed || !maps || !vmid || va > kVaMask || !bytes || ((va | bytes) & 4095))
        return 0;
    for (int i = 0; i < kMaxMaps; ++i) {
        const Map &entry = maps[i];
        if (!entry.used || !entry.softwareGeneration || va < entry.va)
            continue;
        const uint64_t offset = va - entry.va;
        if (offset < entry.size && bytes <= entry.size - offset)
            return entry.softwareGeneration;
    }
    return 0;
}

""" + anchor)
    replace('#include "PhxNativeABI.h"\n',
            '#include "PhxNativeABI.h"\n#include "build34_dcn_render_tlb.h"\n')
    replace("    uint32_t vmidAlloc();\n", "    uint32_t vmidAlloc(const void *client);\n")
    replace("owner->vmidAlloc()", "owner->vmidAlloc(this)")
    replace("        bool busy;\n", "        bool busy;\n"
            "        const void *renderClient;\n"
            "        uint64_t renderContextGeneration, renderBindingGeneration, renderTableGeneration;\n")
    replace("    uint64_t hwTick{0};\n", "    uint64_t hwTick{0};\n"
            "    friend class IOAccelPhxNativeClient;\n"
            "    uint64_t renderVmSerial{0};\n"
            "    bool renderVmClosed{false};\n"
            "    uint64_t nextRenderVmGenerationLocked();\n"
            "    build34::dcn::RenderVmTranslation renderVmIdentityLocked(\n"
            "        uint32_t handle, build34::dcn::RenderMapIdentity mapping);\n")
    replace("    uint64_t softwareMappedHostGenerationLocked(uint64_t va, uint64_t bytes) const;\n",
            "    uint64_t softwareMappedHostGenerationLocked(uint64_t va, uint64_t bytes) const;\n"
            "    build34::dcn::RenderVmTranslation renderTranslationLocked(uint64_t va, uint64_t bytes) const;\n")
    replace(anchor, """build34::dcn::RenderVmTranslation IOAccelPhxNativeClient::renderTranslationLocked(
    uint64_t va, uint64_t bytes) const {
    const uint64_t generation = softwareMappedHostGenerationLocked(va, bytes);
    return generation && owner ? owner->renderVmIdentityLocked(vmid, {this, generation})
                               : build34::dcn::RenderVmTranslation{};
}

""" + anchor)
    replace("void PhxBringup::stop(IOService *provider) {\n",
            "void PhxBringup::stop(IOService *provider) {\n"
            "    __atomic_store_n(&renderVmClosed, true, __ATOMIC_RELEASE);\n")
    replace("    if (ordinal == 0) {\n", "    if (ordinal == 0) {\n"
            "        __atomic_store_n(&renderVmClosed, true, __ATOMIC_RELEASE);\n")
    replace("uint32_t PhxBringup::vmidAlloc() {", """uint64_t PhxBringup::nextRenderVmGenerationLocked() {
    return renderVmSerial < UINT64_MAX - 1 ? ++renderVmSerial : 0;
}

build34::dcn::RenderVmTranslation PhxBringup::renderVmIdentityLocked(
    uint32_t handle, build34::dcn::RenderMapIdentity mapping) {
    if (__atomic_load_n(&renderVmClosed, __ATOMIC_ACQUIRE) || !mapping.client ||
        !build34::dcn::validRenderGeneration(mapping.generation))
        return {};
    const VmCtx *context = vmCtx(handle);
    if (!context || context->renderClient != mapping.client || !context->renderContextGeneration ||
        !context->renderBindingGeneration || !context->renderTableGeneration ||
        context->hw < kFirstUserVmid || context->hw >= kFirstUserVmid + kNumUserVmids ||
        hwv[context->hw - kFirstUserVmid].ctx != handle)
        return {};
    return {mapping, this, context->renderContextGeneration, context->renderBindingGeneration,
            context->renderTableGeneration, 0, handle, context->hw};
}

uint32_t PhxBringup::vmidAlloc(const void *client) {""")
    replace("        c.busy = true;\n        c.hw = 0;\n", "        c.busy = true;\n        c.hw = 0;\n"
            "        c.renderClient = client;\n"
            "        c.renderContextGeneration = nextRenderVmGenerationLocked();\n"
            "        c.renderBindingGeneration = 0;\n"
            "        c.renderTableGeneration = nextRenderVmGenerationLocked();\n")
    replace("    if (h.ctx)\n        vm[h.ctx - 1].hw = 0;\n", "    if (h.ctx) {\n"
            "        vm[h.ctx - 1].renderBindingGeneration = 0;\n"
            "        vm[h.ctx - 1].hw = 0;\n"
            "    }\n")
    replace("    vmFlushTlb(vmid);\n    return vmid;\n", "    vmFlushTlb(vmid);\n"
            "    c.renderBindingGeneration = nextRenderVmGenerationLocked();\n"
            "    return vmid;\n")
    replace("    IOLockLock(gpuLock);\n    VmCtx &c = vm[handle - 1];\n",
            "    IOLockLock(gpuLock);\n    VmCtx &c = vm[handle - 1];\n"
            "    c.renderClient = nullptr;\n"
            "    c.renderContextGeneration = c.renderBindingGeneration = c.renderTableGeneration = 0;\n")
    replace("    IOLockLock(gpuLock);\n    for (uint64_t p = 0; p < size; p += 4096) {\n",
            "    IOLockLock(gpuLock);\n"
            "    if (c.renderTableGeneration)\n"
            "        c.renderTableGeneration = nextRenderVmGenerationLocked();\n"
            "    for (uint64_t p = 0; p < size; p += 4096) {\n", 2)
    replace("            r = pa ? kIOReturnNoMemory : kIOReturnVMError;\n",
            "            r = pa ? kIOReturnNoMemory : kIOReturnVMError;\n"
            "            c.renderTableGeneration = 0;\n")
    return source
