import CoreLocation
import Foundation

/// POST /api/v1/live-detect/analyze with one clip (multipart, as the web
/// app's Live Detect sends it).
enum Analyzer {
    struct Detection: Decodable {
        let common_name: String
        let scientific_name: String?
        let confidence: Double
    }

    private struct Reply: Decodable {
        let detected: Bool
        let detections: [Detection]
    }

    enum Failure: Error {
        case signedOut
        case server(Int, String?)
    }

    private static let session: URLSession = {
        let c = URLSessionConfiguration.default
        c.timeoutIntervalForRequest = 20
        return URLSession(configuration: c)
    }()

    static func analyze(wav: Data, server: URL, token: String?, location: CLLocation?) async throws -> [Detection] {
        var req = URLRequest(url: server.appendingPathComponent("api/v1/live-detect/analyze"))
        req.httpMethod = "POST"
        let boundary = "chirp-\(UUID().uuidString)"
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        req.setValue("ChirpWatch/1", forHTTPHeaderField: "User-Agent")
        if let token { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }

        var fields = ["source": "phone"]
        if let c = location?.coordinate {
            fields["latitude"] = String(c.latitude)
            fields["longitude"] = String(c.longitude)
        }
        var body = Data()
        for (k, v) in fields {
            body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(k)\"\r\n\r\n\(v)\r\n")
        }
        body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"watch.wav\"\r\nContent-Type: audio/wav\r\n\r\n")
        body.append(wav)
        body.append("\r\n--\(boundary)--\r\n")

        let (data, resp) = try await session.upload(for: req, from: body)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 { throw Failure.signedOut }
        guard (200..<300).contains(code) else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
            throw Failure.server(code, detail)
        }
        return try JSONDecoder().decode(Reply.self, from: data).detections
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
