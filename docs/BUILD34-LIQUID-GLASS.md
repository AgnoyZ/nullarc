# Build34 Liquid Glass settings investigation

## November 19, 2026: effective transparency setting restored

The owner requested a Liquid Glass repair on the running default build34
installation, after the accepted startup-order boot. The request did not
include an image or distinguish missing transparency from wrong shader
output, block artifacts or an animation problem.

Before changing rendering code, two independent interfaces identified an
active display preference: the current console user's
`com.apple.universalaccess` / `reduceTransparency` value was true, and AppKit's
`NSWorkspace.accessibilityDisplayShouldReduceTransparency` also returned true.
The `NSGlassEffectView` class was available. Increased contrast was false and
reduced motion was true.

Only that user's `reduceTransparency` preference was changed to false. A
fresh reader and a separate subsequent readback both confirmed the stored
value and effective AppKit value were false. Reduced motion and increased
contrast retained their original effective values. The change did not require
a logout, WindowServer restart or machine restart.

The small native reader was built with warnings treated as errors. It verifies
that its user is the console user and reads the preference, effective AppKit
accessibility properties and class availability. It creates neither a window
nor a Metal device. The reader and all raw observations remain private and
ignored; no diagnostic application or new binary was published.

## Runtime readback

The readback verified the same OS boot and WindowServer process before and
after the preference change. Acceleration and desktop takeover remained
enabled, display hold remained released, and all four checked error counters
stayed zero:

- display-copy submission failures;
- skipped display copies;
- surface GPU timeouts;
- hang kills.

The accepted build34/VBL/AML/render-clear and startup-order installation,
PR28 daily 250 ms setting with WindowServer exclusion, and disabled resident
monitor policy were retained. No driver source, plugin, selected cache, EFI,
ACPI, startup entrypoint or security setting was changed. There was no
explicit GPU-test submission, cursor manipulation or screen capture.

## Acceptance and rollback

This verifies restoration of the stored and effective transparency setting.
It does **not** establish that Liquid Glass refraction, every application,
block-artifact repair, physical FPS or long-term stability has passed visual
or GPU testing. The earlier render-clear boot evidence remains separate;
neither result substitutes for visual acceptance.

The source already contains the earlier Liquid Glass sampler and visible-link
handling. No additional driver patch is justified solely by this setting
finding. If a visual defect remains with effective reduced transparency false,
record its precise symptom and use a fresh compatible, finite diagnostic scope
to distinguish sampling, shader linking, composition and scanout. Do not replay
consumed GPU/startup scopes or the consumed test-restart authorization.

To restore the prior preference, the current console user can run:

```sh
defaults write com.apple.universalaccess reduceTransparency -bool true
```

This is a manual rollback description, not a scheduled action. Respect any
later owner-selected accessibility setting rather than enforcing this value
from startup scripts.

See the [sanitized validation record](validation/build34-liquid-glass-settings-20261119.json).
