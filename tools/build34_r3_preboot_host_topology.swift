import Foundation
import IOKit
import CryptoKit

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
    let acpi: ACPITarget?
    let pciPath: PCIPathCoordinates
}

struct PCIPathCoordinates: Equatable {
    let rootUID: UInt32
    let hops: [UInt32]
}

struct ACPITarget: Equatable {
    let names: [String]
    let rootUID: UInt32
    let bridgeADR: UInt32
    let endpointADR: UInt32
}

func acpiPath(_ entry: io_registry_entry_t) -> [String]? {
    let prefix = "IOACPIPlane:/"
    guard let value = property(entry, "acpi-path") as? String, value.hasPrefix(prefix) else { return nil }
    let components = value.dropFirst(prefix.count).split(separator: "/", omittingEmptySubsequences: false)
    let names = components.map { String($0.prefix { $0 != "@" }) }
    let syntax = /^[A-Z_][A-Z_0-9]{0,3}$/
    return names.allSatisfy { (try? syntax.wholeMatch(in: $0)) != nil } ? names : nil
}

func sample(checkACPI: Bool = false) -> TopologySample {
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
    let pciPath = PCIPathCoordinates(rootUID: uid, hops: [parentBridge.address, endpoint.address].map {
        UInt32($0[1] << 16 | $0[2])
    })
    let acpi: ACPITarget?
    if checkACPI {
        guard let rootPath = acpiPath(root), let bridgePath = acpiPath(bridge), let targetPath = acpiPath(target),
              rootPath.count == 2, bridgePath.count == 3, targetPath.count == 4,
              bridgePath.starts(with: rootPath), targetPath.starts(with: bridgePath) else { refuse("acpi_path") }
        acpi = ACPITarget(names: targetPath, rootUID: uid,
                          bridgeADR: pciPath.hops[0], endpointADR: pciPath.hops[1])
    } else {
        acpi = nil
    }
    return TopologySample(identity: identity, bridgeBus: parentBridge.address[0],
                          downstream: parentBridge.downstream[0]...parentBridge.downstream[1], acpi: acpi, pciPath: pciPath)
}

struct EFIPropertyNode {
    let coordinates: PCIPathCoordinates
    let path: Range<Int>
}

func efiPropertyNodes(_ data: Data) -> [EFIPropertyNode]? {
    guard (12...1_048_576).contains(data.count) else { return nil }
    let bytes = [UInt8](data)
    func word(_ offset: Int) -> UInt32 {
        (0..<4).reduce(0) { $0 | (UInt32(bytes[offset + $1]) << ($1 * 8)) }
    }
    let nodeCount = Int(word(8))
    guard Int(word(0)) == bytes.count, word(4) == 1, (1...256).contains(nodeCount) else { return nil }
    var nodes: [EFIPropertyNode] = []
    var offset = 12
    for _ in 0..<nodeCount {
        guard bytes.count - offset >= 8 else { return nil }
        let nodeSize = Int(word(offset))
        let propertyCount = Int(word(offset + 4))
        guard nodeSize >= 30, nodeSize <= bytes.count - offset, (1...256).contains(propertyCount) else { return nil }
        let end = offset + nodeSize
        let pathStart = offset + 8
        guard word(pathStart) == 0x000c0102, [0x0a0341d0, 0x0a0841d0].contains(word(pathStart + 4)) else {
            return nil
        }
        let uid = word(pathStart + 8)
        var cursor = pathStart + 12
        var hops: [UInt32] = []
        while end - cursor >= 6 && word(cursor) == 0x00060101 {
            let function = bytes[cursor + 4]
            let device = bytes[cursor + 5]
            guard function <= 7, device <= 31, cursor + 10 - pathStart <= 256 else { return nil }
            hops.append(UInt32(device) << 16 | UInt32(function))
            cursor += 6
        }
        guard !hops.isEmpty, end - cursor >= 4, word(cursor) == 0x0004ff7f else { return nil }
        cursor += 4
        let path = pathStart..<cursor
        for _ in 0..<propertyCount {
            guard end - cursor >= 4 else { return nil }
            let nameSize = Int(word(cursor))
            guard nameSize >= 8, nameSize <= end - cursor, nameSize % 2 == 0 else { return nil }
            cursor += nameSize
            guard bytes[cursor - 2] == 0, bytes[cursor - 1] == 0, end - cursor >= 4 else { return nil }
            let valueSize = Int(word(cursor))
            guard (4...(end - cursor)).contains(valueSize) else { return nil }
            cursor += valueSize
        }
        guard cursor == end else { return nil }
        nodes.append(EFIPropertyNode(coordinates: PCIPathCoordinates(rootUID: uid, hops: hops), path: path))
        offset = end
    }
    return offset == bytes.count ? nodes : nil
}

