# Build34 PCI startup observation: first trial and recovery

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

A fresh inactive scope is sealed with the corrected collector and the same
exact images. The failed and earlier inactive scopes remain unchanged. That
new scope has no grant, runtime journal or installed task; using it requires
a fresh finite authorization. See the
[sanitized evidence](validation/build34-r3-pci-irq-trial-20261121.json).
Neither PCI mode at startup nor R3 is accepted by this result.
