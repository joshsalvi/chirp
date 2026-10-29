import Foundation

#if DEBUG
/// Simulator screenshots: launch with
///   -ChirpScreenshots today|recent|live|journal -ChirpServer URL -ChirpToken TOKEN -ChirpUser NAME
/// The screens then show that site's data.
enum Screenshots {
    static func value(_ key: String) -> String? {
        let a = ProcessInfo.processInfo.arguments
        guard let i = a.firstIndex(of: key), i + 1 < a.count else { return nil }
        return a[i + 1]
    }
    static var scene: String? { value("-ChirpScreenshots") }
}
#endif
