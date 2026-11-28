// SPDX-License-Identifier: MIT
#pragma once

#include <libkern/c++/OSObject.h>

class IOAccelAllocationInfo : public OSObject {
    OSDeclareDefaultStructors(IOAccelAllocationInfo);
public:
    void declareAdditionalSystemMemory(unsigned long long size, int pid, const char *desc);
};
