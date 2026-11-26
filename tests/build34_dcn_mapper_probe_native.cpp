#include "PhxDcnMapperProbe.h"

build34::dcn::MapperProbeResult instantiateNonWaitingMapperProbe(IOService *device) {
    return build34::dcn::probeDeviceMapperNoWait<IOMapper>(device);
}
