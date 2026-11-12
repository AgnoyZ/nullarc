# Prioritized downstream improvements

Status at 2026-11-12. Scope: `downstream/780m-tahoe`, Radeon 780M
`1002:1900`, planned Tahoe. The target OS installation/build and real GPU
execution remain unverified. The reference is the ignored source checkout of
NullMoth `7412cdde81447f78da0ebb64216dc258d8beaedb`; NVIDIA hardware routines
are not AMD implementation evidence. No reference source is copied by the
allocation change below. Existing component licences and notices remain intact.

| Priority | Work | Current result / remaining acceptance |
| --- | --- | --- |
| P0.1 | Hardware parameters and resource provenance | QueryInfo now explicitly flags the assumed GC/address profile and system-memory software budgets. Registry metadata distinguishes these from target measurements. Actual IP discovery and exclusive firmware/display reservations still require target evidence; no new register reads or guessed values are introduced. |
| P0.2 | BO lifetime and kernel VA pressure | Reject size-rounding overflow, use subtraction-based budgets for every pool/import, reject a missing kernel view before zeroing. Retain existing descriptor ownership, delayed unmap/free and client quarantine. Moving allocations into the client task is deferred until DMA pinning, temporary kernel views, fence writes, flush paths and client-death lifetimes can be validated together. |
| P0.3 | Truthful Metal capabilities | Optional function-pointer/dynamic-library declarations now require a live backend and their actual translator exports. Both barycentric aliases return false because the Vulkan feature is not enabled. No whole Metal GPU-family/feature-set conformance is advertised. Existing backend-derived sample/length limits and conservative unified-memory answer remain. Shader execution/compliance acceptance is still pending. See `METAL-CAPABILITIES.md`. |
| P1.1 | Present cost | Copy only visible pixels after validating both pitches; batch tightly packed eligible SSE frames into one invocation; forced damage frames no longer read uninitialized shadow pixels. Actual-body host-RAM tests cover pixels, padding, guards, both formats and invocation count. Target A/B remains required before changing copy/sync defaults or claiming a speedup. See `PRESENT-PERFORMANCE.md`. |
| P1.2 | Shader caches | Individual LRU eviction with entry/payload limits; versioned, length/checksum-checked base SPIR-V/index/key-memo files with unique same-directory atomic writes. Host I/O/Foundation tests and actual plugin compilation passed. Existing semantic validation, directory fallback, trimming and specialized cache formats remain; target output/latency acceptance is pending. See `SHADER-CACHE.md`. |
| P1.2a | Duplicate base-shader translation | Share overlapping disk misses for the same full AIR/text/stage/translator identity. At most 64 active tracked owners, bounded waiter timeout, recursion/saturation/disable fallback, success/failure/exception publication and immediate retirement. Native actual-entry concurrency/sanitizer validation must complete before recording a pass; target cold-start and FPS benefit remain unmeasured. See `TRANSLATION-SHARING.md`. |
| P1.3 | Device loss / power | Refuse the main submission if its upload/fill prologue cannot end; release known-unsubmitted command resources/fence/holds, propagate device loss, retain existing uncertain-submit/wait quarantine. Added actual-body fault tests. Suspend/resume/reset still require AMD implementation and target evidence; see `SUBMIT-FAILURE-CONTRACT.md`. |
| P2 | Display discovery | Retain the native-2x opt-in candidate and read-only probe. Adopt PR 9's checked read-only firmware timing metadata with estimated clock and legacy fallback. Both gamma setters and CLUT report unsupported instead of false success without LUT programming. EDID/DDC, extra timing modes, hardware gamma and backlight require separate AMD implementation and hardware validation. Current adoption tests/status are in `UPSTREAM-ADOPTION.md`; see also `DISPLAY-CAPABILITIES.md`. |
| Engineering | Native checks / upstream PRs | All eight pinned upstream candidates passed run `43062283194` with a restored test-only wait overlay. This is modified-model/compiler evidence. PRs 6-9 are now adopted into downstream source with sanitizer targets; current downstream CI results are tracked separately in `UPSTREAM-ADOPTION.md`. No binary uploads or target GPU claims. |

## Allocation contract and rollback

`PhxBoPolicy.hpp` checks the size before adding 4095. A failed check leaves its
output unchanged. Each pool check requires nonzero size, sane existing usage,
and `size <= budget - used`; callers debit only after a descriptor and kernel
view exist. Host import still calls `prepare()` and releases on pin failure.
The new QueryInfo bits are additive diagnostics; wire sizes and ABI minor 12
are unchanged. Existing consumers may ignore unknown flag bits.

`tools/test_bo_create.py` extracts the actual current allocation/import methods
and budgets, rejects missing/duplicate definitions, runs 30 fault/boundary
cases with ASan/UBSan on POSIX Clang, and hashes its inputs. It also exhausts
small budget combinations and the 4095 overflowing page-rounding inputs.
Its descriptor/task/pin/lock observations are fakes, not memory-pressure or GPU
evidence. Windows only checks extraction/refusal; native execution is in the
focused `priority-validation.yml` workflow alongside existing lifetime suites
and real kernel/plugin compilation. Results must be recorded after CI finishes.

Rollback this isolated source experiment by reverting its commit. It changes no
EFI, boot configuration, firmware, disk, OS security or deployed driver.
