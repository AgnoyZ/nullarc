/* Test-only CFString. A fake CFString is a C string literal, so CFSTR() is the identity and no string API is
 * declared. Separate header for the same reason the real SDK has one: <IOKit/IOKitLib.h> pulls it in, and the
 * tools rely on CFSTR() being available after that include. */
#ifndef PHX_TEST_CF_STRING_H
#define PHX_TEST_CF_STRING_H
#include <CoreFoundation/CFBase.h>
typedef const char *CFStringRef;
#define CFSTR(value) (value)
#endif
