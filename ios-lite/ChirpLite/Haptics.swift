import UIKit

/// Haptic taps, unless they're turned off (Account → Haptics).
enum Haptics {
    static let offKey = "hapticsOff"
    static var on: Bool { !UserDefaults.standard.bool(forKey: offKey) }
    static func tap() { if on { UIImpactFeedbackGenerator(style: .light).impactOccurred() } }
    static func select() { if on { UISelectionFeedbackGenerator().selectionChanged() } }
}
