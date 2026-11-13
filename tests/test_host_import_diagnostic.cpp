// Execute actual host-import preparation and diagnostic cleanup with fake descriptors.
#define PHX_NO_BO_CREATE_TEST_MAIN
#include "test_bo_create.cpp"
#include <cstdio>
#include <string>
#include <vector>

static std::vector<std::string> messages;
static void capture(const char *format, va_list arguments) {
    char text[1024]; const int length = vsnprintf(text, sizeof(text), format, arguments);
    assert(length > 0 && size_t(length) < sizeof(text)); messages.emplace_back(text);
}
int main(int argc, char **argv) {
    assert(argc == 2); const std::string test = argv[1];
    IOAccelPhxNativeClient client; logHook = capture;
    IOExternalMethodArguments args; args.scalarInputCount = args.scalarOutputCount = 4;
    args.scalarInput[0] = 0x10000; args.scalarInput[1] = 4096;
    IOReturn expected = kIOReturnSuccess;
    if (test == "host-protection") pinResult = expected = 2;
    else if (test == "host-unknown-result") pinResult = expected = static_cast<int>(0xe0001234u);
    else if (test == "host-descriptor") { allocFail = true; expected = kIOReturnNoMemory; }
    else if (test == "host-budget-silent") { client.hostUsed = UINT64_MAX; expected = kIOReturnNoMemory; }
    else if (test == "host-invalid-silent") { args.scalarInput[2] = 1; expected = kIOReturnBadArgument; }
    else if (test == "host-cap-stages" || test == "host-independent-client" || test == "host-success-after-failure")
        pinResult = expected = 2;
    else assert(test == "host-success-silent");
    const unsigned attempts = test == "host-cap-stages" || test == "host-independent-client" ? 300 : 1;
    const uint64_t before = client.hostUsed;
    for (unsigned i = 0; i < attempts; ++i) {
        assert(client.doBoImportHost(&args) == expected);
        if (expected != kIOReturnSuccess) {
            assert(client.hostUsed == before && !client.bos[1].md);
            for (auto value : args.scalarOutput) assert(value == 77);
        }
    }
    if (test == "host-cap-stages") {
        assert(messages.size() == 4 && releases == 300 && prepares == 300 && allocations == 300);
        allocFail = true;
        for (unsigned i = 0; i < 300; ++i) assert(client.doBoImportHost(&args) == kIOReturnNoMemory);
        assert(messages.size() == 8 && releases == 300 && prepares == 300 && allocations == 600);
        assert(client.allocationFailureLogs[1] == 4 && client.allocationFailureLogs[2] == 4);
    } else if (test == "host-independent-client") {
        IOAccelPhxNativeClient other;
        assert(other.doBoImportHost(&args) == 2 && messages.size() == 5);
        assert(other.allocationFailureLogs[2] == 1 && client.allocationFailureLogs[2] == 4);
    } else if (test == "host-success-after-failure") {
        assert(messages.size() == 1 && releases == 1); pinResult = kIOReturnSuccess;
        assert(client.doBoImportHost(&args) == kIOReturnSuccess && messages.size() == 1);
        assert(client.hostUsed == 4096 && client.bos[1].host && prepares == 2 && releases == 1);
    } else if (expected == kIOReturnSuccess) {
        assert(messages.empty() && client.hostUsed == 4096 && client.bos[1].md && client.bos[1].host);
        assert(args.scalarOutput[0] == 1 && args.scalarOutput[1] == 4096 && !args.scalarOutput[2] && !args.scalarOutput[3]);
        assert(prepares == 1 && !releases && !zeroes);
    } else if (test == "host-invalid-silent" || test == "host-budget-silent") {
        assert(messages.empty() && !allocations && !prepares && !releases);
    } else {
        assert(messages.size() == 1 && allocations == 1);
        if (test == "host-descriptor") {
            assert(!prepares && !releases && messages[0].find("stage=descriptor") != std::string::npos);
        } else {
            assert(prepares == 1 && releases == 1 && messages[0].find("stage=prepare") != std::string::npos);
            assert(messages[0].find(test == "host-protection" ? "IOReturn=0x00000002" : "IOReturn=0xe0001234") != std::string::npos);
        }
    }
    for (const auto &message : messages) {
        assert(message.rfind("PhxAlloc: v1 op=BO_IMPORT_HOST ", 0) == 0);
        assert(message.find("bytes=4096 direction=inout") != std::string::npos);
        assert(message.find("limit=4") != std::string::npos);
        for (const char *forbidden : {"0x10000", "va=", "ptr=", "pid=", "task="})
            assert(message.find(forbidden) == std::string::npos);
    }
    assert(!client.allocationFailureLogs[0] && !zeroes);
    std::cout << "{\"case\":\"" << test << "\",\"passed\":true,\"hardware_executed\":false}\n";
}
