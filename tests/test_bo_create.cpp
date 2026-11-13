// Actual allocation methods, fake IOKit. No device access.
#include "PhxNativeABI.h"
#include "PhxBoPolicy.hpp"
#include "PhxAllocationDiagnostic.hpp"
#include <cassert>
#include <cstdarg>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <strings.h>
using IOReturn = int;
using SInt64 = int64_t;
enum { kIOReturnSuccess, kIOReturnBadArgument, kIOReturnUnsupported,
       kIOReturnNoMemory, kIOReturnNoResources, kIOReturnVMError };
static constexpr unsigned kIODirectionInOut = 3, kIOMemoryKernelUserShared = 0x100, PAGE_SIZE = 4096;
static void *kernel_task = reinterpret_cast<void *>(1);
static SInt64 gBosHandlesHigh = 0, gBosHandlesFull = 0;
static uint32_t gBosHandlesFullLogged = 0;
static void OSAddAtomic64(int n, SInt64 *p) { *p += n; }
static bool OSCompareAndSwap(uint32_t a, uint32_t b, uint32_t *p) { if (*p != a) return false; *p = b; return true; }
static void (*logHook)(const char *, va_list) = nullptr;
static void IOLog(const char *format, ...) {
    va_list arguments; va_start(arguments, format);
    if (logHook) logHook(format, arguments);
    va_end(arguments);
}
static unsigned allocations, releases, prepares, zeroes;
static bool allocFail, bytesFail, pinFail;
static IOReturn pinResult = kIOReturnSuccess;
static uint8_t storage[4096];
static void fakeBzero(void *bytes, size_t size) {
    assert(bytes == storage && size == sizeof storage); ++zeroes; std::memset(bytes, 0, size);
}
struct IOMemoryDescriptor {
    static IOMemoryDescriptor *withAddressRange(uint64_t, uint64_t, unsigned, void *);
    IOReturn prepare() { ++prepares; return pinFail ? kIOReturnVMError : pinResult; }
    void release() { ++releases; }
};
struct IOBufferMemoryDescriptor : IOMemoryDescriptor {
    static IOBufferMemoryDescriptor *inTaskWithOptions(void *task, unsigned flags, uint64_t size, unsigned alignment) {
        assert(task == kernel_task && flags == (kIODirectionInOut | kIOMemoryKernelUserShared));
        assert(size == sizeof storage && alignment == PAGE_SIZE);
        ++allocations; static IOBufferMemoryDescriptor md; return allocFail ? nullptr : &md;
    }
    void *getBytesNoCopy() { return bytesFail ? nullptr : storage; }
};
IOMemoryDescriptor *IOMemoryDescriptor::withAddressRange(uint64_t va, uint64_t size, unsigned flags, void *task) {
    assert(va == 0x10000 && size == 4096 && flags == kIODirectionInOut && task);
    ++allocations; static IOMemoryDescriptor md; return allocFail ? nullptr : &md;
}
struct IOExternalMethodArguments {
    uint32_t scalarInputCount{}, scalarOutputCount{}, structureInputSize{}, structureOutputSize{};
    void *structureInputDescriptor{}, *structureOutputDescriptor{};
    const void *structureInput{};
    uint64_t scalarInput[4]{}, scalarOutput[4]{77, 77, 77, 77};
};
// The actual struct is needed before the test client declaration.
#include "bo-struct.inc"
class IOAccelPhxNativeClient {
public:
#include "bo-state.inc"
    using Bo = PhxClientBo;
    Bo bos[PHXN_MAX_BOS]{};
    uint64_t visUsed{}, hiUsed{}, gttUsed{}, hostUsed{};
    void *task = reinterpret_cast<void *>(2);
    IOReturn doBoCreate(IOExternalMethodArguments *);
    IOReturn doBoImportHost(IOExternalMethodArguments *);
};
#define bzero fakeBzero
#include "bo-methods.inc"
#undef bzero

