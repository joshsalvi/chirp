import AVFoundation
import CoreLocation
import Foundation
import UIKit

/// A listening session: what was heard, when and where. Kept on the phone in
/// Documents/Sessions/<id>/ (session.json plus one WAV per species, its best
/// 3 s).
struct Session: Identifiable, Codable, Hashable {
    var id: String
    var start: Date
    var end: Date
    var latitude: Double?
    var longitude: Double?
    var place: String?          // "Broadmoor", from the phone's location
    var stationID: String?      // listened through a station
    var stationName: String?
    var heard: [Heard]          // best first
    var audio: String?          // the whole session, session.m4a
    /// Signed in: the site's ids for its clips, its address, and how saving went.
    var remoteIDs: [String]?
    var site: String?
    var savedToSite: Bool?
    var siteError: String?
    /// The person's own name for it (rename), and the one made when it was saved.
    var name: String?
    var autoName: String?
    var distance: Double?       // metres the phone moved

    var title: String { name ?? autoName ?? Session.makeTitle(self) }

    /// A friendly name from when, where and how: "Dawn chorus", "Afternoon
    /// walk in Broadmoor", "Owl prowl". A station is a device, not a place,
    /// so its name stays out of the title (the subtitle says "via <station>").
    static func makeTitle(_ s: Session) -> String {
        let h = Calendar.current.component(.hour, from: s.start)
        let part: String = {
            switch h {
            case 4..<7: return "Dawn"
            case 7..<11: return "Morning"
            case 11..<14: return "Midday"
            case 14..<17: return "Afternoon"
            case 17..<21: return "Evening"
            default: return "Night"
            }
        }()
        let n = s.heard.count
        let owl = s.heard.contains { $0.common.localizedCaseInsensitiveContains("owl") }
        let night = part == "Night"
        let place = s.place.map { $0.count <= 28 ? $0 : nil } ?? nil
        if s.stationName != nil {
            if night && owl { return "Owl watch" }
            if n >= 10 { return "Busy \(part.lowercased())" }
            if n <= 1 { return "Quiet \(part.lowercased())" }
            return "\(part) listen"
        }
        let dist = s.distance ?? 0
        if dist >= 250 {
            let speed = dist / max(s.duration, 1)
            if speed > 4 { return "\(part) drive" + (place.map { " near \($0)" } ?? "") }
            if night { return owl ? "Owl prowl" : "Night walk" }
            let walk = dist >= 3000 ? "hike" : (dist < 800 ? "stroll" : "walk")
            return "\(part) \(walk)" + (place.map { " in \($0)" } ?? "")
        }
        if night && owl { return "Owl watch" }
        if part == "Dawn" && n >= 5 { return "Dawn chorus" + (place.map { " at \($0)" } ?? "") }
        if n >= 10 { return "Busy \(part.lowercased())" + (place.map { " at \($0)" } ?? "") }
        if n <= 1 { return "Quiet \(part.lowercased())" + (place.map { " at \($0)" } ?? "") }
        if s.duration < 5 * 60 { return "Quick \(part.lowercased()) listen" }
        return "\(part) listen" + (place.map { " at \($0)" } ?? "")
    }
    var duration: TimeInterval { end.timeIntervalSince(start) }

    /// "Broadmoor · GPS 42.2731, -71.3502", or the station.
    var whereLine: String? {
        if let stationName { return "Via \(stationName)" }
        var parts: [String] = []
        if let place { parts.append(place) }
        if let latitude, let longitude { parts.append(String(format: "GPS %.4f, %.4f", latitude, longitude)) }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
}

@MainActor
final class SessionStore: ObservableObject {
    static let shared = SessionStore()
    @Published private(set) var sessions: [Session] = []
    /// Sessions whose sound is still being levelled and saved.
    @Published private(set) var preparing: Set<String> = []
    /// Sessions being sent to the site right now.
    @Published private(set) var uploading: Set<String> = []

    private let root: URL = {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let url = docs.appendingPathComponent("Sessions", isDirectory: true)
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }()

    private init() { load() }

    func folder(_ s: Session) -> URL { root.appendingPathComponent(s.id, isDirectory: true) }
    func clipURL(_ s: Session, _ h: Heard) -> URL? { h.clip.map { folder(s).appendingPathComponent($0) } }

    /// Every species ever heard (for "new to you").
    var lifeList: Set<String> { Set(sessions.flatMap { $0.heard.map(\.scientific) }) }

