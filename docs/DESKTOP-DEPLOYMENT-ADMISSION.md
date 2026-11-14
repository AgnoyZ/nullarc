# Desktop deployment admission: KDK and AuxKC publication

Status, 2026-11-14, after the original single-request reboot diagnostic:
**build 39 and the exact candidate accelerator loaded; initializer stopped at
queue-selection readback; recovery disarmed the test and a later boot is observed**.
The actual host is macOS 26.7.2, build 25G332, x86_64.
PhxBringup build 39 is loaded on the current boot. The build-39 delivery
for the [checked startup adapter](DESKTOP-STARTUP-ADAPTERS.md) is installed,
with complete original rollback copies retained. The original one-attempt
request is consumed. This identifies the failing check, not the physical cause
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

## Ten separate cache admissions

Each admission had its own private exclusive records. None consumed the
outstanding single desktop-diagnostic request.

| Admission | Cache operation | Observed refusal |
| --- | --- | --- |
| Before KDK installation | `kmutil install --volume-root / --update-all` | Exact-build 25G332 KDK missing. |
| After verified KDK installation | Same operation with the exact `--kdk` path | This was too broad: it attempted Boot/System collections for several variants. Variant kernels were missing and the release operation met the read-only system filesystem. |
| AuxKC-specific admission | `kmutil rebuild` | Detected one PhxAccel replacement, requested user approval, then returned `Biometry is not available.` |
| Fresh current-boot admission after the owner's grants | `kmutil rebuild` from the ordinary owner Terminal, effective UID 501, with a real PTY | Returned `Operation not permitted` before driver approval; no existing sudo ticket was available. |
| After normal Settings approval, with a separately reviewed admission | Fixed `sudo /usr/bin/kmutil rebuild` from the ordinary owner's Terminal, preserving the owner's login identity and controlling terminal | Normal sudo password authentication passed; the candidate replacement was detected, but the subsequent OS authentication request returned `Biometry is not available.` with status 250. |
| First fully manual admission | Fixed `sudo -- /usr/bin/kmutil rebuild`, with all three standard streams attached directly to native owner Terminal | The bounded 480-second owner runner expired without a successful result; the consumed admission was rolled back and independently verified. |
| Fresh fully manual admission after the owner requested reopening | Same fixed command, in a distinct native Terminal window with direct owner password entry | Sudo authentication passed and the candidate replacement was detected; the subsequent OS authentication again returned `Biometry is not available.` with status 250. |
| Eighth, after the owner selected the upstream installer route | Private `kmutil create -n aux` with matching KDK and explicitly authorized `-z` | Status 71: `AppleCentauriManager` depends on unavailable x86_64 `AppleEmbeddedPCIE`; no cache published, complete rollback independently verified. |
| Ninth, with only the existing auxiliary identifiers selected | Same create route with `--explicit-only` and an identifier list for the other three AuxKC extensions | Create returned zero, but the candidate omitted PhxAccel. Exact inspection refused publication; complete rollback independently verified. |
| Tenth, with PhxAccel also in the explicit identifier list | Same private create, explicit Boot/System/Aux inspection, backup verification and atomic publication | Status zero; exact candidate and all 415 unrelated cached extensions verified. AuxKC, candidate EFI driver and next-boot startup entry installed and independently read back. |

The broad second operation was a deployment-command error, not a GPU result.
The local `kmutil(8)` manual describes `install` as updating Boot/System
collections and `rebuild` as requesting an Auxiliary collection rebuild and
authorization. The latter reached approval but did not complete it. The
presence of a matching KDK does not resolve that authorization failure.

Each of the first nine failures restored the entire original PhxAccel bundle. Separate readbacks
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

### Sixth and seventh admissions with direct manual authentication

The owner requested a manual authorization window. A separate sixth installer
was prepared against synchronized source record
`04efe7f17aa5ab0156a09fbe0d5a79dbe7063637`, preserving all previous admissions
and the original empty diagnostic scope. All three standard streams of its
one fixed `sudo -- /usr/bin/kmutil rebuild` command were attached directly to
the ordinary owner's native Terminal. No agent supplied or recorded the
password, and no command output was redirected or recorded by the runner.

Sixteen isolated CPU cases passed before deployment. In addition to bundle
replacement, verification refusal and unknown-content preservation, these
checked fixed-command/result/identity validation, one-use dispatch, timeout,
identity-checked child cancellation, refusal of unknown descendants, and the
actual manual runner with inert child fixtures. They do not exercise a GPU.

