/* Test-only CoreFoundation for the fake IOKit the reference tools' harnesses compile against.
 * C, not C++: every user of tests/fake_iokit is built with -std=c11. Never ship this header.
 *
 * The harnesses model the reference machine, so the numbers handed out here are that machine's carve-out: a tool
 * that checks the layout against what the driver publishes (mesboot.c layout_from_driver) then passes exactly as
 * it does on that machine. Define PHX_FAKE_CF_WITHHOLD to publish nothing and exercise the refusal instead. */
#ifndef PHX_TEST_CF_H
#define PHX_TEST_CF_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
struct FakeCF {
    int kind;
    long long number;
};
typedef const struct FakeCF *CFTypeRef;
typedef const struct FakeCF *CFNumberRef;
typedef const char *CFStringRef;
typedef const void *CFAllocatorRef;
typedef unsigned long CFTypeID;
#define kCFAllocatorDefault ((CFAllocatorRef)0)
#define kCFNumberSInt64Type 4
#define CFSTR(value) (value)
#define PHX_FAKE_CF_NUMBER_KIND 7u
__attribute__((unused)) static CFTypeID CFGetTypeID(CFTypeRef value) { return (CFTypeID)value->kind; }
__attribute__((unused)) static CFTypeID CFNumberGetTypeID(void) { return PHX_FAKE_CF_NUMBER_KIND; }
__attribute__((unused)) static bool CFNumberGetValue(CFNumberRef number, int type, void *out)
{
    (void)type;
    if (!number || !out) return false;
    *(uint64_t *)out = (uint64_t)number->number;
    return true;
}
__attribute__((unused)) static void CFRelease(CFTypeRef value) { (void)value; }
__attribute__((unused)) static CFTypeRef phxFakeNumber(long long value)
{
    static struct FakeCF store;
    store.kind = (int)PHX_FAKE_CF_NUMBER_KIND;
    store.number = value;
    return &store;
}
#endif