    func save(start: Date, end: Date, heard: [Heard], clips: [Int: [Float]], audio: URL?, place: CLLocation?,
              placeName: String?, station: Remote.Station?, remoteIDs: [String]?, distance: Double? = nil) -> Session {
        let id = ISO8601DateFormatter().string(from: start).replacingOccurrences(of: ":", with: "-")
        var s = Session(id: id, start: start, end: end,
                        latitude: station == nil ? place?.coordinate.latitude : nil,
                        longitude: station == nil ? place?.coordinate.longitude : nil,
                        place: station == nil ? placeName : nil, stationID: station?.id, stationName: station?.name,
                        heard: heard.sorted { $0.best > $1.best })
        s.distance = distance
        s.autoName = Session.makeTitle(s)
        let dir = folder(s)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        if let remoteIDs {
            s.remoteIDs = remoteIDs
            s.site = Account.shared.siteName
        }
        for k in s.heard.indices {
            guard let samples = clips[s.heard[k].id] else { continue }
            let name = "\(s.heard[k].id).m4a"
            if SoundFile.writeClip(samples, to: dir.appendingPathComponent(name)) {
                s.heard[k].clip = name
            }
        }
        write(s)
        sessions.insert(s, at: 0)
        // The session's sound is levelled off the main thread, then kept as
        // session.m4a and (signed in) saved to the site.
        if let audio {
            let raw = dir.appendingPathComponent("raw.m4a"), done = dir.appendingPathComponent("session.m4a")
            try? FileManager.default.moveItem(at: audio, to: raw)
            let id = s.id
            preparing.insert(id)
            Task.detached(priority: .utility) {
                do { try SoundFile.level(raw, to: done); try? FileManager.default.removeItem(at: raw) }
                catch {
                    DiagLog.note("level session sound: \(error.localizedDescription)")
                    try? FileManager.default.removeItem(at: done); try? FileManager.default.moveItem(at: raw, to: done)
                }
                await MainActor.run {
                    self.preparing.remove(id)
                    guard var cur = self.sessions.first(where: { $0.id == id }) else { return }
                    if FileManager.default.fileExists(atPath: done.path) { cur.audio = "session.m4a" }
                    self.update(cur)
                    self.upload(cur)
                }
            }
        }
        return s
    }

    /// The whole session's sound, once it's ready.
    func audioURL(_ s: Session) -> URL? {
        guard let a = s.audio else { return nil }
        let u = folder(s).appendingPathComponent(a)
        return FileManager.default.fileExists(atPath: u.path) ? u : nil
    }

    /// Rename a session; an empty name goes back to the automatic one.
    func rename(_ s: Session, to name: String) {
        var s = sessions.first { $0.id == s.id } ?? s
        let t = name.trimmingCharacters(in: .whitespacesAndNewlines)
        s.name = t.isEmpty ? nil : String(t.prefix(60))
        update(s)
    }

    /// Sessions that should be on the site but aren't yet (the app was closed
    /// or offline): tried again when Chirp Live opens. The site recognises a
    /// session it already has, so this never saves one twice.
    func retryPending() {
        for s in sessions where s.site != nil && s.savedToSite == nil && !uploading.contains(s.id) && !preparing.contains(s.id) {
            upload(s)
        }
    }

    private func write(_ s: Session) {
        if let data = try? JSONEncoder().encode(s) {
            try? data.write(to: folder(s).appendingPathComponent("session.json"))
        }
    }

    private func update(_ s: Session) {
        write(s)
        if let i = sessions.firstIndex(where: { $0.id == s.id }) { sessions[i] = s }
    }

