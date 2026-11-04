# Bring-up integration audit: not ready for deployment

Reviewed pinned nullarc `cbb08ddf517c009255a74ad0fbc2cd7e0d6fa339` on 2026-10-30.
This is a source audit, not a firmware or target-hardware test. None of the reviewed
scripts was executed. No source reference-machine address is a verified ThinkBook
address. The build does not install these scripts or tools. The downstream
`mesboot.c` is now staged for compile-only and fake-transport regression checks;
it is not packaged as a deployable initialization tool.

## Concrete blockers in the reference workflow

| Source | Observed behavior | Required downstream change |
| --- | --- | --- |
| `tools/phxctl/bringup5.sh` | Uses literal firmware byte offsets/sizes and literal PSP command words, rather than a verified local firmware manifest and target memory map. | Parse the actual pinned firmware headers, validate payload bounds and expected IP, and derive addresses from reviewed target evidence. Never copy reference command addresses as defaults. |
| `tools/phxctl/mesboot.c` | `VRAM_MC`, `FB_PA`, the system aperture and default/fault-page registers contain reference-machine constants. Queue, GART and scratch regions also have fixed offsets. | Introduce an explicit target layout with verified MC/physical/aperture relationships and exclusive region ownership. BAR bounds alone or finding zero-filled memory does not prove a region is free. |
| `tools/phxctl/mesboot.c` | Upstream helpers discard IOKit return codes and can use initialized zero after a failed read. | Downstream patch `0004` makes IOKit errors and mismatched reply lengths terminal; firmware/GPU response semantics and timeout propagation still need separate work. |
| `tools/phxctl/bringup5.sh`, `tools/phxctl/full.sh` | Firmware/register operations are piped to `grep`/`tail` without `pipefail`; failures can be hidden by a successful final pipeline command. | Use a checked, structured stage runner. Track transport completion and device response separately; do not infer success from a matching log line. |
| `tools/phxctl/full.sh`, `tools/phxctl/phxboot.sh` | The workflow includes automatic reboot timers, `killall shutdown`, sysctl changes, allow-list changes and NVRAM-based display arming. | Keep initial manual compute bring-up separate from desktop takeover and persistent boot configuration. Any recovery mechanism must own only its own timer/process and require an explicitly reviewed deployment plan. No automatic installation here. |
| `src/phxbringup/PhxNativeABI.h` and `PhxBringup.cpp` | The original kernel firmware/ring offsets were coupled to the experimental layout; raw shell PSP words and other userspace constants still duplicate assumptions. | Patch 0009 now supplies an explicit shared descriptor with arithmetic/alignment/overlap checks. Firmware/display reservations and target ownership are still unimplemented; see `PSP-LAYOUT.md`. |

The existing downstream PCI/Darwin/opt-in gate is necessary but does not resolve
these layout, firmware, sequencing or recovery problems. A compiled kext and a
working userspace compiler are not a completed GPU boot sequence.

## Implemented arithmetic correction; target validation pending

`patches/0003-bringup-aperture-bounds.patch` replaces addition-based end checks in
`PhxBringup::doorbellWrite` and `PhxBringup::pspRing`. Their 64-bit offsets could
wrap when adding the access extent. The shared `rangeWithin` policy first checks
the offset against the limit, then compares the extent with the remaining space;
it never computes a potentially overflowing end address. Existing alignment and
privilege/opt-in rules are retained. The ring must fit both below TMR and within
the mapped framebuffer aperture before its first aperture access.

Python tests verify the actual staged patch and ordering before memory access.
The same helper used by the kext has C++ boundary, wraparound and exhaustive
small-range assertions in the sanitizer suite. These are source/host arithmetic
checks, not GPU execution. They do not establish ownership of the selected VRAM
regions, validate firmware, remove the reference-machine constants, or make the
original boot scripts safe to deploy.

## Checked userspace transport (2026-10-31)

