import Accelerate
import Foundation

/// A station answers each request with the last few seconds it heard, so
/// clips asked for every second overlap. This finds where a new clip picks
/// up from the sound already kept (by matching the last quarter second) and
/// returns only the new part: playback runs on without repeats, and the
/// saved session is as long as the listening.
struct StationStitcher {
    static let sampleRate = 48_000
    /// Sound matched against each new clip.
    static let matchSamples = 12_000          // 0.25 s
    /// How much already-kept sound to remember.
    static let keepSamples = 5 * 48_000
    private static let decimate = 8

    private(set) var tail: [Float] = []

    mutating func reset() { tail = [] }

    /// The part of `clip` not heard yet. `expected` is how many samples the
    /// station should have heard since the last request, used when the
    /// sound is too quiet or too regular to match.
    mutating func newPart(of clip: [Float], expected: Int) -> [Float] {
        let new: [Float]
        if tail.count < Self.matchSamples || clip.count <= Self.matchSamples {
            new = clip
        } else if let start = matchEnd(in: clip) {
            new = Array(clip[start...])
        } else {
            new = Array(clip.suffix(max(0, min(clip.count, expected))))
        }
        tail = Array((tail + new).suffix(Self.keepSamples))
        return new
    }

    /// Index in `clip` just after the kept sound ends, or nil without a confident match.
    private func matchEnd(in clip: [Float]) -> Int? {
        let m = Self.matchSamples, d = Self.decimate
        let template = Array(tail.suffix(m))
        let tEnergy = template.reduce(0) { $0 + $1 * $1 }
        guard tEnergy / Float(m) > 1e-9 else { return nil }   // digital silence: nothing to match

        // Coarse search on 8x-averaged copies.
        let td = Self.shrink(template, d), cd = Self.shrink(clip, d)
        guard cd.count > td.count else { return nil }
        let n = cd.count - td.count + 1
        var dots = [Float](repeating: 0, count: n)
        cd.withUnsafeBufferPointer { c in td.withUnsafeBufferPointer { t in
            vDSP_conv(c.baseAddress!, 1, t.baseAddress!, 1, &dots, 1, vDSP_Length(n), vDSP_Length(td.count))
        } }
        let tdNorm = td.reduce(0) { $0 + $1 * $1 }.squareRoot()
        var cum = [Float](repeating: 0, count: cd.count + 1)
        for i in 0..<cd.count { cum[i + 1] = cum[i] + cd[i] * cd[i] }
        var bestCoarse = -1, bestScore: Float = -1
        for o in 0..<n {
            let e = (cum[o + td.count] - cum[o]).squareRoot() * tdNorm
            guard e > 0 else { continue }
            let s = dots[o] / e
            if s > bestScore { bestScore = s; bestCoarse = o }
        }
        guard bestCoarse >= 0, bestScore > 0.5 else { return nil }

        // Refine at full rate around the coarse match.
        let tNorm = tEnergy.squareRoot()
        var best = -1, score: Float = -1
        let lo = max(0, bestCoarse * d - 2 * d), hi = min(clip.count - m, bestCoarse * d + 2 * d)
        guard lo <= hi else { return nil }
        clip.withUnsafeBufferPointer { c in template.withUnsafeBufferPointer { t in
            for o in lo...hi {
                var dot: Float = 0, e: Float = 0
                vDSP_dotpr(c.baseAddress! + o, 1, t.baseAddress!, 1, &dot, vDSP_Length(m))
                vDSP_svesq(c.baseAddress! + o, 1, &e, vDSP_Length(m))
                let s = dot / max(e.squareRoot() * tNorm, 1e-12)
                if s > score { score = s; best = o }
            }
        } }
        guard best >= 0, score > 0.8 else { return nil }
        return best + m
    }

    private static func shrink(_ x: [Float], _ d: Int) -> [Float] {
        let n = x.count / d
        var out = [Float](repeating: 0, count: n)
        for i in 0..<n {
            var s: Float = 0
            for j in 0..<d { s += x[i * d + j] }
            out[i] = s / Float(d)
        }
        return out
    }
}
