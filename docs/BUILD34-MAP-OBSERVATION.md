# Build34 R3 BAR0 mapping-observation preparation

November 21, 2026: this is a small observation prerequisite for the
[trusted fence reader](BUILD34-FENCE-READER.md), not an admitted reader or
deployable R3 kernel. The installed driver/settings and all 172 production
inputs remain unchanged. No kext is linked, packaged, signed, installed or
loaded; no user client is opened, GPU work submitted or power action taken.

## Accepted source and actual passive observation

The current production PhxBringup and every source/licence/build input in
the existing kernel recipe are byte-identical to accepted R1b source commit
`194ce9098b34c9f48483ff0729a50b21c5ca0401`. Its existing private reference
executable still has SHA256
`0414c22119bad9526a33ec97bb56b9e7a8fd26320976cf24e0cb541d0d882d10`.
This is source/reference-artifact provenance, not a fresh loaded-image check.
The retained R2a accelerator is a separate component; it is not reconstructed
from an older accelerator source or replaced by this work.

A passive `ioreg` query of the existing PhxBringup service on macOS **26.7.2,
build 25G332** found build34 and a 268,435,456-byte BAR0 aperture. It found
none of the new observation properties. The filtered result is consequently
**mapping-metadata-unavailable**, with native-reader admission false.
Neither an old source comment about write combining nor the absence of
metadata is evidence of effective mapping/cache attributes. Raw registry
output is held only in process memory; it is not saved or published.

## Minimal staged observation

`tools/build34_map_observation.py` stages one insertion into the existing
successful BAR0 mapping block in `PhxBringup::start`. There are two separately
checked source forms: the exact accepted R1b production source and the exact
frozen [R3 factory stage](BUILD34-NATIVE-FACTORY.md). Removing the insertion
recovers each complete preceding source byte-for-byte. Earlier transforms,
headers, native ABI, bootstrap and evidence remain frozen.

The insertion calls the retained mapping object's existing `getMapOptions()`
once and attempts to publish:

| Property | Meaning |
| --- | --- |
| `phx-bar0-map-options` | Complete 32-bit option value returned by the mapping |
| `phx-bar0-map-cache-option` | Cache-option nibble, using pinned SDK mask/shift |
| `phx-bar0-map-observation-version` | Schema version 1, attempted only after both preceding property writes succeed |

These are startup metadata, not controls or a new selector. The code adds no
mapping or alias, changes no cache option, reads/writes no BAR contents, and
changes no submission, fence, resource or startup decision. A property
allocation failure does not change the existing driver's startup result; the
strict observer subsequently refuses partial metadata. No raw virtual or
physical addresses, descriptor pointers or device identity fields are added.

The pinned SDK documents `getMapOptions()` as the options the mapping was
created with, including cache settings. It does **not** document independent
effective PAT/MTRR readback or guarantee GPU-to-CPU coherence. The already
reviewed XNU source also adjusts default-cache mapping options in one mapping
path; this must not be generalized into proof for the actual installed map.
Default cache (zero), known nondefault cache values and unknown nibbles all
leave `effective_cache_proven`, `mapping_coherency_proven` and
`native_reader_admitted` false. No device reader/mode is bound by this stage.

## Filtered read-only collector

```sh
python3 -B tools/build34_map_observation.py
```

The collector invokes only absolute `sw_vers` and `ioreg` read commands, each
with a 15-second timeout. It requires exactly one root service, build34 and a
nonempty aperture. It accepts all observation fields together with version 1
and a consistent cache nibble; it refuses partial/unknown schemas, invalid
integer widths/types and multiple roots. Child properties cannot supply
missing root metadata. Unknown cache nibbles are reported as unknown, never
silently treated as a supported reader mode.

Only allowlisted numeric metadata and explicit nonacceptance fields leave the
decoder. Serial/registry IDs, physical addresses, children and all other raw
properties are discarded. The command exits **2** for unavailable metadata,
**1** for refused/failed observation, and **0** for successfully observed
options. Exit zero still grants no loaded-image identity, effective-cache,
coherency, GPU completion or native-reader acceptance. It neither saves a raw
dump nor requests elevated access.

## Validation and remaining admission

The [sanitized evidence](validation/build34-r3-map-observation-offline-20261121.json)
records 13 Python unit methods, including all cache nibbles/options, strict
types, partial schemas, sensitive-field filtering and absolute command scope.
The actual inserted mapping block passes ASan/UBSan: **4,897 checks in 385
scenarios**, including no mapping and all eight property-allocation failure
masks across cache options. The CPU map double exposes only metadata getters;
it has no BAR pointer/read/write interface. Three assertion-detected variants
exercise an unconditional schema marker, missing cache mask and fabricated
write-combine value. There is no mutable concurrent algorithm here, so no
TSan/device claim is attached to these checks.

All four complete source forms compile against the independent pinned
MacKernelSDK to nonloadable x86_64 `MH_OBJECT` files. Original/proposed R1b
retain the same three warnings and **375 imports**. The corresponding R3
factory forms retain their same four warnings and **376 imports**, all of
which resolve through the existing six declared KDK providers using the
previously checked provider/reference/alias rules. No new dependency or
private-provider declaration is added.

The baseline pair still inherits `_thread_call_cancel_wait`, which is absent
from its six declared providers in the matching KDK. That existing gap is
reported explicitly, not hidden by a monolithic-kernel symbol lookup or by
the public-provider success of the separate R3 source. Earlier R1b hardware
evidence remains history; this new object check does not create a fresh
baseline kernel admission, prove its loading route or authorize deployment.
The separate R3 public-timer stage removes that import, but its complete
source retains the other reader/protocol/lifetime/quarantine restrictions.
Neither source form is promoted to a loadable candidate here.

```sh
nice -n 15 taskpolicy -b make -j1 test-build34-map-observation \
  KERNEL_SDK="$KERNEL_SDK" KDK="$KDK" \
  MAP_OBSERVATION_OUT=build/build34-r3-map-observation-new-private
```

An initial Python test setup attempted to serialize an out-of-range uint64;
the plist writer itself rejected it before the decoder ran. The corrected
test feeds actual oversized XML input to the decoder. This is test setup
evidence, not an installed-driver/GPU failure. The complete native/CPU run
passes in its first private output directory.

Rollback is to stop deriving this insertion; there is no installed change
to undo. To obtain real mapping observations, first admit a minimal native
observation candidate through the actual build34 loading route with exact
source/ABI/artifact and compatible recovery checks. Do not install the full
quarantining R3 experiment for this purpose, replay an old trial, change cache
modes/add aliases, or convert observed options alone into fence correctness.
Initial external-writer ownership, coherent dword visibility, native protocol,
completion wakeup, healthy resource/service lifetime and sequential real GPU,
FPS/latency/stability acceptance remain in the [R3 ledger](BUILD34-R3-PLAN.md).
