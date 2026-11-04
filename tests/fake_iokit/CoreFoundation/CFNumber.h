/* Test-only CFNumber. Deliberately a separate header that <IOKit/IOKitLib.h> does NOT include, exactly like the
 * real SDK: a translation unit that calls CFNumberGetTypeID()/CFNumberGetValue()/CFNumberCreate() has to ask for
 * <CoreFoundation/CoreFoundation.h> or <CoreFoundation/CFNumber.h> itself. See CFBase.h for the CI failure this
 * models. */
#ifndef PHX_TEST_CF_NUMBER_H
#define PHX_TEST_CF_NUMBER_H
#include <CoreFoundation/CFBase.h>
typedef const struct FakeCF *CFNumberRef;
#define kCFNumberSInt64Type 4
#define kCFNumberIntType 9
__attribute__((unused)) static CFTypeID CFNumberGetTypeID(void) { return PHX_FAKE_CF_NUMBER_KIND; }
__attribute__((unused)) static bool CFNumberGetValue(CFNumberRef number, int type, void *out)
{
    (void)type;
    if (!number || !out) return false;
    *(uint64_t *)out = (uint64_t)number->number;
    return true;
}
__attribute__((unused)) static CFTypeRef phxFakeNumber(long long value)
{
    static struct FakeCF store;
    store.kind = (int)PHX_FAKE_CF_NUMBER_KIND;
    store.number = value;
    return &store;
}
#endif
