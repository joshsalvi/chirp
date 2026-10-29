import XCTest
@testable import ChirpLive

final class StationStitcherTests: XCTestCase {
    /// 30 s of noise with chirps; a station hands back its last 4 s at each request.
    private func sound(seconds: Int) -> [Float] {
        var g = SystemRandomNumberGenerator()
        return (0..<(seconds * 48_000)).map { i in
            let t = Double(i) / 48_000
            let chirp = (Int(t * 2) % 3 == 0) ? Float(0.2 * sin(2 * .pi * 3_000 * t)) : 0
            return Float.random(in: -0.02...0.02, using: &g) + chirp
        }
    }

    func testRebuildsTheSoundWithoutRepeats() {
        let s = sound(seconds: 30)
        var st = StationStitcher()
        var out: [Float] = []
        var end = 4 * 48_000, last = end
        // Requests roughly a second apart, with network jitter.
        let steps = [48_000, 52_000, 41_000, 60_000, 47_500, 49_000, 70_000, 45_000, 48_000, 51_000, 38_000, 55_000]
        out += st.newPart(of: Array(s[(end - 192_000)..<end]), expected: .max)
        for step in steps {
            end += step
            out += st.newPart(of: Array(s[(end - 192_000)..<end]), expected: end - last)
            last = end
        }
        XCTAssertEqual(out.count, end, "kept exactly what the station heard")
        XCTAssertEqual(Array(out.suffix(1000)), Array(s[(end - 1000)..<end]))
        XCTAssertEqual(Array(out[100_000..<101_000]), Array(s[100_000..<101_000]))
    }

    func testSameClipTwiceAddsNothing() {
        let s = sound(seconds: 8)
        var st = StationStitcher()
        let clip = Array(s[0..<192_000])
        _ = st.newPart(of: clip, expected: .max)
        XCTAssertEqual(st.newPart(of: clip, expected: 0).count, 0)
    }

    func testSilenceFallsBackToElapsedTime() {
        var st = StationStitcher()
        let quiet = [Float](repeating: 0, count: 192_000)
        _ = st.newPart(of: quiet, expected: .max)
        XCTAssertEqual(st.newPart(of: quiet, expected: 48_000).count, 48_000)
    }
}
