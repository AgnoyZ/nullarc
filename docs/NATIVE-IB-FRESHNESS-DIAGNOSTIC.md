# Two-policy native IB freshness diagnostic

Status on 2026-11-16: **reuse failed its second dispatch; the separate fresh
trial passed both guarded dispatches** with the same original build34 image,
diagnostic source and binary. Each policy consumed its own bounded scope and
completed one recovery reboot. The comparison prioritizes the rewritten/reused-IB
path for investigation; it does not establish a specific cache cause or accept
the wait candidate. The driver and default branch remain unchanged.

The original build34 byte diagnostic verified pass 0, then reported positive
retirement with actual `0xde` versus expected `0xdf` at the first output byte on
pass 1. That byte matches the previous pass, but the rest of the output was not
captured. See [the observations](FENCE-WAIT-DEADLINE.md#original-build34-byte-diagnostic).
This new diagnostic tests one specific investigation lead without enabling
global BO cache flushing or changing the kernel's packet/fence handling.

## Controlled comparison

`tools/native_ib_freshness_probe.cpp` is a separate tool derived from the
reviewed build34 HOLD adapter. The canonical acceptance probe and production
driver are unchanged. Each invocation selects exactly one policy and performs
at most two dispatches on one native context and one 16-KiB GTT BO.

Both policies use the same shader, four-word output patterns, output address,
BO/VA geometry, guards, sequence validation and wait policy. Before the first
dispatch, both stage the same two complete 320-byte IBs:

| BO-relative offset | Contents |
| --- | --- |
| `0x0000` | Unchanged 79-word reference shader and zeroed page tail |
| `0x1000` | Slot 0: pass 0 IB and two NOP words |
| `0x1200` | Slot 1: pass 1 IB and two NOP words |
| `0x2010` | Reused 1024-byte output, complement-initialized before each pass |
| `0x3000` | Full canary page |

On pass 0, both submit slot 0. On pass 1:

- `--run-reuse` overwrites slot 0 with pass 1's already built packet and submits
  slot 0 again.
- `--run-fresh` leaves both IBs unchanged and submits slot 1.

The controlled factor is rewriting/reusing an IB slot versus selecting its
pre-staged immutable counterpart. The output remains at the same address and is
re-poisoned in both policies. Code, guards, inactive IB and all other bytes remain
in the full 16-KiB comparison. The new reuse control is **not identical to the
earlier frozen probe**: both new policies pre-stage two IBs, leave the common
code/guard data in place, and stop after two dispatches. The new control must
reproduce the failure before a comparison with fresh mode is informative.

## Admission, waits and failure containment

The explicit CLI is:

```text
native-ib-freshness-probe --check|--run-reuse|--run-fresh [--upper]
```

The ambiguous old `--run` argument is refused before device access. Admission
requires x86_64 Darwin 25, exactly one PCI-verified `1002:1900` PhxBringup service,
matching ABI 1.12 and build34, valid geometry and non-hung native-queue readiness.
`--check` opens a connection for identity/readiness only; it creates no context,
BO or mapping and submits no GPU work. Native compilation does not run even
this check.

Each dispatch tries budgets 0 ns, 50,000 ns and then the 2-second cap only while
pending. Positive retirement, exact sequence replies and every checked byte are
required. The original 250-ms inter-dispatch pause remains. No extra fence,
register write, tuning change, queue adoption or cache-flush experiment is added.

An exercise/validation failure enters the original build34 HOLD: it keeps the
connection and any mappings alive, performs no further submit or explicit
cleanup, and waits for external bounded recovery. A successful exercise follows
the existing cleanup checks; a cleanup error cannot print success. This tool
does not install, supervise or recover itself. A separately admitted independent
watchdog, exact-image pins, headless containment and a one-use recovery scope
are required before any future manual `--run-*` invocation. Do not kill a held
probe, unload an initialized driver or reuse a consumed trial packet.

Success prints `DIAGNOSTIC-PASS` with the selected policy and explicitly excludes
driver/display acceptance. It is not the canonical probe's PASS marker, the
wait candidate's 96-dispatch gate, or a frame-rate/stability measurement.

## Interpreting a future comparison

1. If the new reuse control does not reproduce the failure, stop: its changed
   common fixture has not preserved the trigger, so a fresh-mode pass would not
   isolate the original fault.
2. If reuse reproduces the failure and a separately authorized fresh trial
   passes, the evidence would implicate the reused-IB path. It would still not
   distinguish CPU-to-GPU visibility of rewritten commands from GPU command
   caching/prefetch, or establish correctness outside these two dispatches.
3. If both fail, result visibility, execution and fence/data ordering remain
   open. Fresh mode does not prove that all CPU/GPU cache paths are correct.

The earlier byte diagnostic, reuse control and fresh comparison have each
consumed their separate one-init/one-recovery scopes. No runtime controller,
startup job or further trial remains armed. Any additional GPU experiment needs
a new bounded scope; do not replay either policy's consumed packet or promote
the wait fix because a diagnostic marker appears.

## Original build34 reuse control

The separately admitted reuse-only trial on macOS 26.7.2 / 25G332 used the exact
original build34 image and the offline-validated diagnostic source/binary.
Initialization, the original compute/graphics outputs and both queue adoptions
passed. The new two-pre-staged-IB fixture then submitted two dispatches:

- Pass 0 verified the complete 16-KiB BO.
- Pass 1 reported positive retirement, then failed at the first output byte,
  offset `0x2010`: actual `0xde`, expected `0xdf`. The current poison byte was
  `0x20`. CPU-visible bytes before that offset matched the expected image.

This reproduces the previous failure's pass, offset and observed byte with the
new reuse fixture. It establishes the control needed for a future fresh
comparison, but does not show which commands the GPU fetched or prove that the
whole previous output was returned. Fresh policy was not run in that scope;
the separate later comparison follows below. The two-second
wait budget, CPU-load/concurrent-client phases, accelerated desktop and FPS
were not tested, and the wait candidate is not accepted by this result.

The original HOLD retained failed resources, immediate failure detection
requested one serialized recovery reboot, and the recovery observer made zero
GPU calls. Independent result, retirement and final checks passed: the exact
original image, 347 EFI files (including 148 Microsoft files), 46 protected
files, two protected links and security/kernel-collection state were preserved.
No new matching diagnostic report was found. The consumed startup job was
removed; GPU-off and the firmware framebuffer remain in place, with no active
probe or shutdown process. See the
[sanitized reuse record](validation/upstream34-native-ib-reuse-control-20261116.json).

## Original build34 fresh comparison

The separately continued fresh-only trial used macOS 26.7.2 / 25G332 and the
exact same original build34 image, diagnostic source and executable as the
reproduced reuse control. It performed one initialization and at most two
single-client dispatches. Original compute/graphics outputs and both queue
adoptions passed. No EFI/kext replacement, preliminary reboot, tuning write,
CPU-load worker, concurrent client or display takeover was added.

Both pre-staged IBs remained unchanged. Pass 0 submitted slot 0 at `0x1000`;
pass 1 submitted slot 1 at `0x1200`. Both dispatches verified the complete
16-KiB BO, including the shared output at `0x2010`, code, both IBs and guards.
The successful cleanup completed, stderr was empty, and the tool printed its
fresh-policy `DIAGNOSTIC-PASS` marker. WindowServer's PID stayed unchanged
during the trial.

| Pass (zero based) | Budget | Pending | Elapsed |
| --- | --- | --- | --- |
| 0 | 0 ns | yes | 25,037 ns |
| 0 | 50,000 ns | no | 35,226 ns |
| 1 | 0 ns | no | 42,479 ns |

The two-second cap path was not reached. The same three read-only tunables were
zero after initialization and before the probe. This is a two-dispatch
diagnostic result, not the wait candidate's 96-dispatch acceptance gate or a
background-load, desktop-stability or FPS measurement.

| Policy, one trial each | Pass 0 | Pass 1 |
| --- | --- | --- |
| Reuse: rewrite/resubmit slot 0 | Full 16-KiB comparison passed | Positive retirement, then `0xde` instead of `0xdf` at `0x2010` |
| Fresh: select immutable slot 1 | Full 16-KiB comparison passed | Full 16-KiB comparison passed |

This pair supports investigating command modification and IB-address reuse
before adding a broad cache-flush workaround. The policy couples two factors:
rewriting/reusing slot 0 versus selecting immutable slot 1. The two trials also
used separate initialization and boot scopes. One trial per policy does not
separately identify CPU-to-GPU visibility, GPU caching/prefetch, or execution
and fence/data ordering, and does not prove general driver correctness.

After successful native cleanup, the controller requested its one authorized
recovery reboot to return initialized hardware to GPU-off. This was planned
state restoration, not a fresh-probe failure. The recovery observer performed
zero GPU calls. Independent result, retirement and final readbacks confirmed
the exact original image, 347 EFI files (including 148 Microsoft files), 46
protected files, two links and security/kernel collections unchanged. No new
matching diagnostic report was found. The consumed startup job was removed;
GPU-off and the firmware framebuffer were verified, with no active probe or
shutdown process. Neither consumed policy packet may be replayed.

See the [sanitized fresh record](validation/upstream34-native-ib-fresh-control-20261116.json).
The earlier reuse and byte-diagnostic records remain unchanged. Default stays
on A1/A2/corrected-A3; the wait correction is not promoted and accelerated-desktop
HOLD remains in force.

A subsequent [selective CPU IB publication diagnostic](NATIVE-IB-PUBLICATION-DIAGNOSTIC.md)
keeps the reused IB address and changes only targeted CPU cache maintenance
before the second submission. Its later new-source control and publication
treatment both failed pass 1 at `0x2010` with actual `0xde`, expected `0xdf`,
after positive retirement. Five IB-only `CLFLUSH` operations plus `MFENCE` did
not eliminate that signature. Both new scopes were independently recovered and
retired; this result does not prove a specific cache cause or accept a production
fix. The earlier pair and both policy scopes above remain unchanged and consumed.

## Host validation and rollback

`tools/test_native_ib_freshness.py` compiles the actual new C++ source through
the shared fake IOKit fixture under ASan/UBSan, in both VA variants and policies.
The fixture independently checks the complete packets, full pre-submit image,
selected IB address, ABI shapes, wait budgets, cleanup and HOLD traces. Every
word of the extra IB is also corrupted, including when that IB is inactive.
Explicit injected stale-output and stale-IB-fetch models test the diagnostic's
failure handling; they are assumptions supplied by the test, **not** a GPU ISA,
cache or hardware model validated on this machine. The test-only escape from
HOLD throws inside fake `pause()`; production retains its real indefinite pause.

Run only from a clean committed source checkout:

```sh
python3 -m unittest discover -s tests -p test_native_ib_freshness_runner.py -v
python3 tools/test_native_ib_freshness.py --out build/ib-freshness-host-tests
python3 tools/test_native_shader_probe.py --out build/canonical-probe-host-tests
```

The source-only snapshot and exact file hashes bind the offline validation;
see [the validation record](validation/native-ib-freshness-diagnostic-20261116.json).
On 2026-11-16, all 4,288 new diagnostic scenarios (1,072 cases in each
policy/VA combination), 1,970 canonical-probe regression scenarios and 16 focused
runner tests passed. Both C++ matrices used ASan/UBSan. An x86_64 build linked
against real IOKit/CoreFoundation also compiled with warnings treated as errors.
At that offline checkpoint the binary had not been executed, and private
watchdog/controller helper regressions used mocked recovery dispatches only.
The later real reuse and fresh executions are recorded separately above; both
runtime scopes are consumed and their startup jobs have been removed.
The manual source-test workflow also runs the fake-IOKit simulation; no real
diagnostic `--run-*` command is added to CI.
The native framework build step itself is compile-only. No new binary is included in
automatic packaging, installation or public artifact uploads. The reference
shader and AMD notice remain unchanged; [existing provenance](GFX11-SHADER-PROBE.md#provenance-and-licenses)
and the repository's component licenses still apply.

Source rollback is a normal revert of this diagnostic-only change. Each policy
trial completed its single recovery and removed its consumed startup job; no
driver or EFI replacement was made in either trial.
Default stays on A1/A2/corrected-A3; wait promotion and accelerated-desktop HOLD
remain unchanged.
