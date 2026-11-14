# Desktop deployment admission: KDK and AuxKC approval

Status, 2026-11-14, after the owner's manual grants and a host reboot:
**candidate not installed; normal AuxKC replacement approval still unproven;
desktop capture restored; no desktop diagnostic executed**. The actual host is macOS 26.7.2,
build 25G332, x86_64. PhxBringup build 37 remains loaded and installed. The
build-39 delivery for the [checked startup adapter](DESKTOP-STARTUP-ADAPTERS.md)
is staged privately. This record concerns deployment admission, not the cause
of the earlier desktop failure or evidence of acceleration.

## Matching KDK

The exact 26.7.2 / 25G332 Kernel Debug Kit was downloaded through the
owner-requested FlClash proxy from the `dortania/KdkSupportPkg` release for that
build. The image matched both the release asset digest and its checksum file;
`hdiutil verify` also passed. The contained package passed Apple's package
signature verification and installer policy assessment: signed Apple Software,
with the Software Update, Apple Software Update Certification Authority and
Apple Root CA chain; accepted as Apple Installer.

The two component payloads target only
`/Library/Developer/KDKs/KDK_26.7.2_25G332.kdk`. Package inspection found no
install scripts; the distribution check only enforces a minimum OS version.
Installation succeeded and both package receipts were read back. The KDK's
x86_64 kernel image identity matches the live kernel and the kernel entry in
the existing BootKC. Raw identifiers remain private. This installs developer
support files; it does not deploy the candidate drivers.

The [sanitized validation record](validation/desktop-deployment-admission-20261114.json)
contains the image and package sizes and SHA-256 hashes. A root-owned verified
package copy is retained privately. The mounted download image was detached.
FlClash's temporary automatic-start preference was restored, the agent-opened
application and core exited, and effective HTTP, HTTPS, SOCKS and PAC proxies
were independently read back as disabled, matching the original effective
state. Other current application preferences were preserved.

## Three separate cache admissions

Each admission had its own private exclusive records. None consumed the
outstanding single desktop-diagnostic request.

| Admission | Cache operation | Observed refusal |
| --- | --- | --- |
| Before KDK installation | `kmutil install --volume-root / --update-all` | Exact-build 25G332 KDK missing. |
| After verified KDK installation | Same operation with the exact `--kdk` path | This was too broad: it attempted Boot/System collections for several variants. Variant kernels were missing and the release operation met the read-only system filesystem. |
| AuxKC-specific admission | `kmutil rebuild` | Detected one PhxAccel replacement, requested user approval, then returned `Biometry is not available.` |

The broad second operation was a deployment-command error, not a GPU result.
The local `kmutil(8)` manual describes `install` as updating Boot/System
collections and `rebuild` as requesting an Auxiliary collection rebuild and
authorization. The latter reached approval but did not complete it. The
presence of a matching KDK does not resolve that authorization failure.

Each failure restored the entire original PhxAccel bundle. Separate readbacks
verified the original startup plist, the full original 340-file EFI manifest,
all 24 original cache-related files, no additional collection files and
unchanged protected staging. EFI PhxBringup replacement and startup replacement
were never reached. EFI was unmounted after each verification. No collection
needed to be restored from backup because its original hashes still matched.
Candidate kext bundles and source modules remain staged and unchanged.

The final metadata/hash-only readback at 15:49 +08:00 confirmed the same boot,
loaded build 37, the old installed accelerator and original startup inputs,
all 24 cache hashes, no added collection files, unchanged staging and intact
rollback backups. EFI remained unmounted; that last readback did not remount
it or repeat its earlier complete live-file verification. Display arming was
absent and both checked display gates were zero. The competing continuation
job remained absent and disabled, the legacy startup job was absent, and no
GPU helper or reboot process was running.

## Authorization finding and continuation boundary

