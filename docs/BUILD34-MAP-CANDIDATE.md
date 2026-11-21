# Build34 R3 minimal mapping-observer candidate

November 21, 2026: the [mapping-only observation insertion](BUILD34-MAP-OBSERVATION.md)
now has a privately built and strictly signed kernel candidate. **At this
historical build checkpoint it was not installed or loaded.** The later
[authorized trial](BUILD34-MAP-OBSERVER-TRIAL.md) passed independent boot and
desktop readback after one ordinary restart. The image contains none of the full quarantining R3 transforms,
exact receipt protocol or reader binding. All 172 production inputs and the
accepted R1b/R2a/plugin/ACPI/startup installation remained unchanged at build time. Build41/42
are not prepared or used.

## Source and byte-exact control

The source is accepted default-build34 R1b commit
`194ce9098b34c9f48483ff0729a50b21c5ca0401`, plus only the previously tested
startup map-option insertion from transform checkpoint
`3d26409b1b151992d0dcaeb7093ce104a5c034dd`. The new builder's own digest is
recorded separately; the transform checkpoint is not claimed to contain that
later build recipe. The complete observer driver has SHA256
`9826065e11adc6ec7363459210704b685d1fc5df29758271ca674163254cd0c3`.

`tools/build34_map_candidate.py` first checks all kernel source, ABI, build and
licence inputs against the accepted R1b commit and freezes the earlier
104-input observation evidence. It then runs the unchanged kernel build
recipe only inside fresh private snapshots with the independent pinned SDK.
The existing reviewed Radeon-780M-only packaging is applied to output bundles;
source Info.plist, dependencies, identifier and build34 marker stay unchanged.

The control reproduces the **entire accepted R1b bundle byte-for-byte**, not
just its version or one method. The observer has a distinct image identity;
only `Contents/MacOS/PhxBringup` differs within its bundle. Both strict
signatures and x86_64 architecture checks pass. Three existing compiler
warnings and all **375 imports** are identical.

| Executable | SHA256 |
| --- | --- |
| Reproduced accepted R1b | `0414c22119bad9526a33ec97bb56b9e7a8fd26320976cf24e0cb541d0d882d10` |
| Mapping-only observer | `923182fab482d5c584f484520622283922f67a9caaa2d310e638cd71d1fb1dc7` |

No upstream implementation or component was copied into a different-licence
component. Existing licence/notice inputs remain byte-identical, including
the pinned SDK notices in its private snapshot. No binary, SDK, firmware,
runtime, EFI configuration or raw diagnostics are uploaded.

```sh
nice -n 15 taskpolicy -b make -j1 build-build34-map-candidate \
  KERNEL_SDK="$KERNEL_SDK" \
  MAP_CANDIDATE_OUT=build/build34-r3-map-candidate-new-private
```

Seven new CPU unit methods cover exact input/delta refusal, the prohibition on
using the full R3 source as this candidate, and a complete prospective EFI
manifest. The latter retains all 358 paths, including external Microsoft
records, and changes only the exact accepted executable. The earlier mapping
block/sanitizer/native-object evidence is frozen rather than counted as newly
executed hardware evidence.

## Actual loading route and inherited dependency

Fresh `kmutil showloaded` collection queries independently matched the loaded
PhxBringup UUID to the hash-checked accepted R1b reference. It is in the **boot
collection**, with no PhxBringup in system or auxiliary. A separate exact
reference/UUID check also matched the currently loaded accepted R2a accelerator.
Raw UUIDs and addresses remain private. No unload, runtime load, alternate
identifier, private-provider declaration or collection replacement was tried.

The inherited `_thread_call_cancel_wait` import remains absent from the six
declared public KDK providers. This work does **not** waive or close that generic
KPI/AuxKC admission gap. It establishes the actual existing control's boot
route and preserves its whole import set. The later trial independently proved
the observer booted in that same collection. Do not move it into AuxKC or
change identity/security/dependencies to avoid that requirement. The separate
full R3 public-timer source removes the private import but remains an
undeployable, quarantining experiment for its other unresolved requirements.

## Current baseline and inactive recovery references

A new privileged read-only preflight passed complete 358-file EFI comparison,
the full accepted cache metadata comparison, exact R1b/R2a/plugin/optimized
ACPI and source gates, current-boot startup/desktop receipts, jobs and recovery
inputs. It also checked the startup limits, disabled resident monitoring,
same WindowServer, advancing VBL/copy counters and four zero checked errors
over a finite interval on macOS **26.7.2 / 25G332**. This is baseline readback,
not observer loading, GPU correctness, physical FPS or long-term acceptance.

The initial command wrapper used an incorrect absolute taskpolicy path and
did not launch the reader. The corrected read-only preflight outlived the
tool's 30-second response window. It was **not restarted**: independent process
inspection found no remaining reader and read its completed passing filtered
result. That tool timeout is not called a driver or hardware-test failure.

A new root-owned inactive artifact packet contains the exact control/observer
bundle pair, native source/build evidence, the accepted parent's pinned
contract, both current startup-job backups and a prospective full EFI
manifest. Fourteen sealed files and both signatures passed a separate
independent readback. During that inactive artifact check the control was still
loaded; the observer was not.

**The packet is not a trial controller or an authorization.** It contains no
installed launch job, startup adapter, prepared recovery journal, installer,
GPU probe or power dispatcher. No EFI/driver/job/PR28/security setting changed,
no work was submitted and no power request was made. It must not be activated
by replaying an older R1b/R2a controller or by merely copying the new executable.

## Next admission step

The subsequent [observer-compatible startup/recovery adapter](BUILD34-MAP-OBSERVER-SCOPE.md)
now passes 23 CPU unit methods and independent readback of a final 66-file
inactive scope. It preserves R2a/VBL/optimized ACPI/plugin, daily PR28 250 ms/
WindowServer exclusion, 45/150/300-second gates, at most one first-trial
recovery restart and zero daily power recovery. Recovery targets the current
R1b executable and current R2a-compatible jobs. Runtime admission validates and
adds only the three new map properties to the old strict geometry. Its explicit
new-trial grant is false and actual runtime construction refuses it; no job or
driver was installed by that preparation. A distinct owner-authorized scope
later performed the sole ordinary restart and readback; do not activate either
inactive reference packet or replay the consumed trial.

The later observer boot found `map_options=0x1` and the default cache option
`0`. Effective mapping/coherency, external-writer ownership, native
receipt/session/visibility, completion events, healthy teardown and actual
GPU/FPS/latency/stability acceptance remain open in the [R3 ledger](BUILD34-R3-PLAN.md).
See the [sanitized result](validation/build34-r3-map-candidate-offline-20261121.json).