`patches/0004-checked-bringup-transport.patch` routes every `mesboot.c` scalar and
structured IOKit request through checked calls. A non-success status or any
short/long reply exits with status 74 before returning a register value, issuing
the next write, or printing a successful command return. This covers register and
VRAM access, doorbells, system memory, queue adoption, accelerator claim and the
HELLO handshake. HELLO also rejects a different ABI version. Service lookup
references are released after opening.

The fault-injection harness includes the **actual staged tool source**, replacing
only IOKit with an explicit fake transport. Its 47 subprocess cases cover normal
returns, legitimate zero data, transport errors, both reply-length directions,
ABI/open failures and failed read/write prerequisites. ASan/UBSan instrument this
host test; it asserts the exact call count so a later write cannot masquerade as
an acceptable error. Native preflight separately compiles/links the patched tool
against real macOS IOKit without executing it. Run `41087992288` / code `b2cadc9`
passed all 47 injected cases and the real-I/O-library compile/link preflight.
The full native driver build subsequently passed; see
`validation/ci-b2cadc9-full.json` and `validation/ci-b2cadc9-transport.json`.
Neither check executes the real transport
or a GPU workload.

Source provenance is retained for the new patch. The staged tool uses the pinned
upstream MIT option (`LICENSE` and `LICENSES/MIT.txt`); its two unmodified AMD
headers retain their embedded 2021/2022 MIT-style notices. No firmware is added.

**This is not a safe deployment workflow yet.** Stopping userspace does not undo
hardware changes already made, prove that outstanding GPU work is quiescent,
validate firmware responses, propagate every GPU timeout, or remove the hardcoded
reference memory layout. No automatic GPU reset or speculative recovery writes
are added. The real tool is not executed or installed by these checks.

## Completion handling checked on hosts, not target hardware

`patches/0005-checked-gpu-completion.patch` makes missing MES completion terminal
(exit 75), so callers such as `sched_test` cannot ignore a timeout and launch the
next initialization stage. The tool compares the entire 64-bit query fence and
command completion token, requiring the token value 1 that it put in the command.
It validates these before even diagnostic register-selection writes. Reading a
previous scheduler sequence also retains its high 32 bits.

Compute and graphics queue tests now require both their expected scratch-register
value and their expected memory write before later register changes or queue
adoption. The graphics target is initialized to the complement of its expected
value so stale data cannot satisfy the memory check. These markers are the
reference tool's basic execution checks, not a Metal shader/rendering workload.

Completion-field encoding uses `memcpy` rather than an unaligned `uint64_t *`
store: the pinned MES frames have only four-byte alignment. The host harness
exercises a deliberately four-but-not-eight-byte-aligned frame under sanitizers.

The harness now has 52 transport cases plus 20 injected completion-path cases.
The latter run the actual MES submission, scheduler initialization, compute and
graphics functions, including positive adoption paths, timeouts, missing/wrong
tokens, mismatched high fence/token words, and independent scratch/memory failures.
They check bounded polling, no next stage or adoption after failure, and no later
scalar write after the injected failed completion. This is **control-flow testing
with fake observations**, not GPU emulation, packet correctness or hardware proof.
Run `41089800738` / code `61c5c0e` passed all 52 transport and 20 completion
cases under ASan/UBSan. Its macOS preflight also compiled/linked the real tool
without executing it. Its full native driver/plugin build subsequently passed,
including real Metal/AIR translation and relocated plugin compilation; see
`validation/ci-61c5c0e-completion.json` and `validation/ci-61c5c0e-full.json`.

No hardware rollback is attempted. KIQ/SDMA experiments, ring reuse/ownership,
firmware responses, target mappings and safe recovery still
need separate validation before deployment. Process exit is not proof that the
GPU is idle or its earlier writes have been undone.

## Bounded MES submission; no ring reuse

