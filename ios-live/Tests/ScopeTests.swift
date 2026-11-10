import XCTest
@testable import ChirpLive

/// The sound display's analysis: a pure tone lands in the right rows and
/// bars, and the window setting sets how fast columns arrive.
final class ScopeTests: XCTestCase {
    private func tone(_ hz: Float, seconds: Double, amplitude: Float = 0.3) -> [Float] {
        let rate = Float(BirdNET.sampleRate)
        return (0..<Int(seconds * BirdNET.sampleRate)).map { amplitude * sin(2 * .pi * hz * Float($0) / rate) }
    }

    func testToneLandsInItsSpectrogramRowAndSpectrumBar() {
        let feed = ScopeFeed()
        feed.setWindow(4)
        feed.append(tone(3000, seconds: 1))
        let s = feed.snapshot()
        let col = s.spectrogram.last!
        let loudest = col.indices.max { col[$0] < col[$1] }!
        XCTAssertEqual(loudest, Int(3000 / ScopeFeed.topHz * Float(ScopeFeed.bands)), accuracy: 1)   // row 24 of 96
        let bar = s.spectrum.indices.max { s.spectrum[$0] < s.spectrum[$1] }!
        let expected = Int(log(3000 / 300) / log(ScopeFeed.topHz / 300) * Float(ScopeFeed.spectrumBars))
        XCTAssertEqual(bar, expected, accuracy: 1)
        XCTAssertGreaterThan(s.levels.last!, 0.6)                 // 0.3 amplitude ≈ -13 dBFS
        XCTAssertGreaterThan(s.peaks.last!, 0.5)
    }

    func testWindowSetsColumnRate() {
        let feed = ScopeFeed()
        feed.setWindow(10)                                        // 240 columns over 10 s → 24 a second
        feed.append(tone(2000, seconds: 1))
        let lit = feed.snapshot().levels.filter { $0 > 0 }.count
        XCTAssertEqual(lit, 24, accuracy: 1)
        XCTAssertEqual(feed.snapshot().levels.count, ScopeFeed.columns)
    }

    func testSilenceStaysDark() {
        let feed = ScopeFeed()
        feed.setWindow(3)
        feed.append([Float](repeating: 0, count: 48_000))
        let s = feed.snapshot()
        XCTAssertEqual(s.levels.max() ?? 1, 0, accuracy: 0.01)
        XCTAssertEqual(s.spectrogram.last!.max() ?? 1, 0, accuracy: 0.01)
    }

    func testSpectrogramImageSize() {
        let image = Spectrogram.image(ScopeFeed.empty.spectrogram)
        XCTAssertEqual(image?.width, ScopeFeed.columns)
        XCTAssertEqual(image?.height, ScopeFeed.bands)
    }

    func testWaveformScalesQuietSoundUp() {
        // A typical yard: peaks around 0.5% of full scale.
        let quiet: [Float] = [0.002, 0.005, 0.004, 0.006, 0.003]
        let shown = Waveform.scaled(quiet)
        XCTAssertGreaterThan(shown.max() ?? 0, 0.3)          // visible, not a flat line
        XCTAssertLessThan(shown.max() ?? 1, 0.5)             // but kept below a loud call's height
        let loud: [Float] = [0.01, 0.4, 0.05]
        let l = Waveform.scaled(loud)
        XCTAssertEqual(l[1], 1 / pow(1.1, 0.6), accuracy: 0.001)   // the loudest peak nearly fills the card
        XCTAssertGreaterThan(l[0], 0.05)                       // a quiet call beside it still shows
        XCTAssertEqual(Waveform.scaled([0, 0, 0]), [0, 0, 0])   // silence stays flat
    }
}
