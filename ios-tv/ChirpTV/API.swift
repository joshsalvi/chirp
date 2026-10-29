import Foundation

/// Calls to the Chirp server with the TV token.
enum API {
    enum Failure: LocalizedError {
        case signedOut, oldServer, restarting
        case server(Int, String?)
        var errorDescription: String? {
            switch self {
            case .signedOut: return "Signed out. Sign in again on this TV."
            case .oldServer: return "This Chirp server needs an update for the Apple TV app."
            case .restarting: return "The Chirp server is busy or restarting. Trying again…"
            case .server(let code, let detail): return detail ?? "The server answered \(code)."
            }
        }
    }

    private static let session: URLSession = {
        let c = URLSessionConfiguration.default
        c.timeoutIntervalForRequest = 30
        c.requestCachePolicy = .reloadIgnoringLocalCacheData
        return URLSession(configuration: c)
    }()

    static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    @MainActor
    static func data(_ path: String, method: String = "GET", body: Data? = nil,
                     contentType: String = "application/json", auth: Bool = true) async throws -> Data {
        let account = Account.shared
        var req = URLRequest(url: account.url(path))
        req.httpMethod = method
        req.setValue("ChirpTV/1", forHTTPHeaderField: "User-Agent")
        if auth, let t = account.token { req.setValue("Bearer \(t)", forHTTPHeaderField: "Authorization") }
        if let body {
            req.httpBody = body
            req.setValue(contentType, forHTTPHeaderField: "Content-Type")
        }
        let (data, resp) = try await session.data(for: req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 && auth { account.tokenRejected(); throw Failure.signedOut }
        if (code == 404 || code == 405) && path.hasPrefix("api/v1/tv/") { throw Failure.oldServer }
        if [502, 503, 504].contains(code) { throw Failure.restarting }
        guard (200..<300).contains(code) else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
            throw Failure.server(code, detail)
        }
        return data
    }

    @MainActor
    static func get<T: Decodable>(_ path: String, as: T.Type = T.self) async throws -> T {
        try decoder.decode(T.self, from: try await data(path))
    }

    @MainActor
    static func post<T: Decodable>(_ path: String, json: [String: Any], auth: Bool = true, as: T.Type = T.self) async throws -> T {
        let body = try JSONSerialization.data(withJSONObject: json)
        return try decoder.decode(T.self, from: try await data(path, method: "POST", body: body, auth: auth))
    }

    /// multipart/form-data with plain fields (Live Detect's analyze route).
    @MainActor
    static func postForm<T: Decodable>(_ path: String, fields: [String: String], as: T.Type = T.self) async throws -> T {
        let boundary = "chirp-\(UUID().uuidString)"
        var body = Data()
        for (k, v) in fields {
            body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(k)\"\r\n\r\n\(v)\r\n".data(using: .utf8)!)
        }
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        let data = try await data(path, method: "POST", body: body, contentType: "multipart/form-data; boundary=\(boundary)")
        return try decoder.decode(T.self, from: data)
    }

    static func describe(_ error: Error) -> String {
        if let e = error as? Failure { return e.errorDescription ?? "Something went wrong." }
        if let e = error as? URLError {
            switch e.code {
            case .notConnectedToInternet, .networkConnectionLost: return "No internet connection."
            case .cannotFindHost, .cannotConnectToHost: return "Can't reach the Chirp server."
            case .timedOut: return "The server took too long to answer."
            default: return e.localizedDescription
            }
        }
        if error is DecodingError { return "Couldn't read the server's answer." }
        return error.localizedDescription
    }
}

/// "2026-10-21T13:02:11Z" → Date
enum ISO {
    nonisolated static func date(_ s: String?) -> Date? {
        guard let s else { return nil }
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = f.date(from: s) { return d }
        f.formatOptions = [.withInternetDateTime]
        if let d = f.date(from: s) { return d }
        // Python isoformat() without a zone (server times are UTC)
        let n = DateFormatter()
        n.locale = Locale(identifier: "en_US_POSIX")
        n.timeZone = TimeZone(identifier: "UTC")
        for fmt in ["yyyy-MM-dd'T'HH:mm:ss.SSSSSS", "yyyy-MM-dd'T'HH:mm:ss"] {
            n.dateFormat = fmt
            if let d = n.date(from: s) { return d }
        }
        return nil
    }
}
