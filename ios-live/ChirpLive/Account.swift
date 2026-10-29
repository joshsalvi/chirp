import Foundation
import Security

/// Optional sign-in to a Chirp site. Signed in, each bird the phone hears is
/// also sent to the site (which keeps it as a Live Detect recording and gives
/// its own second opinion), and the whole session is saved there at the end,
/// the same way the Chirp app's Live Detect and the Apple Watch do it.
///
/// The password is used once, to get a sign-in; the app keeps only a 30-day
/// Live Detect-only token from POST /auth/watch-token, in the keychain.
@MainActor
final class Account: ObservableObject {
    static let shared = Account()
    static let defaultServer = URL(string: "https://www.ourchirp.com")!

    @Published private(set) var server: URL
    @Published private(set) var username: String
    @Published private(set) var token: String?
    @Published private(set) var expires: Date?

    var signedIn: Bool { token != nil && (expires ?? .distantFuture) > Date() }
    /// "ourchirp.com", or a server's own address with its port ("192.168.1.50:8768").
    var siteName: String {
        guard let host = server.host else { return server.absoluteString }
        let name = host.hasPrefix("www.") ? String(host.dropFirst(4)) : host
        return server.port.map { "\(name):\($0)" } ?? name
    }

    private let defaults = UserDefaults.standard

    private init() {
        server = defaults.string(forKey: "server").flatMap(URL.init(string:)) ?? Self.defaultServer
        username = defaults.string(forKey: "username") ?? ""
        token = Keychain.get("token")
        expires = defaults.object(forKey: "tokenExpires") as? Date
    }

    enum Failure: LocalizedError {
        case badServer, wrongPassword, server(String)
        var errorDescription: String? {
            switch self {
            case .badServer: return "That doesn't look like a Chirp site address."
            case .wrongPassword: return "Wrong username or password."
            case .server(let why): return why
            }
        }
    }

    func signIn(server text: String, username: String, password: String) async throws {
        guard let url = Self.parseServer(text) else { throw Failure.badServer }
        // 1. Username and password → a normal sign-in.
        var req = URLRequest(url: url.appendingPathComponent("api/v1/auth/login"))
        req.httpMethod = "POST"
        req.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        req.setValue("ChirpLive/1", forHTTPHeaderField: "User-Agent")
        req.httpBody = Self.form(["username": username, "password": password, "remember_me": "true"])
        let (data, resp) = try await URLSession.shared.data(for: req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 { throw Failure.wrongPassword }
        guard code == 200,
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let login = json["access_token"] as? String else {
            throw Failure.server(Self.detail(data) ?? (code == 0 ? "Can't reach \(url.host ?? "the site")." : "The site answered \(code)."))
        }
        // 2. Swap it for the Live Detect-only sign-in that lasts 30 days.
        var swap = URLRequest(url: url.appendingPathComponent("api/v1/auth/watch-token"))
        swap.httpMethod = "POST"
        swap.setValue("Bearer \(login)", forHTTPHeaderField: "Authorization")
        swap.setValue("ChirpLive/1", forHTTPHeaderField: "User-Agent")
        let (d2, r2) = try await URLSession.shared.data(for: swap)
        guard (r2 as? HTTPURLResponse)?.statusCode == 200,
              let j2 = try? JSONSerialization.jsonObject(with: d2) as? [String: Any] else {
            throw Failure.server(Self.detail(d2) ?? "The site didn't give a sign-in for Chirp Live. It may need updating.")
        }
        let days = (j2["expires_days"] as? Int) ?? 30
        let live = j2["access_token"] as? String ?? login     // a site without sign-ins: keep the login token
        self.server = url
        self.username = (json["username"] as? String) ?? username
        self.token = live
        self.expires = Date().addingTimeInterval(TimeInterval(days) * 86_400 - 3_600)
        defaults.set(url.absoluteString, forKey: "server")
        defaults.set(self.username, forKey: "username")
        defaults.set(expires, forKey: "tokenExpires")
        Keychain.set("token", live)
    }

    #if DEBUG
    /// App Store screenshots: look signed in, without a token that works.
    func demoSignIn() {
        server = Self.defaultServer; username = "josh"; token = "screenshot"; expires = Date().addingTimeInterval(86_400 * 20)
    }
    #endif

    func signOut() {
        token = nil; expires = nil
        Keychain.set("token", nil)
        defaults.removeObject(forKey: "tokenExpires")
    }

    /// The site turned the sign-in down: forget it.
    func rejected() { signOut() }

    // MARK: Helpers

    /// "ourchirp.com", "192.168.1.50:8768", "unraid:8768" or a full URL.
    /// Home-network addresses get http://, the rest https://.
    nonisolated static func parseServer(_ text: String) -> URL? {
        var t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        while t.hasSuffix("/") { t.removeLast() }
        guard !t.isEmpty else { return nil }
        if !t.contains("://") {
            let host = String(t.prefix { $0 != "/" && $0 != ":" }).lowercased()
            t = (isLocal(host) || t.contains(":") ? "http://" : "https://") + t
        }
        guard let url = URL(string: t), let host = url.host, !host.isEmpty,
              url.scheme == "http" || url.scheme == "https" else { return nil }
        return url
    }

    nonisolated static func isLocal(_ host: String) -> Bool {
        let parts = host.split(separator: ".").compactMap { Int($0) }
        if parts.count == 4 {
            switch (parts[0], parts[1]) {
            case (10, _), (127, _), (192, 168), (169, 254): return true
            case (172, 16...31): return true
            default: return false
            }
        }
        if host == "localhost" || !host.contains(".") { return true }
        return [".local", ".lan", ".home.arpa", ".internal"].contains { host.hasSuffix($0) }
    }

    nonisolated static func form(_ fields: [String: String]) -> Data {
        var allowed = CharacterSet.alphanumerics; allowed.insert(charactersIn: "-._~")
        return Data(fields.map { "\($0.key)=\($0.value.addingPercentEncoding(withAllowedCharacters: allowed) ?? "")" }
            .joined(separator: "&").utf8)
    }

    nonisolated static func detail(_ data: Data) -> String? {
        (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
    }
}

enum Keychain {
    private static let service = "com.joshuasalvimd.chirplive"

    static func get(_ key: String) -> String? {
        var out: AnyObject?
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: key, kSecReturnData as String: true]
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let data = out as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func set(_ key: String, _ value: String?) {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: key]
        _ = SecItemDelete(q as CFDictionary)
        guard let value, !value.isEmpty else { return }
        var add = q
        add[kSecValueData as String] = Data(value.utf8)
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        _ = SecItemAdd(add as CFDictionary, nil)
    }
}
