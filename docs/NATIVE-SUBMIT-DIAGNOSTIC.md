# First native-submit refusal diagnostic

Source candidate, 2026-11-13. Subsequently staged to the actual target EFI
under administrator authorization and verified loaded as build 35. The first
startup initialization did not complete; the owner reports a manual restart
after observing it stuck. The next boot disabled initialization through the
existing protection. See the [initial postboot checkpoint](validation/native-submit-build35-postboot-20261113.json).
The subsequently owner-authorized retry completed the legacy startup checks
and published NMXAccel. That later initialization result is recorded in
[the retry outcome](validation/native-submit-build35-retry-postboot-20261113.json);
it does not accept native Metal workloads or desktop acceleration.

The failed desktop boot logged `VK_ERROR_DEVICE_LOST`, but the pinned RADV
queue layer can convert several distinct failures to that result. Known native
IOKit refusals are often mapped silently. The working fallback is preserved;
this candidate only makes the first non-success native submission result
visible in the kernel log. It does not fix its cause.

The earlier evidence and source audit are in
[DISPLAY-FAILURE-20261113.md](DISPLAY-FAILURE-20261113.md). The sanitized
candidate record is in
[validation/native-submit-diagnostic-20261113.json](validation/native-submit-diagnostic-20261113.json).

## Scope

`IOAccelPhxNativeClient::externalMethod()` checks the unchanged dispatch result
while holding the existing client lock. For `PHXN_SEL_SUBMIT` only, the first
non-success result sets a per-client latch and logs the original 32-bit
IOReturn:

```text
PhxNative: first submit refusal IOReturn=0x........
```

The latch starts clear for each client. Successful submissions and other
selectors do not consume it. Later refusals from that client are returned
normally without additional diagnostic logs. This is a per-client bound, not
a total log limit for the whole boot. No request payload, handle, pointer,
address, process identity or machine identifier is included.

The logging path does not read the request, allocate a diagnostic buffer,
retry a submission or modify its result. Existing before-hello and closed
client gates also produce their original `NotReady` result; those can be the
first refusal logged. The message therefore identifies the external-method
result, not a particular validation stage, proof that the GPU received work,
or a hardware-hang diagnosis. It does not attribute the refusal to a process.

The actual `doSubmit`, BO, map/unmap, pending-resource and related retirement
methods are byte-for-byte unchanged from the parent source. No queue guard,
resource lifetime, budget, native wire layout or ABI version changes. The
source build number changes from 34 to 35 to distinguish the diagnostic
candidate; a build number alone is still not complete provenance.

## Host validation

`tools/test_submit_diagnostic.py` extracts the actual whole dispatcher and
its actual latch declaration, then executes them against explicit IOKit,
lock, logging and handler fakes under ASan/UBSan. The 70 cases cover:

- exact propagation of eight different nonzero 32-bit handler results;
- success before/after failure, one log for 1,024 refusals, and separate clients;
- before-hello and closed-client refusal without dispatch or reclamation;
- 29 non-submit dispatch paths, including an unknown selector;
- logging while the client lock is held and returning with the lock released;
- an unrelated selector failure leaving the submission latch available.

The runner also refuses missing/duplicate extracted definitions and an
existing output directory. These are CPU tests of the actual dispatcher,
not executions of the real handlers. They do not validate concurrent kernel
execution, log persistence, IOKit, GPU submission or desktop stability. The
native CI build was still required at the source-review checkpoint; do not
build or replace an installed kext as part of this diagnostic work.

### Native build and artifact follow-up

On 2026-11-13, priority run `43377876831` completed successfully for source
`2a1c771d19893f20f53a54cb1566c376a4c5fbfb`. Its `macos-15-intel` job passed
the 70 actual-dispatcher CPU cases under ASan/UBSan, compiled and checked
the signatures of both kexts, and compiled/signed the actual Metal plugin
without creating a device. This priority run does not cover a full RADV or
LLVM build and does not exercise the target GPU.

The existing owner-authorized two-kext workflow, run `43378517567`, then
successfully packaged the same source commit. Local verification checked
the GitHub ZIP digest, the outer archive checksum, all 24 inner manifest
entries, both strict signatures after extraction and final copying, and
the exact committed allowlisted source archive. The candidate was staged
locally with its original checksums, build report, licences and sources;
it was not installed. The original source-review JSON remains a historical
checkpoint; the subsequent results are in
[the build/artifact record](validation/native-submit-build35-artifact-20261113.json).

