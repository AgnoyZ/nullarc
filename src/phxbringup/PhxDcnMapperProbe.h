#pragma once

#include <IOKit/IOMapper.h>

namespace build34::dcn {

struct MapperProbeResult {
    bool attempted{false};
    bool resolved{false};
    bool activeAtProbe{false};
};

template<typename Mapper>
MapperProbeResult probeDeviceMapperNoWait(IOService *device) {
    if (!device || device->isInactive()) return {};
    MapperProbeResult result{true, false, false};

    OSString *mapperID = OSDynamicCast(OSString, device->getProperty("iommu-parent"));
    if (!mapperID || mapperID->getLength() == 0 || !gIOMapperIDKey) return result;

    OSDictionary *matching = IOService::serviceMatching("IOMapper");
    if (!matching) return result;
    if (!matching->setObject(gIOMapperIDKey, mapperID)) {
        matching->release();
        return result;
    }

    OSIterator *services = IOService::getMatchingServices(matching);
    matching->release();
    if (!services) return result;

    Mapper *uniqueMapper = nullptr;
    unsigned matchingMapperCount = 0;
    bool invalidMatch = false;
    while (OSObject *object = services->getNextObject()) {
        Mapper *mapper = OSDynamicCast(Mapper, object);
        if (!mapper) {
            invalidMatch = true;
            continue;
        }
        ++matchingMapperCount;
        if (matchingMapperCount == 1) {
            mapper->retain();
            uniqueMapper = mapper;
        } else {
            invalidMatch = true;
        }
    }
    const bool iteratorValid = services->isValid();
    services->release();

    if (iteratorValid && !invalidMatch && matchingMapperCount == 1 && uniqueMapper && !device->isInactive()) {
        result.resolved = true;
        result.activeAtProbe = !uniqueMapper->isInactive();
    }
    if (uniqueMapper) uniqueMapper->release();
    return result;
}

}
