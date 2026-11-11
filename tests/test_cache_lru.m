#import <Foundation/Foundation.h>
#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "nvmtl_lru_cache.h"
static unsigned calls;
static NSData *nvmtl_address_shader_g_uncached(const void *data, size_t len, uint32_t flags, uint32_t *info) {
    calls++; for (unsigned i = 0; i < 4; i++) info[i] = flags + i;
    return flags == 99 ? nil : [NSData dataWithBytes:data length:len];
}
#include "cache_wrapper.inc"
int main(void) { @autoreleasepool {
    NVMTLLRUCache *cache = [[NVMTLLRUCache alloc] initWithCountLimit:3 costLimit:10];
    [cache setObject:@1 forKey:@"a" cost:3]; [cache setObject:@2 forKey:@"b" cost:3];
    [cache setObject:@3 forKey:@"c" cost:3]; assert(cache.count == 3 && cache.cost == 9);
    assert([[cache objectForKey:@"a"] isEqual:@1]);
    [cache setObject:@4 forKey:@"d" cost:3]; assert(![cache objectForKey:@"b"]);
    [cache setObject:@5 forKey:@"a" cost:8]; assert(cache.count == 1 && cache.cost == 8);
    assert([[cache objectForKey:@"a"] isEqual:@5]);
    [cache setObject:@6 forKey:@"oversize" cost:11]; assert(cache.count == 1 && cache.cost == 8);
    [cache setObject:@6 forKey:@"a" cost:11]; assert([[cache objectForKey:@"a"] isEqual:@5]);
    [cache setObject:nil forKey:@"a" cost:1]; assert(cache.cost == 8);
    NSMutableData *key = [NSMutableData dataWithBytes:"abc" length:3];
    NSData *original = [key copy]; [cache setObject:@7 forKey:key cost:1];
    ((char *)key.mutableBytes)[0] = 'x'; assert([[cache objectForKey:original] isEqual:@7]);
    NVMTLLRUCache *zero = [[NVMTLLRUCache alloc] initWithCountLimit:0 costLimit:1];
    [zero setObject:@1 forKey:@1 cost:1]; assert(zero.count == 0);
    NVMTLLRUCache *huge = [[NVMTLLRUCache alloc] initWithCountLimit:3 costLimit:NSUIntegerMax];
    [huge setObject:@1 forKey:@1 cost:NSUIntegerMax - 1];
    [huge setObject:@2 forKey:@2 cost:2]; assert(huge.count == 1 && huge.cost == 2);
    __weak NSObject *weak;
    @autoreleasepool {
        NSObject *value = [NSObject new]; weak = value;
        NVMTLLRUCache *one = [[NVMTLLRUCache alloc] initWithCountLimit:1 costLimit:2];
        [one setObject:value forKey:@1 cost:1]; value = nil; assert(weak);
        [one setObject:@2 forKey:@2 cost:1];
    }
    assert(!weak);
    NVMTLLRUCache *random = [[NVMTLLRUCache alloc] initWithCountLimit:7 costLimit:23];
    NSMutableArray *order = [NSMutableArray new]; NSMutableDictionary *values = [NSMutableDictionary new];
    NSUInteger total = 0; uint32_t rng = 7;
    for (unsigned i = 0; i < 20000; ++i) {
        rng = rng * 1664525u + 1013904223u; NSNumber *k = @(rng % 15);
        NSUInteger cost = (rng >> 8) % 27;
        if (rng & 0x80000000u) {
            [random setObject:@(i) forKey:k cost:cost];
            if (cost && cost <= 23) {
                if (values[k]) { total -= [values[k][1] unsignedIntegerValue]; [order removeObject:k]; [values removeObjectForKey:k]; }
                while (order.count && (order.count >= 7 || cost > 23 - total)) {
                    NSNumber *old = order.lastObject; total -= [values[old][1] unsignedIntegerValue]; [values removeObjectForKey:old]; [order removeLastObject];
                }
                values[k] = @[@(i), @(cost)]; [order insertObject:k atIndex:0]; total += cost;
            }
        } else {
            id hit = [random objectForKey:k]; assert((!hit && !values[k]) || [hit isEqual:values[k][0]]);
            if (values[k]) { [order removeObject:k]; [order insertObject:k atIndex:0]; }
        }
        assert(random.count == order.count && random.cost == total);
    }
    uint32_t info[4], keyWord = 42;
    assert(nvmtl_address_shader_g(&keyWord, sizeof keyWord, 7, info));
    unsigned before = calls; memset(info, 0, sizeof info);
    assert(nvmtl_address_shader_g(&keyWord, sizeof keyWord, 7, info));
    assert(calls == before && info[0] == 7 && info[3] == 10);
    assert(!nvmtl_address_shader_g(&keyWord, sizeof keyWord, 99, info));
    before = calls; assert(!nvmtl_address_shader_g(&keyWord, sizeof keyWord, 99, info));
    assert(calls == before && info[0] == 99 && info[3] == 102);
    for (uint32_t k = 0; k < 4100; ++k) nvmtl_address_shader_g(&k, sizeof k, 0, NULL);
    keyWord = 4099; before = calls; assert(nvmtl_address_shader_g(&keyWord, sizeof keyWord, 0, info)); assert(calls == before);
    keyWord = 0; nvmtl_address_shader_g(&keyWord, sizeof keyWord, 0, info); assert(calls == before + 1);
    puts("{\"lru_operations\": 20000, \"actual_wrapper\": true, \"hardware_executed\": false}");
} }
