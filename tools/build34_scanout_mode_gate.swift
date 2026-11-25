import AppKit
import CoreGraphics
import Foundation

func fail(_ reason: String) -> Never {
    fputs("build34 scanout mode gate refused: \(reason)\n", stderr)
    exit(1)
}

var onlineCount: UInt32 = 0
guard CGGetOnlineDisplayList(0, nil, &onlineCount) == .success else {
    fail("cannot enumerate online displays")
}
guard onlineCount == 1 else {
    fail("expected exactly one online display")
}

let display = CGMainDisplayID()
guard CGDisplayIsActive(display) != 0, CGDisplayIsBuiltin(display) != 0,
      CGDisplayIsInMirrorSet(display) == 0,
      let mode = CGDisplayCopyDisplayMode(display) else {
    fail("expected one active, unmirrored built-in display")
}

guard mode.width == 1280, mode.height == 800,
      mode.pixelWidth == 2560, mode.pixelHeight == 1600,
      abs(mode.refreshRate - 120.0) < 0.001,
      mode.isUsableForDesktopGUI() else {
    fail("current mode is not 1280x800 logical / 2560x1600 pixels at 120 Hz")
}

let internalScreens = NSScreen.screens.filter { screen in
    guard let number = screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber else {
        return false
    }
    return CGDisplayIsBuiltin(number.uint32Value) != 0
}
guard internalScreens.count == 1, let screen = internalScreens.first,
      screen.frame.width == 1280, screen.frame.height == 800,
      abs(screen.backingScaleFactor - 2.0) < 0.000001 else {
    fail("AppKit does not report the built-in panel at native 2x")
}

print("build34 scanout baseline: 1280x800 logical / 2560x1600 pixels / 120 Hz / 2x")