    /// Signed in: saves the session to the site as one recording. Needs at
    /// least one clip the site heard a bird in.
    func upload(_ s: Session) {
        guard s.savedToSite != true, let ids = s.remoteIDs else { return }
        var s = s
        guard let name = s.audio else {
            if !preparing.contains(s.id) {
                s.savedToSite = false
                s.siteError = "This session has no sound to save."
                update(s)
            }
            return
        }
        guard !ids.isEmpty else {
            s.savedToSite = false
            s.siteError = "\(s.site ?? "Your site") didn't confirm any of these birds, so the session wasn't saved there."
            update(s); return
        }
        let account = Account.shared
        guard account.signedIn, let token = account.token else {
            s.siteError = "Sign in to save this session to your site."
            update(s); return
        }
        guard !uploading.contains(s.id) else { return }
        s.siteError = nil; s.savedToSite = nil
        update(s)
        let pending = s
        uploading.insert(s.id)
        // Keep going for a while if the phone is locked or the app is left.
        let bg = UIApplication.shared.beginBackgroundTask(withName: "save-session")
        Task {
            defer {
                uploading.remove(pending.id)
                if bg != .invalid { UIApplication.shared.endBackgroundTask(bg) }
            }
            var done = pending
            do {
                try await Remote.saveSession(audio: folder(done).appendingPathComponent(name), ids: ids, start: done.start,
                                             server: account.server, token: token, lat: done.latitude, lon: done.longitude,
                                             place: done.place, station: done.stationID)
                done.savedToSite = true
            } catch {
                if case Remote.Failure.signedOut = error { account.rejected() }
                if (error as? URLError)?.code == .cancelled || (error as? URLError)?.code == .networkConnectionLost {
                    // Interrupted (app suspended): left pending, tried again on the next open.
                    DiagLog.note("save to site interrupted: \(error.localizedDescription)")
                    update(done)
                    return
                }
                done.savedToSite = false
                done.siteError = error.localizedDescription
                DiagLog.note("save to site: \(error.localizedDescription)")
            }
            update(done)
        }
    }

    #if DEBUG
    /// App Store screenshots: sessions kept in memory only (nothing saved).
    func demo(_ list: [Session]) {
        for s in list {
            try? FileManager.default.createDirectory(at: folder(s), withIntermediateDirectories: true)
            for h in s.heard {
                if let c = h.clip { SoundFile.writeClip([Float](repeating: 0, count: 48_000), to: folder(s).appendingPathComponent(c)) }
            }
        }
        sessions = list
    }
    #endif

    func delete(_ s: Session) {
        try? FileManager.default.removeItem(at: folder(s))
        sessions.removeAll { $0.id == s.id }
    }

    private func load() {
        let dirs = (try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)) ?? []
        sessions = dirs.compactMap { dir in
            guard let data = try? Data(contentsOf: dir.appendingPathComponent("session.json")) else { return nil }
            guard var s = try? JSONDecoder().decode(Session.self, from: data) else { return nil }
            // Station sessions saved before 1.1 were titled "Evening at <station>".
            if s.stationName != nil { s.autoName = Session.makeTitle(s) }
            return s
        }.sorted { $0.start > $1.start }
    }
}

enum WAV {
    /// 16-bit mono WAV.
    static func write(_ samples: [Float], sampleRate: Double, to url: URL) -> Bool {
        guard let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: sampleRate, channels: 1, interleaved: false),
              let buf = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(samples.count)),
              let ch = buf.floatChannelData?[0] else { return false }
        buf.frameLength = AVAudioFrameCount(samples.count)
        samples.withUnsafeBufferPointer { ch.update(from: $0.baseAddress!, count: samples.count) }
        let settings: [String: Any] = [AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: sampleRate,
                                       AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16,
                                       AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false]
        do {
            let file = try AVAudioFile(forWriting: url, settings: settings, commonFormat: .pcmFormatFloat32, interleaved: false)
            try file.write(from: buf)
            return true
        } catch { return false }
    }

    /// A 16-bit mono WAV in memory.
    static func data(_ samples: [Float], sampleRate: Double) -> Data {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("wav-\(UUID().uuidString).wav")
        defer { try? FileManager.default.removeItem(at: url) }
        return write(samples, sampleRate: sampleRate, to: url) ? ((try? Data(contentsOf: url)) ?? Data()) : Data()
    }

    /// Mono samples at `sampleRate` from any audio file (tests, imports).
    static func read(_ url: URL, sampleRate: Double = BirdNET.sampleRate) throws -> [Float] {
        let file = try AVAudioFile(forReading: url)
        guard let target = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: sampleRate, channels: 1, interleaved: false),
              let inBuf = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: AVAudioFrameCount(file.length)),
              let conv = AVAudioConverter(from: file.processingFormat, to: target) else { return [] }
        try file.read(into: inBuf)
        let cap = AVAudioFrameCount(Double(inBuf.frameLength) * sampleRate / file.processingFormat.sampleRate) + 1024
        guard let out = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: cap) else { return [] }
        var fed = false
        var err: NSError?
        conv.convert(to: out, error: &err) { _, status in
            if fed { status.pointee = .endOfStream; return nil }
            fed = true; status.pointee = .haveData; return inBuf
        }
        if let err { throw err }
        return Array(UnsafeBufferPointer(start: out.floatChannelData![0], count: Int(out.frameLength)))
    }
}
