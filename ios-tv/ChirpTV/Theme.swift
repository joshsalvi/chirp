import SwiftUI

/// Chirp's dark forest palette (frontend index.css).
enum Theme {
    static let bg = Color(red: 0.043, green: 0.075, blue: 0.051)       // #0b130d
    static let card = Color(red: 0.075, green: 0.129, blue: 0.090)     // #132117
    static let line = Color(red: 0.141, green: 0.216, blue: 0.165)     // #24372a
    static let ink = Color(red: 0.961, green: 0.937, blue: 0.902)      // #f5efe6
    static let muted = Color(red: 0.62, green: 0.69, blue: 0.635)      // #9fb0a2
    static let amber = Color(red: 0.949, green: 0.757, blue: 0.306)    // #f2c14e
    static let leaf = Color(red: 0.435, green: 0.827, blue: 0.588)     // #6fd396
    static let rose = Color(red: 0.945, green: 0.584, blue: 0.549)     // #f1958c

    static func confidence(_ c: Double?) -> String {
        guard let c else { return "" }
        return "\(Int((c * 100).rounded()))%"
    }

    /// 75.4 → "1:15"
    static func clock(_ seconds: Double) -> String {
        let s = max(0, Int(seconds.rounded(.down)))
        return String(format: "%d:%02d", s / 60, s % 60)
    }
}

/// A bird photo (or a placeholder), loaded with the TV token when it's on the
/// Chirp server.
struct BirdPhoto: View {
    let path: String?
    var size: CGFloat? = nil
    @EnvironmentObject var account: Account

    var body: some View {
        AsyncImage(url: account.mediaURL(path)) { phase in
            switch phase {
            case .success(let img): img.resizable().scaledToFill()
            default:
                ZStack {
                    Theme.card
                    ChirpMark(height: (size ?? 120) * 0.35).opacity(0.5)
                }
            }
        }
        .frame(width: size, height: size)
        .clipped()
    }
}
