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

struct TopologySample: Equatable {
    let identity: [UInt64]
    let bridgeBus: Int
    let downstream: ClosedRange<Int>
}

func sample() -> TopologySample {
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

    let identity = [entryID(driver), entryID(target), entryID(bridge), entryID(root), UInt64(uid)] + ancestors +
        (endpoint.address + parentBridge.address).map(UInt64.init)
    return TopologySample(identity: identity, bridgeBus: parentBridge.address[0],
                          downstream: parentBridge.downstream[0]...parentBridge.downstream[1])
}

struct MCFGWindow {
    let segment: UInt16
    let buses: ClosedRange<Int>
}

func mcfgWindows(_ table: Data) -> [MCFGWindow]? {
    let headerSize = 44
    let entrySize = 16
    guard (headerSize + entrySize...headerSize + 256 * entrySize).contains(table.count),
          (table.count - headerSize) % entrySize == 0 else { return nil }
    let bytes = [UInt8](table)
    let declaredSize = (4..<8).reduce(0) { $0 | (Int(bytes[$1]) << (($1 - 4) * 8)) }
    guard bytes.prefix(4).elementsEqual("MCFG".utf8), declaredSize == bytes.count, bytes[8] == 1,
          bytes.reduce(UInt8(0), &+) == 0, bytes[36..<44].allSatisfy({ $0 == 0 }) else { return nil }

    var windows: [MCFGWindow] = []
    for offset in stride(from: headerSize, to: bytes.count, by: entrySize) {
        let segment = UInt16(bytes[offset + 8]) | (UInt16(bytes[offset + 9]) << 8)
        let start = Int(bytes[offset + 10])
        let end = Int(bytes[offset + 11])
        guard start <= end, bytes[(offset + 12)..<(offset + 16)].allSatisfy({ $0 == 0 }) else { return nil }
        let buses = start...end
        guard !windows.contains(where: { $0.segment == segment && $0.buses.overlaps(buses) }) else { return nil }
        windows.append(MCFGWindow(segment: segment, buses: buses))
    }
    return windows
}

func uniqueMCFGCover(_ windows: [MCFGWindow], bridgeBus: Int, downstream: ClosedRange<Int>) -> Bool {
    let candidates = windows.filter { $0.buses.contains(bridgeBus) || $0.buses.overlaps(downstream) }
    guard candidates.count == 1, let candidate = candidates.first else { return false }
    return candidate.buses.contains(bridgeBus) && candidate.buses.contains(downstream.lowerBound) &&
        candidate.buses.contains(downstream.upperBound)
}

func cachedMCFG() -> Data {
    let platform = uniqueService("IOACPIPlatformExpert") { _ in true }
    defer { IOObjectRelease(platform) }
    guard let tables = property(platform, "ACPI Tables") as? NSDictionary,
          let table = tables["MCFG"] as? Data else { refuse("missing_cached_mcfg") }
    return table
}

func testMCFG() {
    func makeTable(_ rows: [(UInt16, UInt8, UInt8)], change: (inout [UInt8]) -> Void = { _ in }) -> Data {
        let size = 44 + rows.count * 16
        var bytes = [UInt8](repeating: 0, count: size)
        bytes.replaceSubrange(0..<4, with: "MCFG".utf8)
        bytes[4] = UInt8(truncatingIfNeeded: size)
        bytes[5] = UInt8(truncatingIfNeeded: size >> 8)
        bytes[8] = 1
        for (index, (segment, start, end)) in rows.enumerated() {
            let offset = 44 + index * 16
            bytes[offset + 8] = UInt8(truncatingIfNeeded: segment)
            bytes[offset + 9] = UInt8(segment >> 8)
            bytes[offset + 10] = start
            bytes[offset + 11] = end
        }
        change(&bytes)
        bytes[9] = 0 &- bytes.reduce(UInt8(0), &+)
        return Data(bytes)
    }

    let good = makeTable([(7, 32, 95), (3, 0, 31)])
    let ambiguous = makeTable([(7, 32, 95), (0x0107, 60, 60)])
    let split = makeTable([(7, 32, 63), (7, 64, 95)])
    var badChecksum = good
    badChecksum[9] ^= 1
    let cases = [
        mcfgWindows(good).map { uniqueMCFGCover($0, bridgeBus: 32, downstream: 33...95) } == true,
        mcfgWindows(ambiguous).map { uniqueMCFGCover($0, bridgeBus: 32, downstream: 33...95) } == false,
        mcfgWindows(split).map { uniqueMCFGCover($0, bridgeBus: 32, downstream: 33...95) } == false,
        mcfgWindows(good).map { uniqueMCFGCover($0, bridgeBus: 96, downstream: 97...100) } == false,
        mcfgWindows(makeTable([])) == nil,
        mcfgWindows(makeTable(Array(repeating: (7, 32, 63), count: 257))) == nil,
        mcfgWindows(Data(good.dropLast())) == nil,
        mcfgWindows(makeTable([(7, 32, 31)])) == nil,
        mcfgWindows(makeTable([(7, 32, 63), (7, 63, 95)])) == nil,
        mcfgWindows(makeTable([(7, 32, 63)]) { $0[0] ^= 1 }) == nil,
        mcfgWindows(makeTable([(7, 32, 63)]) { $0[4] ^= 1 }) == nil,
        mcfgWindows(makeTable([(7, 32, 63)]) { $0[8] ^= 1 }) == nil,
        mcfgWindows(makeTable([(7, 32, 63)]) { $0[36] = 1 }) == nil,
        mcfgWindows(makeTable([(7, 32, 63)]) { $0[56] = 1 }) == nil,
        mcfgWindows(badChecksum) == nil
    ]
    guard cases.allSatisfy({ $0 }) else { refuse("mcfg_fixture_failed") }
    print("mcfg_fixture_cases_passed=\(cases.count)")
}

let arguments = Array(CommandLine.arguments.dropFirst())
if arguments == ["--test-mcfg"] {
    testMCFG()
    exit(0)
}
let checkMCFG = arguments == ["--check-acpi-mcfg"]
guard checkMCFG || arguments.isEmpty else { refuse("arguments") }
let first = sample()
let firstMCFG = checkMCFG ? cachedMCFG() : nil
let second = sample()
let secondMCFG = checkMCFG ? cachedMCFG() : nil
guard first == second else { refuse("unstable_topology") }
if let table = firstMCFG {
    guard firstMCFG == secondMCFG else { refuse("unstable_cached_mcfg") }
    guard let windows = mcfgWindows(table) else { refuse("invalid_cached_mcfg") }
    guard uniqueMCFGCover(windows, bridgeBus: first.bridgeBus, downstream: first.downstream) else {
        refuse("ambiguous_or_uncovered_mcfg_bus_window")
    }
    print("cached_mcfg_matching_samples=2; allocation_entries=\(windows.count); unique_covering_window=true")
}
print("matching_samples=2; unique_target_and_phx_provider=true; pci_hops=2")
print("cached_coordinates_agree=true; endpoint_within_bridge_bus_range=true; ordered_bridge_and_root_match=true")
print("root_uid_available=true; firmware_path_or_segment_attested=false")
