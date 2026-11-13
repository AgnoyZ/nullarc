# First native-submit refusal diagnostic

Source candidate, 2026-11-13. Not installed or target-accepted.

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

The staging operation compared 55 installed files and retained the same
boot, startup-marker state and framebuffer switches. No deployment,
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
M2 rearming, initialization replay, watchdog or restart is performed by this
diagnostic work. First review native compilation, signing, source/artifact
hashes and the existing recovery backup. Installing this candidate would be
a separate, reviewed operation, followed by a user-controlled boot.

Do not reproduce the desktop failure merely to see whether a log appears.
An eventual bounded session must have an explicit capture and recovery plan.
Capture any refusal with its private boot/time context; the first refusal
could precede the failure of interest. An absent log does not exclude a
userspace failure, an unretained kernel message or an untested path. Preserve
the uncertain in-flight resources and stop at the first failure or timeout.

This candidate does not deploy the separate RADV cleanup-order fix. A
two-kext artifact does not contain that userspace library. Neither candidate
accepts desktop acceleration or corrects the 42-inch display-size report.