Patch `0006` rejects invalid frame sizes/status offsets, an exhausted scheduler
ring and a maximum 64-bit sequence before the submission function modifies the
caller packet, writes status memory or makes any IOKit call (exit 76). The two
64-dword frames must fit within the existing 1,024-dword scheduler allocation.
Subtraction checks avoid arithmetic wrap. Resuming the reference tool reads both
write-pointer words, so a nonzero high word cannot be silently truncated into an
apparently valid low offset. Packet words are copied without alignment-dependent
loads. Existing scheduler initialization and other earlier operations remain
outside this per-submission guarantee.

This finite bring-up path deliberately does not wrap/reuse ring storage. A full
ring is a terminal condition, not permission to clear a running queue or reset
the device. A production scheduler still needs validated consumer synchronization,
exclusive ownership, submission serialization and recovery. Fixed reference
addresses and other initialization experiments remain unresolved.

Sixteen new actual-source host cases cover first/last valid submissions, the last
valid sequence, unaligned packet storage, invalid sizes/offsets, one-word overflow,
full/high-word/max pointers and sequence exhaustion. Negative cases require zero
transport calls and unchanged packet/pointer/sequence; positive cases check all
128 ring writes in order. All sixteen passed Linux ASan/UBSan in run
`41096096384`, code `ff3345a`, along with the existing 52 transport and 20
completion cases. The macOS preflight also passed real IOKit compilation/linking
without executing the tool. Evidence: `validation/ci-ff3345a-submission.json`.
The full native build is still running at this observation. These are not GPU
execution or permission to initialize hardware.

## Evidence required before an initialization experiment

The kernel PSP false-success path is now corrected by patch `0007`; see
`PSP-COMPLETION.md`. PSP completion errors/timeouts return failure, invalidate TMR
readiness and latch subsequent PSP/firmware write refusal. Command preconditions
and padded firmware-staging extents are checked before their respective writes.
Run `41099945379` reports the source job completed/success; all 32 actual-method
sanitizer cases have now been extracted from its log and their method/patch
hashes cross-checked. See `validation/ci-7921a7c-psp.json`; the earlier step-only
observation is retained separately. Full native kernel build verification is
pending. This does not establish target memory ownership or hardware rollback.

Start with `TARGET-INVENTORY.md` for the new metadata-only collector. It records
the actual OS build and whitelisted registry PCI identities/assigned apertures,
with timeouts and without raw dumps. It does not establish independent hardware
identity, GPU IP layout or reserved-region ownership and never approves bring-up.

`FIRMWARE-MANIFEST.md` now covers offline inspection of nine pinned official
firmware candidates, with header-derived components and exact source hashes.
Their 17 reference load extents and the TOC extent match the documented formats;
see `validation/firmware-08624cd.json`. This removes guesswork from file slicing
but does not replace fixed device addresses, validate PSP commands or implement
a checked hardware loader. Firmware selection still requires target IP evidence.

Patch `0008` adds complete-file SHA-256 snapshot binding and checked transfer
errors to the actual `phxctl` tool; see `FIRMWARE-CONTROL.md`. It removes the
short-read/partial-load path and stops after failed prerequisites. This is still
a low-level tool, not a target allocation/command orchestrator. Its original
shell pipelines and raw-debug parameters are not approved for deployment.

Patch `0009` replaces implicit managed kernel PSP placement with an explicit
versioned descriptor shared with `phxctl`. Configuration itself changes only
software metadata. Ring creation rechecks all three regions against reported
VRAM and mapped aperture bounds, verifies MC/physical address arithmetic and
requires pairwise disjoint ranges before aperture writes. This removes the
managed PSP fixed-offset dependency, but does not grant reserved-region ownership
or change the separate `mesboot.c` reference layout. Its 48 kernel-method and 46
CLI cases passed ASan/UBSan in run `41104430767`; see `PSP-LAYOUT.md`.

