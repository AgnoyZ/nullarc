#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <objc/message.h>
#import <objc/runtime.h>
#include <dispatch/dispatch.h>
#include <sys/sysctl.h>
#include <assert.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

static void nvlog(const char *fmt, ...) { (void)fmt; }
#include "async_function_queue.inc"

static _Atomic unsigned calls, active, peak, completions, destructions;
static _Atomic int holdBuild;
static dispatch_semaphore_t buildEntered, buildRelease;
typedef void (^FunctionCompletion)(id<MTLFunction>, NSError *);
@interface TestFunction : NSObject
@property(nonatomic, copy) NSString *value;
@end
@implementation TestFunction
@end
@interface TestLibrary : NSObject
- (id<MTLFunction>)newFunctionWithName:(NSString *)name constantValues:(MTLFunctionConstantValues *)values error:(NSError **)error;
- (id<MTLFunction>)newFunctionWithDescriptor:(id)descriptor error:(NSError **)error;
- (void)newFunctionWithName:(NSString *)name constantValues:(MTLFunctionConstantValues *)values completionHandler:(FunctionCompletion)handler;
- (void)newFunctionWithDescriptor:(id)descriptor completionHandler:(FunctionCompletion)handler;
@end

// The production synchronous method reads these same real Metal constant objects.
// No shader or Metal device is created by this fixture.
static NSString *constantsValue(MTLFunctionConstantValues *values) {
    NSMutableArray *parts = [NSMutableArray new];
    for (NSString *selector in @[@"newIndexedConstantArray", @"newNamedConstantArray"]) {
        SEL sel = NSSelectorFromString(selector);
        assert(!values || [values respondsToSelector:sel]);
        NSArray *entries = values ? ((id (*)(id, SEL))objc_msgSend)(values, sel) : nil;
        for (id entry in entries) {
            Ivar key = class_getInstanceVariable([entry class], [selector isEqual:@"newIndexedConstantArray"] ? "_index" : "_name");
            Ivar type = class_getInstanceVariable([entry class], "_dataType");
            Ivar data = class_getInstanceVariable([entry class], "_data");
            assert(key && type && data);
            const uint8_t *base = (const uint8_t *)(__bridge void *)entry;
            assert(*(const NSUInteger *)(base + ivar_getOffset(type)) == MTLDataTypeInt);
            const int *payload = *(const int *const *)(base + ivar_getOffset(data)); assert(payload);
            NSString *name = [selector isEqual:@"newIndexedConstantArray"]
                ? [NSString stringWithFormat:@"i%lu", (unsigned long)*(const NSUInteger *)(base + ivar_getOffset(key))]
                : [@"n" stringByAppendingString:object_getIvar(entry, key)];
            [parts addObject:[NSString stringWithFormat:@"%@=%d", name, *payload]];
        }
    }
    return [[parts sortedArrayUsingSelector:@selector(compare:)] componentsJoinedByString:@","];
}
static MTLFunctionConstantValues *constants(int value) {
    MTLFunctionConstantValues *values = [MTLFunctionConstantValues new];
    [values setConstantValue:&value type:MTLDataTypeInt atIndex:3];
    value += 1; [values setConstantValue:&value type:MTLDataTypeInt withName:@"named"];
    return values;
}
static MTLFunctionDescriptor *descriptor(NSString *name, int value) {
    MTLFunctionDescriptor *desc = [MTLFunctionDescriptor functionDescriptor];
    desc.name = name; desc.specializedName = @"special"; desc.constantValues = constants(value);
    desc.options = MTLFunctionOptionCompileToBinary;
    return desc;
}
static id<MTLFunction> build(NSString *value, NSError **error) {
    assert(NSOperationQueue.currentQueue == nvmtl_pipeline_compile_queue());
    unsigned n = atomic_fetch_add(&active, 1) + 1, old = atomic_load(&peak);
    while (n > old && !atomic_compare_exchange_weak(&peak, &old, n)) {}
    atomic_fetch_add(&calls, 1);
    if (atomic_load(&holdBuild)) {
        dispatch_semaphore_signal(buildEntered);
        assert(dispatch_semaphore_wait(buildRelease, dispatch_time(DISPATCH_TIME_NOW, 15ll * NSEC_PER_SEC)) == 0);
    }
    if ([value containsString:@"fail"] || [value containsString:@"warn"])
        *error = [NSError errorWithDomain:@"SyntheticSpecialize" code:17 userInfo:nil];
    TestFunction *function = nil;
    if (![value containsString:@"fail"]) { function = [TestFunction new]; function.value = value; }
    atomic_fetch_sub(&active, 1);
    return (id<MTLFunction>)function;
}
@implementation TestLibrary
- (void)dealloc { atomic_fetch_add(&destructions, 1); }
- (id<MTLFunction>)newFunctionWithName:(NSString *)name constantValues:(MTLFunctionConstantValues *)values error:(NSError **)error {
    return build(name ? [NSString stringWithFormat:@"name:%@:%@", name, constantsValue(values)] : @"fail:nil-name", error);
}
- (id<MTLFunction>)newFunctionWithDescriptor:(id)desc error:(NSError **)error {
    if (![desc isKindOfClass:[MTLFunctionDescriptor class]]) return build(@"fail:invalid-descriptor", error);
    MTLFunctionDescriptor *d = desc;
    if (!d.name.length) return build(@"fail:empty-name", error);
    if ([desc isKindOfClass:[MTLIntersectionFunctionDescriptor class]])
        return build([NSString stringWithFormat:@"intersection:%@:%@", d.name, constantsValue(d.constantValues)], error);
    return build([NSString stringWithFormat:@"desc:%@:%@:%@:%lu", d.name, d.specializedName ?: @"",
                  constantsValue(d.constantValues), (unsigned long)d.options], error);
}
#include "async_function_methods.inc"
@end

