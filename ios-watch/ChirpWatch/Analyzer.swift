import CoreLocation
import Foundation

/// Live Detect requests, multipart as the web app sends them:
/// /analyze for each clip, /save-session for the whole session.
enum Analyzer {
    struct Detection: Decodable {
        let common_name: String
        let scientific_name: String?
        let confidence: Double
    }

    struct Reply: Decodable {
        let detected: Bool
        let recording_id: String?
        let detections: [Detection]
    }

    enum Failure: Error {
        case signedOut
        case server(Int, String?)
    }

    private static let session: URLSession = {
        let c = URLSessionConfiguration.default
        c.timeoutIntervalForRequest = 120
        return URLSession(configuration: c)
    }()

    static func analyze(wav: Data, server: URL, token: String?, location: CLLocation?) async throws -> Reply {
        var fields = ["source": "phone"]
        fields.merge(coords(location)) { a, _ in a }
        let data = try await post("api/v1/live-detect/analyze", server: server, token: token, fields: fields,
                                  file: wav, filename: "watch.wav", type: "audio/wav", timeout: 20)
        return try JSONDecoder().decode(Reply.self, from: data)
    }

    /// Turns the session's clips into one recording with the whole session's
    /// audio (the phone's "Save session").
    static func saveSession(audio: URL, recordingIDs: [String], start: Date, server: URL, token: String?,
                            location: CLLocation?) async throws {
        let ids = String(data: try JSONSerialization.data(withJSONObject: recordingIDs), encoding: .utf8) ?? "[]"
        var fields = ["recording_ids": ids, "session_start": ISO8601DateFormatter().string(from: start)]
        fields.merge(coords(location)) { a, _ in a }
        _ = try await post("api/v1/live-detect/save-session", server: server, token: token, fields: fields,
                           file: try Data(contentsOf: audio), filename: "watch.m4a", type: "audio/mp4", timeout: 120)
    }

    private static func coords(_ location: CLLocation?) -> [String: String] {
        guard let c = location?.coordinate else { return [:] }
        return ["latitude": String(c.latitude), "longitude": String(c.longitude)]
    }

    private static func post(_ path: String, server: URL, token: String?, fields: [String: String],
                             file: Data, filename: String, type: String, timeout: TimeInterval) async throws -> Data {
        var req = URLRequest(url: server.appendingPathComponent(path))
        req.httpMethod = "POST"
        req.timeoutInterval = timeout
        let boundary = "chirp-\(UUID().uuidString)"
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        req.setValue("ChirpWatch/1", forHTTPHeaderField: "User-Agent")
        if let token { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        var body = Data()
        for (k, v) in fields {
            body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(k)\"\r\n\r\n\(v)\r\n")
        }
        body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\nContent-Type: \(type)\r\n\r\n")
        body.append(file)
        body.append("\r\n--\(boundary)--\r\n")

        let (data, resp) = try await session.upload(for: req, from: body)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 { throw Failure.signedOut }
        guard (200..<300).contains(code) else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
            throw Failure.server(code, detail)
        }
        return data
    }

    static func describe(_ error: Error) -> String {
        switch error {
        case Failure.server(let code, let detail): return detail ?? "The site answered \(code)."
        case let e as URLError where e.code == .notConnectedToInternet: return "No connection."
        case let e as URLError where e.code == .timedOut: return "The site is slow to answer."
        case let e as URLError: return "Can't reach the site (\(e.code.rawValue))."
        default: return "Something went wrong."
        }
    }
}

private extension Data {
    mutating func append(_ s: String) { append(Data(s.utf8)) }
}

/// 16-bit mono WAV in memory.
enum WAV {
    static func encode(_ samples: [Int16], sampleRate: Int) -> Data {
        let bytes = samples.count * 2
        var d = Data(capacity: 44 + bytes)
        func u32(_ v: UInt32) { withUnsafeBytes(of: v.littleEndian) { d.append(contentsOf: $0) } }
        func u16(_ v: UInt16) { withUnsafeBytes(of: v.littleEndian) { d.append(contentsOf: $0) } }
        d.append(contentsOf: Array("RIFF".utf8)); u32(UInt32(36 + bytes))
        d.append(contentsOf: Array("WAVE".utf8))
        d.append(contentsOf: Array("fmt ".utf8)); u32(16); u16(1); u16(1)
        u32(UInt32(sampleRate)); u32(UInt32(sampleRate * 2)); u16(2); u16(16)
        d.append(contentsOf: Array("data".utf8)); u32(UInt32(bytes))
        // iOS and watchOS are little-endian, so the samples go in as they are.
        samples.withUnsafeBytes { d.append(contentsOf: $0) }
        return d
    }
}
