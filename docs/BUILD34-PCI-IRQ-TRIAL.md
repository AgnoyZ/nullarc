# Build34 PCI startup observation trials

## First trial and recovery

On November 21, 2026, the owner authorized one ordinary restart with the
exact [PCI observation image](BUILD34-PCI-IRQ-CANDIDATE.md) and at most one
startup-failure recovery restart. Preboot readback found the candidate on
disk, the mapping-only control still loaded, the full 358-file EFI delta
limited to the PhxBringup executable, and the trial jobs staged unloaded.

The ordinary restart completed. Both startup workers refused the PCI sample
with `Start-time classification changed around service observation`. They
failed before completing desktop admission or writing a PCI observation
receipt. No independent candidate-image identity or classification was
accepted on that boot. The recovery journal made one rollback decision and
dispatched its single allowed recovery restart. Both restart grants are spent.

Independent readback on the recovery boot verified the original mapping-only
image (SHA256 `923182fab482d5c584f484520622283922f67a9caaa2d310e638cd71d1fb1dc7`)
loaded from the boot collection, with no PhxBringup loaded from the system or
auxiliary collections. The full EFI manifest, both previous startup jobs,
three current startup receipts, cache, optimized ACPI and plugin matched.
The same WindowServer showed VBL and copy progression over a three-second
sample, with all four checked errors zero and no new matching diagnostic
report. The trial watcher retired. There was no extra GPU workload.

## Readback correction

On the recovered system, the old `ioreg -a -r -d 2 -c IOPCIDevice` query gave
the child the same registry identity as the direct query but omitted its
properties at the depth boundary. Adding `-l` exposed the matching build
marker and all three known BAR0 mapping properties. This explains the
collector's false assumption that both views included child properties. It
does not recover the failed boot's classification. A regression test models
the omitted fields and reproduces the same refusal without `-l`.

The collector now adds `-l` only to the provider queries. The two provider
snapshots and intervening direct sample still have to agree on identities
and allowed classification. The restored mapping observer correctly reports
the PCI classification as unavailable because it does not publish it. The
kernel images, existing boot controller and protected production inputs are
unchanged. Repreparing after recovery requires both historical control
acceptance and three current-boot receipts plus live identity/disk checks.

The corrected collector and the same exact images were sealed in a distinct
inactive scope. The failed and earlier inactive scopes remain unchanged.
See the [sanitized first-trial evidence](validation/build34-r3-pci-irq-trial-20261121.json).

## Corrected trial passed startup observation

On November 21, 2026, a new authorized scope used the same observer executable
(SHA256 `d2d6abe1e35a99c6a0f197d4a9a4726e0f8caedaf7942712aba851ab24bfef70`)
and the corrected collector on macOS 26.7.2 (`25G332`). Independent preboot
readback again verified the full 358-file EFI manifest and the staged jobs
while the old mapping-only image was still loaded. One ordinary restart
completed. No recovery restart was fired; the startup watcher retired and
the scope's ordinary restart grant is consumed.

Independent postboot readback matched the candidate to the boot collection
only, validated three current-boot startup receipts and verified desktop
takeover, disk integrity, cache, ACPI and plugin. WindowServer was unchanged
over a three-second sample with progress in VBL and copy, four zero error
counters and no new matching diagnostic report. The corrected collector
matched the direct Radeon `1002:1900` provider and agreed with the same-boot
receipt: `both-message-enables-clear`. No interrupt descriptor or interrupt
accounting entry was visible in the passive registry view. No device was
opened by the collector and no extra GPU workload ran.

This closes only the startup-observation gate. A clear MSI/MSI-X enable
classification does not show that legacy INTx works, that no ISR or IH
consumer exists, or that old writes have drained. The exact image remains
installed. The [next gate](BUILD34-R3-IRQ-ROUTE-TRIAL.md) requires separate
ownership and drain evidence before interrupt registration or IH programming.
R3 is not accepted. See the
[sanitized postboot evidence](validation/build34-r3-pci-irq-retrial-20261121.json).
