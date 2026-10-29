import AVFoundation
import SwiftUI

@main
struct ChirpLiveApp: App {
    @StateObject private var listener = Listener()
    @StateObject private var store = SessionStore.shared
    @StateObject private var player = ClipPlayer()
    @StateObject private var account = Account.shared

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(listener)
                .environmentObject(store)
                .environmentObject(player)
                .environmentObject(account)
                .preferredColorScheme(.dark)
                .tint(Theme.amber)
        }
    }
}

struct RootView: View {
    @AppStorage("welcomed") private var welcomed = false
    @EnvironmentObject var listener: Listener
    @EnvironmentObject var store: SessionStore
    @Environment(\.scenePhase) private var phase
    @State private var finished: Session?
    @State private var tab = 0

    var body: some View {
        Group {
            if !welcomed {
                WelcomeView { welcomed = true; listener.start() }
            } else {
                TabView(selection: $tab) {
                    NavigationStack { ListenView(finished: $finished) }
                        .tabItem { Label("Listen", systemImage: "waveform") }.tag(0)
                    NavigationStack { SessionsView() }
                        .tabItem { Label("Sessions", systemImage: "list.bullet") }.tag(1)
                    NavigationStack { SettingsView() }
                        .tabItem { Label("Settings", systemImage: "gearshape") }.tag(2)
                }
                #if DEBUG
                .task {
                    let shot = Screenshots.apply(listener: listener)
                    tab = shot.tab
                    if let s = shot.summary { finished = s }
                }
                #endif
                .sheet(item: $finished) { s in
                    NavigationStack {
                        SummaryView(session: s)
                            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { finished = nil } } }
                    }
                    .preferredColorScheme(.dark)
                }
            }
        }
        .background(Theme.bg.ignoresSafeArea())
        .task {
            store.retryPending()
            await BirdPack.shared.updateIfNeeded()
        }
        .onChange(of: phase) { _, p in
            guard p == .active else { return }
            // Sessions that didn't reach the site, and pictures to refresh.
            store.retryPending()
            Task { await BirdPack.shared.updateIfNeeded() }
        }
    }
}

/// Plays a session's saved clips, one at a time.
@MainActor
final class ClipPlayer: NSObject, ObservableObject, AVAudioPlayerDelegate {
    @Published private(set) var playing: URL?
    @Published private(set) var problem: String?
    private var player: AVAudioPlayer?
    /// Set by Listener while it listens (its audio session already plays
    /// sound): play alongside it without changing or ending that session.
    static var listenerActive = false

    func toggle(_ url: URL) {
        if playing == url { stop(); return }
        stop()
        problem = nil
        let session = AVAudioSession.sharedInstance()
        do {
            if !Self.listenerActive {
                try session.setCategory(.playback, mode: .default)
                try session.setActive(true)
            }
            let p = try AVAudioPlayer(contentsOf: url)
            p.delegate = self
            p.volume = 1
            p.prepareToPlay()
            guard p.play() else { throw NSError(domain: "ChirpLive", code: 2) }
            player = p
            playing = url
        } catch {
            problem = "Couldn't play that sound."
            DiagLog.note("play \(url.lastPathComponent): \(error.localizedDescription)")
        }
    }

    func stop() {
        player?.stop(); player = nil; playing = nil
        if !Self.listenerActive { try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation) }
    }

    nonisolated func audioPlayerDidFinishPlaying(_ p: AVAudioPlayer, successfully: Bool) {
        Task { @MainActor in self.stop() }
    }
}

