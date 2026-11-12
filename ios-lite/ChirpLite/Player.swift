import AVFoundation
import SwiftUI

/// One sound at a time, app-wide. Recordings come as small AAC files
/// (GET /watch/audio/{id}); reference songs as the site or host serves them.
@MainActor
final class Player: NSObject, ObservableObject, AVAudioPlayerDelegate {
    struct Item: Equatable {
        let key: String
        let path: String
        var start: Double = 0
        let title: String
        var subtitle: String = ""
        var photo: String?
    }

    @Published private(set) var now: Item?
    @Published private(set) var playing = false
    @Published private(set) var loading = false
    @Published private(set) var progress: Double = 0
    @Published private(set) var line: SongLine?          // recordings only
    @Published var error: String?

    private var player: AVAudioPlayer?
    private var timer: Timer?
    private var loadTask: Task<Void, Never>?

    func isActive(_ key: String) -> Bool { now?.key == key }

    func toggle(_ item: Item, account: Account) {
        if now?.key == item.key, let player {
            if player.isPlaying { player.pause(); playing = false; stopTimer() }
            else { player.play(); playing = true; startTimer() }
            return
        }
        stop()
        now = item
        loading = true
        error = nil
        if item.key.hasPrefix("rec-") {
            let id = String(item.key.dropFirst(4))
            let path = "api/v1/lite/recording/\(id)/songline" + API.query(["bird": item.title])
            Task {
                let l: SongLine? = try? await API.get(path, server: account.server, token: account.token)
                if now?.key == item.key { line = l }
            }
        }
        loadTask = Task {
            do {
                let data = try await API.data(item.path, server: account.server, token: account.token)
                guard !Task.isCancelled, now?.key == item.key else { return }
                try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
                try AVAudioSession.sharedInstance().setActive(true)
                let p = try AVAudioPlayer(data: data)
                p.delegate = self
                p.prepareToPlay()
                let start = max(0, item.start - 0.4)
                if start < p.duration - 1 { p.currentTime = start }
                player = p
                loading = false
                p.play()
                playing = true
                startTimer()
                Haptics.tap()
            } catch API.Failure.signedOut {
                loading = false; account.signOut()
            } catch {
                loading = false; playing = false
                self.error = "This sound couldn't be played."
            }
        }
    }

    func stop() {
        loadTask?.cancel()
        player?.stop(); player = nil
        stopTimer()
        now = nil; playing = false; loading = false; progress = 0; line = nil
    }

    /// Jump to a moment of the clip that's playing (song line).
    func seek(to seconds: Double) {
        guard let p = player, p.duration > 0 else { return }
        p.currentTime = min(max(0, seconds), p.duration - 0.05)
        progress = p.currentTime / p.duration
        if !p.isPlaying { p.play(); playing = true; startTimer() }
        Haptics.select()
    }

    private func startTimer() {
        stopTimer()
        timer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self, let p = self.player, p.duration > 0 else { return }
                self.progress = p.currentTime / p.duration
            }
        }
    }

    private func stopTimer() { timer?.invalidate(); timer = nil }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in
            self.playing = false; self.progress = 1; self.stopTimer()
        }
    }
}

/// The round play button, with a ring that fills as the sound plays.
struct PlayButton: View {
    let item: Player.Item?
    var size: CGFloat = 52
    var fill: Color = Theme.green
    var glyph: Color = .white
    var ring: Color = Theme.sun
    @EnvironmentObject var player: Player
    @EnvironmentObject var account: Account

    var body: some View {
        if let item {
            let active = player.isActive(item.key)
            Button { player.toggle(item, account: account) } label: {
                ZStack {
                    Circle().fill(fill)
                    if active && player.loading {
                        ProgressView().tint(glyph)
                    } else {
                        Image(systemName: active && player.playing ? "pause.fill" : "play.fill")
                            .font(.system(size: size * 0.36, weight: .bold))
                            .foregroundStyle(glyph)
                            .offset(x: active && player.playing ? 0 : size * 0.04)
                    }
                    if active {
                        Circle().trim(from: 0, to: player.progress)
                            .stroke(ring, style: StrokeStyle(lineWidth: 3.5, lineCap: .round))
                            .rotationEffect(.degrees(-90))
                            .padding(-5)
                            .animation(.linear(duration: 0.1), value: player.progress)
                    }
                }
                .frame(width: size, height: size)
                .shadow(color: fill.opacity(0.35), radius: 8, y: 4)
            }
            .buttonStyle(Pressable())
            .accessibilityLabel(active && player.playing ? "Pause \(item.title)" : "Play \(item.title)")
        }
    }
}

struct Pressable: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.93 : 1)
            .animation(.spring(response: 0.25, dampingFraction: 0.7), value: configuration.isPressed)
    }
}

/// "Now playing" bar above the tab bar.
struct NowPlayingBar: View {
    @EnvironmentObject var player: Player
    var body: some View {
        if let now = player.now {
            HStack(spacing: 12) {
                Photo(path: now.photo, name: now.title)
                    .frame(width: 44, height: 44)
                    .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
                VStack(alignment: .leading, spacing: 1) {
                    Text(now.title).font(.lite(16, .heavy)).lineLimit(1)
                    if let line = player.line, line.duration > 0, player.error == nil {
                        SongLineView(line: line, progress: player.progress) { player.seek(to: $0) }
                            .frame(height: 30)
                    } else {
                        Text(player.error ?? (now.subtitle.isEmpty ? "Playing" : now.subtitle))
                            .font(.lite(13, .semibold)).opacity(0.7).lineLimit(1)
                    }
                }
                Spacer(minLength: 0)
                PlayButton(item: now, size: 40, ring: Theme.sun)
                Button { player.stop() } label: {
                    Image(systemName: "xmark").font(.system(size: 14, weight: .bold)).frame(width: 34, height: 34)
                }
                .accessibilityLabel("Stop")
            }
            .foregroundStyle(Theme.bg)
            .padding(8)
            .background(Theme.ink, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
            .shadow(color: .black.opacity(0.2), radius: 16, y: 8)
            .padding(.horizontal, 12)
            .padding(.bottom, 6)
            .transition(.move(edge: .bottom).combined(with: .opacity))
        }
    }
}