static void waitGroup(dispatch_group_t group) {
    assert(dispatch_group_wait(group, dispatch_time(DISPATCH_TIME_NOW, 20ll * NSEC_PER_SEC)) == 0);
}
static void verifyCallback(id<MTLFunction> function, NSError *error, NSString *expected, BOOL warning) {
    assert(NSOperationQueue.currentQueue != nvmtl_pipeline_compile_queue());
    if ([expected containsString:@"fail"]) assert(!function && error.code == 17);
    else { assert([((TestFunction *)function).value isEqual:expected]); assert(warning ? error.code == 17 : !error); }
    atomic_fetch_add(&completions, 1);
}
static NSString *descriptorExpected(NSString *name, int value) {
    return [NSString stringWithFormat:@"desc:%@:special:i3=%d,nnamed=%d:%lu", name, value, value + 1,
            (unsigned long)MTLFunctionOptionCompileToBinary];
}
static void snapshots(TestLibrary *library) {
    NSOperationQueue *queue = nvmtl_pipeline_compile_queue(); queue.suspended = YES;
    NSMutableString *name = [NSMutableString stringWithString:@"before"];
    MTLFunctionConstantValues *values = constants(7);
    MTLFunctionDescriptor *desc = descriptor(@"before", 11);
    // Retain the originally assigned object as well as the one exposed by the descriptor.
    MTLFunctionConstantValues *descriptorValues = desc.constantValues;
    MTLIntersectionFunctionDescriptor *intersection = [MTLIntersectionFunctionDescriptor new];
    intersection.name = @"before"; intersection.constantValues = constants(13);
    MTLFunctionConstantValues *intersectionValues = intersection.constantValues;
    dispatch_group_t group = dispatch_group_create();
    dispatch_group_enter(group);
    [library newFunctionWithName:name constantValues:values completionHandler:^(id<MTLFunction> f, NSError *e) {
        verifyCallback(f, e, @"name:before:i3=7,nnamed=8", NO); dispatch_group_leave(group);
    }];
    dispatch_group_enter(group);
    [library newFunctionWithDescriptor:desc completionHandler:^(id<MTLFunction> f, NSError *e) {
        verifyCallback(f, e, descriptorExpected(@"before", 11), NO); dispatch_group_leave(group);
    }];
    dispatch_group_enter(group);
    [library newFunctionWithDescriptor:intersection completionHandler:^(id<MTLFunction> f, NSError *e) {
        verifyCallback(f, e, @"intersection:before:i3=13,nnamed=14", NO); dispatch_group_leave(group);
    }];
    assert(atomic_load(&calls) == 0 && atomic_load(&completions) == 0);
    [name setString:@"after"];
    for (MTLFunctionConstantValues *original in @[values, descriptorValues, intersectionValues]) {
        int replacement = 99;
        [original setConstantValue:&replacement type:MTLDataTypeInt atIndex:3];
        [original setConstantValue:&replacement type:MTLDataTypeInt withName:@"named"];
        [original reset];
    }
    desc.name = @"after"; desc.specializedName = @"after"; desc.constantValues = constants(99); desc.options = 0;
    intersection.name = @"after"; intersection.constantValues = constants(99);
    queue.suspended = NO; waitGroup(group); [queue waitUntilAllOperationsAreFinished];
    assert(atomic_load(&calls) == 3 && atomic_load(&completions) == 3);
}
static void boundedConcurrency(TestLibrary *library, unsigned width) {
    buildEntered = dispatch_semaphore_create(0); buildRelease = dispatch_semaphore_create(0);
    atomic_store(&holdBuild, 1);
    unsigned before = atomic_load(&calls), callbacks = atomic_load(&completions);
    dispatch_group_t returned = dispatch_group_create(), completed = dispatch_group_create();
    for (unsigned i = 0; i < width + 3; ++i) {
        dispatch_group_enter(completed);
        dispatch_group_async(returned, dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{ @autoreleasepool {
            FunctionCompletion handler = ^(id<MTLFunction> f, NSError *e) {
                verifyCallback(f, e, i % 2 ? @"name:held:" : descriptorExpected(@"held", 1), NO);
                dispatch_group_leave(completed);
            };
            if (i % 2) [library newFunctionWithName:@"held" constantValues:nil completionHandler:handler];
            else [library newFunctionWithDescriptor:descriptor(@"held", 1) completionHandler:handler];
        }});
    }
    waitGroup(returned);
    for (unsigned i = 0; i < width; ++i)
        assert(dispatch_semaphore_wait(buildEntered, dispatch_time(DISPATCH_TIME_NOW, 8ll * NSEC_PER_SEC)) == 0);
    assert(atomic_load(&active) == width && atomic_load(&calls) == before + width);
    assert(atomic_load(&completions) == callbacks);
    atomic_store(&holdBuild, 0);
    for (unsigned i = 0; i < width; ++i) dispatch_semaphore_signal(buildRelease);
    waitGroup(completed); [nvmtl_pipeline_compile_queue() waitUntilAllOperationsAreFinished];
    assert(atomic_load(&calls) == before + width + 3 && atomic_load(&active) == 0);
    assert(atomic_load(&completions) == callbacks + width + 3);
}
static void errorsAndNilHandlers(TestLibrary *library) {
    dispatch_group_t group = dispatch_group_create();
    for (NSString *name in @[@"ok", @"fail", @"warn"]) {
        dispatch_group_enter(group);
        [library newFunctionWithName:name constantValues:nil completionHandler:^(id<MTLFunction> f, NSError *e) {
            verifyCallback(f, e, [NSString stringWithFormat:@"name:%@:", name], [name isEqual:@"warn"]);
            dispatch_group_leave(group);
        }];
        dispatch_group_enter(group);
        [library newFunctionWithDescriptor:descriptor(name, 1) completionHandler:^(id<MTLFunction> f, NSError *e) {
            verifyCallback(f, e, descriptorExpected(name, 1), [name isEqual:@"warn"]); dispatch_group_leave(group);
        }];
    }
    dispatch_group_enter(group);
    [library newFunctionWithName:nil constantValues:nil completionHandler:^(id<MTLFunction> f, NSError *e) {
        verifyCallback(f, e, @"fail:nil-name", NO); dispatch_group_leave(group);
    }];
    for (id invalid in @[[NSNull null], [NSObject new], [MTLFunctionDescriptor functionDescriptor]]) {
        dispatch_group_enter(group);
        [library newFunctionWithDescriptor:invalid completionHandler:^(id<MTLFunction> f, NSError *e) {
            verifyCallback(f, e, @"fail", NO); dispatch_group_leave(group);
        }];
    }
    dispatch_group_enter(group);
    [library newFunctionWithDescriptor:nil completionHandler:^(id<MTLFunction> f, NSError *e) {
        verifyCallback(f, e, @"fail", NO); dispatch_group_leave(group);
    }];
    waitGroup(group); [nvmtl_pipeline_compile_queue() waitUntilAllOperationsAreFinished];
    unsigned before = atomic_load(&calls), callbacks = atomic_load(&completions);
    // Neither copy nor enqueue is allowed for a nil handler, even on a non-copyable input.
    [library newFunctionWithName:(id)[NSObject new] constantValues:(id)[NSObject new] completionHandler:nil];
    [library newFunctionWithDescriptor:[NSObject new] completionHandler:nil];
    [nvmtl_pipeline_compile_queue() waitUntilAllOperationsAreFinished];
    assert(atomic_load(&calls) == before && atomic_load(&completions) == callbacks);
}
static void reentrantCompletion(TestLibrary *library) {
    dispatch_group_t group = dispatch_group_create(); dispatch_group_enter(group);
    [library newFunctionWithName:@"outer" constantValues:nil completionHandler:^(id<MTLFunction> f, NSError *e) {
        verifyCallback(f, e, @"name:outer:", NO);
        dispatch_semaphore_t done = dispatch_semaphore_create(0);
        [library newFunctionWithDescriptor:descriptor(@"inner", 1) completionHandler:^(id<MTLFunction> inner, NSError *why) {
            verifyCallback(inner, why, descriptorExpected(@"inner", 1), NO); dispatch_semaphore_signal(done);
        }];
        assert(dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 8ll * NSEC_PER_SEC)) == 0);
        dispatch_group_leave(group);
    }];
    waitGroup(group);
}
static void lifetime(void) {
    for (unsigned which = 0; which < 2; ++which) {
        NSOperationQueue *queue = nvmtl_pipeline_compile_queue(); queue.suspended = YES;
        dispatch_group_t group = dispatch_group_create(); dispatch_group_enter(group);
        unsigned before = atomic_load(&destructions); __weak TestLibrary *weak;
        @autoreleasepool {
            TestLibrary *temporary = [TestLibrary new]; weak = temporary;
            FunctionCompletion handler = ^(id<MTLFunction> f, NSError *e) {
                verifyCallback(f, e, which ? descriptorExpected(@"retained", 1) : @"name:retained:i3=1,nnamed=2", NO);
                dispatch_group_leave(group);
            };
            if (which) [temporary newFunctionWithDescriptor:descriptor(@"retained", 1) completionHandler:handler];
            else [temporary newFunctionWithName:@"retained" constantValues:constants(1) completionHandler:handler];
        }
        assert(weak && atomic_load(&destructions) == before);
        queue.suspended = NO; waitGroup(group); [queue waitUntilAllOperationsAreFinished];
        uint64_t deadline = clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW) + 8ull * NSEC_PER_SEC;
        while (weak) { assert(clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW) < deadline); usleep(1000); }
        assert(atomic_load(&destructions) == before + 1);
    }
}
static void stress(TestLibrary *library) {
    dispatch_group_t callers = dispatch_group_create(), callbacks = dispatch_group_create();
    __block _Atomic unsigned received = 0;
    for (unsigned worker = 0; worker < 16; ++worker) dispatch_group_async(callers,
        dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{ @autoreleasepool {
            for (unsigned i = 0; i < 100; ++i) {
                NSString *name = [NSString stringWithFormat:@"stress-%u-%u", worker, i];
                NSString *expected = i % 2 ? [NSString stringWithFormat:@"name:%@:i3=%u,nnamed=%u", name, i, i + 1]
                                          : descriptorExpected(name, (int)i);
                dispatch_group_enter(callbacks); __block _Atomic unsigned once = 0;
                FunctionCompletion handler = ^(id<MTLFunction> f, NSError *e) {
                    assert(atomic_fetch_add(&once, 1) == 0); verifyCallback(f, e, expected, NO);
                    atomic_fetch_add(&received, 1); dispatch_group_leave(callbacks);
                };
                if (i % 2) [library newFunctionWithName:name constantValues:constants((int)i) completionHandler:handler];
                else [library newFunctionWithDescriptor:descriptor(name, (int)i) completionHandler:handler];
            }
        }});
    waitGroup(callers); waitGroup(callbacks); [nvmtl_pipeline_compile_queue() waitUntilAllOperationsAreFinished];
    assert(atomic_load(&received) == 1600 && atomic_load(&active) == 0);
}
int main(int argc, const char **argv) { @autoreleasepool {
    assert(argc == 2); unsigned width = (unsigned)atoi(argv[1]); assert(width == 1 || width == 2);
    setenv("NVMTL_PIPELINE_THREADS", argv[1], 1); assert(nvmtl_pipeline_compile_queue().maxConcurrentOperationCount == (NSInteger)width);
    TestLibrary *library = [TestLibrary new]; snapshots(library); boundedConcurrency(library, width);
    errorsAndNilHandlers(library); reentrantCompletion(library); lifetime(); stress(library);
    assert(atomic_load(&peak) == width);
    printf("{\"actual_methods\":2,\"actual_queue\":true,\"width\":%u,\"peak_active\":%u,"
           "\"snapshot_and_return_before_build\":true,\"callback_reentry\":true,\"retained_owner\":true,"
           "\"error_and_warning_propagation\":true,\"nil_handler_skips_work\":true,\"native_descriptor_subclass\":true,"
           "\"stress_requests\":1600,\"hardware_executed\":false}\n", width, atomic_load(&peak));
} }
