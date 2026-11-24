"""Stage build34 host-map and GPUVM identities for CPU tests."""

import hashlib

from build34_exact_raw_handoff import WRITERS
from test_build34_exact_ownership import method


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
            '#include "PhxNativeABI.h"\n#include "build34_dcn_render_tlb.h"\n'
            '#include "build34_exact_callbacks.h"\n')
    replace("    uint32_t vmidAlloc();\n", "    uint32_t vmidAlloc(const void *client);\n")
    replace("owner->vmidAlloc()", "owner->vmidAlloc(this)")
    replace("        bool busy;\n", "        bool busy;\n"
            "        const void *renderClient;\n"
            "        uint64_t renderContextGeneration, renderBindingGeneration, renderTableGeneration;\n")
    replace("    uint64_t hwTick{0};\n", "    uint64_t hwTick{0};\n"
            "    friend class IOAccelPhxNativeClient;\n"
            "    uint64_t renderVmSerial{0};\n"
            "    bool renderVmClosed{false};\n"
            "    build34::dcn::RenderVmTranslation renderInvalidateRequest{};\n"
            "    bool renderInvalidateUncertain{false};\n"
            "    bool renderQueuesAdopted[2]{};\n"
            "    bool renderEngine17Owned{false};\n"
            "    phx34_exact::CallbackGate<> renderRawWriters;\n"
            "    bool (*renderEngine17HandoffProof)(const PhxBringup *){nullptr};\n"
            "    bool takeRenderEngine17Locked();\n"
            "    uint64_t nextRenderVmGenerationLocked();\n"
            "    build34::dcn::RenderVmTranslation renderVmIdentityLocked(\n"
            "        uint32_t handle, build34::dcn::RenderMapIdentity mapping);\n"
            "    build34::dcn::RenderTlbAck confirmRenderTlbLocked(\n"
            "        uint32_t handle, build34::dcn::RenderMapIdentity mapping);\n")
    replace("    uint64_t softwareMappedHostGenerationLocked(uint64_t va, uint64_t bytes) const;\n",
            "    uint64_t softwareMappedHostGenerationLocked(uint64_t va, uint64_t bytes) const;\n"
            "    build34::dcn::RenderVmTranslation renderTranslationLocked(uint64_t va, uint64_t bytes) const;\n"
            "    build34::dcn::RenderTlbAck confirmRenderTlbLocked(uint64_t va, uint64_t bytes) const;\n")
    replace(anchor, """build34::dcn::RenderVmTranslation IOAccelPhxNativeClient::renderTranslationLocked(
    uint64_t va, uint64_t bytes) const {
    const uint64_t generation = softwareMappedHostGenerationLocked(va, bytes);
    return generation && owner ? owner->renderVmIdentityLocked(vmid, {this, generation})
                               : build34::dcn::RenderVmTranslation{};
}

build34::dcn::RenderTlbAck IOAccelPhxNativeClient::confirmRenderTlbLocked(uint64_t va, uint64_t bytes) const {
    const uint64_t generation = softwareMappedHostGenerationLocked(va, bytes);
    return generation && owner ? owner->confirmRenderTlbLocked(vmid, {this, generation})
                               : build34::dcn::RenderTlbAck{};
}

""" + anchor)
    replace("void PhxBringup::stop(IOService *provider) {\n",
            "void PhxBringup::stop(IOService *provider) {\n"
            "    __atomic_store_n(&renderVmClosed, true, __ATOMIC_RELEASE);\n")
    replace("    if (ordinal == 0) {\n", "    if (ordinal == 0) {\n"
            "        __atomic_store_n(&renderVmClosed, true, __ATOMIC_RELEASE);\n")
    for name in WRITERS:
        writer = method(source, "IOReturn PhxBringup::" + name + "(")
        brace = writer.index("{\n") + 2
        replace(writer, writer[:brace] +
                "    phx34_exact::CallbackGate<>::Lease rawWriter(renderRawWriters);\n"
                "    if (!rawWriter)\n        return kIOReturnNotReady;\n" + writer[brace:])
    replace("    GpuQueue &q = gq[qi];\n    bzero(&q, sizeof(q));\n",
            "    renderInvalidateRequest = {};\n"
            "    if (renderQueuesAdopted[qi])\n"
            "        renderInvalidateUncertain = true;\n"
            "    renderQueuesAdopted[qi] = true;\n"
            "    GpuQueue &q = gq[qi];\n    bzero(&q, sizeof(q));\n")
    replace("void PhxBringup::killWaves(uint32_t vmid, bool all) {\n",
            "void PhxBringup::killWaves(uint32_t vmid, bool all) {\n"
            "    __atomic_store_n(&renderVmClosed, true, __ATOMIC_RELEASE);\n")
    replace("    void vmFlushTlb(uint32_t vmid) const;\n", "    void vmFlushTlb(uint32_t vmid);\n")
    flush = method(source, "void PhxBringup::vmFlushTlb(")
    replace(flush, """void PhxBringup::vmFlushTlb(uint32_t vmid) {
    renderInvalidateRequest = {};
    const uint32_t mask = (1u << vmid) | 1u;
    const bool track = renderEngine17Owned && !renderInvalidateUncertain &&
        !__atomic_load_n(&renderVmClosed, __ATOMIC_ACQUIRE);
    const uint64_t start = track ? mach_absolute_time() : 0;
    build34::dcn::RenderInvalidateEdges edges(mask);
    __asm__ __volatile__("mfence" ::: "memory");
    wreg(kRegInvEng17Req, 0x00F80000u | mask);
    bool complete = false;
    uint64_t previous = start;
    for (int attempt = 0; attempt < 1000; ++attempt) {
        const uint32_t bits = rreg(kRegInvEng17Ack);
        if (track) {
            const uint64_t now = mach_absolute_time();
            if (now < previous) {
                renderInvalidateUncertain = true;
            } else {
                uint64_t elapsed = 0;
                absolutetime_to_nanoseconds(now - start, &elapsed);
                complete = edges.observe(bits, elapsed);
                previous = now;
            }
        }
        if (bits & (1u << vmid))
            break;
        IODelay(1);
    }
    if (track && !complete)
        renderInvalidateUncertain = true;
}
""")
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
    build34::dcn::RenderVmTranslation result{mapping, this, context->renderContextGeneration,
        context->renderBindingGeneration, context->renderTableGeneration,
        renderInvalidateRequest.invalidateGeneration, handle, context->hw};
    if (renderInvalidateUncertain || !build34::dcn::sameRenderTranslation(result, renderInvalidateRequest))
        result.invalidateGeneration = 0;
    return result;
}

