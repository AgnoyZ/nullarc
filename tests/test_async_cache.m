#import <Foundation/Foundation.h>
#include <assert.h>
#include <errno.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include "nvmtl_translation_flight.h"
#include "nvmtl_async_cache.h"

static _Atomic unsigned translations, frees, syncCalls;
static _Atomic int holdWriter, failSync, throwStore, staleRead;
static dispatch_semaphore_t writerEntered, writerRelease;
static int testSync(int fd) {
    atomic_fetch_add(&syncCalls, 1);
    if (atomic_load(&holdWriter)) {
        dispatch_semaphore_signal(writerEntered);
        assert(dispatch_semaphore_wait(writerRelease, dispatch_time(DISPATCH_TIME_NOW, 20ll * NSEC_PER_SEC)) == 0);
    }
    if (atomic_load(&failSync)) { errno = EIO; return -1; }
    return fsync(fd);
}
#define NVMTL_CACHE_SYNC testSync
#include "nvmtl_cache_io.h"
static NSString *directory;
static _Atomic unsigned long gSpvHit, gSpvMiss, gSpvStored;
static _Atomic unsigned long long gSpvAdded;
static char gXlateTag[80] = "fake-translator-async-v1";
static void nvlog(const char *fmt, ...) { (void)fmt; }
static void nvtrace(const char *fmt, ...) { (void)fmt; }
static BOOL nvmtl_xlate_ready(void) { return YES; }
static void drain(void) {
    dispatch_group_t barrier = dispatch_group_create();
    dispatch_group_async(barrier, nvmtl_async_cache_queue(), ^{});
    assert(dispatch_group_wait(barrier, dispatch_time(DISPATCH_TIME_NOW, 20ll * NSEC_PER_SEC)) == 0);
    assert(nvmtl_async_cache_stats().pending == 0 && nvmtl_async_cache_stats().bytes == 0);
}
static NSString *nvmtl_spvcache_path(NSData *air, NSString *stage) {
    NSData *key = nvmtl_translation_key(air, @"disk", stage, gXlateTag);
    NSMutableString *hex = [NSMutableString new];
    for (NSUInteger i = 0; i < key.length; ++i) [hex appendFormat:@"%02x", ((const uint8_t *)key.bytes)[i]];
    return [directory stringByAppendingPathComponent:hex];
}
static NSData *nvmtl_cache_data(NSString *path, unsigned kind, size_t limit) {
    // Model a miss observed just before another writer commits/retires.
    if (atomic_exchange(&staleRead, 0)) { drain(); return nil; }
    void *bytes = NULL; size_t size = 0;
    if (nvmtl_cache_load(path.fileSystemRepresentation, kind, limit, &bytes, &size)) return nil;
    return [NSData dataWithBytesNoCopy:bytes length:size freeWhenDone:YES];
}
static void nvmtl_cache_touch(const char *path) { (void)path; }
static BOOL nvmtl_cache_save(NSString *path, unsigned kind, NSData *data) {
    if (atomic_load(&throwStore)) @throw [NSException exceptionWithName:@"Injected" reason:@"store" userInfo:nil];
    return nvmtl_cache_store(path.fileSystemRepresentation, kind, data.bytes, data.length) == 0;
}
static uint32_t checksum(const char *text) {
    uint32_t value = 2166136261u;
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p) value = (value ^ *p) * 16777619u;
    return value;
}
static NSData *payload(NSString *text) {
    uint32_t words[5] = {0x07230203u, 0x10000u, 0, 1, checksum(text.UTF8String)};
    return [NSData dataWithBytes:words length:sizeof words];
}
static int fakeTranslate(const char *ll, const char *stage, uint8_t **out, size_t *size, char *error, size_t cap) {
    (void)stage; (void)error; (void)cap; atomic_fetch_add(&translations, 1);
    NSData *data = payload(@(ll)); *size = data.length; *out = malloc(*size); assert(*out);
    memcpy(*out, data.bytes, *size); return 0;
}
static void fakeFree(uint8_t *bytes, size_t size) { assert(bytes && size == 20); free(bytes); atomic_fetch_add(&frees, 1); }
static int (*xlate)(const char *, const char *, uint8_t **, size_t *, char *, size_t) = fakeTranslate;
static void (*xlate_free)(uint8_t *, size_t) = fakeFree;
static int (*xlate_refl)(const char *, const char *, uint8_t **, size_t *, char *, size_t);
#include "translation_entry.inc"

