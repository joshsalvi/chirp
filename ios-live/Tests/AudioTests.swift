import AVFoundation
import XCTest
@testable import ChirpLive

/// Saved sound: clips and the whole session are AAC, loud enough to hear,
/// and play back.
final class AudioTests: XCTestCase {
    private func tone(_ seconds: Double, amplitude: Float) -> [Float] {
        (0..<Int(seconds * BirdNET.sampleRate)).map { amplitude * sin(2 * .pi * 3000 * Float($0) / Float(BirdNET.sampleRate)) }
    }
    private func tmp(_ name: String) -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("\(UUID().uuidString)-\(name)")
    }

    func testClipIsLevelledCompressedAndPlays() throws {
        let url = tmp("clip.m4a")
        XCTAssertTrue(SoundFile.writeClip(tone(3, amplitude: 0.01), to: url))
        let back = try WAV.read(url)
        XCTAssertEqual(Double(back.count), 144_000, accuracy: 4_800)
        let peak = back.map(abs).max() ?? 0
        XCTAssertGreaterThan(peak, 0.3)            // 0.01 raw → near the target
        XCTAssertLessThanOrEqual(peak, 1.0)
        let bytes = try XCTUnwrap(url.resourceValues(forKeys: [.fileSizeKey]).fileSize)
        XCTAssertLessThan(bytes, 100_000)          // a 16-bit WAV would be 288 kB
        let player = try AVAudioPlayer(contentsOf: url)
        XCTAssertEqual(player.duration, 3, accuracy: 0.2)
        XCTAssertTrue(player.prepareToPlay())
    }

    func testLoudSoundIsNotClipped() throws {
        let url = tmp("loud.m4a")
        XCTAssertTrue(SoundFile.writeClip(tone(3, amplitude: 0.95), to: url))
        let peak = try WAV.read(url).map(abs).max() ?? 0
        XCTAssertLessThanOrEqual(peak, 1.02)
        XCTAssertGreaterThan(peak, 0.8)
    }

    func testSessionLevelling() throws {
        // Recorded the way SessionRecorder does it: quiet, AAC.
        let raw = tmp("raw.m4a"), done = tmp("session.m4a")
        try {
            let file = try AVAudioFile(forWriting: raw, settings: AAC.settings(BirdNET.sampleRate),
                                       commonFormat: .pcmFormatFloat32, interleaved: false)
            let fmt = file.processingFormat
            for _ in 0..<5 {        // 25 s, in pieces like the microphone tap
                let s = tone(5, amplitude: 0.005)
                let buf = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: AVAudioFrameCount(s.count))!
                buf.frameLength = AVAudioFrameCount(s.count)
                s.withUnsafeBufferPointer { buf.floatChannelData![0].update(from: $0.baseAddress!, count: s.count) }
                try file.write(from: buf)
            }
        }()
        try SoundFile.level(raw, to: done)
        let back = try WAV.read(done)
        XCTAssertEqual(Double(back.count) / BirdNET.sampleRate, 25, accuracy: 0.5)
        XCTAssertGreaterThan(back.map(abs).max() ?? 0, 0.15)   // 40× cap: 0.005 → 0.2
        let player = try AVAudioPlayer(contentsOf: done)
        XCTAssertEqual(player.duration, 25, accuracy: 0.5)
    }
}
