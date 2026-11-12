import Foundation
import Security

/// Sign-in to a Chirp site. The password is used once: the app swaps the
/// sign-in for a read-only Chirp Lite one (POST /auth/lite-token, 90 days),
/// keeps it in the keychain, and renews it while the app is in use.
@MainActor
final class Account: ObservableObject {
    static let shared = Account()
    static let defaultServer = URL(string: "https://www.ourchirp.com")!

    @Published private(set) var server: URL
    @Published private(set) var username: String
    @Published private(set) var token: String?
    @Published private(set) var expires: Date?
    /// After a password sign-in on a multi-site server: the sites to pick from.
    @Published var sites: [Site] = []
    private var pending: String?          // the password sign-in, until a site is picked
    private var borrowed = false          // a debug sign-in from the build script: never renewed or saved

    var signedIn: Bool { token != nil && (expires ?? .distantFuture) > Date() }
    /// Signed in through "Try the demo": ourchirp.com's read-only demo yard.
    var isDemo: Bool { defaults.bool(forKey: "demo") }
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
        case badServer, wrongPassword, noSites, server(String)
        var errorDescription: String? {
            switch self {
            case .badServer: return "That doesn't look like a Chirp site address."
            case .wrongPassword: return "That username and password didn't match."
            case .noSites: return "This account isn't part of a Chirp site yet. Ask the site's owner for an invite."
            case .server(let why): return why
            }
        }
    }

    func signIn(server text: String, username: String, password: String) async throws {
        guard let url = Self.parseServer(text) else { throw Failure.badServer }
        var req = URLRequest(url: url.appendingPathComponent("api/v1/auth/login"))
        req.httpMethod = "POST"
        req.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        req.setValue(API.userAgent, forHTTPHeaderField: "User-Agent")
        req.httpBody = Self.form(["username": username, "password": password, "remember_me": "true"])
        let data: Data, resp: URLResponse
        do { (data, resp) = try await URLSession.shared.data(for: req) } catch {
            throw Failure.server("Can't reach \(url.host ?? "the site"). Check the address and your connection.")
        }
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 { throw Failure.wrongPassword }
        if code == 429 { throw Failure.server("Too many tries. Wait a minute and try again.") }
        guard code == 200,
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let login = json["access_token"] as? String else {
            throw Failure.server(Self.detail(data) ?? "The site answered \(code).")
        }
        defaults.removeObject(forKey: "demo")
        self.server = url
        self.username = (json["username"] as? String) ?? username
        defaults.set(url.absoluteString, forKey: "server")
        defaults.set(self.username, forKey: "username")

        // A multi-site account with no site in its sign-in picks one first.
        if Self.claims(login)["global_user_id"] != nil && Self.claims(login)["active_instance_id"] == nil {
            let list: [Site] = try await API.get("api/v1/instances", server: url, token: login)
            if list.isEmpty { throw Failure.noSites }
            if list.count == 1 { try await pick(list[0], with: login); return }
            pending = login
            sites = list
            return
        }
        try await finish(with: login)
    }

    func pick(_ site: Site) async throws {
        guard let login = pending else { throw Failure.server("Sign in again.") }
        try await pick(site, with: login)
    }

    private func pick(_ site: Site, with login: String) async throws {
        var req = URLRequest(url: server.appendingPathComponent("api/v1/instances/switch"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("Bearer \(login)", forHTTPHeaderField: "Authorization")
        req.setValue(API.userAgent, forHTTPHeaderField: "User-Agent")
        req.httpBody = try JSONSerialization.data(withJSONObject: ["instance_id": site.id])
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard (resp as? HTTPURLResponse)?.statusCode == 200,
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let siteToken = json["access_token"] as? String else {
            throw Failure.server(Self.detail(data) ?? "Couldn't open \(site.name).")
        }
        try await finish(with: siteToken)
        sites = []
        pending = nil
        defaults.set(site.name, forKey: "siteTitle")
    }

    /// Swap a sign-in (or the current Lite one) for a fresh Lite sign-in.
    private func finish(with login: String) async throws {
        var req = URLRequest(url: server.appendingPathComponent("api/v1/auth/lite-token"))
        req.httpMethod = "POST"
        req.setValue("Bearer \(login)", forHTTPHeaderField: "Authorization")
        req.setValue(API.userAgent, forHTTPHeaderField: "User-Agent")
        let (data, resp) = try await URLSession.shared.data(for: req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 { throw Failure.wrongPassword }
        guard code == 200, let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw Failure.server(Self.detail(data) ?? (code == 404 ? "This Chirp site needs updating to 0.5.19 or later for Chirp Lite."
                                                                   : "The site answered \(code)."))
        }
        let days = (json["expires_days"] as? Int) ?? 90
        let lite = (json["access_token"] as? String) ?? login     // a site without sign-ins
        token = lite
        expires = Date().addingTimeInterval(TimeInterval(days) * 86_400 - 3_600)
        defaults.set(expires, forKey: "tokenExpires")
        Keychain.set("token", lite)
    }

    /// "Try the demo" (POST /auth/demo): a few hours in ourchirp.com's demo
    /// yard, no account needed.
    func tryDemo() async throws {
        let url = Self.defaultServer
        var req = URLRequest(url: url.appendingPathComponent("api/v1/auth/demo"))
        req.httpMethod = "POST"
        req.setValue(API.userAgent, forHTTPHeaderField: "User-Agent")
        let data: Data, resp: URLResponse
        do { (data, resp) = try await URLSession.shared.data(for: req) } catch {
            throw Failure.server("Can't reach ourchirp.com. Check your connection.")
        }
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        guard code == 200, let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let t = json["access_token"] as? String else {
            throw Failure.server(Self.detail(data) ?? "The demo isn't available right now.")
        }
        let minutes = (json["expires_minutes"] as? Int) ?? 360
        server = url; username = "Demo"; token = t
        expires = Date().addingTimeInterval(TimeInterval(minutes - 5) * 60)
        defaults.set(url.absoluteString, forKey: "server")
        defaults.set(expires, forKey: "tokenExpires")
        defaults.set("Demo yard", forKey: "siteTitle")
        defaults.set(true, forKey: "demo")
        Keychain.set("token", t)
    }

    /// Renew the sign-in when it's more than a week old (once per launch).
    func renewIfNeeded() async {
        guard !borrowed, !isDemo, let token, let expires, expires.timeIntervalSinceNow < 83 * 86_400 else { return }
        try? await finish(with: token)
    }

    var siteTitle: String? { defaults.string(forKey: "siteTitle") }

    func cancelSitePick() { sites = []; pending = nil }

    func signOut() {
        token = nil; expires = nil; sites = []; pending = nil
        Keychain.set("token", nil)
        defaults.removeObject(forKey: "tokenExpires")
        defaults.removeObject(forKey: "siteTitle")
        if isDemo { username = "" }
        defaults.removeObject(forKey: "demo")
    }

    #if DEBUG
    /// Screenshots and UI checks: a Lite sign-in handed in by the build script.
    func useToken(_ t: String, server url: URL, username name: String) {
        server = url; username = name; token = t; expires = Date().addingTimeInterval(3_600); borrowed = true
    }
    #endif

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

    /// The unverified claims of a sign-in (only to see whether a site is chosen).
    nonisolated static func claims(_ jwt: String) -> [String: Any] {
        let parts = jwt.split(separator: ".")
        guard parts.count == 3 else { return [:] }
        var b = String(parts[1]).replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        while b.count % 4 != 0 { b += "=" }
        guard let d = Data(base64Encoded: b), let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return [:] }
        return j
    }
}

enum Keychain {
    private static let service = "com.joshuasalvimd.chirp.lite"

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
