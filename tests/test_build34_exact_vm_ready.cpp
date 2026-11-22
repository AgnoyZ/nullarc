
static int executableMap(IOAccelPhxNativeClient &client, uint64_t va) {
    auto request = mapping(1, va);
    request.flags = PHX_AMDGPU_VM_PAGE_EXECUTABLE;
    return gem(client, request);
}

struct SubmitProbe {
    Request request;
    Ticket ticket{sentinel, sentinel, 77};
    Receipt receipt{sentinel, sentinel, 77};

    int invoke(IOAccelPhxNativeClient &client, bool typed) {
        IOLockLock(client.lock);
        const int result = typed
            ? client.submitExactReceipt(request.a.structureInput, request.a.structureInputSize, ticket, receipt)
            : client.doSubmit(&request.a);
        IOLockUnlock(client.lock);
        return result;
    }

    bool untouched() const {
        return request.a.scalarOutput[0] == sentinel && ticket.owner == sentinel && ticket.serial == sentinel &&
               ticket.slot == 77 && receipt.sequence == sentinel && receipt.generation == sentinel &&
               receipt.queue == 77;
    }
};

static void refusal(PhxBringup &service, IOAccelPhxNativeClient &client, bool typed) {
    const auto handle = client.vmid;
    const auto generation = client.vmGeneration;
    const uint64_t priorSequence = service.gSeq;
    unsigned flushes = 0;
    eventHook = [&](const char *event) { if (!std::strcmp(event, "cpu-flush")) ++flushes; };
    SubmitProbe probe;
    const int result = probe.invoke(client, typed);
    eventHook = {};
    CHECK(result == kIOReturnNotReady && probe.untouched());
    CHECK(client.vmid == handle && client.vmGeneration == generation && !client.lastSeq && !client.emitted);
    CHECK(!client.exactResourcesExposed && !client.exactRegistry.occupied() && !client.boCleanupFault);
    CHECK(!flushes && !packetWrites && service.registers.empty() && service.gSeq == priorSequence);
}

static void submitCase(bool typed, bool logicalExecutable, bool logicalData) {
    reset();
    PhxBringup service;
    IOAccelPhxNativeClient client;
    setup(service, client, typed);
    IOMemoryDescriptor executable, data, extra;
    std::vector<uint8_t> executableBytes(4096), dataBytes(4096), extraBytes(4096);
    attach(client, 1, executable, executableBytes);
    if (logicalExecutable || logicalData) service.gq[0].ready = service.gq[1].ready = false;
    if (logicalData) {
        attach(client, 2, data, dataBytes);
        attach(client, 3, extra, extraBytes);
        CHECK(map(client, 2, 0x20000) == kIOReturnSuccess);
        CHECK(map(client, 3, 0x21000) == kIOReturnSuccess);
        CHECK(!client.vmid && !data.segments && !extra.segments && !client.boCleanupFault);
        service.gq[0].ready = service.gq[1].ready = true;
    }
    CHECK(executableMap(client, 0x10000) == kIOReturnSuccess);
    service.gq[0].ready = service.gq[1].ready = true;
    if (logicalExecutable) {
        CHECK(!client.vmid && !executable.segments && !tableStorage.size());
        refusal(service, client, typed);
        auto removal = mapping(1, 0x10000);
        removal.operation = PHX_AMDGPU_VA_OP_UNMAP;
        CHECK(gem(client, removal) == kIOReturnSuccess && !client.vmid);
        CHECK(executableMap(client, 0x10000) == kIOReturnSuccess && executable.segments == 1);
    } else if (logicalData) {
        CHECK(client.vmid && client.vmGeneration && tableStorage.size() == 1 && executable.segments == 1);
        refusal(service, client, typed);
        auto first = mapping(2, 0x20000);
        first.operation = PHX_AMDGPU_VA_OP_UNMAP;
        CHECK(gem(client, first) == kIOReturnSuccess);
        refusal(service, client, typed);
        CHECK(boFree(client, 3) == kIOReturnSuccess && extra.releases == 1);
    }
    const uint64_t priorSequence = service.gSeq;
    const unsigned priorWrites = packetWrites;
    SubmitProbe probe;
    CHECK(probe.invoke(client, typed) == kIOReturnSuccess && !probe.untouched());
    CHECK(packetWrites > priorWrites && service.gSeq > priorSequence && client.lastSeq == service.gSeq);
    if (typed) {
        CHECK(probe.receipt.sequence == service.gSeq && probe.ticket.owner != sentinel &&
              probe.ticket.serial != sentinel && client.exactRegistry.occupied() == 1);
    } else {
        CHECK(probe.request.a.scalarOutput[0] == service.gSeq && !client.exactRegistry.occupied());
    }
}

int main(int argc, char **argv) {
    CHECK(argc == 2);
    const bool typed = !std::strncmp(argv[1], "typed-", 6);
    const char *kind = typed ? argv[1] + 6 : argv[1];
    const bool executable = !std::strcmp(kind, "logical-executable");
    const bool data = !std::strcmp(kind, "logical-data");
    CHECK(executable || data || !std::strcmp(kind, "resident") || !std::strcmp(kind, "mock"));
    submitCase(typed, executable, data);
    CHECK(groups == 1 && !threaded);
    std::printf("PASS %llu checks; GPU_executed=false\n", static_cast<unsigned long long>(checks.load()));
}
