#pragma once

struct IODMACommand;
struct IOPCIDevice;

struct IOMapper : OSObject {
    bool inactive = false;
    bool isInactive() const { return inactive; }
    static IOMapper *copyMapperForDevice(IOPCIDevice *device);
    std::function<bool(const IODMACommand &, uint64_t, uint64_t &)> resolve;
    std::function<bool(const IODMACommand &)> confirmUnmap;
};
