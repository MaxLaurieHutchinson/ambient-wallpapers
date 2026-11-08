// Ambient Wallpapers native macOS adapter.
// Inspect and Plan are read-only. Apply requires a matching plan token and a backup root.
// Swift/AppKit is used rather than AppleScript automation of System Settings.
import AppKit
import CoreGraphics
import CryptoKit
import Foundation

struct WallpaperError: Error, CustomStringConvertible {
    let description: String
    init(_ description: String) { self.description = description }
}

struct Display {
    let screen: NSScreen
    let id: String
    let builtIn: Bool
    let pixelWidth: Int
    let pixelHeight: Int
}

struct Assignment {
    let display: Display
    let role: String
    let image: URL
}

func argument(_ name: String) -> String? {
    let values = CommandLine.arguments
    guard let index = values.firstIndex(of: name), values.indices.contains(index + 1) else { return nil }
    return values[index + 1]
}

func required(_ name: String) throws -> String {
    guard let value = argument(name), !value.isEmpty else { throw WallpaperError("Missing \(name)") }
    return value
}

func readObject(_ path: String) throws -> [String: Any] {
    let data = try Data(contentsOf: URL(fileURLWithPath: path))
    guard let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
        throw WallpaperError("Expected a JSON object: \(path)")
    }
    return obj
}

func emit(_ object: [String: Any]) throws {
    let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys, .prettyPrinted])
    guard let output = String(data: data, encoding: .utf8) else { throw WallpaperError("Cannot encode JSON") }
    print(output)
}

@MainActor func displays() throws -> [Display] {
    var result = [Display]()
    var known = Set<String>()
    for screen in NSScreen.screens {
        guard let number = screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber else {
            throw WallpaperError("A connected macOS display has no CoreGraphics device identifier")
        }
        let displayID = CGDirectDisplayID(number.uint32Value)
        let id = String(displayID)
        guard known.insert(id).inserted else { throw WallpaperError("Duplicate connected display identifier: \(id)") }
        let width = Int(CGDisplayPixelsWide(displayID))
        let height = Int(CGDisplayPixelsHigh(displayID))
        guard width > 0 && height > 0 else { throw WallpaperError("Invalid display pixel size for \(id)") }
        result.append(Display(screen: screen, id: id, builtIn: CGDisplayIsBuiltin(displayID) != 0,
                              pixelWidth: width, pixelHeight: height))
    }
    guard !result.isEmpty else { throw WallpaperError("No connected macOS displays; refusing wallpaper mutation") }
    // Explicit ordering is important: monitors[] follows left-to-right desktop coordinates.
    return result.sorted {
        if $0.screen.frame.minX != $1.screen.frame.minX { return $0.screen.frame.minX < $1.screen.frame.minX }
        if $0.screen.frame.minY != $1.screen.frame.minY { return $0.screen.frame.minY < $1.screen.frame.minY }
        return $0.id < $1.id
    }
}

func imageURL(_ value: String) throws -> URL {
    guard value.hasPrefix("/") else { throw WallpaperError("Wallpaper image path must be absolute") }
    let url = URL(fileURLWithPath: value).standardizedFileURL.resolvingSymlinksInPath()
    var isDir: ObjCBool = false
    guard FileManager.default.fileExists(atPath: url.path, isDirectory: &isDir), !isDir.boolValue else {
        throw WallpaperError("Wallpaper image does not exist: \(value)")
    }
    guard NSImage(contentsOf: url) != nil else { throw WallpaperError("Wallpaper image cannot be decoded: \(value)") }
    return url
}

func signature(_ assignments: [Assignment]) -> String {
    let text = assignments.map {
        "\($0.display.id)|\($0.display.pixelWidth)x\($0.display.pixelHeight)|\($0.role)|\($0.image.path)"
    }.joined(separator: "\n")
    return SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
}

func describe(_ assignment: Assignment) -> [String: Any] {
    ["DevicePath": assignment.display.id, "WallpaperPath": assignment.image.path,
     "Role": assignment.role, "Width": assignment.display.pixelWidth,
     "Height": assignment.display.pixelHeight]
}

func describe(_ display: Display) -> [String: Any] {
    ["DevicePath": display.id, "Connected": true, "Builtin": display.builtIn,
     "Width": display.pixelWidth, "Height": display.pixelHeight,
     "Name": display.screen.localizedName]
}