The sixth owner runner started at 18:20:46 +08:00 and recorded a timeout with
status 124 at 18:28:47. The root worker completed rollback at 18:28:58. After
the owner requested reopening the window, an independent verifier at 18:34:21
checked the complete original accelerator and installed inputs, all 24 cache
files and backups, no extra collections, unchanged protected staging, and
the entire 340-file live EFI against its backup. EFI was unmounted afterward.
The original accelerator remained cached; build 37, the boot identity, zero
display gates, absent arming and the empty original diagnostic scope were
unchanged. The root worker, owner runner and recorded sudo child had exited.
The expired command and installer were not replayed.

A distinct seventh admission was then prepared, with another 16 CPU cases
passing and all deployment preconditions rechecked. Its separate native
Terminal window was raised through a unique Accessibility target, and an
actual screenshot verified the active `Password:` prompt. Independent
handoff readback confirmed the temporary complete candidate accelerator,
exact retained original bundle, original startup, empty diagnostic scope and
live bounded root worker.

The seventh command ran from 18:35:51 to 18:38:13 +08:00. The owner entered
the password directly and reported authorization. The Terminal screenshot
confirmed that normal sudo authentication passed: `kmutil` checked the
AuxKC, detected one PhxAccel addition and removal, and requested user approval.
It then returned status 250 and `Biometry is not available.` without timing
out. A bounded read-only review of this actual request again found the
owner's identity, the host-internal request name `HumanPresence`, and OS
authentication error -6. These observations do not identify a stable public
API or establish the cause of the earlier desktop failure. Direct manual
input and native standard streams have therefore not established a working
cache-admission route.

The worker completed seventh rollback at 18:38:19. Independent readback at
18:39:41 again verified the complete original accelerator, original installed
inputs, all 24 cache files and backups, no additional collections, unchanged
protected staging and the complete 340-file live EFI and backup. EFI was
unmounted. Unfiltered cache inspection found the original accelerator and no
candidate. Build 37 and the same boot remained active, display gates were
zero, arming was absent, the recorded workers were gone, and the original
diagnostic scope was still empty. No cache backup restoration was necessary.

A final read-only review at 18:41:50 checked all ten tested production hashes,
34 current packet pins and seven recovery pins. The three future installed
candidate pins were deliberately excluded rather than reported as passing.
The packet and all four consumed installers in the current-boot delivery were
unchanged. The competing continuation remained absent and disabled, the
legacy startup job was absent, and no GPU helper or reboot process was running.
Settings still showed the existing restart-required row, with no approval
sheet or new Allow control. No restart was clicked. Raw system logs,
screenshots, UI trees and account identifiers remain private and ignored.

### Owner-selected upstream route: admissions eight through ten

After the seventh refusal, the owner requested inspection of the upstream
installer and then explicitly instructed continuation using that route. Before
that instruction, the owner was told that `kinst.sh` uses `-z`, documented by
the installed `kmutil` as skipping approval checks for this action, and directly
replaces the AuxKC. This is an explicit action-approval exception for this local
deployment. Global SIP, authenticated-root and boot arguments were not changed.
It does not establish that normal `kmutil rebuild` authentication was repaired.

The checked upstream chain is `install/install.sh` to `tools/phxctl/kinst.sh`:
create an auxiliary collection, inspect it, back up the old collection and
publish the new one. The full installer was not executed: its unrelated helper,
firmware, plugin and startup-marker changes were outside this adaptation.
The bounded local executor required the installed matching KDK rather than
`--allow-missing-kdk`, exact image identity and all unrelated cached records,
successful backup verification before publication, and checked rollback.
Production source and the original diagnostic packet were unchanged.

Two preparation-only refusals preceded the eighth admission. The first rejected
the original AuxKC's `SF_RESTRICTED` flag; the second found that system Python
lacked the xattr APIs. Neither replaced a driver or claimed deployment. The
reviewed fix accepts only zero or the original restricted flag, preserves the
original flags, owner, mode and extended attributes, and uses macOS `xattr`.
A private file round trip verified this metadata handling before deployment.
Immutable, nounlink and unknown flags remain refused. Both failed preparation
directories were retained, and fresh exclusive evidence was used.

