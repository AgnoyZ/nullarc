#ifndef BUILD34_R3_MESA_IOKIT_H
#define BUILD34_R3_MESA_IOKIT_H

#include <mach/mach.h>

struct acd_kext;

int acd_kext_adopt_exact_iokit(mach_port_t *connection, struct acd_kext **out);

#endif
