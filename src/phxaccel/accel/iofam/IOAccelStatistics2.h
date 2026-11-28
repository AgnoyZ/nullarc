// SPDX-License-Identifier: MIT
#pragma once

#include <libkern/c++/OSObject.h>
#include <libkern/c++/OSDictionary.h>
#include <IOKit/IOReturn.h>
#include <IOKit/IOReportTypes.h>
#include "iofam_types.h"

class IOGraphicsAccelerator2;

enum { kIOAccelStatistics2Size = 0x68 };

class IOAccelStatistics2 : public OSObject {
    OSDeclareDefaultStructors(IOAccelStatistics2);
public:
    virtual bool init(IOGraphicsAccelerator2 *accelerator);
    virtual void writePerformanceStats(OSDictionary *dict, bool reset);
    virtual void writeInternalStats(OSDictionary *dict, bool reset);
    virtual void setupIOReporters();
    virtual void setupChannels();
    virtual IOReturn configureReport(IOReportChannelList *channels, unsigned int action, void *result, void *destination);
    virtual IOReturn updateReport(IOReportChannelList *channels, unsigned int action, void *result, void *destination);
    virtual void _RESERVEDIOAccelStatistics0();
    virtual void _RESERVEDIOAccelStatistics1();
    virtual void _RESERVEDIOAccelStatistics2();
    virtual void _RESERVEDIOAccelStatistics3();
    virtual void _RESERVEDIOAccelStatistics4();
    virtual void _RESERVEDIOAccelStatistics5();
private:
    uint8_t _opaque[kIOAccelStatistics2Size - sizeof(OSObject)];
};

static_assert(sizeof(IOAccelStatistics2) == kIOAccelStatistics2Size, "IOAccelStatistics2 must be 0x68 bytes");
