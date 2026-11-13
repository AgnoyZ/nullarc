# Fresh live preflight and private native build-37 package

On 2026-11-14, fresh live-execution permission allowed an actual root metadata
preflight and a private local native build. This supersedes the earlier
source-only task boundary. The old M2/reboot grants were not reused. This work
does not establish the allocation root cause or authorize an automatic retry.

## Current machine evidence

The preflight observed macOS **26.7.2, build 25G332**, on **x86_64**. Software
registry properties reported one PhxBringup service with `phx-build=36`, one
NMXAccel service, no PhxAMDFB service, and an **IONDRVFramebuffer**. Thus the
new build-37 snapshot implementation was not loaded. No snapshot reader was
run against the old build.

The two available display controls, `debug.nvaccelfb` and `debug.nvaccel_iop`,
read zero. Queries for `debug.phxfb_hold` and `debug.phxagdc` did not produce
values; they are not recorded as zero. The selected display-arming NVRAM
query found no value, and the named pending/M2/one-shot markers were absent.
The bounded helper-process query found no competing named helper. These
observations do not prove that all GPU activity was absent. No inherited
initializer, startup monitor, claim, register/VRAM operation or GPU test was
executed by this work.

Disk metadata described one internal physical disk and its internal virtual
APFS disk; no external physical disk was present in that observation. No
separately usable recovery route was verified. The older offline EFI backup
is still a backup, not evidence of an independently bootable recovery route.
No EFI was mounted or modified, and Windows partitions were not changed.

## Actual native build and retained delivery

The local build used source commit
`2c26f4deffc4940c1a0a69d9b36c6770191ee0a8`. Its 41-file diagnostic source
export passed the existing fixed review gate and was independently read back
against every source-manifest hash. Kernel and reader source remained
identical to the reviewed build-37 implementation.

MacKernelSDK commit `3f750085caa17ec3a7880f11c11bf4f48cd6a164` was fetched
at that exact pin. All **1,232** regular files, including the native startup
library, matched their Git blob identities in the retained official tree
`ef361592c6340fe53560a8aba98619da641ed437`. Sources and original notices were
retained with the SDK input; no external build script was executed.

The compiler was Apple Clang **21.0.0**, build `clang-2100.1.1.101`, with
host SDK **26.5**. The unchanged component recipe built PhxBringup; the
standalone reader linked IOKit and CoreFoundation with C++17 and
`-Wall -Wextra -Werror`. The original repository build directory was not
cleared: compilation used a private extracted source tree.

| Native output | Bytes after signing | SHA-256 |
| --- | ---: | --- |
| PhxBringup executable, build 37 | 116064 | `6e59fe0d3a1247b70eae7b1953268a1239c5b5524870fbb9cdfc3e80783203a1` |
| Standalone allocation-snapshot reader | 35952 | `1610afb0414caa0f03669fb0e2569de78bf0748388650be9c699699aeb65400a` |

Both outputs passed x86_64 architecture checks and strict ad-hoc signature
verification. Sixteen recorded build/static-verification commands succeeded.
These checks establish native compile/link and retained byte identities, not
kernel loadability, a successful service open, reader execution or hardware
correctness. No unchanged CPU suite was rerun or counted as a new test pass.

The exact candidates, corresponding project source, SDK input, notices,
compiler output and command records were copied into root-owned private
storage. An independent staged read-back verified all copied hashes and both
signatures/architectures; a 57-file manifest covers the staged payload and
verification records. Paths, loaded-image identities and raw machine output
remain private. This is an actual retained **private local delivery**, unlike
the earlier hosted compile with zero artifacts. Neither binary was uploaded
publicly; the standalone-reader publication scope was not expanded.

## Remaining execution gate

Native delivery and fresh execution authority are no longer the original
missing inputs. The next prerequisite is a verified independently usable
recovery route and an exact rollback/install packet for the retained package.
Current live identities must be rechecked immediately before any mutation.
The still-blocked Goal engine is a separate continuity issue: its existing
login helper correctly refuses an inactive goal. No goal database was edited
to bypass that guard, and real reboot/resume remains unverified.

After those prerequisites, follow [Phase A](ALLOCATION-EXECUTION-PLAN.md#phase-a-prove-passive-read-feasibility-on-the-firmware-desktop):
install/load only the pinned PhxBringup candidate through the reviewed normal
firmware-desktop route, then perform one valid baseline and at most one
matching same-boot second read, with no added GPU workload. Record the exact
one-use operation before its first mutation. Refusal, timeout or identity
replacement terminates that attempt; it does not permit a new-directory retry
or escalation to M2. No installation, load, reader request, arming or reboot
was performed in this preflight/build phase.

Root cause remains unconfirmed. The old 37 sampled RADV refusals and three
WindowServer crashes still contain no candidate PhxAlloc history. New
package bytes and present firmware-desktop metadata cannot distinguish the
old pending/invalid paths or establish the origin of raw status 2. The
[validation record](validation/allocation-live-preflight-20261114.json)
separates completed native work from these unperformed target steps.