The eighth executor passed 35 CPU cases. Its create operation returned 71:
the KDK's `AppleCentauriManager` has an x86_64 slice but depends on
`AppleEmbeddedPCIE`, which has only arm64e. The former is absent from the
original cache. Independent rollback at 19:15:16 +08:00 verified all 416
original cached records, 24 original cache files and backups, original bundles
and startup, full 340-file live EFI and backup, unchanged staging and metadata.

The ninth executor passed 37 CPU cases and restricted selection to the four
existing auxiliary extensions. Its mixed path/identifier arguments listed only
the other three identifiers. Create returned zero, but inspection found only
those three extensions. A separate read-only inspection with explicit Boot,
System and candidate Aux paths found 415 unchanged unrelated records and no
PhxAccel. Publication was refused. Independent rollback at 19:20:40 verified
the complete original state again. Read-only `kmutil find` comparisons reproduced
the identifier-selection behavior; the next selection explicitly named all
four identifiers, including PhxAccel, and returned exactly the expected bundles.

The tenth executor passed 37 CPU cases. It pinned synchronized source record
`122dfe0fd1799d4a72d95d82759e1512a4ebf89f` and rechecked the current boot,
matching KDK, full EFI, repositories, caches, candidates, packet and backups.
Create returned zero. Explicit three-collection inspection verified all 416
identifiers, the exact candidate image and unchanged version/path/image data
for all 415 unrelated extensions. At 19:23:41 it atomically published the
1,277,952-byte AuxKC after verifying the original and its backup. Candidate EFI
and next-boot startup replacement then completed at 19:24:06. All ten consumed
admissions and their original source bindings remain preserved.

Independent readback at **19:25:23 +08:00** verified the complete installed
candidate and retained original accelerator, startup bytes/ownership, all 37
packet pins, seven recovery pins and ten unchanged production hashes. Exactly
one of the 24 active cache-related files changed: the verified AuxKC. The
other 23 files, all 24 original backups, cache file set, metadata and protected
staging remained exact. Live EFI matched the expected 343-file manifest,
including the retained three-file original driver; its original 340-file backup
was unchanged. EFI was unmounted. No other EFI content was changed.

### State after installation, before one-shot arming

Build 39 is installed for the next boot; build 37 remains loaded. The installed
startup job was not launched. Display arming is absent, both checked display
gates are zero, the competing continuation remains absent and disabled, and
all recorded installer workers have exited. The original single-diagnostic
scope remains empty. Global security settings are unchanged; the authorized
action-specific approval skip is recorded explicitly rather than called normal
approval. No initializer, reader, target snapshot, desktop claim, display
release, arming or agent-requested reboot occurred in these three admissions.

Do not replay any consumed installer or run the staged entry's `run` role on
this initialized boot. A subsequent one-shot arming/fresh-boot stage must first
recheck the installed packet, current source, boot, caches, EFI/startup and
rollback state. Preserve the original diagnostic scope and its one-attempt
limit. Installed and cached bytes are not loaded-driver or acceleration evidence;
desktop behavior and its root cause remain unproven.
The earlier [623-test source validation](validation/desktop-startup-adapters-20261114.json)
is unchanged; it is not a successful installation or a hardware result.
Raw diagnostic material and user configuration remain ignored locally.
Existing license and public binary publication limits are unchanged.

### Original single-request reboot admission

The owner's original request explicitly included one reboot to test desktop
takeover. On 2026-11-14, a separate preparation checked that same request and
its still-empty, original one-attempt diagnostic scope; no new scope or retry
authorization was created. The ten consumed installers remain unchanged.

Fresh read-only admission verified installed build 39 versus currently loaded
build 37, the exact cached candidate and all 415 unrelated cached records,
startup bytes and root ownership, all 37 packet pins, seven recovery pins,
ten unchanged production hashes, the complete Python runtime and alias trees,
all original rollback copies, and the complete expected 343-file live EFI.
EFI was unmounted. The next-boot job is enabled but was not loaded or run on
this already-initialized boot. The competing continuation remains disabled.
Ten inert tests covered known/unknown arming states, scheduler identity,
exclusive receipts, non-replay and cancellation boundaries; no host GPU I/O
was used by these tests.

