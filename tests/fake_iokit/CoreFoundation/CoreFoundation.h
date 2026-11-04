/* Test-only CoreFoundation for the fake IOKit the reference tools' harnesses compile against. C, not C++: every
 * user of tests/fake_iokit is built with -std=c11. Never ship this header.
 *
 * This umbrella exists so a tool that already includes the real <CoreFoundation/CoreFoundation.h> keeps working
 * unchanged against the fakes. It is deliberately NOT what <IOKit/IOKitLib.h> provides: that include gives
 * CFBase.h and CFString.h only, mirroring the SDK. See CFBase.h for the macOS-only failure that follows from
 * assuming the umbrella is available transitively. */
#ifndef PHX_TEST_CF_H
#define PHX_TEST_CF_H
#include <CoreFoundation/CFBase.h>
#include <CoreFoundation/CFString.h>
#include <CoreFoundation/CFNumber.h>
#endif
