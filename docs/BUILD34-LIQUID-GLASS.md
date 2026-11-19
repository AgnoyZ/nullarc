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

## Follow-up: the owner reports completely opaque glass

The owner subsequently clarified that the effect was **completely opaque**.
This means the preference change above did not establish a repair of the
reported appearance. Fresh stored/effective readbacks still returned reduced
transparency false, increased contrast false and reduced motion true. No
current-host, system or managed reduced-transparency override was found in
the checked preference locations. Preserve reduced motion rather than changing
another accessibility preference as a speculative workaround.

A new private finite AppKit comparison displayed regular `NSGlassEffectView`,
clear `NSGlassEffectView`, and an active within-window `NSVisualEffectView`
over the same checkerboard/color background. It was launched once through
Launch Services at normal nice priority, was visible and unoccluded at the
recorded check, and automatically closed after its eight-second observation.
Its three fresh effective-setting readings agreed. The test did not explicitly
create a Metal device or submit a Metal test command; ordinary AppKit drawing
still uses the running compositor.

Screen-capture preflight was false. No screen capture was attempted, requested
or bypassed, and the program did not measure visual output. Window visibility
and successful collection therefore do not identify which of the three
materials rendered correctly. The owner has not yet supplied a visual result
for this comparison. Do not count its collection status as a glass repair.

The before/after release-failure log queries contained the same 49 entries,
with no new entries across the comparison interval. This is a filtered log
observation, not proof of correct rendering: successful draws and every
possible failure are not covered. Earlier no-AIR reflection and imported-host
pointer/linear-view fallback messages were already present before the test;
they are not newly reproduced glass failures or a proved root cause. Existing
sampler/LOD, static-sampler reflection and visible-function-link handling were
reviewed; no driver change was selected from these observations.

ControlCenter was still the process started before the preference change.
After the comparison, only that exact console-user executable/PID was sent
one termination signal. Its automatic replacement was independently checked;
effective accessibility settings remained unchanged. This is a limited
old-process-state check. It is not a WindowServer restart, and its effect on
appearance still requires the owner's visual confirmation. Dock and ordinary
applications were not restarted.

Fresh full runtime checks before and after these actions passed: the same
boot and WindowServer remained, all four checked driver error counters stayed
zero, and the accepted build34/VBL/AML/render-clear/startup-order installation,
complete cache metadata, loaded AML/full EFI/recovery and existing daily wait
and monitoring policy were preserved. No driver, cache, EFI, startup policy,
security preference or power action was changed. Both the comparison and
finite checking worker exited.

**Current status: opaque Liquid Glass remains unresolved.** The next useful
input is the appearance of the refreshed ControlCenter and whether the same
opacity affects Dock and application glass. A new isolated rendering test or
patch should follow a discriminating result; do not replay this consumed
comparison or any historical installer, observer or reboot scope. There is
no new driver deployment or demonstrated visual/FPS/stability acceptance.

See the [opaque-glass follow-up record](validation/build34-liquid-glass-opaque-20261119.json).
