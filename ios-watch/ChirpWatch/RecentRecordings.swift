import AVFoundation
import Foundation

/// The site's five newest recordings (GET /api/v1/watch/recent) and their
/// audio (GET /api/v1/watch/audio/{id}: AAC, mono, at most the first minute),
/// played through the watch speaker or connected headphones.
@MainActor
final class RecentRecordings: NSObject, ObservableObject, AVAudioPlayerDelegate {
    struct Item: Decodable, Identifiable, Equatable {
        let id: String
        let time: Date
        let duration: Double
        let species: String
        let others: [String]
        let confidence: Double?
        let has_audio: Bool
    }

    enum Status: Equatable {
        case idle, loading, loaded
        case failed(String)
    }

    @Published private(set) var items: [Item] = []
    @Published private(set) var status: Status = .idle
    @Published private(set) var playingID: String?
    @Published private(set) var fetchingID: String?
    @Published private(set) var progress: Double = 0
    @Published var playError: String?

    private var player: AVAudioPlayer?
    private var ticker: Timer?
    private var audioCache: [String: Data] = [:]

    private static let session: URLSession = {
        let c = URLSessionConfiguration.default
        c.timeoutIntervalForRequest = 30
        return URLSession(configuration: c)
    }()

    override init() {
        super.init()
        #if DEBUG
        if let scene = Screenshots.scene {
            items = Screenshots.recent()
            status = .loaded
            if scene == "playing" { playingID = "s2"; progress = 0.42 }
        }
        #endif
    }

    func refresh() async {
        #if DEBUG
        if Screenshots.scene != nil { return }
        #endif
        guard let server = Account.shared.server else { return }
        if items.isEmpty { status = .loading }
        do {
            let data = try await get("api/v1/watch/recent", server: server)
            let dec = JSONDecoder()
            dec.dateDecodingStrategy = .custom { d in
                let s = try d.singleValueContainer().decode(String.self)
                if let t = Self.iso(s) { return t }
                throw DecodingError.dataCorrupted(.init(codingPath: d.codingPath, debugDescription: "time \(s)"))
            }
            items = try dec.decode([Item].self, from: data)
            status = .loaded
        } catch {
            status = .failed(Self.describe(error))
        }
    }

    /// Tap a row: play it, or stop it if it's the one playing.
    func toggle(_ item: Item) async {
        if playingID == item.id { stop(); return }
        stop()
        guard item.has_audio, let server = Account.shared.server else { return }
        playError = nil
        do {
            var data = audioCache[item.id]
            if data == nil {
                fetchingID = item.id
                defer { fetchingID = nil }
                data = try await get("api/v1/watch/audio/\(item.id)", server: server)
                audioCache[item.id] = data
            }
            let s = AVAudioSession.sharedInstance()
            try s.setCategory(.playback, mode: .default, options: [])
            try s.setActive(true)
            let p = try AVAudioPlayer(data: data!)
            p.delegate = self
            p.prepareToPlay()
            guard p.play() else { throw Failure.cantPlay }
            player = p
            playingID = item.id
            progress = 0
            ticker = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in
                Task { @MainActor in
                    guard let self, let p = self.player, p.duration > 0 else { return }
                    self.progress = p.currentTime / p.duration
                }
            }
        } catch {
            playError = Self.describe(error)
        }
    }

    func stop() {
        player?.stop()
        player = nil
        ticker?.invalidate()
        ticker = nil
        playingID = nil
        progress = 0
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in self.stop() }
    }

    // MARK: Requests

    enum Failure: Error {
        case signedOut, oldServer, cantPlay
        case server(Int, String?)
    }

    private func get(_ path: String, server: URL) async throws -> Data {
        var req = URLRequest(url: server.appendingPathComponent(path))
        req.setValue("ChirpWatch/1", forHTTPHeaderField: "User-Agent")
        if let t = Account.shared.token { req.setValue("Bearer \(t)", forHTTPHeaderField: "Authorization") }
        let (data, resp) = try await Self.session.data(for: req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 { Account.shared.tokenRejected(); throw Failure.signedOut }
        if code == 403 || (code == 404 && path == "api/v1/watch/recent") { throw Failure.oldServer }
        guard (200..<300).contains(code) else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
            throw Failure.server(code, detail)
        }
        return data
    }

    nonisolated private static func iso(_ s: String) -> Date? {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = f.date(from: s) { return d }
        f.formatOptions = [.withInternetDateTime]
        return f.date(from: s)
    }

    static func describe(_ error: Error) -> String {
        switch error {
        case Failure.signedOut: return "Signed out. Open Chirp on your iPhone."
        case Failure.oldServer: return "This Chirp server needs an update for recordings on the watch."
        case Failure.cantPlay: return "Couldn't play this recording."
        case Failure.server(let code, let detail): return detail ?? "The site answered \(code)."
        case is DecodingError: return "Couldn't read the site's answer."
        default: return Analyzer.describe(error)
        }
    }
}
