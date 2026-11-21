# Build34 PCI startup observer private artifact pair

November 21, 2026, macOS 26.7.2 (`25G332`): the private build reproduced
the previously accepted mapping-only PhxBringup build34 bundle byte-for-byte.
Only then did it build the [PCI startup observer](BUILD34-PCI-IRQ-CONFIG.md)
from the verified source-only delta on `upstream34/vram-layout-fix`. The
independent artifact readback passed. No driver or job was installed, no new
image was loaded, and no GPU work or restart was requested.

| Private executable | SHA256 |
| --- | --- |
| Reproduced mapping-only restore | `923182fab482d5c584f484520622283922f67a9caaa2d310e638cd71d1fb1dc7` |
| Mapping plus PCI startup observation | `d2d6abe1e35a99c6a0f197d4a9a4726e0f8caedaf7942712aba851ab24bfef70` |

The [builder](../tools/build34_pci_irq_candidate.py) checks the reviewed
default source checkpoint, accepted R1b source/ABI/build/license inputs, and
the [offline observation evidence](validation/build34-r3-pci-irq-config-offline-20261121.json).
It uses the pinned SDK and unchanged kernel recipe inside ignored private
directories. The strict ad-hoc signature checks and x86_64 image checks pass
on both bundles. Only `Contents/MacOS/PhxBringup` differs; the other two
bundle files are byte-identical. Three existing compiler warnings and all
375 imports are retained. No changes to the 172 production inputs or to
the full R3 exact path were made.

```sh
nice -n 15 taskpolicy -b python3 -B tools/build34_pci_irq_candidate.py \
  --sdk "$KERNEL_SDK" --out build/build34-r3-pci-irq-candidate-new-private
nice -n 15 taskpolicy -b python3 -B tools/build34_pci_irq_candidate.py \
  --verify --out build/build34-r3-pci-irq-candidate-new-private
```

A separate read-only collection query matched the restore artifact to the
currently loaded **boot collection** image. PhxBringup was absent from the
system and auxiliary collections, and the new observer was not loaded.
The identity comparison remained in memory. This demonstrates the current
control's route; the inherited private `_thread_call_cancel_wait` import is
unchanged and generic public-KPI/AuxKC admission is still refused. No binary,
SDK, EFI data, raw collection data or UUID is published. See the
[sanitized result](validation/build34-r3-pci-irq-candidate-20261121.json).

The subsequent [inactive scope](BUILD34-PCI-IRQ-SCOPE.md) has passed independent
preflight and restore readback. It retains the current mapping-only image and
current recovery jobs. A distinct boot scope still requires a fresh grant.
Passing either private stage supplies neither real MSI/MSI-X readings nor R3
hardware acceptance.