func uniqueEFIPropertyPath(_ nodes: [EFIPropertyNode], for target: PCIPathCoordinates) -> Range<Int>? {
    let matches = nodes.filter { $0.coordinates == target }
    return matches.count == 1 ? matches.first?.path : nil
}

func cachedEFIProperties() -> Data {
    let entry = IORegistryEntryFromPath(kIOMainPortDefault, "IODeviceTree:/efi")
    guard entry != 0 else { refuse("missing_cached_efi_entry") }
    defer { IOObjectRelease(entry) }
    guard let data = property(entry, "device-properties") as? Data else { refuse("missing_cached_efi_properties") }
    return data
}

func testEFIPropertyPaths() {
    let path: [UInt8] = [2, 1, 12, 0, 0xd0, 0x41, 8, 10, 2, 0, 0, 0,
                         1, 1, 6, 0, 1, 4, 1, 1, 6, 0, 0, 5, 0x7f, 0xff, 4, 0]
    let node: [UInt8] = [52, 0, 0, 0, 1, 0, 0, 0] + path + [8, 0, 0, 0, 0x41, 0, 0, 0, 8, 0, 0, 0, 1, 2, 3, 4]
    let fixture = Data([64, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0] + node)
    let target = PCIPathCoordinates(rootUID: 2, hops: [0x40001, 0x50000])
    func mutated(_ index: Int, _ value: UInt8) -> Data {
        var altered = fixture
        altered[index] = value
        return altered
    }
    func selection(_ data: Data, target: PCIPathCoordinates) -> Range<Int>? {
        efiPropertyNodes(data).flatMap { uniqueEFIPropertyPath($0, for: target) }
    }
    let twice = Data([116, 0, 0, 0, 1, 0, 0, 0, 2, 0, 0, 0] + node + node)
    var alternateRoot = twice
    alternateRoot[78] = 3
    var shortNode = Data(fixture.prefix(24))
    shortNode[0] = 24
    var shortProperty = Data(fixture.prefix(52))
    shortProperty[0] = 52
    shortProperty[12] = 40
    let cases = [
        selection(fixture, target: target) == 20..<48,
        selection(mutated(26, 3), target: target) == 20..<48,
        selection(fixture, target: PCIPathCoordinates(rootUID: 3, hops: target.hops)) == nil,
        selection(fixture, target: PCIPathCoordinates(rootUID: 2, hops: [0x40001])) == nil,
        selection(fixture, target: PCIPathCoordinates(rootUID: 2, hops: [0x40000, 0x50001])) == nil,
        efiPropertyNodes(twice)?.count == 2 && selection(twice, target: target) == nil,
        efiPropertyNodes(alternateRoot)?.count == 2 && selection(alternateRoot, target: target) == nil,
        efiPropertyNodes(mutated(4, 2)) == nil,
        efiPropertyNodes(mutated(12, 255)) == nil,
        efiPropertyNodes(mutated(36, 8)) == nil,
        efiPropertyNodes(mutated(45, 1)) == nil,
        efiPropertyNodes(mutated(54, 9)) == nil,
        efiPropertyNodes(mutated(56, 9)) == nil,
        efiPropertyNodes(shortNode) == nil,
        efiPropertyNodes(shortProperty) == nil,
        efiPropertyNodes(Data(fixture.dropLast())) == nil
    ]
    guard cases.allSatisfy({ $0 }) else { refuse("efi_property_fixture_failed") }
    print("efi_property_path_fixture_cases_passed=\(cases.count)")
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

func cachedTables() -> [String: Any] {
    let platform = uniqueService("IOACPIPlatformExpert") { _ in true }
    defer { IOObjectRelease(platform) }
    guard let tables = property(platform, "ACPI Tables") as? [String: Any] else { refuse("missing_cached_acpi") }
    return tables
}

struct ACPITables: Equatable {
    let dsdt: Data
    let mcfg: Data
    let aml: [Data]
}

func staticTables() -> ACPITables {
    let tables = cachedTables()
    guard let dsdt = tables["DSDT"] as? Data, let mcfg = tables["MCFG"] as? Data else {
        refuse("missing_cached_dsdt_or_mcfg")
    }
    let aml = tables.keys.sorted().flatMap { key -> [Data] in
        if let data = tables[key] as? Data { return [data] }
        return tables[key] as? [Data] ?? []
    }.filter { table in
        ["DSDT", "SSDT", "PSDT"].contains(String(decoding: table.prefix(4), as: UTF8.self))
    }
    guard (1...256).contains(aml.count), aml.filter({ $0.starts(with: "DSDT".utf8) }) == [dsdt],
          aml.allSatisfy({ table in
              guard (36...2_097_152).contains(table.count) else { return false }
              let declared = table.dropFirst(4).prefix(4).enumerated().reduce(0) {
                  $0 | (Int($1.element) << ($1.offset * 8))
              }
              return declared == table.count && table.reduce(UInt8(0), &+) == 0
          }) else { refuse("invalid_cached_aml") }
    return ACPITables(dsdt: dsdt, mcfg: mcfg, aml: aml)
}

func staticRootRefusal(_ asl: String, _ target: ACPITarget, bus: Int) -> String? {
    guard target.names.count == 4, target.names[0] == "_SB" || target.names[0] == "_SB_" else {
        return "acpi_system_bus_scope"
    }
    let lines = asl.components(separatedBy: .newlines).map { line in
        let line = line.replacingOccurrences(of: #"/\*.*?\*/"#, with: "", options: .regularExpression)
        return line.range(of: "//").map { String(line[..<$0.lowerBound]) } ?? line
    }
    func bodies(_ words: Set<String>, in range: Range<Int>, depth: Int) -> [Range<Int>] {
        let indent = String(repeating: " ", count: depth * 4)
        let matches = range.filter { words.contains(lines[$0].trimmingCharacters(in: .whitespaces)) &&
            lines[$0].prefix(while: { $0 == " " }).count == indent.count }
        return matches.compactMap { index in
            guard index + 1 < range.upperBound, lines[index + 1].trimmingCharacters(in: .whitespaces) == "{",
                  let end = ((index + 2)..<range.upperBound).first(where: {
                      lines[$0].prefix(while: { $0 == " " }).count == indent.count &&
                      lines[$0].trimmingCharacters(in: .whitespaces) == "}"
                  }) else { return nil }
            return (index + 2)..<end
        }
    }
    func value(_ field: String, in range: Range<Int>, depth: Int) -> String? {
        let prefix = String(repeating: " ", count: depth * 4) + "Name (\(field), "
        let matches = range.map { lines[$0] }.filter { $0.hasPrefix(prefix) }
        guard matches.count == 1, let line = matches.first else { return nil }
        let plain = line.trimmingCharacters(in: .whitespaces)
        let start = "Name (\(field), "
        guard plain.hasSuffix(")") else { return nil }
        return plain.dropFirst(start.count).dropLast().trimmingCharacters(in: .whitespaces)
    }
    func number(_ field: String, in range: Range<Int>, depth: Int) -> UInt32? {
        guard let literal = value(field, in: range, depth: depth) else { return nil }
        if literal == "Zero" { return 0 }
        if literal == "One" { return 1 }
        return literal.hasPrefix("0x") ? UInt32(literal.dropFirst(2), radix: 16) : UInt32(literal)
    }

    let systemBuses = bodies(["Scope (_SB)", "Scope (_SB_)", "Scope (\\_SB)", "Scope (\\_SB_)"],
                             in: lines.indices, depth: 1)
    let roots = systemBuses.flatMap { bodies(["Device (\(target.names[1]))"], in: $0, depth: 2) }
    guard roots.count == 1, let root = roots.first else { return "acpi_root_scope" }
    let bridges = bodies(["Device (\(target.names[2]))"], in: root, depth: 3)
    guard bridges.count == 1, let bridge = bridges.first else { return "acpi_bridge_scope" }
    let endpoints = bodies(["Device (\(target.names[3]))"], in: bridge, depth: 4)
    guard endpoints.count == 1, let endpoint = endpoints.first else { return "acpi_endpoint_scope" }
    guard let hid = value("_HID", in: root, depth: 3),
          ["EisaId (\"PNP0A08\")", "EisaId (\"PNP0A03\")", "\"PNP0A08\"", "\"PNP0A03\""].contains(hid) else {
        return "acpi_root_hid"
    }
    guard number("_UID", in: root, depth: 3) == target.rootUID else { return "acpi_root_uid" }
    guard number("_BBN", in: root, depth: 3) == UInt32(bus) else { return "acpi_root_bus" }
    guard number("_ADR", in: bridge, depth: 4) == target.bridgeADR else { return "acpi_bridge_adr" }
    guard number("_ADR", in: endpoint, depth: 5) == target.endpointADR else { return "acpi_endpoint_adr" }
    return nil
}

func staticSegmentRefusal(_ tables: ACPITables, _ topology: TopologySample) -> String? {
    guard !tables.aml.contains(where: { $0.range(of: Data("_SEG".utf8)) != nil }) else {
        return "explicit_or_unresolved_acpi_segment"
    }
    guard let windows = mcfgWindows(tables.mcfg), uniqueMCFGCover(windows, bridgeBus: topology.bridgeBus,
                                                               downstream: topology.downstream),
          windows.contains(where: { $0.segment == 0 && $0.buses.contains(topology.bridgeBus) }) else {
        return "acpi_default_segment_or_mcfg_disagrees"
    }
    return nil
}

struct CaptureInputs: Equatable {
    let topology: TopologySample
    let tables: ACPITables
    let properties: Data
}

struct CaptureTargetRefusal: Error {
    let reason: String
}

func captureTargetPath(_ first: CaptureInputs, _ second: CaptureInputs, asl: String) throws -> Data {
    guard first == second, let target = first.topology.acpi else {
        throw CaptureTargetRefusal(reason: "unstable_capture_inputs")
    }
    if let reason = staticSegmentRefusal(first.tables, first.topology) ??
        staticRootRefusal(asl, target, bus: first.topology.bridgeBus) {
        throw CaptureTargetRefusal(reason: reason)
    }
    guard let nodes = efiPropertyNodes(first.properties),
          let path = uniqueEFIPropertyPath(nodes, for: first.topology.pciPath) else {
        throw CaptureTargetRefusal(reason: "unsupported_or_ambiguous_capture_path")
    }
    return first.properties.subdata(in: path)
}

func captureTargetSource(_ path: Data) -> Data {
    let bytes = path.map { String(format: "0x%02x", $0) }
    let rows = stride(from: 0, to: bytes.count, by: 12).map { offset in
        "    " + bytes[offset..<min(offset + 12, bytes.count)].joined(separator: ", ") + ","
    }
    return Data(([
        "#include \"build34_r3_preboot_pci.h\"", "",
        "static CONST UINT8 target_path[] = {",
    ] + rows + [
        "};", "", "CONST PHX34_PREBOOT_PCI_PATH_IDENTITY Phx34CaptureTarget = {",
        "    .DevicePath = target_path,", "    .DevicePathBytes = sizeof(target_path),", "    .Segment = 0,",
        "};", "",
    ]).joined(separator: "\n").utf8)
}

func captureInputs() -> CaptureInputs {
    CaptureInputs(topology: sample(checkACPI: true), tables: staticTables(), properties: cachedEFIProperties())
}

func writePrivateCaptureTarget(_ bytes: Data) throws -> String {
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
    let build = root.appendingPathComponent("build", isDirectory: true)
    let attributes = try build.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
    guard attributes.isDirectory == true, attributes.isSymbolicLink == false else {
        throw CaptureTargetRefusal(reason: "private_capture_build_directory")
    }
    var template = build.appendingPathComponent("r3-preboot-capture-private.XXXXXX").path.utf8CString
    guard let newPath = template.withUnsafeMutableBufferPointer({ buffer in
        mkdtemp(buffer.baseAddress!).map { String(cString: $0) }
    }) else {
        throw CaptureTargetRefusal(reason: "private_capture_directory_creation")
    }
    let directory = URL(fileURLWithPath: newPath, isDirectory: true)
    do {
        try captureTargetSource(bytes).write(to: directory.appendingPathComponent("target.c"), options: .withoutOverwriting)
        try bytes.write(to: directory.appendingPathComponent("target-path.bin"), options: .withoutOverwriting)
    } catch {
        try? FileManager.default.removeItem(at: directory)
        throw error
    }
    return "build/\(directory.lastPathComponent)"
}

func disassembleStaticRoot(_ dsdt: Data, using executable: String) throws -> String {
    let binary = URL(fileURLWithPath: executable)
    let digest = SHA256.hash(data: try Data(contentsOf: binary)).map { String(format: "%02x", $0) }.joined()
    guard digest == "93f1f48e6f1ea26b14b45f4a0b6e65a660c1cc6f14969348ec9411ae6b969c12" else {
        throw CocoaError(.fileReadCorruptFile)
    }
    let fileManager = FileManager.default
    let privateDirectory = fileManager.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
    try fileManager.createDirectory(at: privateDirectory, withIntermediateDirectories: false,
                                    attributes: [.posixPermissions: 0o700])
    do {
        try dsdt.write(to: privateDirectory.appendingPathComponent("table.aml"))
        let task = Process()
        task.executableURL = binary
        task.currentDirectoryURL = privateDirectory
        task.arguments = ["-d", "table.aml"]
        task.standardOutput = FileHandle.nullDevice
        task.standardError = FileHandle.nullDevice
        let finished = DispatchSemaphore(value: 0)
        task.terminationHandler = { _ in finished.signal() }
        try task.run()
        if finished.wait(timeout: .now() + 10) == .timedOut {
            if task.isRunning { kill(task.processIdentifier, SIGKILL) }
            task.waitUntilExit()
            throw CocoaError(.fileReadUnknown)
        }
        task.waitUntilExit()
        guard task.terminationStatus == 0 else { throw CocoaError(.fileReadCorruptFile) }
        let asl = try String(contentsOf: privateDirectory.appendingPathComponent("table.dsl"), encoding: .utf8)
        try fileManager.removeItem(at: privateDirectory)
        return asl
    } catch {
        try? fileManager.removeItem(at: privateDirectory)
        throw error
    }
}

func testStaticRoot(includeCapture: Bool = false) {
    let fixture = """
        Scope (\\_SB)
        {
            Device (PCIR)
            {
                Name (_HID, EisaId ("PNP0A08") /* PCI Express root */)
                Name (_UID, 0x34)
                Name (_BBN, One)
                Device (BRDG)
                {
                    Name (_ADR, 0x00060001) // Synthetic bridge
                    Device (GFXD)
                    {
                        Name (_ADR, Zero)
                    }
                }
            }
        }
    """
    let target = ACPITarget(names: ["_SB", "PCIR", "BRDG", "GFXD"], rootUID: 0x34, bridgeADR: 0x60001, endpointADR: 0)
    if includeCapture {
        testCaptureTarget(asl: fixture, target: target)
        return
    }
    func changed(_ old: String, _ new: String) -> String? {
        staticRootRefusal(fixture.replacingOccurrences(of: old, with: new), target, bus: 1)
    }
    let cases = [
        staticRootRefusal(fixture, target, bus: 1) == nil,
        staticRootRefusal(fixture + "\n" + fixture, target, bus: 1) == "acpi_root_scope",
        changed("Scope (\\_SB)", "Scope (\\_TZ)") == "acpi_root_scope",
        changed("Device (BRDG)", "Device (OTHR)") == "acpi_bridge_scope",
        changed("Device (GFXD)", "Device (OTHR)") == "acpi_endpoint_scope",
        changed("PNP0A08", "ACPI0004") == "acpi_root_hid",
        changed("_UID, 0x34", "_UID, 0x35") == "acpi_root_uid",
        changed("Name (_BBN, One)", "Method (_BBN, 0)") == "acpi_root_bus",
        changed("0x00060001", "0x00060000") == "acpi_bridge_adr",
        changed("_ADR, Zero", "_ADR, One") == "acpi_endpoint_adr"
    ]
    guard cases.allSatisfy({ $0 }) else { refuse("acpi_root_fixture_failed") }
    print("static_acpi_root_fixture_cases_passed=\(cases.count)")
}

func makeMCFGTable(_ rows: [(UInt16, UInt8, UInt8)], change: (inout [UInt8]) -> Void = { _ in }) -> Data {
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

func testMCFG() {
    let good = makeMCFGTable([(7, 32, 95), (3, 0, 31)])
    let ambiguous = makeMCFGTable([(7, 32, 95), (0x0107, 60, 60)])
    let split = makeMCFGTable([(7, 32, 63), (7, 64, 95)])
    var badChecksum = good
    badChecksum[9] ^= 1
    let cases = [
        mcfgWindows(good).map { uniqueMCFGCover($0, bridgeBus: 32, downstream: 33...95) } == true,
        mcfgWindows(ambiguous).map { uniqueMCFGCover($0, bridgeBus: 32, downstream: 33...95) } == false,
        mcfgWindows(split).map { uniqueMCFGCover($0, bridgeBus: 32, downstream: 33...95) } == false,
        mcfgWindows(good).map { uniqueMCFGCover($0, bridgeBus: 96, downstream: 97...100) } == false,
        mcfgWindows(makeMCFGTable([])) == nil,
        mcfgWindows(makeMCFGTable(Array(repeating: (7, 32, 63), count: 257))) == nil,
        mcfgWindows(Data(good.dropLast())) == nil,
        mcfgWindows(makeMCFGTable([(7, 32, 31)])) == nil,
        mcfgWindows(makeMCFGTable([(7, 32, 63), (7, 63, 95)])) == nil,
        mcfgWindows(makeMCFGTable([(7, 32, 63)]) { $0[0] ^= 1 }) == nil,
        mcfgWindows(makeMCFGTable([(7, 32, 63)]) { $0[4] ^= 1 }) == nil,
        mcfgWindows(makeMCFGTable([(7, 32, 63)]) { $0[8] ^= 1 }) == nil,
        mcfgWindows(makeMCFGTable([(7, 32, 63)]) { $0[36] = 1 }) == nil,
        mcfgWindows(makeMCFGTable([(7, 32, 63)]) { $0[56] = 1 }) == nil,
        mcfgWindows(badChecksum) == nil
    ]
    guard cases.allSatisfy({ $0 }) else { refuse("mcfg_fixture_failed") }
    print("mcfg_fixture_cases_passed=\(cases.count)")
}

func testCaptureTarget(asl: String, target: ACPITarget) {
    let path: [UInt8] = [2, 1, 12, 0, 0xd0, 0x41, 3, 10, 0x34, 0, 0, 0,
                         1, 1, 6, 0, 1, 6, 1, 1, 6, 0, 0, 0, 0x7f, 0xff, 4, 0]
    let node: [UInt8] = [52, 0, 0, 0, 1, 0, 0, 0] + path + [8, 0, 0, 0, 0x41, 0, 0, 0, 8, 0, 0, 0, 0xa5, 2, 3, 4]
    let properties = Data([64, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0] + node)
    let duplicate = Data([116, 0, 0, 0, 1, 0, 0, 0, 2, 0, 0, 0] + node + node)
    let coords = PCIPathCoordinates(rootUID: target.rootUID, hops: [target.bridgeADR, target.endpointADR])
    let table = makeMCFGTable([(0, 1, 6)])
    func inputs(properties: Data, table: Data, aml: [Data] = [], identity: UInt64 = 1) -> CaptureInputs {
        CaptureInputs(topology: TopologySample(identity: [identity], bridgeBus: 1, downstream: 2...6,
                                               acpi: target, pciPath: coords),
                      tables: ACPITables(dsdt: Data(), mcfg: table, aml: aml), properties: properties)
    }
    let good = inputs(properties: properties, table: table)
    let changed = inputs(properties: properties, table: table, identity: 2)
    let wrongSegment = inputs(properties: properties, table: makeMCFGTable([(1, 1, 6)]))
    let overlapping = inputs(properties: properties, table: makeMCFGTable([(0, 1, 6), (1, 6, 6)]))
    let explicitSegment = inputs(properties: properties, table: table, aml: [Data("_SEG".utf8)])
    let ambiguous = inputs(properties: duplicate, table: table)
    let short = inputs(properties: Data(properties.dropLast()), table: table)
    func check(_ first: CaptureInputs, _ second: CaptureInputs, asl: String, reason: String) -> Bool {
        do {
            _ = try captureTargetPath(first, second, asl: asl)
            return false
        } catch let refusal as CaptureTargetRefusal {
            return refusal.reason == reason
        } catch {
            return false
        }
    }
    guard let bytes = try? captureTargetPath(good, good, asl: asl) else { refuse("capture_target_fixture_failed") }
    let source = String(decoding: captureTargetSource(bytes), as: UTF8.self)
    let cases = [
        bytes == Data(path),
        source.contains(".Segment = 0,") && source.contains(".DevicePathBytes = sizeof(target_path),"),
        source.contains("0x7f, 0xff, 0x04, 0x00,") && !source.contains("0xa5"),
        check(good, changed, asl: asl, reason: "unstable_capture_inputs"),
        check(good, wrongSegment, asl: asl, reason: "unstable_capture_inputs"),
        check(good, ambiguous, asl: asl, reason: "unstable_capture_inputs"),
        check(wrongSegment, wrongSegment, asl: asl, reason: "acpi_default_segment_or_mcfg_disagrees"),
        check(overlapping, overlapping, asl: asl, reason: "acpi_default_segment_or_mcfg_disagrees"),
        check(explicitSegment, explicitSegment, asl: asl, reason: "explicit_or_unresolved_acpi_segment"),
        check(ambiguous, ambiguous, asl: asl, reason: "unsupported_or_ambiguous_capture_path"),
        check(short, short, asl: asl, reason: "unsupported_or_ambiguous_capture_path"),
        check(good, good, asl: asl.replacingOccurrences(of: "Device (BRDG)", with: "Device (OTHR)"),
              reason: "acpi_bridge_scope")
    ]
    guard cases.allSatisfy({ $0 }) else { refuse("capture_target_fixture_failed") }
    print("capture_target_fixture_cases_passed=\(cases.count)")
}

let arguments = Array(CommandLine.arguments.dropFirst())
if arguments == ["--test-efi-property-path"] {
    testEFIPropertyPaths()
    exit(0)
}
if arguments == ["--check-efi-property-path"] {
    let first = sample()
    let firstProperties = cachedEFIProperties()
    let second = sample()
    let secondProperties = cachedEFIProperties()
    guard first == second, firstProperties == secondProperties else { refuse("unstable_efi_property_inputs") }
    guard let nodes = efiPropertyNodes(firstProperties) else { refuse("unsupported_efi_property_buffer") }
    guard uniqueEFIPropertyPath(nodes, for: first.pciPath) != nil else { refuse("missing_or_duplicate_efi_property_path") }
    print("matching_input_pairs=2; validated_pci_property_paths=\(nodes.count); unique_target_path=true")
    print("candidate_complete_binary_path_present=true; installed_firmware_path_or_segment_attested=false")
    exit(0)
}
if arguments == ["--test-mcfg"] {
    testMCFG()
    exit(0)
}
if arguments == ["--test-acpi-root"] {
    testStaticRoot()
    exit(0)
}
if arguments == ["--test-capture-target"] {
    testStaticRoot(includeCapture: true)
    exit(0)
}
if arguments.count == 2 && arguments[0] == "--prepare-capture-target" {
    _ = umask(0o077)
    let first = captureInputs()
    guard let asl = try? disassembleStaticRoot(first.tables.dsdt, using: arguments[1]) else {
        refuse("acpi_disassembly")
    }
    let second = captureInputs()
    do {
        let bytes = try captureTargetPath(first, second, asl: asl)
        print("private_capture_target_directory=\(try writePrivateCaptureTarget(bytes))")
        print("paired_cached_evidence_matches=true; physical_identity_attested=false; activation_authorized=false")
    } catch let refusal as CaptureTargetRefusal {
        refuse(refusal.reason)
    } catch {
        refuse("private_capture_target_write")
    }
    exit(0)
}
if arguments.count == 2 && arguments[0] == "--check-acpi-root" {
    let first = sample(checkACPI: true)
    let firstTables = staticTables()
    let second = sample(checkACPI: true)
    let secondTables = staticTables()
    guard first == second, firstTables == secondTables, let target = first.acpi else { refuse("unstable_acpi_inputs") }
    if let reason = staticSegmentRefusal(firstTables, first) { refuse(reason) }
    guard let asl = try? disassembleStaticRoot(firstTables.dsdt, using: arguments[1]) else { refuse("acpi_disassembly") }
    if let reason = staticRootRefusal(asl, target, bus: first.bridgeBus) { refuse(reason) }
    print("matching_input_pairs=2; validated_aml_tables=\(firstTables.aml.count); static_root_uid_adr_bbn_match=true")
    print("no_seg_nameseg_in_exposed_aml=true; static_acpi_default_segment_matches_mcfg=true")
    print("runtime_aml_namespace_or_uefi_path_attested=false")
    exit(0)
}
let checkMCFG = arguments == ["--check-acpi-mcfg"]
guard checkMCFG || arguments.isEmpty else { refuse("arguments") }
let first = sample()
let firstMCFG = checkMCFG ? cachedTables()["MCFG"] as? Data : nil
let second = sample()
let secondMCFG = checkMCFG ? cachedTables()["MCFG"] as? Data : nil
guard first == second else { refuse("unstable_topology") }
if checkMCFG {
    guard let table = firstMCFG, secondMCFG != nil else { refuse("missing_cached_mcfg") }
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
