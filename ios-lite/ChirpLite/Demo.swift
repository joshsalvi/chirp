import Foundation

/// Debug-only hooks for screenshots and UI checks:
///   LITE_TOKEN=… LITE_SERVER=https://www.ourchirp.com LITE_USER=josh  (environment)
///   -LiteTab 0…3  (launch argument) opens that tab.
enum Demo {
    static var startTab: Int {
        #if DEBUG
        let a = ProcessInfo.processInfo.arguments
        if let i = a.firstIndex(of: "-LiteTab"), i + 1 < a.count, let n = Int(a[i + 1]) { return n }
        #endif
        return 0
    }

    /// -LiteBird <profile id> opens that bird on Today.
    static var startBird: String? {
        #if DEBUG
        let a = ProcessInfo.processInfo.arguments
        if let i = a.firstIndex(of: "-LiteBird"), i + 1 < a.count { return a[i + 1] }
        #endif
        return nil
    }

    #if DEBUG
    @MainActor static func start(_ account: Account) {
        let env = ProcessInfo.processInfo.environment
        guard let t = env["LITE_TOKEN"], !t.isEmpty else { return }
        account.useToken(t, server: URL(string: env["LITE_SERVER"] ?? "https://www.ourchirp.com")!, username: env["LITE_USER"] ?? "josh")
    }
    #endif
}
