# Original build-34 layout correction

This is an isolated recipe for upstream v0.4.0-alpha commit
`9dd76b604fca5e0125bd3caa5723df0f611ff27f`. It does not build the downstream
build-39 kernel, relabel a kernel, install files or execute GPU commands.

```sh
python3 tools/upstream34_layout/build.py build/upstream34-layout-example-private --compile
make test-upstream34-layout
```

The output directory must not exist. The recipe materializes six pinned
upstream user-space inputs and their applicable notices, applies the single
scoped patch, and copies the shared layout validator. On macOS, `--compile`
builds and ad-hoc signs only `mesboot` and `phxctl`, recording input/output
hashes and retaining compiler logs. An existing upstream unused-variable
warning is preserved. No firmware, plugin, accelerator, runtime or EFI is
downloaded, copied into this repository or published.

The separate operational candidate uses the retained, unchanged original
build-34 kext. Source arithmetic and fake-IOKit/shell checks are not GPU
execution or memory-ownership evidence. See
[the correction record](../../docs/UPSTREAM34-LAYOUT-CORRECTION.md) before
considering any deployment. The existing downstream sources and `main` are
not replaced by this recipe; `patches/` remains historical.

After the consumed 2026-11-15 desktop trial, this downstream recipe also retains
initializer stderr and exact failure status, and includes IOKit return codes
and returned/expected lengths in transport diagnostics. PSP-destroy and
firmware-load failures are no longer swallowed by stderr redirection/filtering.
Successful GPU-command order and fail-closed checks are unchanged. The initial
diagnostic candidate was source-only. A later owner continuation installed only
the four diagnostic user files, including command/status details for firmware
refusals, and prepared a new single-use observer. At that preparation checkpoint
no reboot or GPU work had been dispatched. This recipe remains distinct from
the default branch's pinned candidate. The failed trial, actual deployment and
firmware-desktop state are recorded in
[the retest result](../../docs/UPSTREAM34-DESKTOP-RETEST.md#consumed-trial-result-original-startup-requested-fallback).

The later diagnostic boot also failed before queue setup. Offline tests
reproduced a silent status-1 exit when no shutdown timer remained. Both shell
cancellation sites now accept only the exact C-locale no-process diagnostic
with status 1; other cancellation errors remain terminal and visible. An
inherited ERR trap retains the initializer line/status for other failures.
The nested shell fixture verifies original GPU ordering after the benign case
and refuses actual cancellation errors before queue setup. Nineteen focused
methods pass. This establishes a shell correction, not the precise untraced
command from the failed live boot or accelerated desktop success.

The same correction is synchronized to the default branch's actual entrypoints.
A new distinct packet installed only the two shell files; both existing binary
hashes remain unchanged. Its launchd preparation passed with no GPU work.
Dispatch and actual postboot outcomes are separate from this preparation.

## Desktop evidence contract

`desktop_evidence.py` validates already-collected original build-34 frame
samples without importing a GPU, loader or process API. `debug.nvaccelfb=3` is
a write command; its getter returns the boolean `gNvAccelArmed`, so an armed
readback must be **1**, not 3. Both samples must retain the display gates, frame
counts must increase, WindowServer must remain a single unchanged process and
the diagnostic-report list must not grow. Save both private samples before
validation so a failed gate remains diagnosable. CPU regression command:

```sh
python3 -B tests/test_upstream34_desktop_evidence.py
```

`startup_evidence.py` captures a single boot-time cutoff before polling original
startup. Re-reading `kern.boottime` after a wall-clock adjustment can reject a
block admitted earlier in the same boot. The reader retains the original
latest-block and stale-log rules; callers must bind it to one boot identity.
The private witness snapshots once and checks that identity during observation.
Clock-step replay and stale/newest-block CPU regressions run with:

```sh
python3 -B tests/test_upstream34_startup_evidence.py
```
