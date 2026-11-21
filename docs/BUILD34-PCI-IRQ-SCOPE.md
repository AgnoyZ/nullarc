# Build34 PCI startup observation scope

The [first authorized trial](BUILD34-PCI-IRQ-TRIAL.md) refused the PCI sample
and restored the mapping-only control in one recovery restart. The distinct
[corrected trial](BUILD34-PCI-IRQ-TRIAL.md#corrected-trial-passed-startup-observation)
passed without a recovery restart. The original offline evidence below
remains historical; neither trial grants another ordinary restart.

On November 21, 2026, the [exact private observer pair](BUILD34-PCI-IRQ-CANDIDATE.md)
was bound to an inactive boot and restore scope on macOS 26.7.2 (`25G332`).
The current mapping-only PhxBringup build34 remains installed and loaded.
The new scope has a false trial grant, no restart intent or recovery journal,
no installed startup job, and no ordinary restart dispatcher. Its actual
runtime constructor refused the inactive scope.

| Role | PhxBringup executable SHA256 |
| --- | --- |
| Current control and restore | `923182fab482d5c584f484520622283922f67a9caaa2d310e638cd71d1fb1dc7` |
| PCI startup observer | `d2d6abe1e35a99c6a0f197d4a9a4726e0f8caedaf7942712aba851ab24bfef70` |

The [preparer](../tools/build34_pci_irq_scope.py) independently compared the
accepted live identity and the full current 358-file EFI manifest. The only
prospective change is `PhxBringup.kext/Contents/MacOS/PhxBringup`. Independent
readback verified the 71 sealed files, both current startup job backups,
strict disk signature, cache, optimized ACPI and plugin. All 172 protected
production inputs stayed unchanged. The old installer and dispatcher are
excluded. No EFI data, binaries, raw logs, firmware or UUIDs are published.

## Startup and restore

The [adapter](../tools/build34_pci_irq_observer_host.py) requires a separate
explicit grant, a scope- and image-bound ordinary restart intent, and a boot
different from preparation. The journal binds the first eligible boot. The
existing 45/150/300-second gates, PR28 daily 250 ms, WindowServer exclusion and
R1b/R2a desktop settings are preserved. There is no resident monitor or new GPU
pressure probe. The strict desktop check retains all prior properties and
admits one additional start-time PCI classification from the direct 780M
provider. The observation receipt follows existing boot and desktop admission;
absent or inconsistent classification fails admission. No PCI registration,
interrupt enable, IH program or fence read is performed by the observer.

On startup failure, the controller can restore only the current mapping-only
executable and current mapping startup job pair, plus retire its own watcher
and pending/hold state. The separate restore view checks disk, signature,
cache, ACPI, plugin and security without requiring the failed observer to
provide live metadata. The journal allows at most one first-trial recovery
restart after that readback; daily recovery has zero restart allowance. A
successful boot is retained. These controls do not cover every hang before
launchd starts. No write-back, GPU probe or power action was tested on hardware
in this preparation.

Eight adapter tests exercise preparation boot rejection, grant and intent
binding, manifest drift, exact rollback targets, and admission and receipt
ordering. See the [sanitized preparation evidence](validation/build34-r3-pci-irq-scope-offline-20261121.json).

## Remaining gate

Do not activate this packet or reuse the prior mapping trial grant. A distinct
scope requires fresh authorization for these exact image hashes: one ordinary
restart with the bounded existing accelerated startup and passive config read,
plus at most one startup-failure recovery restart. Before installing, verify
the exact current disk and loaded control again, and bind a fresh one-use
request and an independent postboot readback. Stop on drift.

Even a passing startup classification cannot identify the active interrupt
mode, ISR, IH ownership, EOP delivery or fence visibility. Continue through
the [route trial gates](BUILD34-R3-IRQ-ROUTE-TRIAL.md) before registering any
interrupt or issuing a GPU test. R3 remains unaccepted.
