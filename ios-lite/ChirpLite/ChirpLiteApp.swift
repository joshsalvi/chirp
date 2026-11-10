import SwiftUI

@main
struct ChirpLiteApp: App {
    @StateObject private var account = Account.shared
    @StateObject private var player = Player()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(account)
                .environmentObject(player)
                .tint(Theme.green)
        }
    }
}

struct RootView: View {
    @EnvironmentObject var account: Account
    @EnvironmentObject var player: Player
    @Environment(\.scenePhase) private var phase

    var body: some View {
        Group {
            if account.signedIn {
                MainTabs()
                    .transition(.opacity)
            } else {
                SignInView()
                    .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.3), value: account.signedIn)
        #if DEBUG
        .task { Demo.start(account) }
        #endif
        .onChange(of: phase) { _, p in
            if p == .active { Task { await account.renewIfNeeded() } }
        }
        .onChange(of: account.signedIn) { _, on in if !on { player.stop() } }
    }
}

struct MainTabs: View {
    @State private var tab = Demo.startTab
    @State private var showAccount = false
    @State private var paths = Array(repeating: NavigationPath(), count: 4)
    @EnvironmentObject var player: Player

    var body: some View {
        TabView(selection: $tab) {
            stack(0) { TodayView(showAccount: $showAccount) }
                .tabItem { Label("Today", systemImage: "sun.max.fill") }.tag(0)
            stack(1) { BirdsView(showAccount: $showAccount) }
                .tabItem { Label("Birds", systemImage: "square.grid.2x2.fill") }.tag(1)
            stack(2) { ListenView(showAccount: $showAccount) }
                .tabItem { Label("Listen", systemImage: "waveform") }.tag(2)
            stack(3) { GuideView(showAccount: $showAccount) }
                .tabItem { Label("Guide", systemImage: "safari.fill") }.tag(3)
        }
        .sheet(isPresented: $showAccount) { AccountSheet() }
        .task { if let id = Demo.startBird { paths[0].append(BirdRoute(id: id)) } }
        .animation(.spring(response: 0.35, dampingFraction: 0.85), value: player.now?.key)
    }

    private func stack<V: View>(_ i: Int, @ViewBuilder _ root: () -> V) -> some View {
        NavigationStack(path: $paths[i]) {
            root()
                .toolbar(.hidden, for: .navigationBar)
                .navigationDestination(for: BirdRoute.self) { BirdView(id: $0.id) }
                .navigationDestination(for: ListenRoute.self) { ListenView(showAccount: .constant(false), bird: $0.bird) }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) { NowPlayingBar() }
    }
}
