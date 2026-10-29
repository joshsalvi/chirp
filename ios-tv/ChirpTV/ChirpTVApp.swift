import SwiftUI

@main
struct ChirpTVApp: App {
    @StateObject private var account = Account.shared
    @StateObject private var player = Player.shared
    @StateObject private var live = LiveSession()

    var body: some Scene {
        WindowGroup {
            Group {
                if account.signedIn {
                    MainTabs()
                } else {
                    SignInView()
                }
            }
            .environmentObject(account)
            .environmentObject(player)
            .environmentObject(live)
            .preferredColorScheme(.dark)
            .tint(Theme.amber)
        }
    }
}

struct MainTabs: View {
    @EnvironmentObject var player: Player
    @State private var tab = MainTabs.initialTab

    static var initialTab: Int {
        #if DEBUG
        switch Screenshots.scene {
        case "recent", "recording": return 1
        case "live", "listen": return 2
        case "journal": return 3
        case "account": return 4
        default: return 0
        }
        #else
        return 0
        #endif
    }

    var body: some View {
        TabView(selection: $tab) {
            TodayView().tabItem { Text("Today") }.tag(0)
            RecentView().tabItem { Text("Recent") }.tag(1)
            LiveView().tabItem { Text("Live") }.tag(2)
            JournalView().tabItem { Text("Journal") }.tag(3)
            AccountView().tabItem { Text("Account") }.tag(4)
        }
        .background(Theme.bg)
        .overlay(alignment: .bottomTrailing) {
            if let id = player.playingID, id != player.onScreenID {
                HStack(spacing: 16) {
                    Image(systemName: "speaker.wave.2.fill")
                    Text(player.title).font(.headline)
                    ProgressView(value: player.progress).frame(width: 180)
                }
                .padding(.horizontal, 28).padding(.vertical, 18)
                .background(.ultraThinMaterial, in: Capsule())
                .padding(50)
                .accessibilityElement(children: .combine)
            }
        }
    }
}
