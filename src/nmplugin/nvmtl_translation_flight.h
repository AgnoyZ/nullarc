/* Downstream in-flight shader translation sharing. Original implementation;
 * part of src/nmplugin under PolyForm Noncommercial 1.0.0. No GPU operations. */
#ifndef NVMTL_TRANSLATION_FLIGHT_H
#define NVMTL_TRANSLATION_FLIGHT_H
#import <Foundation/Foundation.h>
#import <CommonCrypto/CommonDigest.h>
#include <dispatch/dispatch.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define NVMTL_TRANSLATION_FLIGHT_LIMIT 64u
#ifndef NVMTL_TRANSLATION_WAIT_NS
#define NVMTL_TRANSLATION_WAIT_NS (30ll * NSEC_PER_SEC)
#endif

@interface NVMTLTranslationFlight : NSObject {
@public
    dispatch_group_t done;
    NSThread *owner;
    NSData *result;
    NSString *failure;
}
@end
@implementation NVMTLTranslationFlight
@end

typedef struct {
    unsigned long owners, joins, bypasses, timeouts;
    NSUInteger active, peak;
} NVMTLTranslationFlightStats;
static NVMTLTranslationFlightStats nvmtl_tf_stats;
static NSMutableDictionary<NSData *, NVMTLTranslationFlight *> *nvmtl_translation_flights(void) {
    static NSMutableDictionary *flights;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ flights = [NSMutableDictionary new]; });
    return flights;
}
static NVMTLTranslationFlightStats nvmtl_translation_stats(void) {
    NSMutableDictionary *flights = nvmtl_translation_flights();
    @synchronized (flights) {
        NVMTLTranslationFlightStats stats = nvmtl_tf_stats;
        stats.active = flights.count;
        return stats;
    }
}

// Length-framed full inputs, including the actual text passed to xlate. The disk
// cache filename alone is insufficient: it omits that text. This identity is
// process-local and does not change the existing disposable disk-cache format.
static NSData *nvmtl_translation_key(NSData *air, NSString *ll, NSString *stage, const char *tag) {
    if (!air || !ll || !stage || !tag) return nil;
    NSData *text = [ll dataUsingEncoding:NSUTF8StringEncoding];
    NSData *kind = [stage dataUsingEncoding:NSUTF8StringEncoding];
    if (!text || !kind) return nil;
    NSData *translator = [NSData dataWithBytes:tag length:strlen(tag)];
    CC_SHA256_CTX hash;
    CC_SHA256_Init(&hash);
    const char domain[] = "nvmtl-translation-flight-v1";
    CC_SHA256_Update(&hash, domain, sizeof domain);
    for (NSData *part in @[air, text, kind, translator]) {
        const uint64_t length = part.length;
        CC_SHA256_Update(&hash, &length, sizeof length);
        for (NSUInteger offset = 0; offset < part.length;) {
            const NSUInteger count = MIN((NSUInteger)1u << 30, part.length - offset);
            CC_SHA256_Update(&hash, (const uint8_t *)part.bytes + offset, (CC_LONG)count);
            offset += count;
        }
    }
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256_Final(digest, &hash);
    return [NSData dataWithBytes:digest length:sizeof digest];
}

// Only overlapping requests share a result. Completed entries are removed;
// this is neither an additional shader cache nor a persistent negative cache.
// Translation and disk I/O never hold the registry monitor.
static NSData *nvmtl_translation_share(NSData *key, NSString **error,
                                     NSData *(^produce)(NSString **)) {
    key = [key copy];
    NSMutableDictionary *flights = nvmtl_translation_flights();
    NVMTLTranslationFlight *flight = nil;
    BOOL isOwner = NO;
    @synchronized (flights) {
        if (key && !getenv("NVMTL_TRANSLATE_COALESCE_OFF")) {
            flight = flights[key];
            // A reentrant translator must never wait on its own invocation.
            if (flight && flight->owner == NSThread.currentThread) flight = nil;
            else if (flight) ++nvmtl_tf_stats.joins;
            else if (flights.count < NVMTL_TRANSLATION_FLIGHT_LIMIT) {
                flight = [NVMTLTranslationFlight new];
                flight->done = dispatch_group_create();
                dispatch_group_enter(flight->done);
                flight->owner = NSThread.currentThread;
                flights[key] = flight;
                isOwner = YES;
                ++nvmtl_tf_stats.owners;
                if (flights.count > nvmtl_tf_stats.peak) nvmtl_tf_stats.peak = flights.count;
            }
        }
        if (!flight) ++nvmtl_tf_stats.bypasses;
    }
    if (flight && !isOwner) {
        if (dispatch_group_wait(flight->done, dispatch_time(DISPATCH_TIME_NOW, NVMTL_TRANSLATION_WAIT_NS)) == 0) {
            @synchronized (flights) {
                if (error) *error = flight->failure;
                return flight->result;
            }
        }
        @synchronized (flights) { ++nvmtl_tf_stats.timeouts; }
        // Bypass only this request. Never remove/publish another owner's entry.
        flight = nil;
    }
    NSData *value = nil;
    NSString *why = nil;
    BOOL returned = NO;
    @try {
        value = [produce(&why) copy];
        why = [why copy];
        returned = YES;
        if (error) *error = why;
        return value;
    } @finally {
        if (flight && isOwner) {
            @synchronized (flights) {
                flight->result = returned ? value : nil;
                flight->failure = returned ? why : @"shader translation owner exited exceptionally";
                if (flights[key] == flight) [flights removeObjectForKey:key];
                // Publish even on exception so attached callers are not stranded.
                dispatch_group_leave(flight->done);
            }
        }
    }
}
#endif
