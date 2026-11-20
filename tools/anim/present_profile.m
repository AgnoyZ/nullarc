// SPDX-License-Identifier: MIT
// A finite CPU-drawn, nonactivating display stimulus; no explicit Metal API.
// Launch the containing LSUIElement app through Launch Services with a private
// result path. AppKit/WindowServer can use the installed accelerated stack.
#import <Cocoa/Cocoa.h>
#import <CoreGraphics/CoreGraphics.h>

@interface PresentProfileView : NSView
@property unsigned frameCount;
@property unsigned drawCount;
@end
@implementation PresentProfileView
- (BOOL)isOpaque { return YES; }
- (void)drawRect:(NSRect)rect
{
    (void)rect;
    ++_drawCount;
    [NSColor.blackColor setFill]; NSRectFill(self.bounds);
    [NSColor.cyanColor setFill];
    NSRectFill(NSMakeRect((_frameCount % 60) * 4, 0, 48, 120));
}
@end

int main(int argc, const char **argv)
{
    @autoreleasepool {
        if (argc != 2) return 64;
        NSString *result = [NSString stringWithUTF8String:argv[1]];
        if (!result.isAbsolutePath || [[NSFileManager defaultManager] fileExistsAtPath:result]) return 65;
        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
        NSPanel *panel = [[NSPanel alloc] initWithContentRect:NSMakeRect(80, 80, 300, 120)
            styleMask:NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
            backing:NSBackingStoreBuffered defer:NO];
        panel.ignoresMouseEvents = YES; panel.level = NSFloatingWindowLevel;
        panel.hidesOnDeactivate = NO; panel.releasedWhenClosed = NO;
        PresentProfileView *view = [[PresentProfileView alloc] initWithFrame:panel.contentView.bounds];
        panel.contentView = view;
        [panel orderFrontRegardless];
        __block unsigned visible = 0, checked = 0;
        __block BOOL allOnscreen = YES;
        NSTimeInterval start = NSProcessInfo.processInfo.systemUptime;
        id activity = [NSProcessInfo.processInfo beginActivityWithOptions:NSActivityUserInitiated
            reason:@"Finite display-copy measurement"];
        NSTimer *timer = [NSTimer timerWithTimeInterval:1.0/60 repeats:YES block:^(NSTimer *t) {
            ++view.frameCount; view.needsDisplay = YES;
            if (view.frameCount % 30 == 0) {
                NSArray *windows = CFBridgingRelease(CGWindowListCopyWindowInfo(
                    kCGWindowListOptionIncludingWindow, (CGWindowID)panel.windowNumber));
                BOOL onscreen = windows.count == 1 && [windows[0][(id)kCGWindowIsOnscreen] boolValue];
                ++checked; if (onscreen) ++visible; else allOnscreen = NO;
            }
            if (NSProcessInfo.processInfo.systemUptime - start >= 12.0) {
                [t invalidate];
                NSDictionary *record = @{@"timer_callbacks":@(view.frameCount), @"draw_callbacks":@(view.drawCount),
                    @"onscreen_checks":@(checked), @"onscreen_passed":@(visible),
                    @"all_onscreen":@(allOnscreen && checked > 0),
                    @"elapsed_seconds":@(NSProcessInfo.processInfo.systemUptime-start),
                    @"explicit_Metal_API":@NO, @"physical_FPS_measured":@NO};
                NSData *data = [NSJSONSerialization dataWithJSONObject:record options:0 error:NULL];
                BOOL saved = data && [data writeToFile:result options:NSDataWritingWithoutOverwriting error:NULL];
                [panel orderOut:nil]; [panel close];
                [NSProcessInfo.processInfo endActivity:activity];
                if (!saved) exit(66);
                [NSApp terminate:nil];
            }
        }];
        [[NSRunLoop mainRunLoop] addTimer:timer forMode:NSRunLoopCommonModes];
        [NSApp run];
    }
    return 0;
}