At **2026-11-14T19:45:22.250575+08:00**, the frozen executor set only the one-shot
`phxfb-boot=1` display flag, forced its NVRAM synchronization and read it back,
then dispatched one identified five-minute restart scheduler. Expected restart
time is approximately **2026-11-14T19:50:22.250575+08:00**. Independent readback at
**2026-11-14T19:45:53.509957+08:00** verified that exact scheduler, the armed state,
unchanged inputs, unmounted EFI and the still-empty original diagnostic scope.
The restart was scheduled; neither the reboot nor its desktop result had yet
been observed when this record was written.

On the next boot, only the already-installed byte-pinned entry may claim
the original diagnostic. It provides one pre-initializer baseline, at most one
failure snapshot, the bounded initialize/claim/display/release/monitor sequence,
and an independent recovery watchdog with the original 240-second deadline.
The framebuffer consumes the one-shot NVRAM flag before takeover. No persistent
M2 marker was created and success does not automatically rearm the system.
Recovery attempts disarming, display recovery and reboot; it cannot guarantee
recovery from a kernel or bus hard hang. The verified operator rollback remains
necessary. No global security setting, Windows EFI, partition or BIOS changed.

After reboot, inspect the original scope and recovery receipts before any other
action. Do not replay this scheduler, any installer, the initializer or a
consumed diagnostic. An armed scheduled test remains pending hardware evidence;
it is not an acceleration claim or proof of the earlier failure's cause.

### Observed reboot result and recovery

The owner reported the reboot. Read-only verification at 19:58:45 +08:00 found
the original request's durable boot and startup claims, diagnostic identity for
build 39, and the exact candidate accelerator image. Four startup journal
records passed their hash-chain and identity checks. The pre-initializer
baseline completed at **19:50:56 +08:00**, was bound to observer readiness and
admission, and had zero observations across its seven allocation reason counts.
This earlier baseline does not describe or explain the later failure. There
was one snapshot invocation; no failure snapshot was saved. No replacement
snapshot was requested during this review.

The firmware/power helper returned zero and reported GFX boot readiness. The
next `mesboot desktop-init` returned **75** with
`desktop queue selection not confirmed; stopping (no rollback)`. Its wrapper
returned 74, recorded `startup-stage-failed`, and requested recovery. The failing
`desktop_idle_queue` check precedes GART/MES initialization and queue submission.
There are no claim, display, release or monitor stage claims. The retained
pre-initializer display history still showed the panel held, no release and
no framebuffer server request. These are admission/failure observations, not
executed compute or graphics completion evidence.

The independent recovery had been handed from metadata discovery to the
coordinator. Recovery was requested before watchdog expiry, completed disarming,
and requested reboot with command status zero. Two display-recovery writes
(`nvaccel_iop` and `nvaccelfb`) returned 1; the other two returned zero. This is
not a claim that every display-recovery operation succeeded. A subsequent boot
began at **19:51:20 +08:00**, with a boot identity different from the diagnostic's.
That observation is not proof of the configured firmware fallback route.

Current metadata verifies loaded build 39 and the candidate accelerator,
absent one-shot arming, the recovery off marker present, no persistent M2 flag,
no candidate framebuffer service, no active startup job and no GPU helper. Display sysctls
are unavailable on this boot; they are not reported as zero. All 37 packet pins,
seven recovery pins, the full trusted runtime, installed candidate/startup,
retained original accelerator, exact candidate cache and all 415 unrelated
cached records were reverified. EFI remained unmounted and was not remounted.
The original consumed scope and all ten consumed installers remain intact.

The installed error omits which of the four queue selections failed and both
actual readbacks, so it cannot distinguish a rejected write from a later changed
selection. A source-only diagnostic change now logs the exact ME/pipe, requested
selection, already-returned write readback and existing later readback when
selection or idle restoration fails. It adds no hardware I/O calls and preserves
the existing comparison and exit 75. Twenty-one native CLI/provider test methods
passed with address/undefined-behavior sanitizers, including six new fault cases
in two methods. The changed helper compiled and linked against the real macOS
IOKit/CoreFoundation frameworks. That binary was neither run nor installed;
the deployed byte-pinned delivery remains unchanged. This improves failure
evidence; it does not establish a hardware fix.

The [sanitized postboot record](validation/desktop-postboot-20261114.json)
records these limits and source hashes. Do not replay this consumed diagnostic,
rearm it or reset its claims. Preserve the off marker and recovery records.
A future target test needs a separate explicit one-attempt authorization and
reviewed byte-bound delivery; this review dispatched no new target work or reboot.
