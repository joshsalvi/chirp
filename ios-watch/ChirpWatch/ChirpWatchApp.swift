import SwiftUI

/// Chirp for Apple Watch: Live Detect from the wrist. The iPhone app signs
/// it in; clips go straight to the Chirp server over the watch's own
/// connection (Wi-Fi, cellular or through the iPhone).
@main
struct ChirpWatchApp: App {
    @StateObject private var account = Account.shared
    @StateObject private var live = LiveSession()
    @StateObject private var recent = RecentRecordings()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(account)
                .environmentObject(live)
                .environmentObject(recent)
        }
    }
}