The separate cleanup-order fix at source
`4f35a609331752d5e2dcac24f8b878d32aa6f309` also completed full native CI
run `43370193766` successfully. That older run is separate evidence for
that commit, not a full-stack acceptance of build 35. The two-kext package
does not distribute the rebuilt RADV, translator, LLVM or Metal plugin.

That earlier local artifact-staging operation compared 55 installed entries
and retained the same boot, startup-marker state and framebuffer switches. No deployment,
initialization replay, M2 rearming, reboot or new GPU workload was performed.
Desktop acceleration, the original submission failure and the physical
display-size issue remain unresolved.

Run the CPU-only check with a fresh output directory:

```sh
python3 tools/test_submit_diagnostic.py --out build/submit-diagnostic-check
```

The main source workflow includes the same check before the designated
`macos-15-intel` native build. The historical patch is
`patches/0029-first-native-submit-refusal.patch`; source preparation hashes
it for provenance and does not reapply it.

## Conditions before a separate hardware session

Keep the current fallback and the existing recovery behavior. No deployment,
M2 rearming, initialization replay, watchdog or restart was part of the
source or package preparation. A later, separate administrator-authorized
operation replaced only `PhxBringup.kext` in the actual EFI, after native
build/provenance review and a verified full EFI backup. The known-running
old bundle remains on that EFI; all 328 unrelated EFI files, the existing
config, 55 installed system-stack entries and startup/display state were
preserved. PhxAccel was not replaced. The source difference from the
installed PhxBringup baseline is only the diagnostic latch/log and build
number. See [the target staging record](validation/native-submit-build35-deployment-20261113.json).

At the historical deployment checkpoint, the current kernel was still build 34 and
the partition was unmounted. A single user-controlled normal reboot is
required to load the candidate. Keep M2 off and the firmware framebuffer
policy intact; do not re-enable the failed desktop takeover. The prepared
private collector refuses the original boot and checks both the candidate
binary identity and build 35 before reading logs. It filters refusal records
by the new boot identity and submits no GPU work. Full backup contents and
rollback copies were checked; external bootable recovery media was not
tested, and no guarantee of recovery from every possible failure is made.

Do not reproduce the desktop failure merely to see whether a log appears.
An eventual bounded session must have an explicit capture and recovery plan.
Capture any refusal with its private boot/time context; the first refusal
could precede the failure of interest. An absent log does not exclude a
userspace failure, an unretained kernel message or an untested path. Preserve
the uncertain in-flight resources and stop at the first failure or timeout.

This candidate does not deploy the separate RADV cleanup-order fix. A
two-kext artifact does not contain that userspace library. Neither candidate
accepts desktop acceleration or corrects the 42-inch display-size report.

## Postboot investigation: initialization stopped

Read-only inspection on 2026-11-13 verified build 35 and an exact match between
the loaded PhxBringup binary identity and the candidate. PhxAccel is loaded,
but the current boot has no NMXAccel service and no PhxAMDFB. IONDRVFramebuffer
remains present. The three accelerator display sysctls are unregistered
(`unknown oid`), not registered values of zero. M2 and the framebuffer NVRAM
arming remain absent.

The private startup log establishes this sequence, in UTC+08:00:

- At 15:01:52, initialization began with PhxAMDFB off the panel. No completion
  entry was retained for that attempt.
- The owner subsequently confirmed that the machine appeared stuck and they
  manually restarted it. This is owner-reported manual intervention, not
  evidence that a watchdog automatically recovered the machine.
- At 15:05:07, the next startup detected the unfinished attempt, created the
  persistent stop marker and removed the pending marker. This protective
  stop is distinct from the preceding manual restart.

The firmware-load log was modified at 15:01:54 and contains 17 load responses,
all with zero IOReturn and zero PSP status. These responses show that those
requests returned reported success; they do not establish later RLC autoload,
SMU power-up, MES/queue readiness, completed GPU work or desktop acceleration.
The retained output does not identify the exact stage where initialization
stopped. The startup pipeline filters/buffers output, so missing compute or
graphics lines cannot establish that those stages were never entered.

Bounded unified-log extraction was parsed using timezone-aware timestamps
and separated by boot identity. Of 14,581 returned kernel records, 1,328 were
outside the requested interval and excluded. The retained set contains 622
records from the previous working boot, 3,512 from the unfinished attempt and
9,119 from the protective boot. These boot groups were kept separate. No
first-native-submit refusal was recovered from either new boot. Missing
messages do not exclude a native failure; this diagnostic also does not
instrument every legacy firmware/power/queue initialization step.