@MainActor func makePlan(_ obj: [String: Any], _ connected: [Display]) throws -> [Assignment] {
    let roleMap: [String: String]
    if let raw = obj["display_roles"] {
        guard let roles = raw as? [String: String] else { throw WallpaperError("display_roles must map device IDs to laptop or monitor") }
        roleMap = roles
    } else { roleMap = [:] }
    let ids = Set(connected.map { $0.id })
    for (id, role) in roleMap {
        guard ids.contains(id), role == "laptop" || role == "monitor" else {
            throw WallpaperError("Unknown display or invalid role: \(id) = \(role)")
        }
    }
    guard let laptopPath = obj["laptop"] as? String,
          let monitorPaths = obj["monitors"] as? [String] else {
        throw WallpaperError("Assignment requires laptop path and monitors array")
    }
    let roles = connected.map { roleMap[$0.id] ?? ($0.builtIn ? "laptop" : "monitor") }
    guard roles.filter({ $0 == "laptop" }).count <= 1 else {
        throw WallpaperError("Multiple displays have laptop role; supply an explicit role mapping")
    }
    let monitorCount = roles.filter { $0 == "monitor" }.count
    guard monitorPaths.count >= monitorCount else {
        throw WallpaperError("\(monitorCount) connected external displays but only \(monitorPaths.count) monitor images")
    }
    var nextExternal = 0
    var result = [Assignment]()
    for (display, role) in zip(connected, roles) {
        let path: String
        if role == "laptop" {
            path = laptopPath
        } else {
            path = monitorPaths[nextExternal]
            nextExternal += 1
        }
        result.append(Assignment(display: display, role: role, image: try imageURL(path)))
    }
    return result
}

@MainActor func readback(_ screen: NSScreen, expected: URL) -> Bool {
    guard let selected = NSWorkspace.shared.desktopImageURL(for: screen) else { return false }
    return selected.standardizedFileURL.resolvingSymlinksInPath().path == expected.path
}

@MainActor func waitForReadback(_ screen: NSScreen, expected: URL) -> Bool {
    for attempt in 0..<20 {
        if readback(screen, expected: expected) { return true }
        if attempt < 19 { Thread.sleep(forTimeInterval: 0.1) }
    }
    return false
}

@MainActor func snapshotOptions(_ screen: NSScreen) -> [String: Any] {
    let options = NSWorkspace.shared.desktopImageOptions(for: screen) ?? [:]
    var result = [String: Any]()
    if let scale = options[.imageScaling] as? NSNumber { result["scale"] = scale.intValue }
    if let clip = options[.allowClipping] as? NSNumber { result["allow_clipping"] = clip.boolValue }
    if let color = options[.fillColor] as? NSColor,
       let rgb = color.usingColorSpace(.deviceRGB) {
        result["fill_rgba"] = [Double(rgb.redComponent), Double(rgb.greenComponent),
                               Double(rgb.blueComponent), Double(rgb.alphaComponent)]
    }
    return result
}

func restoredOptions(_ raw: Any?) -> [NSWorkspace.DesktopImageOptionKey: Any] {
    guard let values = raw as? [String: Any] else { return [:] }
    var result: [NSWorkspace.DesktopImageOptionKey: Any] = [:]
    if let scale = values["scale"] as? Int { result[.imageScaling] = NSNumber(value: scale) }
    if let clip = values["allow_clipping"] as? Bool { result[.allowClipping] = NSNumber(value: clip) }
    if let rgba = values["fill_rgba"] as? [Double], rgba.count == 4 {
        result[.fillColor] = NSColor(deviceRed: rgba[0], green: rgba[1], blue: rgba[2], alpha: rgba[3])
    }
    return result
}

@MainActor func restoreSnapshots(_ snapshots: [[String: Any]], _ connected: [Display]) throws -> [[String: Any]] {
    let lookup = Dictionary(uniqueKeysWithValues: connected.map { ($0.id, $0) })
    guard snapshots.count == connected.count else {
        throw WallpaperError("Display topology differs from the saved state; refusing partial restoration")
    }
    var planned = [(Display, URL, [NSWorkspace.DesktopImageOptionKey: Any])]()
    var seen = Set<String>()
    for snapshot in snapshots {
        guard let id = snapshot["device_id"] as? String, seen.insert(id).inserted,
              let display = lookup[id], let path = snapshot["backup_path"] as? String else {
            throw WallpaperError("Missing/duplicate saved display or disconnected monitor; refusing partial restore")
        }
        // Validate every backup before touching any display.
        let file = try imageURL(path)
        planned.append((display, file, restoredOptions(snapshot["options"])))
    }
    for (display, image, options) in planned {
        try NSWorkspace.shared.setDesktopImageURL(image, for: display.screen, options: options)
    }
    for (display, image, _) in planned {
        guard waitForReadback(display.screen, expected: image) else {
            throw WallpaperError("macOS did not verify the restored image for display \(display.id)")
        }
    }
    return planned.map { ["DevicePath": $0.0.id, "WallpaperPath": $0.1.path] }
}

