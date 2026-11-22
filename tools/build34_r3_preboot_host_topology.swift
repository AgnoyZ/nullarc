import Foundation
import IOKit

func refuse(_ reason: String) -> Never {
    print("refused_\(reason)")
    exit(1)
}

func property(_ entry: io_registry_entry_t, _ key: String) -> AnyObject? {
    IORegistryEntryCreateCFProperty(entry, key as CFString, kCFAllocatorDefault, 0)?.takeRetainedValue()
}

func entryID(_ entry: io_registry_entry_t) -> UInt64 {
    var identifier: UInt64 = 0
    guard IORegistryEntryGetRegistryEntryID(entry, &identifier) == KERN_SUCCESS, identifier != 0 else {
        refuse("registry_identity")
    }
    return identifier
}

func parent(_ entry: io_registry_entry_t, _ plane: String) -> io_registry_entry_t {
    var result: io_registry_entry_t = 0
    return IORegistryEntryGetParentEntry(entry, plane, &result) == KERN_SUCCESS ? result : 0
}

func uniqueService(_ service: String, _ predicate: (io_service_t) -> Bool) -> io_service_t {
    var iterator: io_iterator_t = 0
    guard IOServiceGetMatchingServices(kIOMainPortDefault, IOServiceMatching(service), &iterator) == KERN_SUCCESS else {
        refuse("matching_query")
    }
    defer { IOObjectRelease(iterator) }
    var selected: io_service_t = 0
    for _ in 0..<256 {
        let entry = IOIteratorNext(iterator)
        if entry == 0 {
            guard selected != 0, IOIteratorIsValid(iterator) != 0 else { refuse("missing_or_changed_service") }
            return selected
        }
        if predicate(entry) {
            guard selected == 0 else { refuse("multiple_matches") }
            selected = entry
        } else {
            IOObjectRelease(entry)
        }
    }
    refuse("matching_limit")
}

func coordinates(_ entry: io_registry_entry_t) -> (address: [Int], downstream: [Int]) {
    guard let bytes = property(entry, "reg") as? Data, (20...240).contains(bytes.count), bytes.count % 20 == 0,
          bytes.dropFirst(4).prefix(16).allSatisfy({ $0 == 0 }),
          let debug = property(entry, "pcidebug") as? String else {
        refuse("missing_configuration_address")
    }
    let configuration = bytes.prefix(4).enumerated().reduce(UInt32(0)) {
        $0 | (UInt32($1.element) << ($1.offset * 8))
    }
    guard configuration & 0xff0000ff == 0 else { refuse("invalid_configuration_cell") }
    let address = [Int((configuration >> 16) & 255), Int((configuration >> 11) & 31), Int((configuration >> 8) & 7)]
    let syntax = /^([0-9]{1,3}):([0-9]{1,2}):([0-7])(?:\(([0-9]{1,3}):([0-9]{1,3})\))?$/
    guard let match = try? syntax.wholeMatch(in: debug),
          [Int(match.1), Int(match.2), Int(match.3)] == address.map(Optional.some) else {
        refuse("cached_coordinates_disagree")
    }
    let range = [match.4, match.5].compactMap { field in field.flatMap { Int($0) } }
    guard range.allSatisfy({ (0...255).contains($0) }) else { refuse("invalid_bridge_bus_range") }
    return (address, range)
}

func sample() -> [UInt64] {
    let target = uniqueService("IOPCIDevice") { entry in
        (property(entry, "vendor-id") as? Data) == Data([2, 16, 0, 0]) &&
        (property(entry, "device-id") as? Data) == Data([0, 25, 0, 0])
    }
    defer { IOObjectRelease(target) }
    let driver = uniqueService("PhxBringup") { _ in true }
    defer { IOObjectRelease(driver) }
    let provider = parent(driver, "IOService")
    guard provider != 0 else { refuse("missing_provider") }
    defer { IOObjectRelease(provider) }
    guard entryID(provider) == entryID(target) else { refuse("different_provider") }

    let bridge = parent(target, "IODeviceTree")
    guard bridge != 0 else { refuse("missing_bridge") }
    defer { IOObjectRelease(bridge) }
    let root = parent(bridge, "IODeviceTree")
    guard root != 0 else { refuse("missing_root") }
    defer { IOObjectRelease(root) }
    let endpoint = coordinates(target)
    let parentBridge = coordinates(bridge)
    guard endpoint.downstream.isEmpty, parentBridge.downstream.count == 2,
          parentBridge.downstream[0] <= endpoint.address[0], endpoint.address[0] <= parentBridge.downstream[1],
          parentBridge.address[0] < endpoint.address[0] else { refuse("bridge_bus_range_mismatch") }

    var ancestors: [UInt64] = []
    var node = parent(target, "IOService")
    for _ in 0..<8 {
        if node == 0 { break }
        ancestors.append(entryID(node))
        let next = parent(node, "IOService")
        IOObjectRelease(node)
        node = next
    }
    if node != 0 { IOObjectRelease(node) }
    guard let bridgeIndex = ancestors.firstIndex(of: entryID(bridge)),
          let rootIndex = ancestors.firstIndex(of: entryID(root)), bridgeIndex < rootIndex else {
        refuse("tree_topology_disagreement")
    }
    let uid = (property(root, "_UID") as? String).flatMap { value in
        UInt32(value) ?? (value.hasPrefix("0x") ? UInt32(value.dropFirst(2), radix: 16) : nil)
    }
    guard let uid else { refuse("root_uid_unavailable") }

    return [entryID(driver), entryID(target), entryID(bridge), entryID(root), UInt64(uid)] + ancestors +
        (endpoint.address + parentBridge.address + parentBridge.downstream).map(UInt64.init)
}

let first = sample()
let second = sample()
guard first == second else { refuse("unstable_topology") }
print("matching_samples=2; unique_target_and_phx_provider=true; pci_hops=2")
print("cached_coordinates_agree=true; endpoint_within_bridge_bus_range=true; ordered_bridge_and_root_match=true")
print("root_uid_available=true; firmware_path_or_segment_attested=false")
