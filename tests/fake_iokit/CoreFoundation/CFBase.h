/* Test-only CoreFoundation base types for the fake IOKit the reference tools' harnesses compile against.
 * C, not C++: every user of tests/fake_iokit is built with -std=c11. Never ship this header.
 *
 * The headers here copy the real SDK's include graph, because that graph is itself a gate: on macOS,
 * <IOKit/IOKitLib.h> pulls in CFBase.h and CFString.h but *not* CFNumber.h, so a tool that calls
 * CFNumberGetValue() without including <CoreFoundation/CFNumber.h> compiles and links against these fakes and
 * fails in `macos-kexts` (CI run 41789199775, tools/phxctl/mesboot.c). Keeping CFNumber out of the fake
 * IOKitLib.h make that same mistake fail in `source-tests` instead.
 *
 * The harnesses model the reference machine, so the numbers handed out by the fake registry are that machine's
 * carve-out: a tool that checks the layout against what the driver publishes (mesboot.c layout_from_driver)
 * then passes exactly as it does on that machine. Define PHX_FAKE_CF_WITHHOLD to publish nothing and exercise
 * the refusal instead. */
#ifndef PHX_TEST_CF_BASE_H
#define PHX_TEST_CF_BASE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
struct FakeCF {
    int kind;
    long long number;
};
typedef const struct FakeCF *CFTypeRef;
typedef const void *CFAllocatorRef;
typedef unsigned long CFTypeID;
#define kCFAllocatorDefault ((CFAllocatorRef)0)
__attribute__((unused)) static CFTypeID CFGetTypeID(CFTypeRef value) { return (CFTypeID)value->kind; }
__attribute__((unused)) static void CFRelease(CFTypeRef value) { (void)value; }
#endif
