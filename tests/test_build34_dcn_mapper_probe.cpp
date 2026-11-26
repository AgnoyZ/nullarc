#include <cassert>
#include <cstdio>
#include <functional>

struct OSObject {
    unsigned released = 0;
    void release() { ++released; }
};

#include <IOKit/IOMapper.h>

struct IOPCIDevice {
    bool inactive = false;
    unsigned mapperLookups = 0;
    IOMapper *mapper = nullptr;
    bool isInactive() const { return inactive; }
};

IOMapper *IOMapper::copyMapperForDevice(IOPCIDevice *device) {
    ++device->mapperLookups;
    return device->mapper;
}

#include "PhxDcnMapperProbe.h"

using build34::dcn::MapperProbeResult;
using build34::dcn::probeDeviceMapper;

static void testNullOrInactiveDeviceSkipsLookup() {
    IOPCIDevice device;
    device.inactive = true;
    const MapperProbeResult nullResult = probeDeviceMapper<IOMapper>(nullptr);
    const MapperProbeResult inactiveResult = probeDeviceMapper<IOMapper>(&device);
    assert(!nullResult.attempted && !nullResult.resolved && !nullResult.activeAtProbe);
    assert(!inactiveResult.attempted && !inactiveResult.resolved && !inactiveResult.activeAtProbe);
    assert(device.mapperLookups == 0);
}

static void testUnresolvedLookup() {
    IOPCIDevice device;
    const MapperProbeResult result = probeDeviceMapper<IOMapper>(&device);
    assert(result.attempted && !result.resolved && !result.activeAtProbe);
    assert(device.mapperLookups == 1);
}

static void testResolvedMapperIsSampledAndReleased() {
    IOPCIDevice device;
    IOMapper mapper;
    device.mapper = &mapper;
    const MapperProbeResult activeResult = probeDeviceMapper<IOMapper>(&device);
    assert(activeResult.attempted && activeResult.resolved && activeResult.activeAtProbe);
    assert(device.mapperLookups == 1 && mapper.released == 1);

    mapper.inactive = true;
    mapper.released = 0;
    const MapperProbeResult inactiveResult = probeDeviceMapper<IOMapper>(&device);
    assert(inactiveResult.attempted && inactiveResult.resolved && !inactiveResult.activeAtProbe);
    assert(device.mapperLookups == 2 && mapper.released == 1);
}

int main() {
    testNullOrInactiveDeviceSkipsLookup();
    testUnresolvedLookup();
    testResolvedMapperIsSampledAndReleased();
    std::puts("[PASS] build34 mapper lookup probe CPU-only");
}