bool PhxBringup::takeRenderEngine17Locked() {
    if (__atomic_load_n(&renderVmClosed, __ATOMIC_ACQUIRE) || renderInvalidateUncertain)
        return false;
    if (renderEngine17Owned)
        return true;
    if (!renderQueuesAdopted[0] || !renderQueuesAdopted[1] || !renderEngine17HandoffProof)
        return false;
    renderRawWriters.close();
    if (!renderRawWriters.drained() || !renderEngine17HandoffProof(this) ||
        __atomic_load_n(&renderVmClosed, __ATOMIC_ACQUIRE))
        return false;
    renderEngine17Owned = true;
    return true;
}

build34::dcn::RenderTlbAck PhxBringup::confirmRenderTlbLocked(
    uint32_t handle, build34::dcn::RenderMapIdentity mapping) {
    using namespace build34::dcn;
    renderInvalidateRequest = {};
    auto request = renderVmIdentityLocked(handle, mapping);
    if (!request.provider || !mmio || mmio->getLength() < 4u * (kRegInvEng17Ack + 1u) ||
        !takeRenderEngine17Locked() ||
        !sameRenderTranslation(request, renderVmIdentityLocked(handle, mapping)))
        return {};
    const uint32_t mask = (1u << request.vmid) | 1u;
    const uint32_t baseline = rreg(kRegInvEng17Ack);
    if (baseline == UINT32_MAX || (baseline & mask) != mask ||
        !sameRenderTranslation(request, renderVmIdentityLocked(handle, mapping)))
        return {};
    const uint64_t generation = nextRenderVmGenerationLocked();
    if (!generation)
        return {};

    request.invalidateGeneration = generation;
    renderInvalidateRequest = request;
    struct Sampling {
        PhxBringup *provider;
        RenderVmTranslation request;
        uint64_t start;
        uint64_t previous;
    } sampling{this, request, mach_absolute_time(), 0};
    sampling.previous = sampling.start;
    const auto sample = [](void *opaque, RenderTlbSample *value) -> bool {
        auto &state = *static_cast<Sampling *>(opaque);
        auto *device = state.provider;
        const auto &expected = state.request;
        if (!sameRenderTranslation(expected, device->renderVmIdentityLocked(expected.context, expected.mapping)))
            return false;
        const uint64_t before = mach_absolute_time();
        uint64_t elapsed = 0;
        if (before < state.previous)
            return false;
        absolutetime_to_nanoseconds(before - state.start, &elapsed);
        if (elapsed >= 1000000)
            return false;
        value->ackBits = device->rreg(kRegInvEng17Ack);
        const uint64_t after = mach_absolute_time();
        if (after < before)
            return false;
        state.previous = after;
        absolutetime_to_nanoseconds(after - state.start, &value->elapsedNs);
        value->current = device->renderVmIdentityLocked(expected.context, expected.mapping);
        return true;
    };
    __asm__ __volatile__("mfence" ::: "memory");
    wreg(kRegInvEng17Req, 0x00F80000u | mask);
    const auto ack = RenderTlbAck::observe(request, &sampling, sample, 1u);
    if (!ack.matches(renderVmIdentityLocked(handle, mapping))) {
        renderInvalidateRequest = {};
        renderInvalidateUncertain = true;
        return {};
    }
    return ack;
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