The relevant readable report inventory found a shutdown-stall report from
the earlier working boot's shutdown, before the unfinished attempt began.
No later matching report was observed in the scanned readable directories;
one legacy report directory was absent or inaccessible. No NVRAM panic-info
variable was available. Neither observation proves there was no panic. A
loginwindow historical-panic preference and the scripts' existing timed
restart commands do not override the owner's report or identify the hang.

Readback matched 53 of the 55 installed-stack entries against the deployment
baseline, with no unreadable entries. The two changed files were startup
runtime outputs: the application allowlist now contains the built-in-tools
policy, and the firmware-address log contains the new attempt's responses.
Installed kexts, plugins, libraries, firmware and startup helper bytes were
unchanged. Do not describe all 55 entries as unchanged after startup.

The agent performed no initialization replay, new GPU workload, display
arming, driver replacement, EFI operation or reboot during this inspection.
The stop marker is preserved. The next useful diagnostic is a reviewed way
to retain individual initialization-stage results before any separate
hardware session; clearing protection and repeating the same opaque boot
is not an accepted next step. Desktop acceleration and physical display
size remain unresolved. Earlier source, artifact and deployment JSONs are
historical checkpoints and have not been rewritten.

## Subsequent owner-authorized initialization retry

After clarifying that the 15:01 restart was manual, the owner explicitly
requested another reboot and said they would let initialization run without
manually interrupting it. This new authorization supersedes the previous
stop-and-investigate next step for this one attempt. It does not establish
that the earlier hang or the automatic recovery mechanism is fixed.

The preparation rechecked the running build/identity, all 55 current installed
entries, firmware framebuffer, inactive initialization state, absence of
M2/NVRAM arming and absence of an existing shutdown process. An initial
backup-metadata check stopped before marker removal because the copy inherited
the destination group. Readback confirmed that protection remained intact
and no reboot had been scheduled. A separately pinned revision retained the
backup ownership explicitly and passed the same checks.

At 15:27 local time, the administrator-authorized operation backed up and
removed only the stop marker, then scheduled the requested normal reboot for
approximately 15:30. Independent readback verified the backup bytes/metadata,
marker removal, scheduled process, all 55 installed entries unchanged and
M2/NVRAM arming still absent. Startup helpers, drivers, userspace and EFI
were not changed, and initialization was not replayed in the running boot.

The existing three-/four-minute initialization restart timers are unchanged;
they require a responsive system and are not a verified recovery guarantee
for a wedged kernel or bus. The owner should allow six to eight minutes after
restart before judging this attempt. Reboot completion, initialization,
acceleration and any automatic protective recovery are still unverified at
this scheduled-reboot checkpoint. See [the retry record](validation/native-submit-build35-retry-20261113.json).

## Retry outcome: startup initialization completed

The requested normal reboot led to a new boot at 15:30:38 local time on
2026-11-13. The startup log records initialization starting at 15:30:41 and
finishing at 15:30:50. Its compute and graphics scratch/test-buffer values
match the expected sentinels; both queue-adoption calls and the accelerator
claim report zero return codes. These are the existing legacy startup
checks, not an independent native-submit or Metal regression suite.

Readback verified loaded build 35 against the pinned candidate identity and
confirmed PhxAccel loaded and NMXAccel present. The stop, M2 and pending
markers are absent. IONDRVFramebuffer remains present, PhxAMDFB absent, and
the framebuffer NVRAM arming absent. The display sysctls are now registered
and report zero, unlike the unregistered OIDs in the protective boot.
No initialization or shutdown process was observed at the first readback.

The kernel query through 15:34:10 returned 196 records matching the bounded
driver/GPU/panic/watchdog predicate. All parsed into the current boot and
timezone-aware window. No first-native-submit refusal or selected driver
queue-stuck/fault message was observed. The readable report inventory found
no matching new WindowServer, panic, kernel, watchdog or shutdown report.
These are bounded observations; missing logs or reports do not prove the
absence of a fault or establish native submission correctness.

Of 55 installed entries, 53 matched the retry baseline. The application
allowlist changed from the built-in-tools policy to the existing non-M2
application policy, and the firmware-address log was refreshed by startup.
Installed kext, userspace, firmware and startup-helper bytes were unchanged.
The read-only investigation did not replay initialization, submit additional
GPU work, change switches, deploy a driver or reboot.

The outcome establishes completion of this boot's existing initialization
sequence and restoration of its accelerator service. It does not explain
the preceding stuck attempt, validate automatic recovery from a hang,
retest the six earlier Metal compute cases, resolve the original native
submission failure, enable desktop takeover or correct physical display
size. Keep M2 off while diagnosing the failed native/display path. Earlier
checkpoints retain their original observations.
