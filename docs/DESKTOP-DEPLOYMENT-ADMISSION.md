# Desktop deployment admission: KDK and AuxKC approval

Status, 2026-11-14, after the owner's manual grants and a host reboot:
**candidate not installed; normal GUI driver approval completed, but a fifth
admission through ordinary Terminal sudo still met the biometric refusal;
no desktop diagnostic executed**. The actual host is macOS 26.7.2,
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

## Five separate cache admissions

Each admission had its own private exclusive records. None consumed the
outstanding single desktop-diagnostic request.

| Admission | Cache operation | Observed refusal |
| --- | --- | --- |
| Before KDK installation | `kmutil install --volume-root / --update-all` | Exact-build 25G332 KDK missing. |
| After verified KDK installation | Same operation with the exact `--kdk` path | This was too broad: it attempted Boot/System collections for several variants. Variant kernels were missing and the release operation met the read-only system filesystem. |
| AuxKC-specific admission | `kmutil rebuild` | Detected one PhxAccel replacement, requested user approval, then returned `Biometry is not available.` |
| Fresh current-boot admission after the owner's grants | `kmutil rebuild` from the ordinary owner Terminal, effective UID 501, with a real PTY | Returned `Operation not permitted` before driver approval; no existing sudo ticket was available. |
| After normal Settings approval, with a separately reviewed admission | Fixed `sudo /usr/bin/kmutil rebuild` from the ordinary owner's Terminal, preserving the owner's login identity and controlling terminal | Normal sudo password authentication passed; the candidate replacement was detected, but the subsequent OS authentication request returned `Biometry is not available.` with status 250. |

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

The earlier metadata/hash-only readback at 15:49 +08:00 confirmed the same boot,
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
this review. By that review, no fourth deployment admission, cache rebuild,
GPU operation, arming or agent-requested reboot had occurred. The old packet's
preparation boot remains deliberately unchanged and differs from the current boot.

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

### Fourth admission and independent recovery

At 17:07 +08:00, the ordinary Terminal again completed an actual screenshot
and Accessibility readback. Its category tab was then uniquely identified and
selected normally. The visible extension categories did not expose a Phx
approval control; no driver approval button was clicked.

A separate delivery was prepared for the current boot and synchronized source
commit `b29e09d21aefce9c912fb86ec382e985456518d7`. All ten tested production
input hashes were unchanged. Both candidate bundles, three native helpers,
nine firmware files, a fresh complete 340-file live EFI backup and all 24
cache-file backups were verified. The fresh packet has 37 input pins and seven
recovery pins. The original diagnostic scope remained empty. No old delivery,
preparation, packet or consumed admission was modified or replayed.

The fourth installer passed eight isolated CPU cases covering bundle
replacement/recovery, refusal, preservation of unknown content, Terminal
delegation, UID checking, timeout and blocked redispatch. In the real admission,
the root worker temporarily replaced PhxAccel and opened the owner's ordinary
Terminal. No existing sudo ticket was available, so the actual rebuild ran
with UID and effective UID 501. It finished between 17:16:57 and 17:17:01,
returning status 1 and `Operation not permitted`; it did not time out or reach
driver approval. This does not test whether an administrator operation in that
Terminal can complete the candidate's normal OS approval.

The worker recorded the refusal and completed rollback at 17:17:12. A separate
verifier checked the complete original accelerator, startup, live EFI manifest,
all 24 cache hashes, absence of extra collections, unchanged protected staging
and empty original diagnostic scope. EFI was unmounted afterward. No cache
backup restoration was needed. A further metadata/hash readback at 17:31:16
confirmed loaded build 37, the original cached accelerator using unfiltered
inspection, unchanged candidate inputs and backups, zero display gates, no
arming, and the competing continuation absent and disabled. This last readback
did not remount EFI or repeat the independent verifier's live EFI scan.

Read-only probes compared direct root, root in the owner's graphical bootstrap,
root with a PTY, and the combined context. All shared the same security session;
the PTY changed the actual terminal availability but did not change the public
authentication-policy availability results. A separate login-identity probe
found that those privileged contexts retained root as the login identity,
whereas the ordinary Terminal had the console owner's login identity. That
difference is a continuation hypothesis, not a demonstrated cause or approval
route. These probes did not evaluate authentication, supply credentials or
rebuild a collection. No fifth deployment was attempted.

### Direct operation of the PhxAccel approval UI

After the owner explicitly reiterated permission to use sudo and desktop
control, a normal Terminal-launched UI readback found a retained notification:
the PhxAccel system extension had been updated and required approval in
**Privacy & Security**. Its uniquely matched Open System Settings button led
to that pane, which displayed an updated-software row naming
`Unidentified - PhxAccel`. This was a different pane from the earlier extension
category view.

