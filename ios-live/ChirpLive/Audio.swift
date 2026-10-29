import AVFoundation
import CoreTransferable
import UniformTypeIdentifiers

/// Session sound on disk: AAC in .m4a, brought up to a listenable level.
/// The microphone is recorded in measurement mode (no automatic gain, which
/// BirdNET wants), so raw birdsong is often too quiet to hear on playback.
enum SoundFile {
    /// Peak level after the gain; louder moments are softly limited.
    static let target: Float = 0.89
    static let maxGain: Float = 40

    /// Gain that puts the loud end of the sound (99.9th percentile of
    /// |sample|, so one knock doesn't decide it) at `target`.
    static func gain(_ histogram: [Int], total: Int) -> Float {
        guard total > 0 else { return 1 }
        var seen = 0
        let stop = Int(Double(total) * 0.999)
        for (i, n) in histogram.enumerated().reversed() {
            seen += n
            if seen >= max(1, total - stop) {
                let level = binLevel(i)
                return level > 1e-5 ? min(maxGain, max(1, target / level)) : 1
            }
        }
        return 1
    }

    // 240 bins from -120 dBFS to 0 dBFS.
    static func bin(_ x: Float) -> Int {
        let db = 20 * log10(max(abs(x), 1e-6))
        return min(239, max(0, Int((db + 120) * 2)))
    }
    static func binLevel(_ i: Int) -> Float { pow(10, (Float(i) / 2 - 120 + 0.5) / 20) }

    static func histogram(_ samples: UnsafeBufferPointer<Float>, into h: inout [Int]) {
        for s in samples { h[bin(s)] += 1 }
    }

    /// Gain with a soft knee above `target`, so nothing clips.
    @inline(__always) static func apply(_ x: Float, gain: Float) -> Float {
        let y = x * gain
        let a = abs(y)
        guard a > target else { return y }
        let over = a - target
        let limited = target + (1 - target) * over / (over + (1 - target))
        return y < 0 ? -limited : limited
    }

    /// A bird's best 3 s, levelled, as .m4a.
    @discardableResult
    static func writeClip(_ samples: [Float], to url: URL) -> Bool {
        var h = [Int](repeating: 0, count: 240)
        samples.withUnsafeBufferPointer { histogram($0, into: &h) }
        let g = gain(h, total: samples.count)
        guard let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: BirdNET.sampleRate,
                                         channels: 1, interleaved: false),
              let buf = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(samples.count)),
              let ch = buf.floatChannelData?[0] else { return false }
        buf.frameLength = AVAudioFrameCount(samples.count)
        for i in samples.indices { ch[i] = apply(samples[i], gain: g) }
        do {
            let file = try AVAudioFile(forWriting: url, settings: AAC.settings(BirdNET.sampleRate),
                                       commonFormat: .pcmFormatFloat32, interleaved: false)
            try file.write(from: buf)
            return true
        } catch { return false }
    }

    /// The whole session, levelled, from the raw recording to `dst` (.m4a).
    /// Reads in 10 s pieces, so a long walk doesn't fill memory.
    static func level(_ src: URL, to dst: URL) throws {
        let input = try AVAudioFile(forReading: src)
        let format = input.processingFormat
        let chunk: AVAudioFrameCount = AVAudioFrameCount(format.sampleRate * 10)
        guard let buf = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: chunk) else { return }
        var h = [Int](repeating: 0, count: 240)
        var total = 0
        while input.framePosition < input.length {
            try input.read(into: buf, frameCount: chunk)
            guard buf.frameLength > 0, let ch = buf.floatChannelData?[0] else { break }
            histogram(UnsafeBufferPointer(start: ch, count: Int(buf.frameLength)), into: &h)
            total += Int(buf.frameLength)
        }
        let g = gain(h, total: total)
        input.framePosition = 0
        let out = try AVAudioFile(forWriting: dst, settings: AAC.settings(format.sampleRate),
                                  commonFormat: .pcmFormatFloat32, interleaved: false)
        while input.framePosition < input.length {
            try input.read(into: buf, frameCount: chunk)
            guard buf.frameLength > 0 else { break }
            for c in 0..<Int(format.channelCount) {
                guard let ch = buf.floatChannelData?[c] else { continue }
                for i in 0..<Int(buf.frameLength) { ch[i] = apply(ch[i], gain: g) }
            }
            try out.write(from: buf)
        }
    }
}

/// A sound file to share, under a readable name ("Morning listen, Oct 27 2026.m4a").
struct SharedSound: Transferable {
    let url: URL
    let name: String

    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(exportedContentType: .mpeg4Audio) { item in
            let dir = FileManager.default.temporaryDirectory.appendingPathComponent("share-\(UUID().uuidString)", isDirectory: true)
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let safe = item.name.replacingOccurrences(of: "/", with: "-").replacingOccurrences(of: ":", with: ".")
            let dst = dir.appendingPathComponent(safe + ".m4a")
            try FileManager.default.copyItem(at: item.url, to: dst)
            return SentTransferredFile(dst)
        }
    }
}
