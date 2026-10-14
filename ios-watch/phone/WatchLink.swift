import Foundation
import WatchConnectivity

/// iPhone side of the watch link. Sends the watch its sign-in as the
/// application context (delivered even if the watch app isn't running) and
/// answers the watch when it asks for it again (after a reinstall, say).
final class WatchLink: NSObject, WCSessionDelegate {
    static let shared = WatchLink()

    private var waiting: [() -> Void] = []
    private let key = "credentials"

    func activate() {
        guard WCSession.isSupported() else { return }
        let s = WCSession.default
        if s.delegate == nil {
            s.delegate = self
            s.activate()
        }
    }

    /// Runs `body` on the main queue once the session is active.
    func whenActive(_ body: @escaping () -> Void) {
        DispatchQueue.main.async {
            guard WCSession.isSupported() else { return body() }
            if WCSession.default.activationState == .activated { body() } else { self.waiting.append(body); self.activate() }
        }
    }

    var paired: Bool { WCSession.isSupported() && WCSession.default.isPaired }
    var installed: Bool { WCSession.isSupported() && WCSession.default.isWatchAppInstalled }

    func send(_ context: [String: Any]) {
        if let data = try? JSONSerialization.data(withJSONObject: context) {
            ChirpKeychain.set(key, String(data: data, encoding: .utf8))
        }
        whenActive {
            var ctx = context
            ctx["sentAt"] = Date().timeIntervalSince1970  // always a change, so it's delivered
            try? WCSession.default.updateApplicationContext(ctx)
        }
    }

    private var saved: [String: Any] {
        guard let s = ChirpKeychain.get(key), let d = s.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return [:] }
        return obj
    }

    // MARK: WCSessionDelegate

    func session(_ session: WCSession, activationDidCompleteWith state: WCSessionActivationState, error: Error?) {
        DispatchQueue.main.async {
            let run = self.waiting
            self.waiting = []
            run.forEach { $0() }
        }
    }

    func sessionDidBecomeInactive(_ session: WCSession) {}

    // Switching to another watch: activate again for the new one.
    func sessionDidDeactivate(_ session: WCSession) { WCSession.default.activate() }

    func session(_ session: WCSession, didReceiveMessage message: [String: Any],
                 replyHandler: @escaping ([String: Any]) -> Void) {
        replyHandler(message["request"] as? String == "credentials" ? saved : [:])
    }
}
