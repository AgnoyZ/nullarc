#import <Foundation/Foundation.h>
#include <dispatch/dispatch.h>
#include <assert.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

// Keep normal tests generous; override only the timeout fixture to 50 ms.
static _Atomic int64_t testWaitNs = 10ll * NSEC_PER_SEC;
#define NVMTL_TRANSLATION_WAIT_NS atomic_load(&testWaitNs)
#include "nvmtl_translation_flight.h"

static _Atomic unsigned translations, freedOutputs, storedOutputs;
static _Atomic int translatorMode, holdTranslator;
static dispatch_semaphore_t entered, releaseTranslator;
static BOOL ready = YES, storeSucceeds;
static NSData *diskHit;
static _Atomic unsigned long gSpvHit, gSpvMiss, gSpvStored;
static _Atomic unsigned long long gSpvAdded;
static char gXlateTag[80] = "fake-translator-v1";
#define NVMTL_CACHE_SPIRV 1u
static void nvlog(const char *fmt, ...) { (void)fmt; }
static void nvtrace(const char *fmt, ...) { (void)fmt; }
static BOOL nvmtl_xlate_ready(void) { return ready; }
static NSString *nvmtl_spvcache_path(NSData *air, NSString *stage) { (void)air; (void)stage; return @"fake.spv"; }
static NSData *nvmtl_cache_data(NSString *path, unsigned kind, size_t limit) {
    (void)path; (void)kind; (void)limit; return diskHit;
}
static void nvmtl_cache_touch(const char *path) { (void)path; }
static BOOL nvmtl_cache_save(NSString *path, unsigned kind, NSData *data) {
    (void)path; (void)kind; assert(data); atomic_fetch_add(&storedOutputs, 1); return storeSucceeds;
}
static uint32_t checksum(const char *ll, const char *stage) {
    uint32_t value = 2166136261u;
    for (const char *p = ll; *p; ++p) value = (value ^ (unsigned char)*p) * 16777619u;
    for (const char *p = stage; *p; ++p) value = (value ^ (unsigned char)*p) * 16777619u;
    return value;
}
static int fakeTranslate(const char *ll, const char *stage, uint8_t **out, size_t *size, char *error, size_t cap) {
    atomic_fetch_add(&translations, 1);
    if (atomic_load(&holdTranslator)) {
        dispatch_semaphore_signal(entered);
        assert(dispatch_semaphore_wait(releaseTranslator, dispatch_time(DISPATCH_TIME_NOW, 20ll * NSEC_PER_SEC)) == 0);
    }
    *size = 20; *out = malloc(*size); assert(*out);
    uint32_t words[5] = {0x07230203u, 0x00010000u, 0u, 1u, checksum(ll, stage)};
    memcpy(*out, words, sizeof words);
    if (atomic_load(&translatorMode) == 2) @throw [NSException exceptionWithName:@"Injected" reason:@"translator" userInfo:nil];
    if (atomic_load(&translatorMode) == 1) { snprintf(error, cap, "injected translation failure"); return -1; }
    return 0;
}
static void fakeFree(uint8_t *p, size_t size) { assert(p && size == 20); free(p); atomic_fetch_add(&freedOutputs, 1); }
static int (*xlate)(const char *, const char *, uint8_t **, size_t *, char *, size_t) = fakeTranslate;
static void (*xlate_free)(uint8_t *, size_t) = fakeFree;
static int (*xlate_refl)(const char *, const char *, uint8_t **, size_t *, char *, size_t);
#include "translation_entry.inc"

