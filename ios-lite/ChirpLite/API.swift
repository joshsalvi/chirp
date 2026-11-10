import Foundation
import SwiftUI

/// Requests to the signed-in Chirp site.
enum API {
    static let userAgent = "ChirpLite/1"

    enum Failure: LocalizedError {
        case signedOut, server(Int, String?), offline
        var errorDescription: String? {
            switch self {
            case .signedOut: return "Your sign-in has ended. Please sign in again."
            case .offline: return "Can't reach your Chirp. Check your connection."
            case .server(let code, let detail): return detail ?? "Your Chirp answered \(code)."
            }
        }
    }

    static let session: URLSession = {
        let c = URLSessionConfiguration.default
        c.timeoutIntervalForRequest = 30
        c.urlCache = URLCache(memoryCapacity: 30 << 20, diskCapacity: 200 << 20)
        return URLSession(configuration: c)
    }()

    /// A server path ("api/v1/…", "/api/v1/…") or a full URL.
    static func url(_ path: String, server: URL) -> URL? {
        if path.hasPrefix("http://") || path.hasPrefix("https://") { return URL(string: path) }
        let trimmed = path.hasPrefix("/") ? String(path.dropFirst()) : path
        return URL(string: trimmed, relativeTo: server.appendingPathComponent(""))?.absoluteURL
    }

    static func request(_ path: String, server: URL, token: String?) -> URLRequest? {
        guard let u = url(path, server: server) else { return nil }
        var req = URLRequest(url: u)
        req.setValue(userAgent, forHTTPHeaderField: "User-Agent")
        // Only the site gets the sign-in, never a photo host.
        if let token, u.host == server.host { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        return req
    }

    static func data(_ path: String, server: URL, token: String?) async throws -> Data {
        guard let req = request(path, server: server, token: token) else { throw Failure.server(0, "Bad address") }
        let data: Data, resp: URLResponse
        do { (data, resp) = try await session.data(for: req) } catch { throw Failure.offline }
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 { throw Failure.signedOut }
        guard (200..<300).contains(code) else { throw Failure.server(code, Account.detail(data)) }
        return data
    }

    static func get<T: Decodable>(_ path: String, server: URL, token: String?) async throws -> T {
        try JSONDecoder.chirp.decode(T.self, from: try await data(path, server: server, token: token))
    }

    static func query(_ items: [String: String?]) -> String {
        var c = URLComponents()
        c.queryItems = items.compactMap { k, v in v.map { URLQueryItem(name: k, value: $0) } }.sorted { $0.name < $1.name }
        return c.queryItems?.isEmpty == false ? "?" + (c.percentEncodedQuery ?? "") : ""
    }
}

/// Loads one screen's data and keeps the last good copy while refreshing.
@MainActor
final class Loader<T: Decodable>: ObservableObject {
    @Published var value: T?
    @Published var error: String?
    @Published var loading = false
    private let path: () -> String

    init(_ path: @escaping () -> String) { self.path = path }

    func load(_ account: Account) async {
        loading = true
        defer { loading = false }
        do {
            value = try await API.get(path(), server: account.server, token: account.token)
            error = nil
        } catch API.Failure.signedOut {
            account.signOut()
        } catch {
            if value == nil { self.error = error.localizedDescription }
        }
    }
}
