import XCTest
@testable import ChirpLive

/// BirdNET on iOS gives the same answers as the station's birdnetlib on the
/// same clip (bird15.wav: the first 15 s of the 60 s field recording used to
/// check the server; reference values from tflite in Python).
final class BirdNETTests: XCTestCase {
    func testScoresMatchStation() throws {
        let model = try BirdNET()
        XCTAssertEqual(model.species.count, 6522)
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "bird15", withExtension: "wav"))
        let audio = try WAV.read(url)
        XCTAssertEqual(audio.count, 720_000, accuracy: 10)
        let goldfinch = try XCTUnwrap(model.species.firstIndex { $0.common == "American Goldfinch" })
        let hermit = try XCTUnwrap(model.species.firstIndex { $0.common == "Hermit Thrush" })
        // (window start in s, species, expected score)
        let expected: [(Int, Int, Float)] = [(0, goldfinch, 0.405), (3, goldfinch, 0.197), (6, hermit, 0.200),
                                             (9, goldfinch, 0.673), (12, goldfinch, 0.275)]
        for (start, i, want) in expected {
            let a = start * 48_000
            let scores = try model.scores(Array(audio[a..<a + BirdNET.windowSamples]))
            XCTAssertEqual(scores[i], want, accuracy: 0.02, "\(model.species[i].common) at \(start) s")
        }
    }

    func testLocationList() throws {
        let model = try BirdNET()
        var c = DateComponents(); c.year = 2026; c.month = 10; c.day = 27
        let date = try XCTUnwrap(Calendar.current.date(from: c))
        XCTAssertEqual(BirdNET.week48(date), 40)   // ceil(300 / 365 × 48), as birdnetlib
        let likely = try model.likely(latitude: 42.28, longitude: -71.35, on: date)
        XCTAssertEqual(likely.count, 110, accuracy: 2)   // 110 in birdnetlib
        let names = Set(likely.map { model.species[$0].common })
        XCTAssertTrue(names.contains("Blue Jay"))
        XCTAssertFalse(names.contains("Mountain Chickadee"))   // western bird
    }
}
