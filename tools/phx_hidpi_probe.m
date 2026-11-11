// Read-only CoreGraphics mode inventory. No UUIDs, serials, EDID or mode writes.
#import <Foundation/Foundation.h>
#import <CoreGraphics/CoreGraphics.h>
#include <stdio.h>

static NSDictionary *describe(CGDisplayModeRef mode) {
    size_t w = CGDisplayModeGetWidth(mode), h = CGDisplayModeGetHeight(mode);
    size_t pw = CGDisplayModeGetPixelWidth(mode), ph = CGDisplayModeGetPixelHeight(mode);
    return @{ @"logical_width": @(w), @"logical_height": @(h),
              @"pixel_width": @(pw), @"pixel_height": @(ph),
              @"hi_dpi_2x": @((BOOL)(w && h && pw == w * 2 && ph == h * 2)),
              @"refresh_hz": @(CGDisplayModeGetRefreshRate(mode)),
              @"io_flags": @(CGDisplayModeGetIOFlags(mode)) };
}

int main(void) {
    @autoreleasepool {
        uint32_t count = 0;
        if (CGGetActiveDisplayList(0, NULL, &count) != kCGErrorSuccess || count > 64) return 1;
        CGDirectDisplayID ids[64];
        if (CGGetActiveDisplayList(64, ids, &count) != kCGErrorSuccess) return 1;
        NSMutableArray *displays = [NSMutableArray array];
        for (uint32_t i = 0; i < count; i++) {
            CGDisplayModeRef current = CGDisplayCopyDisplayMode(ids[i]);
            if (!current) return 2;
            CFArrayRef modes = CGDisplayCopyAllDisplayModes(ids[i],
                (__bridge CFDictionaryRef)@{ (__bridge NSString *)kCGDisplayShowDuplicateLowResolutionModes: @YES });
            if (!modes) { CGDisplayModeRelease(current); return 2; }
            NSMutableArray *items = [NSMutableArray array];
            for (CFIndex j = 0; j < CFArrayGetCount(modes); j++)
                [items addObject:describe((CGDisplayModeRef)CFArrayGetValueAtIndex(modes, j))];
            [displays addObject:@{ @"built_in": @((BOOL)CGDisplayIsBuiltin(ids[i])),
                @"vendor_id": @(CGDisplayVendorNumber(ids[i])),
                @"product_id": @(CGDisplayModelNumber(ids[i])),
                @"current": describe(current), @"modes": items }];
            CFRelease(modes);
            CGDisplayModeRelease(current);
        }
        NSDictionary *report = @{ @"schema": @1, @"read_only": @YES,
            @"os": NSProcessInfo.processInfo.operatingSystemVersionString,
            @"displays": displays, @"acceleration_verified": @NO };
        NSError *error = nil;
        NSData *json = [NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted error:&error];
        if (!json) return 3;
        if (fwrite(json.bytes, 1, json.length, stdout) != json.length || putchar('\n') == EOF) return 3;
    }
    return 0;
}