Patch `0010` connects the TOC response's actual TMR-size field to exact-size,
aligned TMR setup and prevents managed engine loading before TMR completion.
The staged TOC uses the checked snapshot transport. This implements part of the
initialization sequence, but component selection, owned memory and the broader
GART/queue/power workflow remain unresolved. Its 69 actual-kernel-method and 60
actual-CLI cases passed ASan/UBSan in run `41145000196`; full native kernel
compilation is still pending. See `PSP-TOC.md`.

1. Confirm the actual target Tahoe build, a tested external-disk/EFI recovery path
   and the exact driver/firmware revisions. The last verified target environment
   remains Sonoma Recovery, not Tahoe.
2. Capture target PCI resources and GPU IP discovery, framebuffer/UMA bounds and
   console/reserved-region ownership without modifying hardware. Keep raw data
   private. A Windows resource snapshot is not proof of the macOS memory layout.
3. Pin and audit each firmware input. Validate its hash, header, payload ranges,
   engine/IP version and licensing; do not publish firmware files or reuse
   reference byte counts without checking the actual input.
4. Retain the checked transport/completion paths and replace the duplicated
   reference layout before building a target execution plan. Validate rejection paths using fault
   injection and boundary tests, without claiming that these are GPU tests.
5. Review a single, explicit manual initialization sequence and its recovery
   procedure. Hardware execution needs a separate authorized target-machine step;
   the repository build must not run it.
6. Prove real compute completion and correct output before enabling display
   takeover. Then validate the actual panel, repeated boot, WindowServer and
   stability independently. A printed `done`, fabricated fence or device name
   cannot satisfy any of these checks.

This is the next hardware-facing integration work, not a proposal to reduce the
goal to a compiler-only or no-device-only stack. Full Radeon 780M operation on
Tahoe remains the objective and is still unproven.

## Checked stage runner (2026-11-02)

`tools/phx_boot_gate.sh` (documented in `BOOT-GATE.md`) implements the control-flow
change this audit requires, without importing the reference workflow's side effects.
It runs an operator-supplied, bytewise-ordered stage directory with a per-stage
timeout, stops at the first failure, and runs an operator-supplied release hook on
every exit path once it holds the lock, so a failed attempt cannot leave PhxAMDFB
holding the GPU. A crash marker distinguishes a handled failure (marker removed,
77/78) from a killed attempt (marker kept; the next run refuses with 76 and leaves
the panel on the firmware framebuffer). A stale lock is replaced only when its
recorded PID is gone; a live holder gets 75 and no release call.

It performs no reboot, NVRAM write, sysctl write, process-name kill, installation
or address-constant lookup: the expected kext build is a required argument, and the
only facts it reads are `uname` and the `phx-*` properties PhxBringup publishes
(`phx-build`, `phx-780m-policy`, `phx-fb-phys`, `phx-fb-aper-len`). It does not
replace the non-parameterised register sequence in `mesboot.c`; the stage programs
remain the audited `phxctl`/`mesboot` entries, and no stage is shipped here. POSIX
shell tests in `tests/test_boot_gate_shell.py` exercise the real script with fake
host commands; they run in Linux CI, and Windows only ran `sh -n` plus a manual
smoke. No macOS host or target machine has run it.

## Same-base audit from RadeArc (2026-11-03)

`Kreytus/RadeArc` is a second downstream of the upstream pin this branch uses: same base `cbb08dd`, ported to
Phoenix 2 (Radeon 740M, GC 11.0.4) in a desktop with HDMI/DP only. Its `docs/PORTING_AUDIT.md` catalogues every
reference-machine constant in that base, so the list applies here too. Read at `main` = `d8d8d18`; the rest of
that assessment is in `docs/RADEARC-REFERENCE.md`.

