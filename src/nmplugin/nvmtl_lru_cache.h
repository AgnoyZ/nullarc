/* Downstream bounded shader cache. Existing component licence applies.
 * Caller serializes all access; nodes are owned by the dictionary, links are non-owning. */
#ifndef NVMTL_LRU_CACHE_H
#define NVMTL_LRU_CACHE_H
#import <Foundation/Foundation.h>
@interface NVMTLLRUEntry : NSObject {
@public
    id<NSCopying> _key; id _value; NSUInteger _cost;
    __unsafe_unretained NVMTLLRUEntry *_prev, *_next;
}
@end
@implementation NVMTLLRUEntry
@end
@interface NVMTLLRUCache : NSObject {
    NSMutableDictionary *_entries;
    NVMTLLRUEntry *_head, *_tail;
    NSUInteger _maxEntries, _maxCost, _cost;
}
- (instancetype)initWithCountLimit:(NSUInteger)count costLimit:(NSUInteger)cost;
- (id)objectForKey:(id<NSCopying>)key;
- (void)setObject:(id)value forKey:(id<NSCopying>)key cost:(NSUInteger)cost;
- (NSUInteger)count;
- (NSUInteger)cost;
@end
@implementation NVMTLLRUCache
- (instancetype)initWithCountLimit:(NSUInteger)count costLimit:(NSUInteger)cost {
    if ((self = [super init])) { _entries = [NSMutableDictionary new]; _maxEntries = count; _maxCost = cost; }
    return self;
}
- (void)detach:(NVMTLLRUEntry *)node {
    if (node->_prev) node->_prev->_next = node->_next; else _head = node->_next;
    if (node->_next) node->_next->_prev = node->_prev; else _tail = node->_prev;
    node->_prev = nil; node->_next = nil;
}
- (void)prepend:(NVMTLLRUEntry *)node {
    node->_next = _head;
    if (_head) _head->_prev = node; else _tail = node;
    _head = node;
}
- (id)objectForKey:(id<NSCopying>)key {
    NVMTLLRUEntry *node = _entries[key];
    if (!node) return nil;
    [self detach:node]; [self prepend:node]; return node->_value;
}
- (void)setObject:(id)value forKey:(id<NSCopying>)key cost:(NSUInteger)cost {
    if (!value || !key || !_maxEntries || !cost || cost > _maxCost) return;
    NVMTLLRUEntry *node = _entries[key];
    if (node) { [self detach:node]; _cost -= node->_cost; [_entries removeObjectForKey:key]; }
    while (_tail && (_entries.count >= _maxEntries || cost > _maxCost - _cost)) {
        NVMTLLRUEntry *old = _tail;
        [self detach:old]; _cost -= old->_cost; [_entries removeObjectForKey:old->_key];
    }
    if (!node) node = [NVMTLLRUEntry new];
    node->_key = [key copyWithZone:NULL]; node->_value = value; node->_cost = cost;
    _entries[node->_key] = node; _cost += cost; [self prepend:node];
}
- (NSUInteger)count { return _entries.count; }
- (NSUInteger)cost { return _cost; }
@end
#endif
