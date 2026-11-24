"""Stage build34 host-map bookkeeping for CPU tests, not a runtime build."""

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

    def replace(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ValueError("Build34 DCN render-map anchor drift: " + old[:100])
        source = source.replace(old, new, 1)

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
    return source
