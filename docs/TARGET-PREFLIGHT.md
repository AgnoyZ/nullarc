# Target preflight: check-only gate

`tools/target_preflight.py` converts a private `inventory.json` into a bounded,
private checklist for the next manual target step. It never opens IOKit, loads a
kext, writes EFI/NVRAM, changes disks, initializes firmware or submits GPU work.

After importing a Recovery capture on Windows, run:

```text
python tools/target_preflight.py local/target-inventory-from-recovery-01/inventory.json --out local/target-preflight-01
```

The output is `preflight.json` with mode `0600` on POSIX. Existing output is
refused. The report allows only the non-submitting `native-shader-probe --check`
step when it observes x86_64 Darwin 25 on the target laptop, exactly one `1002:1900` registry
candidate, nonempty assigned-address metadata, and no positive execution claims
in the source inventory. Missing, ambiguous, altered or unsafe metadata blocks
even that check.

Both live collection and Recovery import explicitly set `hardware_executed`
to false, alongside the other non-execution flags. Before the 2026-11-12 local
check, the collector omitted this field and its own output failed the preflight's
strict false-only gate. The collector/importer integration tests now pass their
actual reports into the preflight. Missing, true or non-boolean flags still
block the check; the preflight policy has not been relaxed.

Local validation on 2026-11-12 used Python 3.13.18: 20 inventory/preflight and
16 Recovery tests passed. A fresh live capture on macOS 26.7.2 / 25G332,
Darwin 25.6.0 x86_64 with one registry candidate passed the check-only gate;
`native_probe_run_allowed` remained false. This records the observed local OS,
not independent hardware identity, source-to-installed-driver provenance or
GPU execution by this branch.

This is a policy gate, not hardware proof. Assigned PCI ranges are not an
independent configuration-space read and do not prove VRAM, firmware residency,
UMA reservations, queue ownership or display state. The report always sets
`native_probe_run_allowed`, `safe_to_initialize`, `reserved_region_ownership_verified`
and `gpu_work_submitted` to false. A later, separately reviewed manual procedure
must run `native-shader-probe --check` first; `--run` remains prohibited until
target firmware, GPUVM, queue ownership and recovery are independently verified.
