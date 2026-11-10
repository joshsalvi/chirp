import SwiftUI

/// Meadow palette, matching the web app (frontend/src/lite/lite.css).
enum Theme {
    static let green = Color(hex: 0x22B573)
    static let greenDeep = Color(light: 0x138A55, dark: 0x6FE0A6)
    static let greenSoft = Color(light: 0xDDF5E8, dark: 0x173A27)
    static let sun = Color(hex: 0xFFC53D)
    static let sunSoft = Color(light: 0xFFF3CF, dark: 0x3A3115)
    static let sunInk = Color(light: 0x8A5A00, dark: 0xFFD976)
    static let coral = Color(hex: 0xFF7A59)
    static let coralSoft = Color(light: 0xFFE6DE, dark: 0x3D2119)
    static let coralInk = Color(light: 0xC2401F, dark: 0xFFA48C)
    static let sky = Color(hex: 0x3AA0F2)
    static let skySoft = Color(light: 0xDDEFFD, dark: 0x142E44)
    static let skyInk = Color(light: 0x1C6FB4, dark: 0x8CC8F8)
    static let bg = Color(light: 0xF4F8F2, dark: 0x0E1A13)
    static let card = Color(light: 0xFFFFFF, dark: 0x17271D)
    static let ink = Color(light: 0x10261A, dark: 0xEEF6F0)
    static let muted = Color(light: 0x5B6F62, dark: 0x9FB4A6)
    static let line = Color(light: 0xE2EBE3, dark: 0x24382B)

    static func chance(_ likely: String) -> (bg: Color, ink: Color) {
        switch likely {
        case "common": return (greenSoft, greenDeep)
        case "uncommon": return (sunSoft, sunInk)
        default: return (coralSoft, coralInk)
        }
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(red: Double((hex >> 16) & 0xFF) / 255, green: Double((hex >> 8) & 0xFF) / 255, blue: Double(hex & 0xFF) / 255)
    }
    init(light: UInt32, dark: UInt32) {
        self.init(UIColor { $0.userInterfaceStyle == .dark ? UIColor(Color(hex: dark)) : UIColor(Color(hex: light)) })
    }
}

extension Font {
    /// Rounded system type, the app's voice.
    static func lite(_ size: CGFloat, _ weight: Font.Weight = .bold) -> Font {
        .system(size: size, weight: weight, design: .rounded)
    }
}

struct CardStyle: ViewModifier {
    var radius: CGFloat = 22
    func body(content: Content) -> some View {
        content
            .background(Theme.card, in: RoundedRectangle(cornerRadius: radius, style: .continuous))
            .shadow(color: .black.opacity(0.07), radius: 12, y: 6)
    }
}

extension View {
    func card(radius: CGFloat = 22) -> some View { modifier(CardStyle(radius: radius)) }
}

/// The Chirp Lite bird (icon geometry, 100-unit grid), as one shape.
struct BirdShape: Shape {
    func path(in r: CGRect) -> Path {
        let s = min(r.width, r.height) / 100
        let o = CGPoint(x: r.midX - 50 * s, y: r.midY - 50 * s)
        func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: o.x + x * s, y: o.y + y * s) }
        var path = Path()
        path.move(to: p(27, 58)); path.addLine(to: p(8, 44)); path.addQuadCurve(to: p(24, 69), control: p(10, 61)); path.closeSubpath()
        path.addEllipse(in: CGRect(x: o.x + 20 * s, y: o.y + 39 * s, width: 50 * s, height: 42 * s))
        path.addEllipse(in: CGRect(x: o.x + 44.5 * s, y: o.y + 29.5 * s, width: 31 * s, height: 31 * s))
        path.move(to: p(74.5, 41.5)); path.addLine(to: p(86, 45)); path.addLine(to: p(74.5, 49)); path.closeSubpath()
        return path
    }
}

/// The app icon's bird, in color, for the sign-in screen and empty states.
struct BirdMark: View {
    var size: CGFloat = 80
    var tile = true
    var body: some View {
        Canvas { ctx, sz in
            let s = sz.width / 100
            func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: x * s, y: y * s) }
            if tile {
                ctx.fill(Path(roundedRect: CGRect(origin: .zero, size: sz), cornerRadius: 23 * s, style: .continuous),
                         with: .linearGradient(Gradient(colors: [Color(hex: 0x34CC86), Color(hex: 0x139C5D)]),
                                               startPoint: .zero, endPoint: CGPoint(x: sz.width * 0.35, y: sz.height)))
            }
            ctx.fill(BirdShape().path(in: CGRect(origin: .zero, size: sz)), with: .color(.white))
            var wing = Path(); wing.move(to: p(33, 58)); wing.addQuadCurve(to: p(59, 61), control: p(47, 50))
            wing.addQuadCurve(to: p(33, 58), control: p(46, 70))
            ctx.fill(wing, with: .color(Color(hex: 0xD4F2E2)))
            var beak = Path(); beak.move(to: p(74.5, 41.5)); beak.addLine(to: p(86, 45)); beak.addLine(to: p(74.5, 49)); beak.closeSubpath()
            ctx.fill(beak, with: .color(Color(hex: 0xFF8A3D)))
            ctx.fill(Path(ellipseIn: CGRect(x: 61.7 * s, y: 38.7 * s, width: 5.6 * s, height: 5.6 * s)), with: .color(Color(hex: 0x0C3A24)))
            for (x, y, h) in [(80.0, 17.0, 11.0), (86, 13, 19), (92, 18, 9)] {
                ctx.fill(Path(roundedRect: CGRect(x: x * s, y: y * s, width: 4.2 * s, height: h * s), cornerRadius: 2.1 * s),
                         with: .color(Color(hex: 0xFFE45C)))
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}
