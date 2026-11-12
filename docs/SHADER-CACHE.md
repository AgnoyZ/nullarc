# Downstream shader-cache experiment

Scope: host cache correctness, not shader execution or a measured speedup.
Original downstream helpers; no NullMoth reference code is copied. The existing
`src/nmplugin` PolyForm Noncommercial licence remains applicable.

## In-memory address-lowering cache

A mutex still serializes cache operations. Keys retain all input bytes and flags;
values retain both the result (including failure) and all four info words. The
cache now evicts least-recently-used entries individually instead of discarding
every entry at 4096. Limits are 4096 entries and 64 MiB of key/result/info payload.
Objective-C object/dictionary overhead and concurrent in-flight translation are
not included in that payload budget. Oversize entries bypass insertion without
flushing existing entries. This address-lowering cache does not coalesce in-flight
work. The separate base-library translation experiment now shares overlapping
misses; see `TRANSLATION-SHARING.md` for its limits and validation scope.

## Disposable files

Base SPIR-V, library-index and library-key memo files now use a 32-byte versioned
header with a format kind, exact payload length and FNV-1a checksum. This detects
accidental corruption; it provides no authentication, signature or provenance.
Readers reject symlinks/non-regular files, truncated/extended/corrupt records and
payloads above 256 MiB (the memo reader additionally limits to its fixed record
size). Existing SPIR-V magic, plist/library structure and memo stat/content-edge
checks remain. An invalid file is a cache miss and is not unlinked by the reader,
avoiding deletion of a concurrent replacement.

Writers use a unique same-directory `mkstemp` file (0600), handle short/EINTR
writes, check file sync/close, then rename atomically. Failed writes leave the
previous destination intact and remove their own temporary file. This avoids
the former same-PID collision between threads. Directory sync is intentionally
absent: these are disposable caches, not power-loss-durable application data.
Directory ownership/parent symlinks and hostile replacement are not a security
boundary. The writable-directory probe also uses a unique temporary name; the
existing SPIR-V writable fallback and disk trimming/tag sweep remain intact.

Older unwrapped files become misses and are replaced lazily. AIR text and the
other specialized function/link/reflection caches retain their existing formats;
this is not a claim of hardening every disk cache in the plugin. Existing cache
disable environment switches remain available.

## Checks and rollback

`python3 tools/test_shader_cache.py --out build/cache-fresh` compiles the actual
I/O header under ASan/UBSan on Linux/macOS. It checks corruption in every header
field and payload, all truncation boundaries, size/type refusal, symlinks/FIFOs,
EINTR/short/zero/error I/O, sync/rename failures and preservation of the previous
record. Four processes and then four threads perform 480 concurrent writes with
complete-record reads and no temporary-file leaks. On macOS it also runs the
actual Foundation LRU and extracted actual shader-cache wrapper: 20000 oracle
operations, mutable-key copying, payload/count overflow boundaries, entry
lifetime, recency, negative-result/info/flags behavior and the 4096-entry limit.
The runner hashes current inputs. Windows extraction tests are not native passes.

Native results must be recorded only after CI finishes. Revert this isolated
commit to roll back source behavior; cache files are disposable and a format
miss rebuilds them. No driver installation, EFI or OS-security changes occur.
