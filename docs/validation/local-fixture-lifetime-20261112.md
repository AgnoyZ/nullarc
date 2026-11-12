# Local async fixture lifetime checks — 2026-11-12

Starting downstream source: `ba5ac9d1fe4bb239db7538aa6c82ae0a378b5145`.
Local runtime reports macOS 26.7.2 / 25G332, Darwin 25.6.0 x86_64;
Apple Clang 21.0.0, macOS SDK 26.5, Python 3.13.18.
Evidence class: host fixture execution only, with no Metal device or GPU work.

The initial async-library ThreadSanitizer run failed the lifetime fixture's
`destructions == before + 1` assertion. The fixture had stopped waiting when
its weak owner became nil; that observation does not synchronize the separate
atomic increment in `dealloc`. This result is retained as a failed run, not a
production scheduling or GPU failure and not a successful TSan pass.

Both library and function lifetime fixtures now wait for the weak owner to
clear **and** the destructor count to advance. The existing eight-second
deadline and final exact-count assertion remain. No production API, queue,
snapshot or retention code is changed. Rollback is a normal revert of this
test-only correction.

After the correction, each of the two fixture runners passed ASan/UBSan and
separate TSan at compile-pool widths one and two. Each resulting executable
then passed five additional fresh-process repeats at each width. This is
48 passing processes and 76,800 mixed stress requests across the corrected
runs. Each process also exercises snapshot, callback, concurrency-bound and
owner-lifetime checks. These are test counts, not a latency or FPS measurement.

The runners record hashes of the actual extracted production bodies, queue
helpers and fixtures. Reports, failed-run details, binaries and raw logs remain
in ignored local build output. Compilation and shader output in the fixtures
are synthetic; no installed-driver provenance, real shader correctness,
WindowServer behavior or target acceleration is established.