static NSData *air(void) { return [@"fake AIR" dataUsingEncoding:NSUTF8StringEncoding]; }
static void verify(NSData *data, NSString *ll, NSString *stage) {
    assert(data.length == 20);
    uint32_t words[5]; memcpy(words, data.bytes, sizeof words);
    assert(words[0] == 0x07230203u && words[4] == checksum(ll.UTF8String, stage.UTF8String));
}
static void waitGroup(dispatch_group_t group) {
    assert(dispatch_group_wait(group, dispatch_time(DISPATCH_TIME_NOW, 30ll * NSEC_PER_SEC)) == 0);
}
static void waitJoins(unsigned long wanted) {
    uint64_t deadline = clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW) + 8ull * NSEC_PER_SEC;
    while (nvmtl_translation_stats().joins < wanted) {
        assert(clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW) < deadline);
        usleep(1000);
    }
}
static void freshGates(void) {
    entered = dispatch_semaphore_create(0); releaseTranslator = dispatch_semaphore_create(0);
}
static void sameShaderBatch(int mode) {
    freshGates(); atomic_store(&holdTranslator, 1); atomic_store(&translatorMode, mode);
    const unsigned before = atomic_load(&translations), beforeFree = atomic_load(&freedOutputs);
    const unsigned beforeStore = atomic_load(&storedOutputs);
    const NVMTLTranslationFlightStats stats = nvmtl_translation_stats();
    dispatch_group_t group = dispatch_group_create();
    __block _Atomic unsigned exceptions = 0;
    for (unsigned i = 0; i < 32; ++i) dispatch_group_async(group, dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{ @autoreleasepool {
        NSString *error = nil;
        @try {
            NSData *value = nvmtl_compile_library_entry(air(), @"same-text", @"fragment",
                                                        [NSString stringWithFormat:@"name-%u", i], &error);
            if (mode) {
                assert(!value);
                assert([error isEqualToString:mode == 1 ? @"injected translation failure" : @"shader translation owner exited exceptionally"]);
            } else { verify(value, @"same-text", @"fragment"); assert(!error); }
        } @catch (NSException *exception) {
            assert(mode == 2 && [exception.name isEqualToString:@"Injected"]);
            atomic_fetch_add(&exceptions, 1);
        }
    }});
    assert(dispatch_semaphore_wait(entered, dispatch_time(DISPATCH_TIME_NOW, 8ll * NSEC_PER_SEC)) == 0);
    waitJoins(stats.joins + 31);
    assert(atomic_load(&translations) == before + 1);
    dispatch_semaphore_signal(releaseTranslator); waitGroup(group);
    assert(atomic_load(&translations) == before + 1 && atomic_load(&freedOutputs) == beforeFree + 1);
    assert(atomic_load(&storedOutputs) == beforeStore + (mode ? 0u : 1u));
    assert(atomic_load(&exceptions) == (mode == 2 ? 1u : 0u));
    assert(nvmtl_translation_stats().active == 0 && nvmtl_translation_stats().owners == stats.owners + 1);
    atomic_store(&holdTranslator, 0); atomic_store(&translatorMode, 0);
    // No persistent success/failure memo in the sharing layer: a later disk miss retries.
    verify(nvmtl_compile_library_entry(air(), @"same-text", @"fragment", @"retry", NULL), @"same-text", @"fragment");
    assert(atomic_load(&translations) == before + 2);
}
static void identityTests(void) {
    NSData *base = nvmtl_translation_key(air(), @"text", @"fragment", "v1");
    assert([base isEqual:nvmtl_translation_key(air(), @"text", @"fragment", "v1")]);
    assert(![base isEqual:nvmtl_translation_key([@"other" dataUsingEncoding:NSUTF8StringEncoding], @"text", @"fragment", "v1")]);
    assert(![base isEqual:nvmtl_translation_key(air(), @"other", @"fragment", "v1")]);
    assert(![base isEqual:nvmtl_translation_key(air(), @"text", @"vertex", "v1")]);
    assert(![base isEqual:nvmtl_translation_key(air(), @"text", @"fragment", "v2")]);
    NSData *a = [@"a" dataUsingEncoding:NSUTF8StringEncoding], *ab = [@"ab" dataUsingEncoding:NSUTF8StringEncoding];
    assert(![nvmtl_translation_key(a, @"bc", @"d", "v") isEqual:nvmtl_translation_key(ab, @"c", @"d", "v")]);
    NSMutableString *longText = [NSMutableString stringWithCapacity:8193];
    for (unsigned i = 0; i < 8192; ++i) [longText appendString:@"x"];
    NSData *first = nvmtl_translation_key(air(), longText, @"fragment", "v1");
    [longText appendString:@"z"];
    assert(![first isEqual:nvmtl_translation_key(air(), longText, @"fragment", "v1")]);
    assert(!nvmtl_translation_key(nil, @"x", @"y", "v"));
}
static void differentKeysParallel(void) {
    freshGates(); atomic_store(&holdTranslator, 1);
    const unsigned before = atomic_load(&translations);
    dispatch_group_t group = dispatch_group_create();
    for (NSString *text in @[@"first-text", @"second-text"]) dispatch_group_async(group,
        dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{ @autoreleasepool {
            verify(nvmtl_compile_library_entry(air(), text, @"fragment", @"entry", NULL), text, @"fragment");
        }});
    // Both distinct owners reach the translator before either is released.
    for (unsigned i = 0; i < 2; ++i) assert(dispatch_semaphore_wait(entered, dispatch_time(DISPATCH_TIME_NOW, 8ll * NSEC_PER_SEC)) == 0);
    assert(atomic_load(&translations) == before + 2);
    for (unsigned i = 0; i < 2; ++i) dispatch_semaphore_signal(releaseTranslator);
    waitGroup(group); atomic_store(&holdTranslator, 0);
}
static void bypassTests(void) {
    unsigned before = atomic_load(&translations);
    assert(setenv("NVMTL_TRANSLATE_COALESCE_OFF", "1", 1) == 0);
    const NVMTLTranslationFlightStats stats = nvmtl_translation_stats();
    for (unsigned i = 0; i < 2; ++i) verify(nvmtl_compile_library_entry(air(), @"off", @"fragment", @"entry", NULL), @"off", @"fragment");
    assert(nvmtl_translation_stats().owners == stats.owners && nvmtl_translation_stats().bypasses == stats.bypasses + 2);
    unsetenv("NVMTL_TRANSLATE_COALESCE_OFF");
    assert(atomic_load(&translations) == before + 2);
    // Simulate a saturated registry without starting 64 artificial blocked OS threads.
    NSMutableDictionary *flights = nvmtl_translation_flights();
    @synchronized (flights) {
        for (unsigned i = 0; i < NVMTL_TRANSLATION_FLIGHT_LIMIT; ++i)
            flights[[NSData dataWithBytes:&i length:sizeof i]] = [NVMTLTranslationFlight new];
    }
    verify(nvmtl_compile_library_entry(air(), @"saturated", @"fragment", @"entry", NULL), @"saturated", @"fragment");
    assert(nvmtl_translation_stats().active == NVMTL_TRANSLATION_FLIGHT_LIMIT);
    @synchronized (flights) { [flights removeAllObjects]; }
    // Same-thread recursion bypasses its own pending entry instead of deadlocking.
    NSData *key = nvmtl_translation_key(air(), @"recursive", @"fragment", "v1");
    __block unsigned nested = 0;
    NSData *value = nvmtl_translation_share(key, NULL, ^NSData *(NSString **error) {
        (void)error;
        return nvmtl_translation_share(key, NULL, ^NSData *(NSString **innerError) {
            (void)innerError; ++nested; return air();
        });
    });
    assert(nested == 1 && [value isEqual:air()] && nvmtl_translation_stats().active == 0);
    before = atomic_load(&translations);
    uint32_t spv[5] = {0x07230203u,0,0,0,0};
    NSData *direct = [NSData dataWithBytes:spv length:sizeof spv];
    assert(nvmtl_compile_library_entry(direct, @"x", @"fragment", @"entry", NULL) == direct);
    diskHit = direct;
    assert(nvmtl_compile_library_entry(air(), @"hit", @"fragment", @"entry", NULL) == direct);
    diskHit = nil; assert(atomic_load(&translations) == before);
    ready = NO; NSString *error = nil;
    assert(!nvmtl_compile_library_entry(air(), @"x", @"fragment", @"entry", &error));
    assert([error isEqualToString:@"missing entry or translator"]); ready = YES;
    assert(!nvmtl_compile_library_entry(nil, @"x", @"fragment", @"entry", NULL));
}
static void timeoutAndMutableKey(void) {
    dispatch_semaphore_t started = dispatch_semaphore_create(0), release = dispatch_semaphore_create(0);
    dispatch_group_t group = dispatch_group_create();
    NSMutableData *key = [[@"mutable" dataUsingEncoding:NSUTF8StringEncoding] mutableCopy];
    NSData *original = [key copy];
    const NVMTLTranslationFlightStats before = nvmtl_translation_stats();
    dispatch_group_async(group, dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{ @autoreleasepool {
        assert([nvmtl_translation_share(key, NULL, ^NSData *(NSString **error) {
            (void)error; dispatch_semaphore_signal(started);
            assert(dispatch_semaphore_wait(release, dispatch_time(DISPATCH_TIME_NOW, 8ll * NSEC_PER_SEC)) == 0);
            return air();
        }) isEqual:air()]);
    }});
    assert(dispatch_semaphore_wait(started, dispatch_time(DISPATCH_TIME_NOW, 8ll * NSEC_PER_SEC)) == 0);
    ((char *)key.mutableBytes)[0] = 'z';
    atomic_store(&testWaitNs, 50ll * NSEC_PER_MSEC);
    NSData *fallback = nvmtl_translation_share(original, NULL, ^NSData *(NSString **error) {
        (void)error; return [@"fallback" dataUsingEncoding:NSUTF8StringEncoding];
    });
    assert([fallback isEqual:[@"fallback" dataUsingEncoding:NSUTF8StringEncoding]]);
    assert(nvmtl_translation_stats().timeouts == before.timeouts + 1 && nvmtl_translation_stats().active == 1);
    dispatch_semaphore_signal(release); waitGroup(group);
    atomic_store(&testWaitNs, 10ll * NSEC_PER_SEC);
    assert(nvmtl_translation_stats().active == 0);
}
static void stress(void) {
    dispatch_group_t group = dispatch_group_create();
    for (unsigned worker = 0; worker < 16; ++worker) dispatch_group_async(group,
        dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{ @autoreleasepool {
            for (unsigned i = 0; i < 100; ++i) {
                NSString *text = [NSString stringWithFormat:@"stress-%u", (i + worker) % 11];
                verify(nvmtl_compile_library_entry(air(), text, @"fragment", @"entry", NULL), text, @"fragment");
            }
        }});
    waitGroup(group);
    assert(nvmtl_translation_stats().active == 0 && nvmtl_translation_stats().peak <= NVMTL_TRANSLATION_FLIGHT_LIMIT);
}
int main(void) { @autoreleasepool {
    unsetenv("NVMTL_TRANSLATE_COALESCE_OFF"); unsetenv("NVMTL_REFLECT"); unsetenv("NVMTL_SPVCACHE_OFF");
    identityTests(); sameShaderBatch(0); sameShaderBatch(1); sameShaderBatch(2);
    differentKeysParallel(); bypassTests(); timeoutAndMutableKey(); stress();
    // Disk-cache disable is not a request to disable in-flight work sharing.
    setenv("NVMTL_SPVCACHE_OFF", "1", 1); sameShaderBatch(0); unsetenv("NVMTL_SPVCACHE_OFF");
    assert(atomic_load(&translations) == atomic_load(&freedOutputs));
    assert(nvmtl_translation_stats().active == 0);
    puts("{\"actual_entry\":true,\"same_shader_requests\":32,\"same_shader_translations\":1,"
         "\"success_failure_exception_batches\":4,\"stress_requests\":1600,\"hardware_executed\":false}");
} }
