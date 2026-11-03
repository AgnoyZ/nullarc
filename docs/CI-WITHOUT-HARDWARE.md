# Working on the driver without the target laptop

The target machine is a ThinkBook with the Radeon 780M that the panel is wired to. When it is not available,
the honest question is not "can CI replace it" — it cannot — but "what can CI still settle, and what does it
have to keep for the laptop".

This file answers that, and lists the queue this project can ship while the laptop is away.

## 1. The rule that does not move

Acceleration, smoothness and panel behaviour are claims about **this GPU executing this driver on this
panel**. Nothing below produces evidence for them:

- a hosted `macos-15-intel` runner has no 780M, so the kexts compile, link and sign but never attach;
- an `ubuntu-24.04` runner runs the real kernel sources against fake IOKit, which tests logic and refusal
  paths, not hardware;
- `metal-smoke` on CI is expected to **refuse** the host (exit 4) — that refusal is the assertion.

So every document, tool and test added here keeps `hardware_execution_established: false`, and none of them
is called a result. What they remove is *avoidable* hardware time: a wasted capture, a mis-read column, a
verdict re-derived by hand from a JSON file, a renamed counter discovered after a reboot.

## 2. What CI genuinely establishes today

| question | gate | what it does not establish |
| --- | --- | --- |
| Do the two kexts, the Metal plugin, the AIR translator and Mesa RADV still build, link and sign against the pinned MacKernelSDK/Vulkan-Headers/LLVM? | `macos-kexts` job | that anything loads, runs or draws |
| Does the display-path policy behave (patch 0028: alias retry budget, VRAM pool release validation, pool shrink)? | `tests/test_hardware_policy.cpp` under ASan/UBSan on Linux | that the policy fixes a real frame rate |
| Do the present-pacing rules behave (complete on the next tick, complete anyway past two refreshes, four held frames then copy, gap buckets unchanged)? | `tests/test_present_pacing.cpp` under ASan/UBSan on Linux | that frames reach the panel, or when |
| Do the real kernel source paths behave under fault injection? | the `tools/test_*.py` fake-IOKit runners | any behaviour of the actual GPU |
| Does the translator/plugin ABI still match, and is the generated SPIR-V valid? | `translator`, `air-runtime`, `plugin-runtime` steps | that Metal renders correctly |
| Can the phase-1 capture read what the analysis needs, under the names the kernel actually declares? | `tests/test_phase1_baseline_shell.py`, `tools/phx_counter_contract.py` | any counter value |
| Is the H1–H4 verdict a computation instead of an opinion? | `tools/phx_baseline_report.py`, `tests/test_baseline_report.py` | the measurement itself |

The last four rows are what the two headless changes added; §4 explains why they are worth CI time.

## 3. What only the laptop can answer

- Every number in `docs/analysis.md`: present rate, copy cost, tick lateness, cadence.
- Whether the carve-out alias is ever verified against the BAR (`alias:` lines in the kernel log).
- Wake-from-sleep repaint, a black screen at cold boot, panel timing on any panel other than the one the
  firmware lit, external displays, backlight.
- Whether any optimisation actually helped. That needs a before/after pair of captures, per change.

## 4. What CI can still push, and in what order

1. **Instrumentation contract** (`tools/phx_counter_contract.py`, in CI). The capture script, the kernel
   sources and `docs/analysis.md` name the same OIDs, and the knobs the A/B plan relies on still start at
   the values the plan assumes. A rename or a flipped default now fails CI instead of costing a session.
2. **Capture completeness** (`tools/phx_baseline.sh`). The present-cadence counters
   (`debug.nvaccel_iop_gap1`–`gap4`, `_vsync_waits`, `_vsync_late`) are recorded, so H3 is decidable from
   the *first* capture rather than from a second trip.
3. **Mechanical verdict** (`tools/phx_baseline_report.py`, in CI). Thresholds written down in
   `docs/analysis.md` §9, refused inputs (snapshot, missing counter, a record claiming hardware execution),
   undecidable hypotheses named as undecidable, and A/B comparisons printed with their noise caveat.
4. **Host-testable present pacing** (`src/phxaccel/PhxPresentPacing.hpp`, `tests/test_present_pacing.cpp`, in
   CI). `isTransactionComplete` (complete a copied frame on the next tick, complete anyway past two
   refreshes), the gap bucketing and the four-held-frames limit were inline expressions inside IOKit calls.
   They are now pure functions the driver calls, asserted on every push — including a value-by-value
   comparison of the bucket rule with the expression it replaced, odd refresh periods included, so the
   cadence counters stay comparable with earlier captures. `docs/DISPLAY-PATH.md` records the three rules
   and what still needs the laptop.
5. **Status honesty, per card.** A `CARD-SUPPORT`-style table (target hardware, what is verified, what is
   not, how it was verified) written the way the nullmoth reference does it. Cheap, and it stops
   "compiles in CI" from reading as "works". Next candidate.
6. **Anything that needs a frame on the panel.** Hardware only, by definition.

## 5. The one hardware session, when the laptop is back

```sh
# 1. baseline, three 60 s windows, read-only
sh tools/phx_baseline.sh --out /Users/Shared/phx-baseline-$(date +%Y%m%d-%H%M) --window 60 --samples 3

# 2. one A/B per switch, changing nothing else (docs/analysis.md §7)
#    B1 debug.nvaccel_iop_sse=0   B2 debug.phxfb_vbl_staged=0
#    B3 debug.nvaccel_iop_vsync=0 B4 debug.phxfb_alias=0

# 3. the verdict, anywhere (this needs no hardware)
python3 tools/phx_baseline_report.py baseline=BASE b1-sse-off=B1 b2-plain-tick=B2 --out build/verdict
```

Send back `baseline.json` (and the A/B `baseline.json` files) plus the `alias:` lines from the kernel log.
Everything else — which hypothesis holds, what the next commit should change, what the A/B changed — is
computed from those files, so a single session produces a decision instead of a folder of numbers.

## 6. Where the project stands

| verification class | state |
| --- | --- |
| kexts, plugin, translator, RADV compile/link/sign (macOS runner) | green in CI |
| offline logic: patch 0028 policy, present-pacing policy, fake-IOKit kernel runners, translator/plugin ABI | green in CI |
| capture ↔ source ↔ analysis contract | green in CI |
| verdict pipeline (fixture only) | green in CI |
| driver loaded and executing GPU work on the 780M | **not established** |
| frames on the panel, present rate, judder, wake | **not measured** |

The bottom two rows are the project's actual acceptance criteria (`docs/DOWNSTREAM-ROADMAP.md`). CI has made
the path to them short and checkable; it has not walked it.