| Reference-machine assumption | Where it lives in this tree (verified) | Status here |
| --- | --- | --- |
| `IOPCIMatch 0x19001002` only | `src/phxbringup/Info.plist`, `src/phxaccel/Info.plist` | Phoenix 1 only, by design; other Phoenix parts are out of scope |
| `kGbAddrConfig = 0x242`, `kGcVersion = 11.0.1`, `kVisTotal = 256 MiB`, `kHiTotal = 1.5 GiB`, all sent to RADV in QueryInfo | `PhxBringup.cpp:59-65`, `1938-1945` | **still literal.** Linux reads `GB_ADDR_CONFIG` from the hardware; these are the Firebat's values |
| GC / MMHUB / OSSSYS segment bases as absolute dwords (`SEG0` 0x1260, `SEG1` 0xA000) and the `SET_HW_RESOURCES` base tables | `mesboot.c` `SEG0()`/`SEG1()`, `SET_HW_RESOURCES` | **still literal**, copied from the Firebat discovery table |
| MMHUB `FB_LOCATION_BASE`/`FB_LOCATION_TOP`/`FB_OFFSET` at `0x1A8EC`/`0x1A8ED`/`0x1A8D7` (MMHUB 3.0.1, segment 1 base `0x1A000`) | `PhxNativeABI.h:68-70` | **still literal**, and these are exactly the registers a chip-derived layout would have to read |
| NBIO HDP flush at `0xE4D` (NBIF 7.7.0), SMUIO `GOLDEN_TSC` at `0x16a2d` (SMUIO 13.0.7) | `PhxNativeABI.h:114`, `PhxBringup.cpp:1961` | **still literal** |
| PSP and SMU mailboxes in MP0/MP1 **segment 1** (`0x16000`) of 13.0.4 | `PhxNativeABI.h:72-82`, `119-122` | **still literal.** RadeArc found 13.0.11 dispatches through **segment 0**, so a chip reporting 13.0.11 needs different mailbox offsets. Phoenix 1 is 13.0.4 and unaffected — but only a live read settles which segment a target uses |
| `mesboot`: `VRAM_MC 0x8000000000`, `FB_PA 0x6A0000000`, `GART_VA`/`GART_PT`, the KIQ/scheduler VRAM offsets | `mesboot.c:119-140` | **still literal.** Their replacement — chip-gated values read from `phx-fb-mc-base` / `phx-fb-size` / `phx-fb-phys`, refusing an unknown chip — is the pattern to adopt when this becomes in scope |
| Firmware payload offsets and sizes as literals | `tools/phxctl/bringup5.sh:13-35` | **not this repository's path.** This workflow is not run here (`docs/BOOT-GATE.md`). The audited path derives extents from the files themselves: `tools/firmware_manifest.py` parses each header (`payload_offset`, `total`, per-component sizes) with bounds and overlap checks, `tools/firmware_profile.py` generates `PhxFirmwareProfile.h` from that audited manifest, and `phxctl firmware-sequence` loads from the generated steps with per-file SHA-256 from the reviewed lock. The literals survive only for the reference file set, in a script nothing here invokes |
| TMR MC address `0x6A0C000000` = Firebat `FB_OFFSET` + `0xC000000` | `tools/phxctl/bringup5.sh:15` | same: reference script, not this path; `phxctl` takes the TMR extent from the checked layout instead |

Two consequences worth keeping in view:

1. Nothing in the table above can be parameterised from the table alone. Those are machine facts, and the only
   honest sources are what the driver publishes about itself (`phx-fb-phys`, `phx-fb-aper-len`, `phx-build`,
   `phx-780m-policy`) or what a live read returns. Inventing values would look safer than the literals and be
   worse. See `docs/RADEARC-REFERENCE.md` §3 for the shape that does work.
2. The firmware-offset finding does not apply to the audited path; it applies to the script this audit has always
   said not to run. That is now asserted rather than remembered: `tests/test_reference_scripts.py`, and each of
   the four reference scripts carries a "not run by this repository" banner so nobody mistakes it for the entry
   point.
