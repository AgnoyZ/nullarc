# Local Hackintosh comparison and validation — 2026-11-12

This records source comparison, CPU fixture execution, native compilation and
Metal compute correctness on the existing installed stack. The installed
build-34 smoke passed; it is **not** GPU acceptance of the downstream build-33
driver or a performance comparison.

## Source pins and comparison

- Upstream `luuumi-dev/nullarc` main: `8aba872560a3c9b7dc7a0ddebfad001c6dddf315`,
  fetched during this session; its commit date is 2026-11-09.
- Starting downstream: `ba5ac9d1fe4bb239db7538aa6c82ae0a378b5145`.
- Common ancestor: `cbb08ddf517c009255a74ad0fbc2cd7e0d6fa339`.
- At those pins there are 49 upstream-only and 89 downstream-only commits;
  the direct tree diff changes 455 files. These counts precede this session's
  tooling/test fixes. No upstream merge, rebase or main-branch update was made.
- Validated tooling/test tree: `15b684def735ea70cf1a9247dbb12954075f859b`,
  tree `7097f78e9257af72dc07f542db90d94bfee9e9ea`.
  A disposable committed local snapshot with this exact tree ran the final
  suite. The production `src/` tree is unchanged from the starting downstream.

This is a focused comparison of the validation and integration risks, not a
complete audit of every new upstream component.

| Area | Upstream versus downstream | Integration consequence |
| --- | --- | --- |
| Native wait | Upstream `4459c40` uses 50-us polls for the first nominal millisecond, then 1-ms sleeps. Downstream still uses 100-us busy polls up to its timeout cap. | A useful isolated follow-up candidate; preserve downstream close/reaping/locking behavior rather than replacing the whole method. Host model success is not kernel scheduling evidence. |
| Missing hardware | Upstream's current `doWaitSeq` fallback reports emitted work retired when the GPU is not ready; downstream returns not-ready. | Do not import the upstream function wholesale and lose the no-fabricated-retirement contract. |
| Device and ownership scope | Downstream retains the Darwin-25/780M opt-in gate, bounds, checked transports and deferred client/BO/queue retirement. Upstream has also added 740M/760M topology and power-management work. | Keep the requested 780M scope; new profiles and power/display writes need their own review and target evidence. |
| Display | Upstream adds panel PWM/backlight work and gamma-related registry properties. Downstream retains explicit unsupported gamma/CLUT callbacks plus adopted read-only panel timing and native-2x HiDPI policy. | These are different display paths, not interchangeable fixes. Panel, color and sleep behavior remain untested for the downstream candidate. |
| Metal scheduling and caches | Downstream contains the adopted sampler/surface/descriptor-key work and its bounded caches, translation sharing and async library/function dispatch. Upstream has newer surface-copy, allocation-pool and linked-shader changes. | Test combinations separately. CPU fixtures establish neither rendering correctness nor measured latency/FPS gains. |
| Other components | Upstream adds an HDA component and reference-machine operational scripts. | Not adopted. Component/per-file licensing, provenance and machine-specific behavior still require review before adoption. |

The root `LICENSE`, `LICENSES/` and `THIRD_PARTY_NOTICES.md` are unchanged
between the two compared trees and by this session. Existing component terms
remain distinct: bring-up/tools use their MIT/GPL notices, while accelerator
and plugin code retain PolyForm Noncommercial notices. The existing broader
publication audit is not resolved by this comparison. No upstream driver code
or binaries were added to the tracked tree during this session.

## Observed local runtime

The local system reports **macOS 26.7.2, build 25G332**, Darwin 25.6.0,
x86_64. Apple Clang is 21.0.0 (`clang-2100.1.1.101`); the selected CLT SDK
is 26.5. The final suite and corrected-fixture runs used the existing managed
Python 3.13.18; earlier attempts are distinguished below and in JSON.