A small local native probe called only `LAContext.canEvaluatePolicy` in the
ordinary user and privileged execution contexts. Both had graphical-session
access. Device-owner authentication was reported available; biometric
authentication was unavailable with error -6. The probe never called
`evaluatePolicy`, supplied credentials or changed security settings. Policy
availability is not authorization, and these results do not establish a
working approval route for `kmutil rebuild`. Moving to another Terminal or
having sudo privileges has not been demonstrated to fix this failure.
Apple's [API documentation](https://developer.apple.com/documentation/localauthentication/lacontext/canevaluatepolicy(_:error:))
describes this as a prerequisite check. Its [extension approval guidance](https://support.apple.com/en-us/120363)
points to Login Items & Extensions on macOS 15 and later when a relevant system
alert asks for approval. A successful normal approval of this candidate's
AuxKC replacement has not been observed here.

### Readbacks after the owner's manual grants

The host rebooted at 16:27:54 +08:00. This was observed, not requested by the
agent. The current boot no longer matches the private delivery's preparation
boot. Neither the old preparation record nor any consumed installer was
modified to make it reusable.

At 16:29, a helper launched through the ordinary Terminal application reported
Accessibility and Screen Recording access, and an actual desktop screenshot
succeeded. At 16:37 a window-only screenshot and Accessibility readback of
System Settings also succeeded. These results establish permission for
Terminal's execution context; they do not establish permission for every
agent or privileged process. Private screenshots and UI trees are not published.
The visible Login Items & Extensions pane did not establish a candidate-specific
approval. No approval control was clicked. A later attempt to select only its
category tab found no unique target and performed no click.

A read-only query of the system kext policy database found an existing
`com.luuumi.PhxAccel` row with `allowed = 1`. The observation does not establish
when that approval was granted or authorize a claim that the new candidate is
already cached. Both the original and staged candidate's `kmutil print-diagnostics`
returned status zero while reporting `Authenticating extension failed: Bad code
signature`. The installed original separately passed strict `codesign`
verification and remains loaded. Cryptographic signature verification, system
authentication, the policy row, and a successful AuxKC replacement are distinct
observations. The diagnostic message alone is not evidence of a new absolute
installation blocker or of the desktop failure's cause.

The filtered cache inspection returned no accelerator rows. A subsequent
unfiltered inspection found the original PhxAccel image and did not find the
candidate image in its row. An empty filtered result must not be treated as
proof that no accelerator exists in the collection.

The 16:40 metadata readback found loaded build 37, no display arming, both
checked display gates at zero, and no legacy startup job. The competing
continuation remained absent and disabled after reboot. The original single
diagnostic scope was still empty. At 16:44 the graphical console reported
locked: Terminal still reported both permissions, but an actual screenshot
failed with `could not create image from display`. This is a current session
condition, not evidence that the owner's grants were lost.

A separate 16:46 hash-only review reverified all 24 original cache files and
their backups, the original installed PhxAccel and its rollback copy, all five
other pinned installed inputs, both candidate bundles, all four staged source
modules against the checkout, all nine firmware pins, and every packet pin
other than the intentionally future installed-candidate entries. The complete
340-file EFI backup still matches; live EFI was not remounted or revalidated in
this review. No fourth deployment admission, cache rebuild, GPU operation,
arming or agent-requested reboot occurred. The old packet's preparation boot
remains deliberately unchanged and differs from the current boot.

At the owner's subsequent request to disable automatic locking, automatic
display sleep and idle system sleep were set to zero for both battery and AC
power. A readback at 16:54 verified both profiles; the screen saver idle timer
was already zero and was left unchanged. Original power settings and a restore
command were saved privately. A normal user-activity wake was issued, and at
16:55 a real desktop screenshot succeeded again. Password requirements and
credentials were not changed, and no authentication bypass was used. The
earlier locked-console observation is historical rather than the current
capture status. This power-setting change is not driver deployment or AuxKC
replacement approval. A subsequent Terminal screen-capture consent alert was
accepted with its uniquely matched standard Allow button through Accessibility;
this was a capture-permission action, not driver-replacement approval.

Continuation needs a new review of the then-current source, boot, live EFI and
rollback state, with graphical-session availability rechecked. The next deployment
admission requires a normal OS approval path that actually succeeds. Do not
substitute approval-skipping flags, raw-cache activation,
security changes or a live driver load on the already-initialized current boot.
Do not replay any of the three consumed installers or the earlier build-37
operations. A future admission must be newly reviewed against the then-current
source, installed inputs and rollback state; the consumed installers also pin
their original source HEAD.

After successful installation, verify the complete installed packet, the exact
candidate in the applicable kernel collection, EFI/startup replacements and
rollback before one-shot arming and a fresh boot. Full packet verification
currently expects future candidate PhxAccel bytes and should refuse the
restored old installation. Never run the staged entry's `run` role on this
initialized boot. Preserve the existing empty diagnostic scope rather than
creating a replacement to obtain another attempt.

No new target snapshot, initialization, desktop claim, display release,
arming or reboot occurred during these admissions. The diagnostic request
remains unconsumed, and desktop behavior and its root cause remain unproven.
The earlier [623-test source validation](validation/desktop-startup-adapters-20261114.json)
is unchanged; it is not a successful installation or a hardware result.
Raw diagnostic material and user configuration remain ignored locally.
Existing license and public binary publication limits are unchanged.
