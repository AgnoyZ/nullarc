/* Test-only CoreFoundation declarations for the fake IOKit the reference tools' harnesses compile against.
 * C, not C++: every user of tests/fake_iokit is built with -std=c11. Never ship this header. */
#ifndef PHX_TEST_CF_H
#define PHX_TEST_CF_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
struct FakeCF;
typedef const struct FakeCF *CFTypeRef;
typedef const struct FakeCF *CFNumberRef;
typedef const char *CFStringRef;
typedef const void *CFAllocatorRef;
typedef unsigned long CFTypeID;
#define kCFAllocatorDefault ((CFAllocatorRef)0)
#define kCFNumberSInt64Type 4
#define CFSTR(value) (value)
CFTypeID CFGetTypeID(CFTypeRef);
CFTypeID CFNumberGetTypeID();
bool CFNumberGetValue(CFNumberRef, int, void *);
void CFRelease(CFTypeRef);
#endif
