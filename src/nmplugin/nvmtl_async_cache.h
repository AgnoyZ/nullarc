/* Original downstream bounded disposable-cache writer. Existing nmplugin
 * PolyForm Noncommercial 1.0.0 licence applies. No GPU operations. */
#ifndef NVMTL_ASYNC_CACHE_H
#define NVMTL_ASYNC_CACHE_H
#import <Foundation/Foundation.h>
#include <dispatch/dispatch.h>

#define NVMTL_ASYNC_CACHE_ENTRIES 32u
#define NVMTL_ASYNC_CACHE_BYTES (32u << 20)
typedef struct {
    unsigned long accepted, reused, skipped, completed, failed, exceptions;
    NSUInteger pending, bytes, peakEntries, peakBytes;
} NVMTLAsyncCacheStats;
static NVMTLAsyncCacheStats nvmtl_ac_stats;
static NSMutableDictionary<NSData *, NSData *> *nvmtl_async_cache_pending(void) {
    static NSMutableDictionary *pending;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ pending = [NSMutableDictionary new]; });
    return pending;
}
static dispatch_queue_t nvmtl_async_cache_queue(void) {
    static dispatch_queue_t queue;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        dispatch_queue_attr_t attr = dispatch_queue_attr_make_with_qos_class(
            DISPATCH_QUEUE_SERIAL, QOS_CLASS_UTILITY, 0);
        queue = dispatch_queue_create("nullarc.spirv-cache-writer", attr);
    });
    return queue;
}
static NVMTLAsyncCacheStats nvmtl_async_cache_stats(void) {
    NSMutableDictionary *pending = nvmtl_async_cache_pending();
    @synchronized (pending) {
        NVMTLAsyncCacheStats stats = nvmtl_ac_stats;
        stats.pending = pending.count;
        return stats;
    }
}
static NSData *nvmtl_async_cache_lookup(NSData *key) {
    if (!key) return nil;
    NSMutableDictionary *pending = nvmtl_async_cache_pending();
    @synchronized (pending) {
        NSData *data = pending[key];
        if (data) ++nvmtl_ac_stats.reused;
        return data;
    }
}
// Bounds include the active writer. No cache I/O occurs under this monitor.
// Full/oversize queues skip persistence rather than block shader compilation.
static BOOL nvmtl_async_cache_enqueue(NSData *key, NSString *path, unsigned kind, NSData *data,
                                     BOOL (^store)(NSString *, unsigned, NSData *)) {
    NSMutableDictionary *pending = nvmtl_async_cache_pending();
    @synchronized (pending) {
        if (key && pending[key]) return YES;
        const NSUInteger size = data.length;
        if (!key || !path || !kind || !size || !store || size > NVMTL_ASYNC_CACHE_BYTES ||
            pending.count >= NVMTL_ASYNC_CACHE_ENTRIES || size > NVMTL_ASYNC_CACHE_BYTES - nvmtl_ac_stats.bytes) {
            ++nvmtl_ac_stats.skipped;
            return NO;
        }
        // Foundation mutable inputs cannot change the queued snapshot/identity.
        key = [key copy]; path = [path copy]; data = [data copy];
        pending[key] = data;
        nvmtl_ac_stats.bytes += size;
        ++nvmtl_ac_stats.accepted;
        nvmtl_ac_stats.peakEntries = MAX(nvmtl_ac_stats.peakEntries, pending.count);
        nvmtl_ac_stats.peakBytes = MAX(nvmtl_ac_stats.peakBytes, nvmtl_ac_stats.bytes);
        dispatch_async(nvmtl_async_cache_queue(), ^{ @autoreleasepool {
            BOOL ok = NO, exceptional = NO;
            @try { ok = store(path, kind, data); }
            @catch (NSException *exception) { (void)exception; exceptional = YES; }
            @finally {
                @synchronized (pending) {
                    [pending removeObjectForKey:key];
                    nvmtl_ac_stats.bytes -= size;
                    if (ok) ++nvmtl_ac_stats.completed;
                    else ++nvmtl_ac_stats.failed;
                    if (exceptional) ++nvmtl_ac_stats.exceptions;
                }
            }
        }});
        return YES;
    }
}
#endif