The exact row's standard Allow button was pressed successfully through
Accessibility, followed by one press of the resulting sheet's Unlock button.
Both actions had one uniquely matched target and returned AX success. The
subsequent readback and screenshot still showed the normal OS account-password
sheet; approval had not completed. Sudo execution was available, but no
credential was read, guessed or supplied to the sheet. A separate generic
administrator probe was cancelled without executing its read-only helper.
Screenshots and UI trees remain private.

At 17:40:39 +08:00, independent readback confirmed the original installed and
cached accelerator, original startup and other installed inputs, all 24
original cache files and backups, no added collections, unchanged staging,
loaded build 37, no display arming, zero checked display gates and the original
empty diagnostic scope. EFI remained unmounted and was not remounted in this
readback. The retained notification and Allow click do not establish that the
candidate is installed or approved. No fifth deployment, GPU diagnostic or
reboot followed these UI actions. At that stage the real driver-approval
password sheet was left open for normal account authentication.

The owner subsequently supplied the account password and explicitly requested
entry into that sheet. A one-use same-user local socket delivered it in memory
to the ordinary Terminal's Accessibility helper, which set only the uniquely
matched secure field and pressed Unlock. No password was written to a script,
file or application log. The sheet closed, and Settings changed the PhxAccel
row to a restart-required message. Independent readback at 17:46:34 confirmed
that normal GUI authentication completed while the original accelerator was
still installed and cached, all 24 cache hashes remained unchanged, and the
candidate remained absent. The policy row was allowed with flags zero. No
restart or GPU diagnostic was requested. This establishes a working normal GUI
approval route, not a successful candidate installation.

### Fifth admission after normal GUI approval

The record commit `1e92204d366b3ceafd663add3728723c7a5eb0c1` was pushed and
independently verified before preparing a separate fifth installer. The existing
delivery preparation, packet, four consumed installers and original diagnostic
scope were preserved. All ten tested production input hashes still matched.
Fresh preflight checked the complete live EFI against its backup, all 24 cache
files and backups, original installed accelerator and startup inputs, candidate
bundles, geometry, current boot and unfiltered original-cache identity. Ordinary
Terminal again completed Accessibility readback and a desktop screenshot.

Thirteen isolated CPU cases passed before deployment. They cover bundle
replacement and recovery, verification refusal, unknown-content preservation,
Terminal result/identity/command checking, refusal and timeout, blocked
redispatch, and a same-user single-use credential channel including invalid
framing. These are local installer/channel checks, not GPU validation.

The owner-authorized password was supplied only in memory to normal sudo for
one fixed `/usr/bin/kmutil rebuild` operation. It was not stored in scripts,
files, command arguments or application logs. The ordinary Terminal runner
verified the owner's UID, effective UID and login identity, and inherited its
controlling terminal. It did not expose an arbitrary privileged command route.
The one-use socket was removed afterward.

The operation ran between 17:55:50 and 17:56:29 +08:00. Sudo authentication
passed: `kmutil` checked the collection, identified one PhxAccel addition and
removal, and requested approval. It then returned status 250 and
`Biometry is not available.` without timing out. A bounded read-only system-log
review recorded the OS authentication service applying the owner's identity
to this actual request and returning error -6. The log named its request
`HumanPresence`; these host-internal details are observations, not stable public
API contracts. The earlier root-versus-owner login difference alone does not
resolve this failure. Neither that finding nor this cache refusal establishes
the cause of the earlier desktop failure.

The worker completed rollback. An independent verifier at 17:57:42 checked
the complete original accelerator and backup, installed startup inputs, all 24
original cache files and backups, no extra collections, unchanged protected
staging, and the complete 340-file live EFI and its backup. It unmounted EFI
afterward. Unfiltered inspection still found the original cached accelerator;
the candidate was absent. Build 37 remained loaded on the same boot, display
gates were zero, arming was absent and the original diagnostic scope was empty.
No cache needed restoration from backup. No EFI/startup replacement, new GPU
snapshot, initialization, desktop claim or reboot occurred.

Settings still displayed the restart-required row and no new candidate-specific
Allow control. The successful password-based Settings approval and the refused
`kmutil` authentication remain distinct observations. Repeating the same sudo
command is not an established continuation route.

Any further deployment admission requires a normal OS approval path that
actually succeeds, reviewed against then-current source, boot, GUI, live EFI,
cache and rollback state. Do not
substitute approval-skipping flags, raw-cache activation,
security changes or a live driver load on the already-initialized current boot.
Do not replay any of the five consumed installers or the earlier build-37
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
