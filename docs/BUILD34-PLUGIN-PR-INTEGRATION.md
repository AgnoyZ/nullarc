# Build34 plugin PR integration

On 2026-11-16 the owner requested testing and integration of several upstream
PRs before continuing hardware investigation. This batch derives from default
`upstream34/vram-layout-fix` at
`aef50d8d52c679e4d63f27a204e0a85e66cc4105`, with the accepted A1/A2/corrected-A3
checkpoint `64f3d991a4ddc3af5bbf30cbced9f11d3e7dd50c` preserved.

These are narrow source backports from `luuumi-dev/nullarc`, not a merge of
upstream main or its later kernel builds. Only four existing `src/nmplugin`
files change. PhxBringup remains original build34; its source, native ABI,
production phxctl, PhxAccel and admission checks are unchanged. Neither
build41 nor build42 is a candidate. No installation, plugin loading, GPU
initialization, submission, desktop adoption or reboot is part of this batch.

## Priority and exact upstream inputs

Each selected PR used base `8aba872560a3c9b7dc7a0ddebfad001c6dddf315`.
The head revisions and six changed-file Git blob identities were independently
read back through GitHub's API before integration. Test order was 16, 19, 15,
22; each stage passed its CPU behavior test and native plugin compile before
the next source change was applied.

| Priority | Upstream PR | Pinned head | Selected change |
| --- | --- | --- | --- |
| 1 | [#16](https://github.com/luuumi-dev/nullarc/pull/16) | `0ebda0dc13da7b658dea0c2e9688917ea13d4c25` | Seven-field string key for the texture-wrapping cache; sweep expired weak entries above 256 entries. |
| 2 | [#19](https://github.com/luuumi-dev/nullarc/pull/19) | `f4623df5aefb5689dbd87fa50ac3b6d971ad8592` | Store cache entries through an exclusive temporary file in the same directory and rename; include the local zero-progress-write correction below. |
| 3 | [#15](https://github.com/luuumi-dev/nullarc/pull/15) | `2d198ea005ae2ea8b9828f1cb3e1df99895238b5` | Promote Unknown usage for eligible single-plane application surfaces; preserve the WindowServer, multiplane, explicit-usage and environment opt-outs. |
| 4 | [#22](https://github.com/luuumi-dev/nullarc/pull/22) | `4bb4a6d8eaa05222c8b7e3432e1f67c2a37e508a` | Preserve descriptor `isDrawable` on textures and cached aliases; expose it through views. |

This ordering targets a per-frame CPU cache lookup first, reliable shader
cache storage second, and narrow texture correctness fixes next. It is an
engineering priority, not a measured frame-rate ranking on Radeon 780M.
The upstream application reports explain motivation; their FPS, sandbox and
CoreImage outcomes have not been reproduced on this machine in this batch.

PR16's seven-field texture-wrapping key is separate from A1's two-field
surface-ID/plane writer and synchronization key. The latter is unchanged.
PR15 and PR22 required context-only placement around the preceding changes;
their selected behavior was retained without replacing the A1 implementation.

## PR19 correction found by testing

The unmodified PR19 write loop repeated without progress if `write()` returned
zero with bytes remaining. A CPU failure-injection test reproduced this: the
fourth zero-progress call deliberately exited with status 90 rather than
allowing an unbounded loop. This is a synthetic boundary test, not evidence
that the machine's filesystem returned zero during normal operation.

The local correction treats zero as `EIO`, closes the descriptor, removes its
temporary file and leaves the old entry intact. Negative `EINTR` still retries;
positive short writes advance normally. All cache-store cases then passed.
This is PR19 **with a local correction**, not an unmodified upstream merge.
The implementation uses rename for complete-entry replacement; it does not
add `fsync` or claim power-loss durability.

## Validation and limits

The checked-in result is
[`validation/build34-plugin-prs-20261116.json`](validation/build34-plugin-prs-20261116.json).
Raw logs, generated test sources, source snapshots and compiled bundles stay
in ignored local build directories. No plugin or full-stack binary is uploaded.

`make test-upstream34-plugin-prs` compiles extracted production code under
AddressSanitizer and UndefinedBehaviorSanitizer, with subprocess timeouts:

- PR16: equal inputs, independent variation of all seven fields, absent surface,
  300 surface hashes, expired weak entries and preservation of live identities.
- PR19: complete replacement, short writes, interrupted writes, empty and text
  entries, open/write/zero-progress/close/rename failure, absent inputs and long
  path rejection. Failed stores retain the previous complete entry and leave
  no new temporary file.
- PR15: 144 cases spanning application/WindowServer/environment opt-out,
  zero/one/two planes, storage capability, A8, absent surface and explicit
  usage. Promotion copies the descriptor without mutating the caller's input.
- PR22: descriptor flags, absent descriptor/selector, root textures, parent
  inheritance and the production initialization/alias assignment sites.

The combined gate also runs the existing A1 sampler/surface/descriptor-mask,
A2 framebuffer/alias, corrected-A3 panel, build34 layout and MEC host tests,
plus the baseline unit suite. Firmware fixture tests are skipped when fixtures
are absent; synthetic parser cases still run. The real plugin is compiled for
x86_64 using the existing source recipe, and a release-mode build is checked
for architecture, expected entry points and an ad-hoc code signature without
loading it. Build warnings are compared with the unchanged default source.

These results admit a source integration only. They do not establish GPU
correctness, cache acceptance inside WebKit's real sandbox, Photo Booth image
orientation, desktop stability, lower UI latency or improved FPS. The existing
IB wrong value remains unresolved; wait promotion and accelerated desktop
remain on HOLD. PR28's synchronous commit wait is deferred for separate
analysis because it can directly affect blocking and UI latency. Kernel,
initialization, power and SDMA changes are outside this batch.

The owner's later PR28 wait-timing request is tracked in the separate
[bounded, default-off source adaptation](BUILD34-PR28-WAIT-TIMING.md). It does
not change the results or hardware limits recorded for this four-PR batch.

## License and rollback

The four changed plugin files retain their existing
`PolyForm-Noncommercial-1.0.0` notices. The root license and third-party notices
were reviewed; the selected patches add no external library or binary.
`LICENSE`, `LICENSES/` and `THIRD_PARTY_NOTICES.md` are unchanged. The limited
kext/RADV publication exceptions do not authorize publishing this plugin.

To undo this source batch, use `git revert` on its integration commit after
reviewing any later dependencies. Preserve history and the accepted A1/A2/A3
commits. Because this batch does not deploy anything, it requires no machine
rollback. Any future GPU trial needs its own explicit scope, recovery plan
and real execution evidence.