The private inventory found one registry `1002:1900` candidate and assigned
range metadata. PhxBringup, PhxAMDFB and NMXAccel services are present.
Registry identity is not independent physical/IP discovery or region-ownership
verification. The inventory and preflight retain their false execution and
initialization flags. Read-only recovery review found a separate EFI Git
repository, complete prior-update driver/kernel-collection backups, and
existing rollback scripts. No recovery boot or rollback was performed; the
external-disk migration and actual recovery bootability remain unverified.
One existing rollback script writes the internal EFI; it was not executed.

**The loaded PhxBringup reports build 34; downstream source defines build 33.**
The installed source SHA is unknown. A matching device or ABI cannot establish
that the downstream commits are installed.

- `native-shader-probe --check`: exit 0, identity and ABI readiness only;
  no context/BO allocation, mapping or GPU submission.
- `metal-smoke --list`: exit 0, one PCI-matched 780M Metal device; the existing
  runtime reports native ABI 1.12 / build 34.
- The display baseline attempt stopped with exit 5 at missing
  `debug.nvaccel_iop_damage`. No baseline JSON, cadence/FPS or H1-H4 verdict
  was accepted. The collector was not weakened to tolerate missing counters.

## Installed-stack GPU baseline

After the owner explicitly authorized GPU acceptance and the read-only
recovery review above, `metal-smoke` ran once against the existing stack:
**exit 0, all six cases passed**. Its source matches `15b684d` and has SHA-256
`2f93cf5879426c24ecd1450d606e17fc6fbc4971b5f4623dc9057115c270af4a`.
No newly built driver or plugin was installed for this test.

| uint32 elements | Output offset (bytes) | Acceptance |
| --- | --- | --- |
| 1 | 0 | Exact arithmetic results, unchanged input and guards passed |
| 63 | 256 | Exact arithmetic results, unchanged input and guards passed |
| 64 | 0 | Exact arithmetic results, unchanged input and guards passed |
| 257 | 256 | Exact arithmetic results, unchanged input and guards passed |
| 4,097 | 0 | Exact arithmetic results, unchanged input and guards passed |
| 65,537 | 256 | Exact arithmetic results, unchanged input and guards passed |

The probe selected the unique registry-matched PCI `1002:1900` Metal device,
compiled project-owned MSL through the installed Metal runtime, dispatched real
Metal compute commands and checked every output word, poisoned output, input
and guard region. It has no default-device or CPU-result fallback. Each
command had a 30-second completion limit; none timed out or reported failure.
The process finished in 2.372 seconds; this elapsed time is **not** a benchmark.

This establishes the installed stack's bounded Metal compute correctness,
not its source provenance, physical/IP ownership, sustained stability,
WindowServer/rendering, video, sleep/wake or performance. In particular,
**build 34 / unknown installed SHA cannot accept this branch's build 33**.
The native low-level shader probe remained check-only; its ownership gate was
not bypassed. Raw runtime diagnostics remain private and ignored.

## Completed source and host checks

- Final Python suite: **360 tests, zero failures/errors/skips**, Python 3.13.18,
  on the exact committed validation tree above.
- Both upstream and downstream `make test` passed with ASan/UBSan and strict
  warnings. Their firmware-file-dependent cases were explicitly skipped because
  no Phoenix firmware fixtures were downloaded. Synthetic extractor checks ran.
  Upstream includes topology and a wait model; downstream includes 43 panel
  timing cases. These different test sets are not a performance A/B.
- Actual sampler-key, IOSurface registry/monitor and descriptor-mask fixtures
  passed. The optional IOSurface GPU probe was compiled but not executed.
- Translation-sharing and async-cache fixtures passed ASan/UBSan and separate
  TSan. After the lifetime-fixture correction, async library and function
  fixtures passed both sanitizers at widths one and two, plus five additional
  processes per width/configuration: **48 processes / 76,800 stress requests**.
  See [the lifetime record](local-fixture-lifetime-20261112.md).
- Hardware-gate, present-pacing and copy-path policies passed ASan/UBSan;
  the source/counter contract passed. Actual-method transport, lifetime,
  allocation, firmware, queue, VM and probe-simulation outcomes are recorded
  individually in the [JSON companion](local-hackintosh-20261112.json).
