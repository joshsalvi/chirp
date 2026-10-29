import AVFoundation
import Foundation

/// Live Detect requests to a Chirp site, multipart as the Chirp app and the
/// watch send them: /analyze for each clip a bird was heard in, then
/// /save-session with the whole session's audio.
enum Remote {
    /// A Chirp station with a bird microphone (GET /tv/stations).
    struct Station: Decodable, Identifiable, Hashable {
        let id: String
        let name: String
        let online: Bool
        let mic: String
    }

    static func stations(server: URL, token: String) async throws -> [Station] {
        try JSONDecoder().decode([Station].self, from: try await get("api/v1/tv/stations", server: server, token: token))
    }

    /// A few seconds of live audio from a station's bird microphone (WAV).
    static func listen(_ station: Station, server: URL, token: String) async throws -> Data {
        try await get("api/v1/tv/listen/\(station.id)", server: server, token: token, timeout: 20)
    }

    private static func get(_ path: String, server: URL, token: String, timeout: TimeInterval = 15) async throws -> Data {
        var req = URLRequest(url: server.appendingPathComponent(path))
        req.timeoutInterval = timeout
        req.setValue("ChirpLive/1", forHTTPHeaderField: "User-Agent")
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, resp) = try await session.data(for: req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 { throw Failure.signedOut }
        guard (200..<300).contains(code) else { throw Failure.server(code, Account.detail(data)) }
        return data
    }

    struct Reply: Decodable {
        let detected: Bool
        let recording_id: String?
    }

    enum Failure: LocalizedError {
        case signedOut, server(Int, String?)
        var errorDescription: String? {
            switch self {
            case .signedOut: return "Your sign-in has ended. Sign in again in Settings."
            case .server(let code, let detail): return detail ?? "The site answered \(code)."
            }
        }
    }

    private static let session: URLSession = {
        let c = URLSessionConfiguration.default
        c.timeoutIntervalForRequest = 120
        return URLSession(configuration: c)
    }()

    /// One 3 s clip; returns the site's recording id when it heard a bird too.
    /// From a station (`station`), the clip is credited to it and placed where it is.
    static func analyze(_ samples: [Float], server: URL, token: String, lat: Double?, lon: Double?,
                        place: String?, station: String? = nil) async throws -> String? {
        let aac = AAC.encode(samples, sampleRate: BirdNET.sampleRate)
        var fields = ["source": station == nil ? "phone" : "device"]
        if let station { fields["device_id"] = station }
        if let lat, let lon, station == nil { fields["latitude"] = String(lat); fields["longitude"] = String(lon) }
        if let place, station == nil { fields["place_name"] = place }
        let file = aac ?? WAV.data(samples, sampleRate: BirdNET.sampleRate)
        let data = try await post("api/v1/live-detect/analyze", server: server, token: token, fields: fields,
                                  file: file, filename: aac != nil ? "live.m4a" : "live.wav",
                                  type: aac != nil ? "audio/mp4" : "audio/wav", timeout: 30)
        let reply = try JSONDecoder().decode(Reply.self, from: data)
        return reply.detected ? reply.recording_id : nil
    }

    /// The whole session as one recording on the site.
    static func saveSession(audio: URL, ids: [String], start: Date, server: URL, token: String,
                            lat: Double?, lon: Double?, place: String?, station: String?) async throws {
        let list = String(data: try JSONSerialization.data(withJSONObject: ids), encoding: .utf8) ?? "[]"
        var fields = ["recording_ids": list, "session_start": ISO8601DateFormatter().string(from: start)]
        if let station { fields["device_id"] = station }
        if let lat, let lon, station == nil { fields["latitude"] = String(lat); fields["longitude"] = String(lon) }
        if let place, station == nil { fields["place_name"] = place }
        _ = try await post("api/v1/live-detect/save-session", server: server, token: token, fields: fields,
                           file: try Data(contentsOf: audio), filename: "session.m4a", type: "audio/mp4", timeout: 180)
    }

    private static func post(_ path: String, server: URL, token: String, fields: [String: String],
                             file: Data, filename: String, type: String, timeout: TimeInterval) async throws -> Data {
        var req = URLRequest(url: server.appendingPathComponent(path))
        req.httpMethod = "POST"
        req.timeoutInterval = timeout
        let boundary = "chirp-\(UUID().uuidString)"
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        req.setValue("ChirpLive/1", forHTTPHeaderField: "User-Agent")
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        var body = Data()
        for (k, v) in fields {
            body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(k)\"\r\n\r\n\(v)\r\n".utf8))
        }
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\nContent-Type: \(type)\r\n\r\n".utf8))
        body.append(file)
        body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        let (data, resp) = try await session.upload(for: req, from: body)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 { throw Failure.signedOut }
        guard (200..<300).contains(code) else { throw Failure.server(code, Account.detail(data)) }
        return data
    }
}

/// A clip as AAC in an .m4a: about a fifth the size of the WAV.
enum AAC {
    static func encode(_ samples: [Float], sampleRate: Double) -> Data? {
        guard let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: sampleRate, channels: 1, interleaved: false),
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(samples.count)),
              let dst = buffer.floatChannelData?[0] else { return nil }
        buffer.frameLength = AVAudioFrameCount(samples.count)
        samples.withUnsafeBufferPointer { dst.update(from: $0.baseAddress!, count: samples.count) }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("clip-\(UUID().uuidString).m4a")
        defer { try? FileManager.default.removeItem(at: url) }
        do {
            try {   // scoped so the file is closed before it's read back
                let file = try AVAudioFile(forWriting: url, settings: AAC.settings(sampleRate),
                                           commonFormat: .pcmFormatFloat32, interleaved: false)
                try file.write(from: buffer)
            }()
            let data = try Data(contentsOf: url)
            return data.count > 512 ? data : nil
        } catch { return nil }
    }

    static func settings(_ sampleRate: Double) -> [String: Any] {
        [AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: sampleRate, AVNumberOfChannelsKey: 1,
         AVEncoderBitRateKey: 96_000]
    }
}
