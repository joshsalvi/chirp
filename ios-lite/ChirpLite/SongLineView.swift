import SwiftUI

/// A recording's loudness as one row of bars, with the stretches where the
/// bird was identified highlighted (a soft band behind sun-gold bars). Tap to
/// jump there. No per-call marks: detections are 3–5 s windows, so a mark
/// placed from loudness can point at the wrong sound (the server sends
/// `calls` empty). Drawn for the dark now-playing bar.
struct SongLineView: View {
    let line: SongLine
    let progress: Double
    let seek: (Double) -> Void

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            Canvas { ctx, size in
                let d = line.duration, pos = progress * d
                guard d > 0 else { return }
                let spans = line.spans
                let inside = { (t: Double) in spans.contains { $0.contains(t) } }
                for s in spans {          // the bird's stretches: a band the full height
                    ctx.fill(Path(roundedRect: CGRect(x: size.width * s.lowerBound / d, y: 0,
                                                      width: size.width * (s.upperBound - s.lowerBound) / d, height: size.height),
                                  cornerRadius: 4), with: .color(Theme.sun.opacity(0.16)))
                }
                let n = line.bars.count
                if n > 0 {
                    let step = size.width / CGFloat(n), bw = max(1, step - 1.5), barH = size.height - 4
                    for (i, v) in line.bars.enumerated() {
                        let t = (Double(i) + 0.5) * d / Double(n)
                        let played = t <= pos
                        let color: Color = inside(t) ? Theme.sun.opacity(played ? 1 : 0.42) : Theme.bg.opacity(played ? 0.75 : 0.22)
                        let bh = max(2.5, CGFloat(v) * barH)
                        ctx.fill(Path(roundedRect: CGRect(x: CGFloat(i) * step, y: (size.height - bh) / 2, width: bw, height: bh), cornerRadius: 1),
                                 with: .color(color))
                    }
                    if progress > 0 {
                        ctx.fill(Path(CGRect(x: size.width * progress - 1, y: 0, width: 2, height: size.height)), with: .color(Theme.sun))
                    }
                } else {
                    let y = size.height / 2 - 3
                    ctx.fill(Path(roundedRect: CGRect(x: 0, y: y, width: size.width, height: 6), cornerRadius: 3), with: .color(Theme.bg.opacity(0.22)))
                    for s in spans {
                        ctx.fill(Path(CGRect(x: size.width * s.lowerBound / d, y: y,
                                             width: size.width * (s.upperBound - s.lowerBound) / d, height: 6)), with: .color(Theme.sun.opacity(0.42)))
                    }
                    ctx.fill(Path(roundedRect: CGRect(x: 0, y: y, width: size.width * progress, height: 6), cornerRadius: 3), with: .color(Theme.sun))
                }
            }
            .contentShape(Rectangle())
            .gesture(DragGesture(minimumDistance: 0).onEnded { g in
                seek(Self.target(x: g.location.x, width: w, line: line))
            })
        }
        .accessibilityElement()
        .accessibilityLabel(line.bird.map { bird in
            let at = line.spans.map { "\(Int($0.lowerBound)) to \(Int($0.upperBound))" }.joined(separator: ", ")
            return at.isEmpty ? bird : "\(bird), at \(at) seconds"
        } ?? "Recording")
        .accessibilityValue("\(Int(progress * line.duration)) of \(Int(line.duration)) seconds")
        .accessibilityAdjustableAction { dir in
            let now = progress * line.duration
            switch dir {
            case .increment: seek(min(line.duration, now + 2))
            case .decrement: seek(max(0, now - 2))
            @unknown default: break
            }
        }
    }

    /// Where a tap goes: that point of the clip.
    static func target(x: CGFloat, width: CGFloat, line: SongLine) -> Double {
        guard width > 0, line.duration > 0 else { return 0 }
        return Double(min(max(0, x / width), 1)) * line.duration
    }
}
