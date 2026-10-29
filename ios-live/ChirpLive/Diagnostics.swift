import AVFoundation
import CoreLocation
import SwiftUI
import Foundation
import UIKit

/// What went wrong recently, kept on the iPhone (last 40 lines) for the
/// diagnostics export. Never holds passwords or the sign-in token.
enum DiagLog {
    private static let key = "diagLog"
    private static let lock = NSLock()

    static func note(_ what: String) {
        lock.lock(); defer { lock.unlock() }
        var lines = UserDefaults.standard.stringArray(forKey: key) ?? []
        lines.append("\(ISO8601DateFormatter().string(from: Date()))  \(what.prefix(300))")
        UserDefaults.standard.set(Array(lines.suffix(40)), forKey: key)
    }

    static var lines: [String] { UserDefaults.standard.stringArray(forKey: key) ?? [] }
}

/// Settings → Export diagnostics: a text file about this copy of Chirp Live.
@MainActor
enum Diagnostics {
    static func report(listener: Listener, store: SessionStore, account: Account) -> String {
        var out: [String] = ["Chirp Live diagnostics", "Made \(ISO8601DateFormatter().string(from: Date()))"]
        func h(_ t: String) { out.append(""); out.append("== \(t) ==") }
        func add(_ k: String, _ v: Any?) { out.append(k.padding(toLength: 24, withPad: " ", startingAt: 0) + " " + "\(v ?? "")") }

        let info = Bundle.main.infoDictionary ?? [:]
        h("App")
        add("Version", "\(info["CFBundleShortVersionString"] ?? "?") (\(info["CFBundleVersion"] ?? "?"))")
        add("Lowest confidence", Theme.percent(listener.minConfidence))
        add("Listening", "\(listener.state)")
        add("Source", { if case .station(let s) = listener.source { return "station \(s.name)" }; return "this iPhone" }())

        h("Device")
        var sys = utsname(); uname(&sys)
        let model = withUnsafeBytes(of: &sys.machine) { String(decoding: $0.prefix { $0 != 0 }, as: UTF8.self) }
        add("Model", model)
        add("iOS", UIDevice.current.systemVersion)
        add("Language, time zone", "\(Locale.current.identifier), \(TimeZone.current.identifier)")
        if let free = try? URL(fileURLWithPath: NSHomeDirectory()).resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey])
            .volumeAvailableCapacityForImportantUsage {
            add("Free space", ByteCountFormatter.string(fromByteCount: free, countStyle: .file))
        }

        h("Permissions and sound")
        add("Microphone", { switch AVAudioApplication.shared.recordPermission {
            case .granted: return "allowed"; case .denied: return "denied"; default: return "not asked" } }())
        add("Location", { switch CLLocationManager().authorizationStatus {
            case .authorizedAlways, .authorizedWhenInUse: return "allowed"; case .denied: return "denied"
            case .restricted: return "restricted"; default: return "not asked" } }())
        let session = AVAudioSession.sharedInstance()
        add("Audio category", "\(session.category.rawValue) / \(session.mode.rawValue)")
        add("Output", session.currentRoute.outputs.map { "\($0.portType.rawValue) (\($0.portName))" }.joined(separator: ", "))
        add("Input", session.currentRoute.inputs.map { "\($0.portType.rawValue) (\($0.portName))" }.joined(separator: ", "))
        add("Output volume", String(format: "%.2f", session.outputVolume))

        h("Chirp site")
        add("Signed in", account.signedIn ? "yes, \(account.username) on \(account.siteName)" : "no")
        if let e = account.expires { add("Sign-in expires", ISO8601DateFormatter().string(from: e)) }
        add("Stations", listener.stations.count)

        h("Sessions")
        let all = store.sessions
        add("Kept on this iPhone", all.count)
        let root = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("Sessions")
        add("Space used", ByteCountFormatter.string(fromByteCount: folderSize(root), countStyle: .file))
        for s in all.prefix(8) {
            let audio = store.audioURL(s)
            let size = audio.flatMap { try? $0.resourceValues(forKeys: [.fileSizeKey]).fileSize } ?? 0
            let clips = s.heard.filter { store.clipURL(s, $0).map { FileManager.default.fileExists(atPath: $0.path) } ?? false }.count
            var site = "-"
            if s.site != nil { site = s.savedToSite == true ? "saved" : s.savedToSite == false ? "not saved: \(s.siteError ?? "?")" : "pending" }
            out.append("  \(ISO8601DateFormatter().string(from: s.start))  \(Int(s.duration))s  \(s.heard.count) species  "
                       + "sound \(audio == nil ? (store.preparing.contains(s.id) ? "preparing" : "none") : ByteCountFormatter.string(fromByteCount: Int64(size), countStyle: .file))  "
                       + "clips \(clips)/\(s.heard.count)  site \(site)")
        }

        h("Recent problems")
        let lines = DiagLog.lines
        out.append(contentsOf: lines.isEmpty ? ["  none"] : lines.map { "  " + $0 })
        return out.joined(separator: "\n") + "\n"
    }

    private static func folderSize(_ url: URL) -> Int64 {
        let keys: [URLResourceKey] = [.fileSizeKey]
        guard let e = FileManager.default.enumerator(at: url, includingPropertiesForKeys: keys) else { return 0 }
        var total: Int64 = 0
        for case let f as URL in e { total += Int64((try? f.resourceValues(forKeys: Set(keys)).fileSize) ?? 0) }
        return total
    }
}

/// The system share sheet for one file.
struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }
    func updateUIViewController(_ vc: UIActivityViewController, context: Context) {}
}

extension Diagnostics {
    /// Writes the report to a .txt file for the share sheet.
    static func file(listener: Listener, store: SessionStore, account: Account) -> URL? {
        let d = DateFormatter(); d.dateFormat = "yyyy-MM-dd-HHmm"
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("chirp-live-diagnostics-\(d.string(from: Date())).txt")
        do { try report(listener: listener, store: store, account: account).write(to: url, atomically: true, encoding: .utf8); return url }
        catch { return nil }
    }
}
