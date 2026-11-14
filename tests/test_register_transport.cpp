// Actual extracted methods; only BAR storage, IOKit marshaling and locks are fake.
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include "PhxNativeABI.h"
#include "PhxDesktopHandoff.h"
#include "PhxAllocationSnapshot.h"

using IOReturn = int;
using kern_return_t = int;
using io_connect_t = unsigned;
static constexpr IOReturn kIOReturnSuccess = 0, kIOReturnBadArgument = 1,
    kIOReturnNotReady = 2, kIOReturnNotPrivileged = 3, kIOReturnUnsupported = 4,
    kIOReturnBusy = 5;
static constexpr kern_return_t KERN_SUCCESS = 0;
// Independent software address/field oracles. These are not physical BAR addresses.
static constexpr uint32_t selectorDword = 0xa900, selectorByte = 0x2a400;
static_assert(selectorDword * sizeof(uint32_t) == selectorByte, "dword/byte oracle");
struct IOExternalMethodDispatch {};
struct OSObject {};
struct IOExternalMethodArguments {
    uint32_t scalarInputCount{0}, scalarOutputCount{0};
    const uint64_t *scalarInput{nullptr};
    uint64_t *scalarOutput{nullptr};
    size_t structureInputSize{0}, structureOutputSize{0};
    const void *structureInput{nullptr};
    void *structureOutput{nullptr};
    void *structureInputDescriptor{nullptr}, *structureOutputDescriptor{nullptr};
};
struct FakeLock { bool held{false}; unsigned entries{0}; };
static void IOLockLock(FakeLock *lock) { assert(!lock->held); lock->held = true; ++lock->entries; }
static void IOLockUnlock(FakeLock *lock) { assert(lock->held); lock->held = false; }
static void IOLog(const char *, ...) { assert(!"unexpected submit logging"); }
struct FakeMMIO {
    std::vector<uint32_t> words = std::vector<uint32_t>(0x20000, 0xfeedface);
    uint64_t length{words.size() * sizeof(uint32_t)};
    unsigned accesses{0};
    bool loseSelectorStore{false};
    uint64_t getLength() const { return length; }
    uintptr_t getVirtualAddress() {
        // Fault injection between the actual store and its readback, never a
        // replacement for either provider method or an observation of hardware.
        if (loseSelectorStore && accesses) words[selectorDword] = 0;
        ++accesses;
        return reinterpret_cast<uintptr_t>(words.data());
    }
};
class PhxBringup {
public:
    FakeMMIO *mmio{nullptr};
    bool debug{true};
    IOReturn mutationResult{kIOReturnSuccess};
    unsigned mutationLocks{0}, mutationUnlocks{0};
    bool debugEnabled() const { return debug; }
    IOReturn lockDebugMutation(const void *, uint32_t selector) {
        assert(selector == PHXN_SEL_DBG_WRITE_REG); ++mutationLocks; return mutationResult;
    }
    void unlockDebugMutation() { ++mutationUnlocks; }
    uint32_t rreg(uint32_t) const;
    void wreg(uint32_t, uint32_t) const;
    IOReturn writeReg(uint32_t, uint32_t, uint32_t *);
    IOReturn readRegs(uint32_t, uint32_t, uint32_t *);
};
class IOAccelPhxNativeClient {
public:
    PhxBringup *owner{nullptr};
    FakeLock storage, *lock{&storage};
    bool closed{false}, hello{true}, privileged{true}, submitFailureLogged{false};
    unsigned reaps{0};
    void reapPending() { ++reaps; }
    IOReturn externalMethod(uint32_t, IOExternalMethodArguments *, IOExternalMethodDispatch *, OSObject *, void *);
    IOReturn doReadRegs(IOExternalMethodArguments *);
    IOReturn doDbgWriteReg(IOExternalMethodArguments *);
#include "register-unused.inc"
};
#include "register-provider.inc"

