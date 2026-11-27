#ifndef NVMTL_VIDEO_DECODE_GATE_H
#define NVMTL_VIDEO_DECODE_GATE_H

#include <stdint.h>
#include <string.h>

static inline int nvmtl_nmxvt_registration_allowed(uint16_t vendor_id,
                                                   const char *process_name,
                                                   const char *enable_value)
{
    return vendor_id == 0x1002 && process_name && strcmp(process_name, "WindowServer") != 0 &&
           enable_value && strcmp(enable_value, "1") == 0;
}

#endif
