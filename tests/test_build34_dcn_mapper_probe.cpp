#include <cassert>
#include <cstdio>
#include <IOKit/IOMapper.h>

#include "PhxDcnMapperProbe.h"

using build34::dcn::MapperProbeResult;
using build34::dcn::probeDeviceMapperNoWait;

namespace fake_dcn_mapper {
std::vector<IOMapper *> mapperServices;
unsigned serviceMatchingCalls = 0;
unsigned matchingServicesCalls = 0;
bool serviceMatchingFails = false;
bool setObjectFails = false;
bool matchingServicesFails = false;
bool iteratorIsValid = true;
const OSSymbol mapperIDKey("iommu-id");
}

static void resetLookupState() {
    fake_dcn_mapper::mapperServices.clear();
    fake_dcn_mapper::serviceMatchingCalls = 0;
    fake_dcn_mapper::matchingServicesCalls = 0;
    fake_dcn_mapper::serviceMatchingFails = false;
    fake_dcn_mapper::setObjectFails = false;
    fake_dcn_mapper::matchingServicesFails = false;
    fake_dcn_mapper::iteratorIsValid = true;
}

static void testNullOrInactiveDeviceSkipsLookup() {
    resetLookupState();
    IOService device;
    device.setInactive(true);
    const MapperProbeResult nullResult = probeDeviceMapperNoWait<IOMapper>(nullptr);
    const MapperProbeResult inactiveResult = probeDeviceMapperNoWait<IOMapper>(&device);
    assert(!nullResult.attempted && !nullResult.resolved && !nullResult.activeAtProbe);
    assert(!inactiveResult.attempted && !inactiveResult.resolved && !inactiveResult.activeAtProbe);
    assert(fake_dcn_mapper::serviceMatchingCalls == 0);
    assert(fake_dcn_mapper::matchingServicesCalls == 0);
}

static void testMissingMalformedOrEmptyParentDoesNotEnumerate() {
    resetLookupState();
    IOService device;
    const MapperProbeResult missing = probeDeviceMapperNoWait<IOMapper>(&device);
    OSObject wrongType;
    device.setMapperParent(&wrongType);
    const MapperProbeResult malformed = probeDeviceMapperNoWait<IOMapper>(&device);
    OSString emptyID("");
    device.setMapperParent(&emptyID);
    const MapperProbeResult empty = probeDeviceMapperNoWait<IOMapper>(&device);
    for (const MapperProbeResult result : {missing, malformed, empty}) {
        assert(result.attempted && !result.resolved && !result.activeAtProbe);
    }
    assert(fake_dcn_mapper::serviceMatchingCalls == 0);
    assert(fake_dcn_mapper::matchingServicesCalls == 0);
}

static void testNoMatchingCurrentServiceRemainsUnresolved() {
    resetLookupState();
    IOService device;
    OSString parent("mapper-target");
    device.setMapperParent(&parent);
    OSString unrelatedID("other-mapper");
    IOMapper unrelated(&unrelatedID);
    fake_dcn_mapper::mapperServices.push_back(&unrelated);
    const MapperProbeResult result = probeDeviceMapperNoWait<IOMapper>(&device);
    assert(result.attempted && !result.resolved && !result.activeAtProbe);
    assert(fake_dcn_mapper::serviceMatchingCalls == 1);
    assert(fake_dcn_mapper::matchingServicesCalls == 1);
}

static void testUniqueCurrentMapperIsSampledAndRetainedOnlyDuringProbe() {
    resetLookupState();
    IOService device;
    OSString parent("mapper-target");
    OSString mapperID("mapper-target");
    OSString unrelatedID("other-mapper");
    device.setMapperParent(&parent);
    IOMapper mapper(&mapperID);
    IOMapper unrelated(&unrelatedID);
    fake_dcn_mapper::mapperServices = {&unrelated, &mapper};
    const MapperProbeResult activeResult = probeDeviceMapperNoWait<IOMapper>(&device);
    assert(activeResult.attempted && activeResult.resolved && activeResult.activeAtProbe);
    assert(mapper.referenceCount() == 1);
    assert(parent.referenceCount() == 1);

    mapper.setInactive(true);
    const MapperProbeResult inactiveResult = probeDeviceMapperNoWait<IOMapper>(&device);
    assert(inactiveResult.attempted && inactiveResult.resolved && !inactiveResult.activeAtProbe);
    assert(mapper.referenceCount() == 1);
    assert(parent.referenceCount() == 1);
}

static void testAmbiguousCurrentMappersFailClosed() {
    resetLookupState();
    IOService device;
    OSString parent("mapper-target");
    OSString firstID("mapper-target");
    OSString secondID("mapper-target");
    device.setMapperParent(&parent);
    IOMapper first(&firstID);
    IOMapper second(&secondID);
    fake_dcn_mapper::mapperServices = {&first, &second};
    const MapperProbeResult result = probeDeviceMapperNoWait<IOMapper>(&device);
    assert(result.attempted && !result.resolved && !result.activeAtProbe);
    assert(first.referenceCount() == 1 && second.referenceCount() == 1);
}

static void testLookupAndIteratorFailuresFailClosed() {
    OSString parent("mapper-target");
    IOService device;
    device.setMapperParent(&parent);

    resetLookupState();
    fake_dcn_mapper::serviceMatchingFails = true;
    MapperProbeResult result = probeDeviceMapperNoWait<IOMapper>(&device);
    assert(result.attempted && !result.resolved && !result.activeAtProbe);
    assert(fake_dcn_mapper::matchingServicesCalls == 0);

    resetLookupState();
    fake_dcn_mapper::setObjectFails = true;
    result = probeDeviceMapperNoWait<IOMapper>(&device);
    assert(result.attempted && !result.resolved && !result.activeAtProbe);
    assert(fake_dcn_mapper::matchingServicesCalls == 0);

    resetLookupState();
    fake_dcn_mapper::matchingServicesFails = true;
    result = probeDeviceMapperNoWait<IOMapper>(&device);
    assert(result.attempted && !result.resolved && !result.activeAtProbe);

    resetLookupState();
    OSString mapperID("mapper-target");
    IOMapper mapper(&mapperID);
    fake_dcn_mapper::mapperServices = {&mapper};
    fake_dcn_mapper::iteratorIsValid = false;
    result = probeDeviceMapperNoWait<IOMapper>(&device);
    assert(result.attempted && !result.resolved && !result.activeAtProbe);
    assert(mapper.referenceCount() == 1);
}

int main() {
    testNullOrInactiveDeviceSkipsLookup();
    testMissingMalformedOrEmptyParentDoesNotEnumerate();
    testNoMatchingCurrentServiceRemainsUnresolved();
    testUniqueCurrentMapperIsSampledAndRetainedOnlyDuringProbe();
    testAmbiguousCurrentMappersFailClosed();
    testLookupAndIteratorFailuresFailClosed();
    std::puts("[PASS] build34 non-waiting mapper probe CPU-only");
}