- PhxBringup and PhxAccel compiled/linked and passed ad-hoc signing plus strict
  verification. The real Metal plugin compiled/linked, its class exports and
  Mach-O structure were checked, and signing/strict verification passed. These
  binaries were not installed or loaded. The plugin is compile-only and lacks
  its separately built runtime dependencies.

The component sources built were pinned at the starting downstream commit;
their Git tree IDs are unchanged in the validated revision and recorded in
JSON. MacKernelSDK `3f750085caa17ec3a7880f11c11bf4f48cd6a164` and Vulkan-Headers
`6802bb4733b63ed5efd3adb308a6c885ef180ea1` were fetched into ignored local
build output. Their APSL/per-file and Apache-2.0/MIT notices were reviewed
before use; neither dependency nor any resulting binary was published.
Build logs contain three bring-up shadow warnings and 336 plugin warning
lines, predominantly deprecated Metal declarations; this is not a warning-free
build. Extracted-fixture input hashes were checked against committed blobs.

## Failures found and corrected

1. The inventory omitted `hardware_executed=false`, so its own output failed
   the strict preflight. Commit `d5dd49b` adds the explicit field and collector/
   Recovery-to-preflight integration coverage without relaxing the gate.
2. Async-library TSan exposed a fixture assertion that observed weak nil
   before checking the separate destructor counter. Commit `6e75d6f` waits
   for both observations in library/function fixtures, retaining the deadline
   and final exact-count assertion. Production retention code is unchanged.
3. The IB regression runner forced unsupported leak detection on Apple ASan
   and exited before reaching the fixture. Commit `15b684d` disables that
   unsupported feature on Darwin, preserves Linux leak detection, and reports
   the distinction. The old actual method then produced its required heap
   overread and all **112 corrected scenarios passed** with ASan/UBSan.

The initial system-Python 3.9.6 run had one error in 358 tests because
`Path.write_text(newline=...)` requires a newer interpreter; the project
already requires Python 3.10+. The supported-interpreter rerun supersedes it.
Nineteen harness attempts were initially refused by the clean-source guard
while fixture edits were uncommitted. A subsequent clean run exposed the IB
startup issue above and stopped there. These failed/refused attempts are
retained locally and are not counted as passes. The fixes were validated on
committed source without bypassing the clean-source checks.

The first parallel shader/native-probe simulation attempts exceeded the
outer runner's 240-second group budget. Those two timeouts are not passes.
Only those groups were rerun with a 900-second outer budget; the scripts'
15-second per-case timeouts and all assertions were unchanged. The JSON
records both attempts and their final outcomes.
The retries passed **1,830 shader-probe and 1,970 native-probe simulation
cases**, taking 768.3 and 789.58 seconds respectively. These 3,800 ASan
scenarios ran on CPU/fake IOKit and are separate from the Metal GPU test.

## Remaining acceptance and rollback

`xcrun --find metal` exits 72 under the selected CLT installation; no Xcode
application was found in the standard application directories. Metal.framework
descriptor tests, plugin linking and the installed runtime's MSL compile
succeeded, but the repository's full Apple Metal/AIR compiler chain was not
exercised here. The relocated-plugin no-device test
also requires a host without target services; do not disable that safeguard
or interrupt the installed stack to force a passing result.

No source-correlated candidate runtime, tested recovery boot, display
regression, sustained workload or latency/memory/frame-time A/B has been
established. The installed build-34 compute pass and CPU model tests do not
accept the downstream build-33 code. Before candidate GPU acceptance, a human
must confirm the recovery boot and deploy an identified candidate using the
separate EFI procedure, preserving the known working configuration. This
session submitted the bounded Metal smoke to the already-running stack;
it performed no deployment, manual firmware initialization, reboot,
EFI/NVRAM/BIOS/disk/security change or binary upload.

The three fixes affect tools and fixtures only; rollback is a normal reviewed
revert of the corresponding commit. No running driver rollback is needed.
Raw logs, private inventory/ranges, binaries, caches and disposable source
trees remain ignored under local `build/`; public evidence contains only
selected metadata, hashes, results and limitations.
