// Actual native dispatcher and latch declaration; explicit CPU-only IOKit/handler fakes.
#include <cassert>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>
#include "PhxNativeABI.h"
#include "PhxBootMemory.h"

using IOReturn = uint32_t;
constexpr IOReturn kIOReturnSuccess = 0;
constexpr IOReturn kIOReturnBadArgument = 0xe00002c2u;
constexpr IOReturn kIOReturnNotReady = 0xe00002d8u;
struct IOExternalMethodArguments {};
struct IOExternalMethodDispatch {};
struct OSObject {};
struct FakeLock { bool held{false}; };
static FakeLock *activeLock = nullptr;
static std::vector<std::string> events, logs;

static void IOLockLock(FakeLock *lock) {
    assert(lock && !lock->held && !activeLock);
    lock->held = true;
    activeLock = lock;
    events.emplace_back("lock");
}
static void IOLockUnlock(FakeLock *lock) {
    assert(lock && lock->held && activeLock == lock);
    lock->held = false;
    activeLock = nullptr;
    events.emplace_back("unlock");
}
static void IOLog(const char *format, ...) {
    assert(activeLock && activeLock->held);
    char text[128];
    va_list args;
    va_start(args, format);
    const int length = vsnprintf(text, sizeof(text), format, args);
    va_end(args);
    assert(length > 0 && static_cast<size_t>(length) < sizeof(text));
    logs.emplace_back(text);
    events.emplace_back("log");
}

#define FAKE_HANDLERS(X) \
    X(doAllocationSnapshot, PHXN_SEL_ALLOCATION_SNAPSHOT) \
    X(doHello, PHXN_SEL_HELLO) \
    X(doQueryInfo, PHXN_SEL_QUERYINFO) \
    X(doReadRegs, PHXN_SEL_READREGS) \
    X(doBoCreate, PHXN_SEL_BOCREATE) \
    X(doBoFree, PHXN_SEL_BOFREE) \
    X(doBoImportHost, PHXN_SEL_BOIMPORTHOST) \
    X(doGemVa, PHXN_SEL_GEMVA) \
    X(doCtx, PHXN_SEL_CTX) \
    X(doSubmit, PHXN_SEL_SUBMIT) \
    X(doWaitSeq, PHXN_SEL_WAITSEQ) \
    X(doTopology, PHXN_SEL_TOPOLOGY) \
    X(doSurfGpuMark, PHXN_SEL_SURF_GPU_MARK) \
    X(doDbgSmu, PHXN_SEL_DBG_SMU) \
    X(doDbgPspRing, PHXN_SEL_DBG_PSP_RING) \
    X(doDbgPspLayout, PHX_PSP_LAYOUT_SELECTOR) \
    X(doDbgBootMemory, PHX_BOOT_MEMORY_SELECTOR) \
    X(doDbgLoadToc, PHX_PSP_LOAD_TOC_SELECTOR) \
    X(doDbgVramRead, PHXN_SEL_DBG_VRAM_READ) \
    X(doDbgPspSubmit, PHXN_SEL_DBG_PSP_SUBMIT) \
    X(doDbgFwStage, PHXN_SEL_DBG_FW_STAGE) \
    X(doDbgLoadIpFw, PHXN_SEL_DBG_PSP_LOADIPFW) \
    X(doDbgPspCtl, PHXN_SEL_DBG_PSP_CTL) \
    X(doDbgPspRaw, PHXN_SEL_DBG_PSP_RAW) \
    X(doDbgWriteReg, PHXN_SEL_DBG_WRITE_REG) \
    X(doDbgVramWrite, PHXN_SEL_DBG_VRAM_WRITE) \
    X(doDbgDoorbell, PHXN_SEL_DBG_DOORBELL) \
    X(doDbgSysMem, PHXN_SEL_DBG_SYSMEM) \
    X(doDbgAdoptQueue, PHXN_SEL_DBG_ADOPTQ) \
    X(doDbgClaim, PHXN_SEL_DBG_CLAIM)

class IOAccelPhxNativeClient {
public:
    FakeLock mutex;
    FakeLock *lock{&mutex};
    bool hello{false}, closed{false};
#include "submit-diagnostic-state.inc"
    unsigned calls{0}, reaps{0};
    uint32_t calledSelector{UINT32_MAX};
    IOExternalMethodArguments *calledArgs{nullptr};
    IOReturn handlerResult{kIOReturnSuccess};
    IOReturn externalMethod(uint32_t, IOExternalMethodArguments *, IOExternalMethodDispatch *, OSObject *, void *);
    void reapPending() {
        assert(activeLock == lock && lock->held && !closed);
        ++reaps;
        events.emplace_back("reap");
    }
    IOReturn handle(uint32_t selector, IOExternalMethodArguments *args) {
        const bool early = selector == PHXN_SEL_WAITSEQ || selector == PHXN_SEL_TOPOLOGY ||
                           selector == PHXN_SEL_SURF_GPU_MARK || selector == PHXN_SEL_ALLOCATION_SNAPSHOT;
        assert(early ? !activeLock : activeLock == lock && lock->held);
        ++calls;
        calledSelector = selector;
        calledArgs = args;
        events.emplace_back("handler");
        return handlerResult;
    }
#define DEFINE_HANDLER(name, selector) \
    IOReturn name(IOExternalMethodArguments *args) { return handle(selector, args); }
    FAKE_HANDLERS(DEFINE_HANDLER)
#undef DEFINE_HANDLER
};
#include "submit-diagnostic-method.inc"