static IOAccelPhxNativeClient *client;
static io_connect_t conn = 7;
static kern_return_t IOConnectCallScalarMethod(io_connect_t connection, uint32_t selector,
    const uint64_t *input, uint32_t inputCount, uint64_t *output, uint32_t *outputCount) {
    assert(connection == 7 && selector == PHXN_SEL_DBG_WRITE_REG);
    IOExternalMethodArguments args;
    args.scalarInput = input; args.scalarInputCount = inputCount;
    args.scalarOutput = output; args.scalarOutputCount = *outputCount;
    const auto result = client->externalMethod(selector, &args, nullptr, nullptr, nullptr);
    *outputCount = args.scalarOutputCount;
    return result;
}
static kern_return_t IOConnectCallMethod(io_connect_t connection, uint32_t selector,
    const uint64_t *input, uint32_t inputCount, const void *inputData, size_t inputSize,
    uint64_t *output, uint32_t *outputCount, void *outputData, size_t *outputSize) {
    assert(connection == 7 && selector == PHXN_SEL_READREGS && !outputCount);
    IOExternalMethodArguments args;
    args.scalarInput = input; args.scalarInputCount = inputCount; args.scalarOutput = output;
    args.structureInput = inputData; args.structureInputSize = inputSize;
    args.structureOutput = outputData; args.structureOutputSize = *outputSize;
    const auto result = client->externalMethod(selector, &args, nullptr, nullptr, nullptr);
    *outputSize = args.structureOutputSize;
    return result;
}
#include "register-cli.inc"

