import Combine
import Foundation
import WatchConnectivity

/// The watch's sign-in, sent by the iPhone app (WatchLink.swift there):
/// server address, a Live Detect-only token (30 days) and the site name.
final class Account: NSObject, ObservableObject, WCSessionDelegate {
    static let shared = Account()

    @Published private(set) var server: URL?
    @Published private(set) var site = ""
    @Published private(set) var asking = false
    private(set) var token: String?

    private let defaults = UserDefaults.standard

    var signedIn: Bool { server != nil }

    private override init() {
        super.init()
        server = defaults.string(forKey: "server").flatMap(URL.init(string:))
        site = defaults.string(forKey: "site") ?? ""
        token = Keychain.get("token")
        #if DEBUG
        if Screenshots.scene != nil {
            server = URL(string: "https://www.ourchirp.com")
            site = "Natick Birds"
            return
        }
        #endif
        if WCSession.isSupported() {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
    }

    /// Ask the iPhone for the sign-in again (it answers if Chirp is open there).
    func askPhone() {
        guard WCSession.isSupported(), WCSession.default.activationState == .activated else { return }
        let s = WCSession.default
        if !s.receivedApplicationContext.isEmpty { apply(s.receivedApplicationContext) }
        guard s.isReachable else { return }
        DispatchQueue.main.async { self.asking = true }
        s.sendMessage(["request": "credentials"], replyHandler: { reply in
            if !reply.isEmpty { self.apply(reply) }
            DispatchQueue.main.async { self.asking = false }
        }, errorHandler: { _ in
            DispatchQueue.main.async { self.asking = false }
        })
    }

    /// The server turned the token down (expired or signed out).
    func tokenRejected() {
        askPhone()
    }

    private func apply(_ ctx: [String: Any]) {
        DispatchQueue.main.async {
            if ctx["signedOut"] as? Bool == true {
                self.server = nil
                self.site = ""
                self.token = nil
                self.defaults.removeObject(forKey: "server")
                self.defaults.removeObject(forKey: "site")
                Keychain.set("token", nil)
                return
            }
            guard let s = ctx["server"] as? String, let url = URL(string: s), url.scheme != nil else { return }
            self.server = url
            self.site = ctx["site"] as? String ?? url.host ?? ""
            let t = ctx["token"] as? String
            self.token = (t?.isEmpty ?? true) ? nil : t
            self.defaults.set(s, forKey: "server")
            self.defaults.set(self.site, forKey: "site")
            Keychain.set("token", self.token)
        }
    }

    // MARK: WCSessionDelegate

    func session(_ session: WCSession, activationDidCompleteWith state: WCSessionActivationState, error: Error?) {
        guard state == .activated else { return }
        if !session.receivedApplicationContext.isEmpty {
            apply(session.receivedApplicationContext)
        } else if server == nil {
            askPhone()
        }
    }

    func session(_ session: WCSession, didReceiveApplicationContext ctx: [String: Any]) {
        apply(ctx)
    }
}