static IOReturn call(IOAccelPhxNativeClient &client, uint32_t selector,
                     IOExternalMethodArguments *args = nullptr) {
    events.clear();
    const IOReturn result = client.externalMethod(selector, args, nullptr, nullptr, nullptr);
    assert(!activeLock && !client.mutex.held);
    const bool early = selector == PHXN_SEL_WAITSEQ || selector == PHXN_SEL_TOPOLOGY ||
                       selector == PHXN_SEL_SURF_GPU_MARK || selector == PHXN_SEL_ALLOCATION_SNAPSHOT;
    assert(early ? events == std::vector<std::string>{"handler"} :
                   !events.empty() && events.front() == "lock" && events.back() == "unlock");
    return result;
}

int main() {
    unsigned cases = 0;
    IOExternalMethodArguments arguments;
    // Values are handler fakes, including high-bit/unknown statuses: no return-code normalization.
    const IOReturn errors[] = {0xe00002c2u, 0xe00002c5u, 0xe00002bdu, 0xe00002d8u,
                              0xe00002d6u, 0x80000001u, 0xffffffffu, 0x12345678u};
    for (IOReturn error : errors) {
        logs.clear();
        IOAccelPhxNativeClient client;
        client.hello = true;
        assert(!client.submitFailureLogged);
        assert(call(client, PHXN_SEL_SUBMIT, &arguments) == kIOReturnSuccess);
        assert(logs.empty() && !client.submitFailureLogged);
        client.handlerResult = error;
        assert(call(client, PHXN_SEL_SUBMIT, &arguments) == error);
        assert(client.calls == 2 && client.reaps == 2 && client.calledArgs == &arguments);
        assert(events == (std::vector<std::string>{"lock", "reap", "handler", "log", "unlock"}));
        char expected[128];
        snprintf(expected, sizeof(expected), "PhxNative: first submit refusal IOReturn=0x%08x\n", error);
        assert(logs == std::vector<std::string>{expected} && client.submitFailureLogged);
        client.handlerResult = error ^ 1u;
        assert(call(client, PHXN_SEL_SUBMIT) == (error ^ 1u));
        client.handlerResult = kIOReturnSuccess;
        assert(call(client, PHXN_SEL_SUBMIT) == kIOReturnSuccess);
        assert(logs.size() == 1 && client.calls == 4 && client.reaps == 4);
        ++cases;
    }
    {
        logs.clear();
        IOAccelPhxNativeClient client;
        client.hello = true;
        client.handlerResult = errors[0];
        for (unsigned i = 0; i < 1024; ++i)
            assert(call(client, PHXN_SEL_SUBMIT) == errors[0]);
        assert(logs.size() == 1 && client.calls == 1024 && client.reaps == 1024);
        ++cases;
    }
    {
        logs.clear();
        IOAccelPhxNativeClient first, second;
        first.hello = second.hello = true;
        first.handlerResult = second.handlerResult = errors[1];
        assert(call(first, PHXN_SEL_SUBMIT) == errors[1]);
        assert(call(second, PHXN_SEL_SUBMIT) == errors[1]);
        assert(logs.size() == 2 && first.submitFailureLogged && second.submitFailureLogged);
        ++cases;
    }
    for (bool closed : {false, true}) {
        logs.clear();
        IOAccelPhxNativeClient client;
        client.closed = closed;
        client.hello = closed;
        assert(call(client, PHXN_SEL_SUBMIT) == kIOReturnNotReady);
        assert(!client.calls && !client.reaps && logs.size() == 1);
        assert(events == (std::vector<std::string>{"lock", "log", "unlock"}));
        assert(call(client, PHXN_SEL_SUBMIT) == kIOReturnNotReady);
        assert(!client.calls && !client.reaps && logs.size() == 1);
        ++cases;
    }
    const uint32_t selectors[] = {
#define SELECTOR(name, selector) selector,
        FAKE_HANDLERS(SELECTOR)
#undef SELECTOR
    };
    unsigned nonSubmitPaths = 0;
    for (uint32_t selector : selectors) {
        if (selector == PHXN_SEL_SUBMIT) continue;
        ++nonSubmitPaths;
        for (IOReturn result : {kIOReturnSuccess, errors[0]}) {
            logs.clear();
            IOAccelPhxNativeClient client;
            client.hello = true;
            client.handlerResult = result;
            assert(call(client, selector, &arguments) == result);
            assert(client.calls == 1 && client.calledSelector == selector && client.calledArgs == &arguments);
            assert(logs.empty() && !client.submitFailureLogged);
            ++cases;
        }
    }
    {
        logs.clear();
        IOAccelPhxNativeClient client;
        client.hello = true;
        assert(call(client, UINT32_MAX) == kIOReturnBadArgument);
        assert(!client.calls && client.reaps == 1 && logs.empty() && !client.submitFailureLogged);
        ++nonSubmitPaths;
        ++cases;
    }
    {
        logs.clear();
        IOAccelPhxNativeClient client;
        client.hello = true;
        client.handlerResult = errors[2];
        assert(call(client, PHXN_SEL_BOCREATE) == errors[2]);
        assert(logs.empty() && !client.submitFailureLogged);
        assert(call(client, PHXN_SEL_SUBMIT) == errors[2]);
        assert(logs.size() == 1 && client.calls == 2 && client.reaps == 2);
        ++cases;
    }
    assert(cases == 72 && nonSubmitPaths == 30);
    printf("{\"cases\":%u,\"non_submit_dispatch_paths\":%u,\"hardware_executed\":false,\"kernel_loaded\":false}\n",
           cases, nonSubmitPaths);
}