static NSData *air(NSString *text) { return [text dataUsingEncoding:NSUTF8StringEncoding]; }
static NSData *compile(NSString *text) {
    NSData *data = nvmtl_compile_library_entry(air(text), text, @"fragment", @"entry", NULL);
    assert([data isEqual:payload(text)]); return data;
}
static void gate(void) {
    writerEntered = dispatch_semaphore_create(0); writerRelease = dispatch_semaphore_create(0);
    atomic_store(&holdWriter, 1);
}
static void entered(void) {
    assert(dispatch_semaphore_wait(writerEntered, dispatch_time(DISPATCH_TIME_NOW, 8ll * NSEC_PER_SEC)) == 0);
}
static void releaseWriter(void) {
    atomic_store(&holdWriter, 0); dispatch_semaphore_signal(writerRelease);
}
static void pendingAndRetirement(void) {
    gate(); const unsigned before = atomic_load(&translations);
    dispatch_group_t caller = dispatch_group_create();
    dispatch_group_async(caller, dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{ @autoreleasepool { compile(@"pending"); }});
    entered();
    // Actual compilation returns while real fsync is still held.
    assert(dispatch_group_wait(caller, dispatch_time(DISPATCH_TIME_NOW, 8ll * NSEC_PER_SEC)) == 0);
    for (unsigned i = 0; i < 100; ++i) compile(@"pending");
    assert(atomic_load(&translations) == before + 1 && nvmtl_async_cache_stats().pending == 1);
    assert(nvmtl_async_cache_stats().reused >= 100);
    releaseWriter(); atomic_store(&staleRead, 1); compile(@"pending");
    assert(atomic_load(&translations) == before + 1);
    drain(); compile(@"pending"); assert(atomic_load(&translations) == before + 1);
}
static BOOL realStore(NSString *path, unsigned kind, NSData *data) { return nvmtl_cache_save(path, kind, data); }
static NSData *keyFor(unsigned i) { return [NSData dataWithBytes:&i length:sizeof i]; }
static NSString *pathFor(unsigned i) { return [directory stringByAppendingPathComponent:[NSString stringWithFormat:@"queue-%u", i]]; }
static void countAndSnapshot(void) {
    gate();
    NSMutableData *key = [keyFor(1000) mutableCopy], *data = [payload(@"snapshot") mutableCopy];
    NSData *originalKey = [key copy], *original = [data copy];
    NSMutableString *path = [pathFor(1000) mutableCopy]; NSString *originalPath = [path copy];
    BOOL (^store)(NSString *, unsigned, NSData *) = ^BOOL(NSString *p, unsigned k, NSData *d) { return realStore(p, k, d); };
    assert(nvmtl_async_cache_enqueue(key, path, 1, data, store)); entered();
    ((uint8_t *)key.mutableBytes)[0] ^= 0xff; ((uint8_t *)data.mutableBytes)[0] ^= 0xff; [path appendString:@"changed"];
    assert([nvmtl_async_cache_lookup(originalKey) isEqual:original]);
    for (unsigned i = 1; i < NVMTL_ASYNC_CACHE_ENTRIES; ++i)
        assert(nvmtl_async_cache_enqueue(keyFor(1000+i), pathFor(1000+i), 1, original, store));
    NVMTLAsyncCacheStats stats = nvmtl_async_cache_stats();
    assert(stats.pending == NVMTL_ASYNC_CACHE_ENTRIES && stats.bytes == original.length * NVMTL_ASYNC_CACHE_ENTRIES);
    assert(!nvmtl_async_cache_enqueue(keyFor(2000), pathFor(2000), 1, original, store));
    assert(nvmtl_async_cache_enqueue(originalKey, originalPath, 1, original, store));
    assert(nvmtl_async_cache_stats().accepted == stats.accepted);
    // Capacity pressure must still return correct shader output immediately.
    compile(@"queue-full");
    assert(nvmtl_async_cache_stats().skipped == stats.skipped + 2);
    releaseWriter(); drain();
    assert([nvmtl_cache_data(originalPath, 1, 1024) isEqual:original]);
    assert(![[NSFileManager defaultManager] fileExistsAtPath:path]);
    assert(!nvmtl_async_cache_lookup(originalKey));
}
static void byteLimit(void) { @autoreleasepool {
    gate();
    NSData *large = [NSMutableData dataWithLength:NVMTL_ASYNC_CACHE_BYTES];
    BOOL (^store)(NSString *, unsigned, NSData *) = ^BOOL(NSString *p, unsigned k, NSData *d) { return realStore(p, k, d); };
    assert(nvmtl_async_cache_enqueue(keyFor(3000), pathFor(3000), 1, large, store)); entered();
    assert(nvmtl_async_cache_stats().bytes == NVMTL_ASYNC_CACHE_BYTES);
    assert(!nvmtl_async_cache_enqueue(keyFor(3001), pathFor(3001), 1, payload(@"small"), store));
    releaseWriter(); drain();
    NSData *oversize = [NSMutableData dataWithLength:NVMTL_ASYNC_CACHE_BYTES + 1];
    assert(!nvmtl_async_cache_enqueue(keyFor(3002), pathFor(3002), 1, oversize, store));
    assert(!nvmtl_async_cache_enqueue(nil, pathFor(3002), 1, payload(@"small"), store));
    assert(nvmtl_async_cache_stats().bytes == 0);
} }
static void failureAndRetry(void) {
    NSString *path = pathFor(4000); NSData *old = payload(@"old"), *next = payload(@"new");
    assert(nvmtl_cache_save(path, 1, old));
    atomic_store(&failSync, 1); unsigned long failed = nvmtl_async_cache_stats().failed;
    assert(nvmtl_async_cache_enqueue(keyFor(4000), path, 1, next,
        ^BOOL(NSString *p, unsigned k, NSData *d) { return realStore(p, k, d); }));
    drain(); assert(nvmtl_async_cache_stats().failed == failed + 1);
    assert([nvmtl_cache_data(path, 1, 1024) isEqual:old]);
    compile(@"failure"); drain(); atomic_store(&failSync, 0);
    unsigned before = atomic_load(&translations); compile(@"failure"); drain();
    assert(atomic_load(&translations) == before + 1); compile(@"failure"); assert(atomic_load(&translations) == before + 1);
    atomic_store(&throwStore, 1); unsigned long exceptional = nvmtl_async_cache_stats().exceptions;
    compile(@"exception"); drain(); assert(nvmtl_async_cache_stats().exceptions == exceptional + 1);
    atomic_store(&throwStore, 0); compile(@"exception"); drain();
    for (NSString *file in [[NSFileManager defaultManager] contentsOfDirectoryAtPath:directory error:NULL])
        assert([file rangeOfString:@".tmp."].location == NSNotFound);
}
static void switches(void) {
    setenv("NVMTL_SPVCACHE_ASYNC_OFF", "1", 1);
    unsigned long stored = atomic_load(&gSpvStored);
    compile(@"synchronous"); assert(atomic_load(&gSpvStored) == stored + 1 && !nvmtl_async_cache_stats().pending);
    unsetenv("NVMTL_SPVCACHE_ASYNC_OFF");
    gate(); setenv("NVMTL_SPVCACHE_OFF", "1", 1);
    unsigned before = atomic_load(&translations); compile(@"read-off"); entered(); compile(@"read-off");
    assert(atomic_load(&translations) == before + 2);
    releaseWriter(); drain(); unsetenv("NVMTL_SPVCACHE_OFF");
    compile(@"read-off"); assert(atomic_load(&translations) == before + 2);
}
static void stress(void) {
    dispatch_group_t group = dispatch_group_create();
    for (unsigned worker = 0; worker < 16; ++worker) dispatch_group_async(group,
        dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{ @autoreleasepool {
            for (unsigned i = 0; i < 100; ++i) compile([NSString stringWithFormat:@"stress-%u", (worker+i)%11]);
        }});
    assert(dispatch_group_wait(group, dispatch_time(DISPATCH_TIME_NOW, 30ll * NSEC_PER_SEC)) == 0); drain();
    NVMTLAsyncCacheStats stats = nvmtl_async_cache_stats();
    assert(stats.peakEntries <= NVMTL_ASYNC_CACHE_ENTRIES && stats.peakBytes <= NVMTL_ASYNC_CACHE_BYTES);
    assert(stats.accepted == stats.completed + stats.failed);
    assert(atomic_load(&translations) == atomic_load(&frees));
}
int main(void) { @autoreleasepool {
    unsetenv("NVMTL_SPVCACHE_ASYNC_OFF"); unsetenv("NVMTL_SPVCACHE_OFF"); unsetenv("NVMTL_TRANSLATE_COALESCE_OFF"); unsetenv("NVMTL_REFLECT");
    char tmp[] = "/tmp/nullarc-async-XXXXXX"; assert(mkdtemp(tmp)); directory = @(tmp);
    pendingAndRetirement(); countAndSnapshot(); byteLimit(); failureAndRetry(); switches(); stress();
    assert([[NSFileManager defaultManager] removeItemAtPath:directory error:NULL]);
    puts("{\"actual_entry\":true,\"actual_cache_io\":true,\"returned_before_fsync\":true,"
         "\"pending_reuse_requests\":100,\"entry_limit\":32,\"payload_limit_bytes\":33554432,"
         "\"failure_retry_and_exception\":true,\"stress_requests\":1600,\"hardware_executed\":false}");
} }