#ifndef PHX_NO_BO_CREATE_TEST_MAIN
int main() {
    uint64_t rounded = 17;
    assert(!phx780m::boPageSize(0, &rounded) && rounded == 17);
    assert(!phx780m::boPageSize(1, nullptr));
    for (uint64_t i = 0; i < 4095; ++i)
        assert(!phx780m::boPageSize(UINT64_MAX - i, &rounded) && rounded == 17);
    assert(phx780m::boPageSize(UINT64_MAX - 4095, &rounded) && rounded == UINT64_MAX - 4095);
    for (uint64_t budget = 0; budget < 64; ++budget)
        for (uint64_t used = 0; used < 80; ++used)
            for (uint64_t bytes = 0; bytes < 80; ++bytes)
                assert(phx780m::boBudgetFits(used, bytes, budget) == (bytes && used + bytes <= budget));
    assert(!phx780m::boBudgetFits(UINT64_MAX, 1, 4096));
    for (unsigned test = 0; test < 30; ++test) {
        IOAccelPhxNativeClient client;
        allocations = releases = prepares = zeroes = 0; allocFail = bytesFail = pinFail = false;
        std::memset(storage, 0xa5, sizeof storage);
        IOExternalMethodArguments args; phxn_gem_create_in in{1, 0, PHX_AMDGPU_GEM_DOMAIN_VRAM, 0};
        args.scalarOutputCount = 4; args.structureInput = &in; args.structureInputSize = sizeof in;
        IOReturn expected = kIOReturnSuccess;
        const bool host = test >= 22;
        switch (test) {
            case 0: break;
            case 1: in.bo_size = 0; expected = kIOReturnBadArgument; break;
            case 2: in.bo_size = UINT64_MAX; expected = kIOReturnBadArgument; break;
            case 3: in.bo_size = UINT64_MAX - 4095; expected = kIOReturnNoMemory; break;
            case 4: in.alignment = 8193; expected = kIOReturnBadArgument; break;
            case 5: in.alignment = 4ull << 20; expected = kIOReturnBadArgument; break;
            case 6: in.domains = 0; expected = kIOReturnUnsupported; break;
            case 7: in.domain_flags = PHX_AMDGPU_GEM_CREATE_ENCRYPTED; expected = kIOReturnUnsupported; break;
            case 8: client.visUsed = kVisTotal - 4096; break;
            case 9: client.visUsed = kVisTotal; expected = kIOReturnNoMemory; break;
            case 10: client.visUsed = UINT64_MAX; expected = kIOReturnNoMemory; break;
            case 11: client.visUsed = kVisTotal; in.domain_flags = PHX_AMDGPU_GEM_CREATE_NO_CPU_ACCESS; client.hiUsed = kHiTotal - 4096; break;
            case 12: client.visUsed = kVisTotal; in.domain_flags = PHX_AMDGPU_GEM_CREATE_NO_CPU_ACCESS; client.hiUsed = UINT64_MAX; expected = kIOReturnNoMemory; break;
            case 13: client.visUsed = kVisTotal; in.domain_flags = PHX_AMDGPU_GEM_CREATE_NO_CPU_ACCESS | PHX_AMDGPU_GEM_CREATE_CPU_ACCESS_REQUIRED; expected = kIOReturnNoMemory; break;
            case 14: in.domains = PHX_AMDGPU_GEM_DOMAIN_GTT; client.gttUsed = kGttCap - 4096; break;
            case 15: in.domains = PHX_AMDGPU_GEM_DOMAIN_GTT; client.gttUsed = UINT64_MAX; expected = kIOReturnNoMemory; break;
            case 16: in.domains = PHX_AMDGPU_GEM_DOMAIN_GTT; in.bo_size = kGttMaxBo + 1; expected = kIOReturnNoMemory; break;
            case 17: allocFail = true; expected = kIOReturnNoMemory; break;
            case 18: bytesFail = true; expected = kIOReturnNoMemory; break;
            case 19: for (auto &bo : client.bos) bo.md = reinterpret_cast<IOMemoryDescriptor *>(1); expected = kIOReturnNoResources; break;
            case 20: args.scalarOutputCount = 3; expected = kIOReturnBadArgument; break;
            case 21: in.alignment = 2ull << 20; break;
            case 22: client.hostUsed = kHostCap - 4096; break;
            case 23: client.hostUsed = UINT64_MAX; expected = kIOReturnNoMemory; break;
            case 24: pinFail = true; expected = kIOReturnVMError; break;
            case 25: allocFail = true; expected = kIOReturnNoMemory; break;
            case 26: client.task = nullptr; expected = kIOReturnBadArgument; break;
            case 27: args.scalarInput[2] = 1; expected = kIOReturnBadArgument; break;
            case 28: expected = kIOReturnNoMemory; break;
            case 29: for (auto &bo : client.bos) bo.md = reinterpret_cast<IOMemoryDescriptor *>(1); expected = kIOReturnNoResources; break;
        }
        const auto beforeVis = client.visUsed, beforeHi = client.hiUsed, beforeGtt = client.gttUsed, beforeHost = client.hostUsed;
        if (host) {
            args.scalarInputCount = 4; args.structureInput = nullptr; args.structureInputSize = 0;
            args.scalarInput[0] = 0x10000; args.scalarInput[1] = test == 28 ? kHostMaxBo + 4096 : 4096;
        }
        const auto status = host ? client.doBoImportHost(&args) : client.doBoCreate(&args);
        assert(status == expected);
        if (status == kIOReturnSuccess) {
            assert(allocations == 1 && releases == 0 && args.scalarOutput[0] == 1 && args.scalarOutput[1] == 4096);
            auto &bo = client.bos[1]; assert(bo.md && bo.size == 4096 && bo.host == host && !bo.pendingFree);
            assert(client.visUsed + client.hiUsed + client.gttUsed + client.hostUsed == beforeVis + beforeHi + beforeGtt + beforeHost + 4096);
            if (host) { assert(prepares == 1 && !zeroes && !bo.kva); }
            else { assert(!prepares && zeroes == 1 && bo.kva == storage); for (auto b : storage) assert(b == 0); }
        } else {
            assert(client.visUsed == beforeVis && client.hiUsed == beforeHi && client.gttUsed == beforeGtt && client.hostUsed == beforeHost);
            for (auto output : args.scalarOutput) assert(output == 77);
            assert(!zeroes);
            if (test == 18 || test == 24) assert(allocations == 1 && releases == 1);
            else assert(!releases);
            if (test != 17 && test != 18 && test != 24 && test != 25) assert(!allocations);
        }
    }
    std::cout << "{\"allocation_cases\":30,\"hardware_executed\":false}\n";
}
#endif
