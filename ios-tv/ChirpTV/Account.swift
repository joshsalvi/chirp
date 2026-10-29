import Foundation

/// The TV's sign-in: which Chirp server, and a TV-only token (180 days) from
/// the sign-in-by-code flow (SignInView, server api/tv.py).
@MainActor
final class Account: ObservableObject {
    static let shared = Account()
    static let defaultServer = URL(string: "https://www.ourchirp.com")!

    @Published private(set) var server: URL
    @Published private(set) var username = ""
    @Published private(set) var token: String?

    var signedIn: Bool { token != nil }

    private let defaults = UserDefaults.standard

    private init() {
        server = defaults.string(forKey: "server").flatMap(URL.init(string:)) ?? Self.defaultServer
        username = defaults.string(forKey: "username") ?? ""
        token = Keychain.get("token")
        #if DEBUG
        // Screenshots: launch with -ChirpServer URL -ChirpToken TOKEN -ChirpUser NAME
        if let s = Screenshots.value("-ChirpServer"), let u = URL(string: s) { server = u }
        if let t = Screenshots.value("-ChirpToken") { token = t; username = Screenshots.value("-ChirpUser") ?? "" }
        #endif
    }

    func signIn(token: String, username: String) {
        self.token = token
        self.username = username
        Keychain.set("token", token)
        defaults.set(username, forKey: "username")
    }

    func signOut() {
        token = nil
        username = ""
        Keychain.set("token", nil)
        defaults.removeObject(forKey: "username")
    }

    /// Typed on the sign-in screen: "ourchirp.com", "192.168.1.50:8768",
    /// "unraid:8768", a full URL. Home-network addresses get http://, the
    /// rest https://; typing the scheme yourself always wins.
    func setServer(_ text: String) -> Bool {
        guard let url = Self.parseServer(text) else { return false }
        server = url
        defaults.set(url.absoluteString, forKey: "server")
        signOut()
        return true
    }

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

    /// Private and link-local IPv4, localhost, single-label names (unraid,
    /// tower) and .local / .lan / .home.arpa / .internal names.
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

    /// A page of this server's web app, under any path the server lives at
    /// (https://example.com/chirp → https://example.com/chirp/tv).
    func pageURL(_ page: String, query: [URLQueryItem] = []) -> URL {
        var c = URLComponents(url: server, resolvingAgainstBaseURL: false) ?? URLComponents()
        var base = c.path
        while base.hasSuffix("/") { base.removeLast() }
        c.path = base + "/" + page
        c.queryItems = query.isEmpty ? nil : query
        c.fragment = nil
        return c.url ?? server
    }

    /// How to write an address for someone to type: no https:// and no www.,
    /// but http:// stays, since browsers would otherwise try https first.
    /// keepWWW for text that gets typed back in as the server address.
    nonisolated static func typable(_ url: URL, keepWWW: Bool = false) -> String {
        var s = url.absoluteString
        if s.hasPrefix("https://") { s.removeFirst(8) }
        if !keepWWW, s.hasPrefix("www.") { s.removeFirst(4) }
        while s.hasSuffix("/") { s.removeLast() }
        return s
    }

    /// The server turned the token down: back to the sign-in screen.
    func tokenRejected() {
        signOut()
    }

    // MARK: URLs

    /// "api/v1/x" or "/api/v1/x" → under the server, keeping any path it lives at.
    func url(_ path: String) -> URL {
        if let u = URL(string: path), u.scheme != nil { return u }
        var base = server.absoluteString
        while base.hasSuffix("/") { base.removeLast() }
        let rel = path.hasPrefix("/") ? String(path.dropFirst()) : path
        return URL(string: base + "/" + rel) ?? server
    }

    /// For images: the token goes in the query (media routes read it there),
    /// since AsyncImage can't add headers. Photos hosted elsewhere stay as is.
    func mediaURL(_ path: String?) -> URL? {
        guard let path, !path.isEmpty else { return nil }
        let u = url(path)
        guard u.host == server.host, let token,
              var c = URLComponents(url: u, resolvingAgainstBaseURL: true) else { return u }
        c.queryItems = (c.queryItems ?? []) + [URLQueryItem(name: "token", value: token)]
        return c.url
    }
}
