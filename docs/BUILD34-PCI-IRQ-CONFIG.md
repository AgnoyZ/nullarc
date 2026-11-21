# Build34 start-time PCI interrupt configuration observer

The [source-only transform](../tools/build34_pci_irq_config.py) adds a one-shot
observation to the same mapping-only source used as the previous boot test's
control. It does not layer R3 exact submission, waits or the event adapter
into that source. The added code runs at the existing configuration-read
site in `PhxBringup::start`, after retaining the matched PCI provider and
before PhxBringup registers with power management or writes the command
register. No new device operation is performed by the passive collector.
The [public IOPCIFamily implementation](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOPCIDevice.cpp#L1124-L1168)
checks access then delegates reads to the parent bridge; this reference does
not identify the actual running IOPCIFamily image or guarantee bridge latency.

The observer requires Radeon `1002:1900`, a type-0 header, conventional PCI
capability-list support and a valid power-management capability. It walks at
most 48 aligned capability positions within the first 256 bytes, and refuses
cycles, duplicate target capabilities, overlapping known capability spans
and invalid reads. It brackets the MSI and MSI-X control reads with matching
D0 power status and PCI identities, then requires two matching relevant
snapshots. It refuses both enable bits set simultaneously. MSI-X table
contents, per-vector masking, address/data fields and BARs are not read.
The capability definitions follow the public
[PCI register definitions in Linux v6.12](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/include/uapi/linux/pci_regs.h).
No Linux code is included.

One versioned registry property carries only a fixed classification. The
collector requires the same classification on the exact PhxBringup child
in both PCI snapshots and the intervening service snapshot. The provider
queries use `ioreg -l` so the depth-limited child includes its properties;
see the [first trial and recovery](BUILD34-PCI-IRQ-TRIAL.md). Failed reads
or publication leave the classification unavailable. Both enable bits clear
does not prove legacy INTx delivery, and a clear MSI-X function mask does not
prove that an individual vector is unmasked. This records what the provider
returned at startup; two samples are not an atomic snapshot and cannot detect
a complete change away and back between reads. The collector neither attests
the loaded image nor proves the configuration still applies after startup,
sleep or rebind. No ISR registration, IH ownership, EOP delivery or CPU fence
visibility can be concluded from this property.

The [offline runner](../tools/test_build34_pci_irq_config.py) extracts the
actual observer and publication block from the transformed source for the CPU
fixture. ASan/UBSan passed 1,483 checks; five deliberately broken variants
hit assertions. The matching pinned SDK and KDK were checked on macOS 26.7.2
(`25G332`). Complete control and proposed sources compiled to nonloadable
x86_64 objects with the same 375 imports and three existing warnings. The
inherited private `thread_call_cancel_wait` admission gap is unchanged.
All 172 production inputs are unchanged; see the
[sanitized result](validation/build34-r3-pci-irq-config-offline-20261121.json).

```sh
nice -n 15 taskpolicy -b python3 -B tools/test_build34_pci_irq_config.py \
  --out build/build34-r3-pci-irq-config-new-private --sdk "$KERNEL_SDK" --kdk "$KDK"
```

The initial source-only verification did not link a kernel. The subsequent
[private artifact build](BUILD34-PCI-IRQ-CANDIDATE.md) now reproduces the
previously accepted mapping-only image and strictly verifies the new
observation-only pair. The corrected collector is sealed in a distinct
inactive scope for those exact images; the previous trial's spent boot grant
is not reused. A good startup sample would only close the first observation
step in the [IRQ route trial](BUILD34-R3-IRQ-ROUTE-TRIAL.md).
