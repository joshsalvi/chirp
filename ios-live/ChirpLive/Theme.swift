import SwiftUI

/// Chirp's dark forest palette, as in the Chirp apps.
enum Theme {
    static let bg = Color(red: 0.039, green: 0.086, blue: 0.047)       // #0a160c
    static let card = Color(red: 0.075, green: 0.149, blue: 0.102)     // #13261a
    static let line = Color(red: 0.961, green: 0.937, blue: 0.902).opacity(0.1)
    static let ink = Color(red: 0.961, green: 0.937, blue: 0.902)      // #f5efe6
    static let body = Color(red: 0.847, green: 0.820, blue: 0.773)     // #d8d1c5
    static let muted = Color(red: 0.62, green: 0.69, blue: 0.635)      // #9fb0a2
    static let amber = Color(red: 0.984, green: 0.749, blue: 0.141)    // #fbbf24
    static let orange = Color(red: 0.984, green: 0.573, blue: 0.235)   // #fb923c
    static let red = Color(red: 0.937, green: 0.267, blue: 0.267)      // #ef4444
    static let leaf = Color(red: 0.525, green: 0.937, blue: 0.675)     // #86efac

    static func percent(_ p: Double) -> String { "\(Int((p * 100).rounded()))%" }

    /// 192 → "03:12"
    static func clock(_ seconds: TimeInterval) -> String {
        let s = max(0, Int(seconds))
        return String(format: "%02d:%02d", s / 60, s % 60)
    }
}

/// The Chirp bird with sound rings: the Chirp Live mark.
struct LiveMark: View {
    var height: CGFloat = 32
    var ink: Color = Theme.ink
    var rings: [Color] = [Color(red: 0.992, green: 0.729, blue: 0.455), Theme.orange,
                          Color(red: 0.918, green: 0.345, blue: 0.047)]

    var body: some View {
        Canvas { ctx, size in
            // View box: x 6...120, y 6...76.
            let s = size.height / 70
            ctx.scaleBy(x: s, y: s)
            ctx.translateBy(x: -6, y: -6)
            let line = StrokeStyle(lineWidth: 5.6, lineCap: .round, lineJoin: .round)
            var bird = ctx
            bird.translateBy(x: 46, y: 56); bird.rotate(by: .degrees(-8)); bird.translateBy(x: -46, y: -56)
            bird.stroke(Self.birdPath, with: .color(ink), style: line)
            bird.fill(Path(ellipseIn: CGRect(x: 56.9, y: 37.9, width: 6.3, height: 6.3)), with: .color(ink))
            for (i, r) in [11.0, 21.0, 31.0].enumerated() {
                var p = Path()
                p.addArc(center: CGPoint(x: 81.74, y: 37.53), radius: r,   // centered on the beak tip
                         startAngle: .degrees(-52), endAngle: .degrees(52), clockwise: false)
                ctx.stroke(p, with: .color(rings[i]), style: line)
            }
        }
        .frame(width: height * 114 / 70, height: height)
        .accessibilityHidden(true)
    }

    static let birdPath: Path = {
        var p = Path()
        p.move(to: CGPoint(x: 13, y: 49)); p.addLine(to: CGPoint(x: 26.5, y: 62))
        p.move(to: CGPoint(x: 71, y: 49))
        p.addCurve(to: CGPoint(x: 42, y: 71), control1: CGPoint(x: 69, y: 62), control2: CGPoint(x: 56, y: 71))
        p.addCurve(to: CGPoint(x: 26.5, y: 62), control1: CGPoint(x: 34, y: 71), control2: CGPoint(x: 28.5, y: 67))
        p.addCurve(to: CGPoint(x: 55, y: 32), control1: CGPoint(x: 28, y: 45), control2: CGPoint(x: 40, y: 32))
        p.addCurve(to: CGPoint(x: 71, y: 42), control1: CGPoint(x: 63, y: 32), control2: CGPoint(x: 69, y: 36))
        p.move(to: CGPoint(x: 71, y: 42)); p.addLine(to: CGPoint(x: 80.5, y: 42.2)); p.addLine(to: CGPoint(x: 71, y: 49))
        p.move(to: CGPoint(x: 34, y: 59.5))
        p.addCurve(to: CGPoint(x: 50.5, y: 51), control1: CGPoint(x: 40.5, y: 59.5), control2: CGPoint(x: 46.5, y: 56.3))
        return p
    }()
}

/// Big pill button in Chirp amber, or outlined.
struct PillButtonStyle: ButtonStyle {
    var filled = true
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 17, weight: filled ? .semibold : .medium))
            .frame(maxWidth: .infinity, minHeight: 54)
            .foregroundStyle(filled ? Color(red: 0.1, green: 0.08, blue: 0.02) : Theme.ink)
            .background(filled ? Theme.amber : .clear, in: Capsule())
            .overlay(Capsule().stroke(filled ? .clear : Theme.ink.opacity(0.18)))
            .opacity(configuration.isPressed ? 0.75 : 1)
    }
}
