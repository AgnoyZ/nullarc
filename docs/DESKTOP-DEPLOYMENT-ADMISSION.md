# Desktop deployment admission: KDK and AuxKC approval

Status, 2026-11-14: **deployment blocked; candidate restored out of the installed
location; no desktop diagnostic executed**. The actual host is macOS 26.7.2,
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
alert asks for approval; a successful approval there has not been observed here.

The next deployment admission requires a normal OS approval path that actually
succeeds. Do not substitute approval-skipping flags, raw-cache activation,
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