@MainActor func apply(_ assignments: [Assignment], _ backupRoot: String) throws -> [String: Any] {
    let fm = FileManager.default
    let root = URL(fileURLWithPath: backupRoot, isDirectory: true).standardizedFileURL
    let folder = root.appendingPathComponent(UUID().uuidString, isDirectory: true)
    try fm.createDirectory(at: folder, withIntermediateDirectories: true)
    try? fm.setAttributes([.posixPermissions: 0o700], ofItemAtPath: folder.path)
    var snapshots = [[String: Any]]()
    // All copies must succeed before a single wallpaper change.
    for assignment in assignments {
        guard let original = NSWorkspace.shared.desktopImageURL(for: assignment.display.screen), original.isFileURL else {
            throw WallpaperError("Cannot read original file-backed wallpaper on display \(assignment.display.id); no changes made")
        }
        guard NSImage(contentsOf: original) != nil else {
            throw WallpaperError("Original wallpaper is not a static image that this adapter can reliably restore; no changes made")
        }
        let backup = folder.appendingPathComponent("original-\(assignment.display.id).\(original.pathExtension.isEmpty ? "img" : original.pathExtension)")
        try fm.copyItem(at: original, to: backup)
        snapshots.append(["device_id": assignment.display.id,
                          "original_path": original.path,
                          "backup_path": backup.path,
                          "options": snapshotOptions(assignment.display.screen)])
    }
    let receipt = folder.appendingPathComponent("state.json")
    var state: [String: Any] = ["version": 1, "platform": "macos",
                                "status": "prepared", "snapshots": snapshots,
                                "restore_note": "Restores static image copies and recorded scaling options. Dynamic/video wallpapers and every macOS Space are not guaranteed to be restored."]
    try JSONSerialization.data(withJSONObject: state, options: [.prettyPrinted, .sortedKeys]).write(to: receipt, options: .atomic)
    do {
        for assignment in assignments {
            try NSWorkspace.shared.setDesktopImageURL(assignment.image, for: assignment.display.screen, options: [:])
        }
        for assignment in assignments {
            guard waitForReadback(assignment.display.screen, expected: assignment.image) else {
                throw WallpaperError("macOS did not verify image on display \(assignment.display.id)")
            }
        }
    } catch {
        do {
            _ = try restoreSnapshots(snapshots, assignments.map { $0.display })
            state["status"] = "rolled_back"
            try JSONSerialization.data(withJSONObject: state, options: [.prettyPrinted, .sortedKeys]).write(to: receipt, options: .atomic)
            throw WallpaperError("Apply failed: \(error). Original static wallpapers restored; receipt: \(receipt.path)")
        } catch let restoreError as WallpaperError where restoreError.description.hasPrefix("Apply failed:") {
            throw restoreError
        } catch {
            throw WallpaperError("Apply failed and automatic rollback could not be verified: \(error). Manual receipt: \(receipt.path)")
        }
    }
    state["status"] = "applied"
    try JSONSerialization.data(withJSONObject: state, options: [.prettyPrinted, .sortedKeys]).write(to: receipt, options: .atomic)
    return ["Result": "Applied", "StatePath": receipt.path,
            "Assignment": assignments.map(describe), "RestoreNote": state["restore_note"] ?? ""]
}

@MainActor func run() throws {
    let mode = try required("--mode")
    let connected = try displays()
    if mode == "Inspect" {
        try emit(["Result": "Inspected", "Monitors": connected.map(describe)])
        return
    }
    if mode == "Restore" {
        let statePath = try required("--state-path")
        let state = try readObject(statePath)
        guard state["platform"] as? String == "macos", state["version"] as? Int == 1,
              let snapshots = state["snapshots"] as? [[String: Any]] else {
            throw WallpaperError("Not a supported macOS restore receipt")
        }
        let restored = try restoreSnapshots(snapshots, connected)
        try emit(["Result": "RestoredStaticImages", "Assignment": restored,
                  "StatePath": statePath,
                  "RestoreNote": "macOS dynamic wallpapers, Space-specific settings and rotations may require manual restoration in System Settings."])
        return
    }
    guard mode == "Plan" || mode == "Apply" else {
        throw WallpaperError("Unsupported mode \(mode); expected Inspect, Plan, Apply or Restore")
    }
    let obj = try readObject(try required("--assignment-path"))
    let assignments = try makePlan(obj, connected)
    let token = signature(assignments)
    if mode == "Plan" {
        try emit(["Result": "Planned", "Assignment": assignments.map(describe),
                  "PlanID": token, "Monitors": connected.map(describe)])
        return
    }
    let expected = try required("--plan-id")
    guard expected == token else {
        throw WallpaperError("Plan does not match current displays or resolved images; no changes made")
    }
    let applied = try apply(assignments, required("--backup-root"))
    try emit(applied)
}

do {
    try run()
} catch {
    fputs("ambient-wallpapers macOS: \(error)\n", stderr)
    exit(2)
}
