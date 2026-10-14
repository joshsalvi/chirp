import SwiftUI

/// The Chirp Songbird mark (frontend SongbirdMark.jsx), drawn natively.
/// `animate` plays the Live Detect meter: the three bars move like a level
/// meter and the bird blinks now and then (index.css .cb-meter).
struct ChirpMark: View {
    var height: CGFloat = 24
    var animate = false

    private static let viewBox = CGRect(x: 6, y: 12, width: 106, height: 72)
    private static let ink = Color(red: 0.961, green: 0.937, blue: 0.902)          // #f5efe6
    private static let warm = [Color(red: 0.992, green: 0.729, blue: 0.455),       // #fdba74
                               Color(red: 0.984, green: 0.573, blue: 0.235),       // #fb923c
                               Color(red: 0.918, green: 0.345, blue: 0.047)]       // #ea580c
    private static let bars: [(x: CGFloat, cy: CGFloat, h: CGFloat)] =
        [(88.74, 34.73, 9), (95.24, 33.33, 18), (101.74, 31.93, 11)]
    // Bar periods and start offsets, as in index.css.
    private static let meter: [(period: Double, offset: Double)] = [(1.1, 0), (0.8, 0.3), (1.35, 0.6)]

    var body: some View {
        let width = height * Self.viewBox.width / Self.viewBox.height
        Group {
            if animate {
                TimelineView(.animation) { tl in
                    canvas(t: tl.date.timeIntervalSinceReferenceDate)
                }
            } else {
                canvas(t: nil)
            }
        }
        .frame(width: width, height: height)
        .accessibilityLabel("Chirp")
    }

    private func canvas(t: Double?) -> some View {
        Canvas { ctx, size in
            let s = size.width / Self.viewBox.width
            ctx.scaleBy(x: s, y: s)
            ctx.translateBy(x: -Self.viewBox.minX, y: -Self.viewBox.minY)
            let w = Self.weight(forWidth: size.width)
            let line = StrokeStyle(lineWidth: w, lineCap: .round, lineJoin: .round)

            // Bird, tilted -8° about (46, 56).
            var bird = ctx
            bird.translateBy(x: 46, y: 56)
            bird.rotate(by: .degrees(-8))
            bird.translateBy(x: -46, y: -56)
            bird.stroke(Self.birdPath, with: .color(Self.ink), style: line)

            let r = max(w * 0.56, 2.7)
            let blink = t.map { Self.blink(at: $0) } ?? 1
            var eye = bird
            eye.translateBy(x: 60, y: 41)
            eye.scaleBy(x: 1, y: blink)
            eye.fill(Path(ellipseIn: CGRect(x: -r, y: -r, width: 2 * r, height: 2 * r)), with: .color(Self.ink))
            let c = max(r * 0.34, 0.9)
            eye.fill(Path(ellipseIn: CGRect(x: r * 0.36 - c, y: -r * 0.36 - c, width: 2 * c, height: 2 * c)), with: .color(.black))

            let bw = max(w * 0.9, 3.2)
            for (i, b) in Self.bars.enumerated() {
                let k = t.map { Self.level(at: $0, Self.meter[i].period, Self.meter[i].offset) } ?? 1
                let half = b.h / 2 * k
                var p = Path()
                p.move(to: CGPoint(x: b.x, y: b.cy - half))
                p.addLine(to: CGPoint(x: b.x, y: b.cy + half))
                ctx.stroke(p, with: .color(Self.warm[i]), style: StrokeStyle(lineWidth: bw, lineCap: .round))
            }
        }
    }

    // M13 49 L26.5 62 · body · beak · wing (SongbirdMark.jsx PATHS)
    private static let birdPath: Path = {
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

    /// Line weight in view-box units for the rendered width (as on the web).
    private static func weight(forWidth px: CGFloat) -> CGFloat {
        let table: [(CGFloat, CGFloat)] = [(24, 6.5), (36, 6.0), (56, 5.2), (96, 4.4), (180, 3.8), (420, 3.4)]
        if px <= table[0].0 { return table[0].1 }
        for i in 1..<table.count where px <= table[i].0 {
            let (x1, y1) = table[i - 1], (x2, y2) = table[i]
            return y1 + (y2 - y1) * (px - x1) / (x2 - x1)
        }
        return table.last!.1
    }

    /// cb-meter: 0% .35 · 45% .9 · 70% .6 · 100% 1.1, ease-in-out, alternating.
    private static func level(at t: Double, _ period: Double, _ offset: Double) -> CGFloat {
        let u = (t + offset) / period
        var f = u - floor(u)
        if Int(floor(u)) % 2 != 0 { f = 1 - f }
        let keys: [(Double, Double)] = [(0, 0.35), (0.45, 0.9), (0.7, 0.6), (1, 1.1)]
        for i in 1..<keys.count where f <= keys[i].0 {
            let (a, va) = keys[i - 1], (b, vb) = keys[i]
            let x = (f - a) / (b - a)
            let e = x * x * (3 - 2 * x)
            return CGFloat(va + (vb - va) * e)
        }
        return 1.1
    }

    /// cb-blink: shut briefly at 80% of a 4.6 s loop.
    private static func blink(at t: Double) -> CGFloat {
        let f = (t / 4.6).truncatingRemainder(dividingBy: 1)
        switch f {
        case 0.78..<0.80: return CGFloat(1 - 0.9 * (f - 0.78) / 0.02)
        case 0.80..<0.82: return CGFloat(0.1 + 0.9 * (f - 0.80) / 0.02)
        default: return 1
        }
    }
}