static IOExternalMethodArguments readArgs(const uint64_t *input, uint32_t *output, uint64_t count = 1) {
    IOExternalMethodArguments a;
    a.scalarInput = input; a.scalarInputCount = 3;
    a.structureOutput = output; a.structureOutputSize = count * 4;
    return a;
}
static IOExternalMethodArguments writeArgs(const uint64_t *input, uint64_t *output) {
    IOExternalMethodArguments a;
    a.scalarInput = input; a.scalarInputCount = 2;
    a.scalarOutput = output; a.scalarOutputCount = 1;
    return a;
}
int main(int argc, char **argv) {
    assert(argc == 2);
    const char *name = argv[1];
    FakeMMIO bar; PhxBringup provider; provider.mmio = &bar;
    IOAccelPhxNativeClient native; native.owner = &provider; client = &native;
    if (!strcmp(name, "roundtrip")) {
        assert(grbm_select(0, 0, 0, 1) == 0x10);
        assert(bar.words[selectorDword] == 0x10 && rd(selectorDword) == 0x10);
        assert(grbm_select(3, 1, 7, 15) == 0x7fd);
        assert(rd(selectorDword) == 0x7fd);
        assert(grbm_select(0, 0, 0, 0) == 0 && rd(selectorDword) == 0);
        assert(wr(selectorDword, 0x80000010) == 0x80000010 && rd(selectorDword) == 0x80000010);
        assert(bar.words[selectorDword - 1] == 0xfeedface && bar.words[selectorDword + 1] == 0xfeedface);
        assert(provider.mutationLocks == 4 && provider.mutationUnlocks == 4 && native.reaps == 8);
    } else if (!strcmp(name, "bounds")) {
        uint32_t output = 0x12345678;
        provider.wreg(selectorDword, 0x80000010);
        assert(provider.rreg(selectorDword) == 0x80000010);
        assert(provider.readRegs(selectorDword, 1, &output) == 0 && output == 0x80000010);
        bar.length = 4ull * (selectorDword + 1);
        assert(provider.writeReg(selectorDword, 0xf0, &output) == 0 && output == 0xf0);
        assert(provider.readRegs(selectorDword, 1, &output) == 0 && output == 0xf0);
        const auto accesses = bar.accesses;
        for (auto reg : {selectorDword + 1, UINT32_MAX}) {
            output = 0x12345678;
            assert(provider.writeReg(reg, 0x10, &output) == kIOReturnBadArgument);
            assert(provider.readRegs(reg, 1, &output) == kIOReturnBadArgument);
            assert(output == 0x12345678 && bar.accesses == accesses);
        }
        assert(provider.readRegs(selectorDword, 2, &output) == kIOReturnBadArgument);
        provider.mmio = nullptr;
        assert(provider.writeReg(0, 0x10, &output) == kIOReturnNotReady);
        assert(provider.readRegs(0, 1, &output) == kIOReturnNotReady);
        assert(bar.accesses == accesses);
    } else if (!strcmp(name, "read-abi")) {
        uint64_t input[] = {selectorDword, 1, UINT32_MAX}; uint32_t output[16]{};
        auto valid = readArgs(input, output);
        for (unsigned fault = 0; fault < 9; ++fault) {
            auto a = valid; input[0] = selectorDword; input[1] = 1; input[2] = UINT32_MAX;
            switch (fault) {
                case 0: a.scalarInputCount = 2; break;
                case 1: a.scalarOutputCount = 1; break;
                case 2: a.structureInputSize = 4; break;
                case 3: input[1] = 0; break;
                case 4: input[1] = 17; a.structureOutputSize = 68; break;
                case 5: input[2] = 0; break;
                case 6: a.structureOutputSize = 8; break;
                case 7: input[0] = 1ull << 32; break;
                case 8: input[0] = UINT32_MAX; break;
            }
            assert(native.doReadRegs(&a) == kIOReturnBadArgument && bar.accesses == 0);
        }
        input[0] = selectorDword; input[1] = 16; input[2] = UINT32_MAX;
        auto a = readArgs(input, output, 16);
        assert(native.doReadRegs(&a) == 0 && output[0] == 0xfeedface && output[15] == 0xfeedface);
        native.privileged = false;
        assert(native.doReadRegs(&a) == kIOReturnNotPrivileged);
        // Independent timestamp exception oracle; never a privilege bypass for GRBM.
        input[0] = 0x16a2d; input[1] = 2; a.structureOutputSize = 8;
        assert(native.doReadRegs(&a) == 0);
        input[0] = 0x16a2e; input[1] = 1; a.structureOutputSize = 4;
        assert(native.doReadRegs(&a) == 0);
        const auto accesses = bar.accesses;
        input[1] = 2; a.structureOutputSize = 8;
        assert(native.doReadRegs(&a) == kIOReturnNotPrivileged && bar.accesses == accesses);
    } else if (!strcmp(name, "write-abi")) {
        uint64_t input[] = {selectorDword, 0x10}, output = 0xfeed;
        auto valid = writeArgs(input, &output);
        for (unsigned fault = 0; fault < 9; ++fault) {
            auto a = valid; input[0] = selectorDword; input[1] = 0x10;
            switch (fault) {
                case 0: a.scalarInputCount = 1; break;
                case 1: a.scalarOutputCount = 0; break;
                case 2: a.structureInputSize = 4; break;
                case 3: a.structureOutputSize = 4; break;
                case 4: a.structureInputDescriptor = &bar; break;
                case 5: a.structureOutputDescriptor = &bar; break;
                case 6: input[0] = 1ull << 32; break;
                case 7: input[1] = 1ull << 32; break;
                case 8: input[0] = UINT32_MAX; break;
            }
            assert(native.doDbgWriteReg(&a) == kIOReturnBadArgument && bar.accesses == 0);
        }
        input[0] = selectorDword; input[1] = 0x10;
        auto a = valid; provider.debug = false;
        assert(native.doDbgWriteReg(&a) == kIOReturnUnsupported);
        provider.debug = true; native.privileged = false;
        assert(native.doDbgWriteReg(&a) == kIOReturnNotPrivileged && bar.accesses == 0);
        native.privileged = true; provider.mmio = nullptr; output = 0xfeed;
        assert(native.doDbgWriteReg(&a) == kIOReturnNotReady && output == 0);
    } else if (!strcmp(name, "dispatch")) {
        uint64_t input[] = {selectorDword, 0x10}, output = 0;
        auto a = writeArgs(input, &output);
        native.hello = false;
        assert(native.externalMethod(108, &a, nullptr, nullptr, nullptr) == kIOReturnNotReady);
        native.hello = true; native.closed = true;
        assert(native.externalMethod(108, &a, nullptr, nullptr, nullptr) == kIOReturnNotReady);
        native.closed = false; provider.mutationResult = kIOReturnBusy;
        assert(native.externalMethod(108, &a, nullptr, nullptr, nullptr) == kIOReturnBusy);
        assert(bar.accesses == 0 && provider.mutationLocks == 1 && provider.mutationUnlocks == 0);
        assert(rd(selectorDword) == 0xfeedface && provider.mutationLocks == 1);
        provider.mutationResult = 0;
        assert(wr(selectorDword, 0x10) == 0x10 && provider.mutationUnlocks == 1);
        assert(!native.storage.held);
    } else if (!strcmp(name, "lost-store")) {
        bar.loseSelectorStore = true;
        assert(grbm_select(0, 0, 0, 1) == 0);
        assert(rd(selectorDword) == 0 && bar.accesses == 3);
        assert(provider.mutationLocks == 1 && provider.mutationUnlocks == 1);
    } else if (!strcmp(name, "read-not-ready")) {
        provider.mmio = nullptr; (void)rd(selectorDword); assert(false);
    } else if (!strcmp(name, "write-not-ready")) {
        provider.mmio = nullptr; (void)grbm_select(0, 0, 0, 1); assert(false);
    } else if (!strcmp(name, "write-denied")) {
        native.privileged = false; (void)grbm_select(0, 0, 0, 1); assert(false);
    } else { assert(!"unknown register case"); }
    printf("actual-register-methods-passed %s\n", name);
}
