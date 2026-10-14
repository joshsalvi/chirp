import Capacitor
import WatchConnectivity

/// window.Capacitor plugin "ChirpWatch" (frontend: native.watch in
/// src/native/index.js). The web app hands over a Live Detect-only sign-in
/// and the watch app uses it to send clips straight to the server.
@objc(ChirpWatchPlugin)
public class ChirpWatchPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "ChirpWatchPlugin"
    public let jsName = "ChirpWatch"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "status", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "setCredentials", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "clearCredentials", returnType: CAPPluginReturnPromise),
    ]

    override public func load() {
        WatchLink.shared.activate()
    }

    @objc func status(_ call: CAPPluginCall) {
        WatchLink.shared.whenActive {
            call.resolve(["supported": WCSession.isSupported(),
                          "paired": WatchLink.shared.paired,
                          "installed": WatchLink.shared.installed])
        }
    }

    @objc func setCredentials(_ call: CAPPluginCall) {
        guard let server = call.getString("server"), !server.isEmpty else {
            return call.reject("server is required")
        }
        WatchLink.shared.send(["server": server,
                               "token": call.getString("token") ?? "",
                               "site": call.getString("site") ?? ""])
        call.resolve()
    }

    @objc func clearCredentials(_ call: CAPPluginCall) {
        WatchLink.shared.send(["signedOut": true])
        call.resolve()
    }
}
