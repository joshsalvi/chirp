import AVFoundation
import Foundation

/// Plays one recording at a time through the TV (GET /watch/audio/{id}: AAC,
/// the first minute). Shared by Today, Recent and the recording screen.
@MainActor
final class Player: NSObject, ObservableObject, AVAudioPlayerDelegate {
    static let shared = Player()

    @Published private(set) var playingID: String?
    @Published private(set) var loadingID: String?
    @Published private(set) var title = ""
    @Published private(set) var progress: Double = 0
    @Published private(set) var duration: Double = 0
    @Published var error: String?
    /// The recording whose own screen is open: it shows its playback, so the
    /// floating now-playing pill stays hidden for it.
    @Published var onScreenID: String?

    private var player: AVAudioPlayer?
    private var ticker: Timer?
    private var cache: [String: Data] = [:]

    func toggle(id: String, title: String) async {
        if playingID == id { stop(); return }
        stop()
        error = nil
        loadingID = id
        defer { if loadingID == id { loadingID = nil } }
        do {
            var data = cache[id]
            if data == nil {
                data = try await API.data("api/v1/watch/audio/\(id)")
                if cache.count > 30 { cache.removeAll() }
                cache[id] = data
            }
            guard loadingID == id else { return }   // another tap since
            try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
            try AVAudioSession.sharedInstance().setActive(true)
            let p = try AVAudioPlayer(data: data!)
            p.delegate = self
            p.prepareToPlay()
            guard p.play() else { error = "Couldn't play this recording."; return }
            player = p
            playingID = id
            self.title = title
            duration = p.duration
            progress = 0
            ticker = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
                Task { @MainActor in
                    guard let self, let p = self.player, p.duration > 0 else { return }
                    self.progress = p.currentTime / p.duration
                }
            }
        } catch {
            self.error = API.describe(error)
        }
    }

    /// Plays from `seconds` in (the clip holds the first minute). Seeks if
    /// this recording is already playing; past the clip → from the start.
    func play(id: String, title: String, at seconds: Double) async {
        if playingID != id { await toggle(id: id, title: title) }
        guard playingID == id, let p = player else { return }
        seek(to: seconds < p.duration - 1 ? seconds : 0)
        if !p.isPlaying { p.play() }
    }

    /// Moves playback to `seconds` in the current recording.
    func seek(to seconds: Double) {
        guard let p = player else { return }
        p.currentTime = min(max(0, seconds), max(0, p.duration - 0.25))
        progress = p.duration > 0 ? p.currentTime / p.duration : 0
    }

    func stop() {
        player?.stop()
        player = nil
        ticker?.invalidate()
        ticker = nil
        playingID = nil
        progress = 0
        title = ""
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in self.stop() }
    }
}
