#pragma once

#include <IOKit/IOMapper.h>

namespace build34::dcn {

struct MapperProbeResult {
    bool attempted{false};
    bool resolved{false};
    bool activeAtProbe{false};
};

template<typename Mapper>
MapperProbeResult probeDeviceMapper(IOPCIDevice *device) {
    if (!device || device->isInactive()) return {};
    MapperProbeResult result{true, false, false};
    auto *mapper = Mapper::copyMapperForDevice(device);
    result.resolved = mapper != nullptr;
    result.activeAtProbe = mapper && !mapper->isInactive();
    if (mapper) mapper->release();
    return result;
}

}
