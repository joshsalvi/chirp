import Capacitor
import UIKit

/// window.Capacitor plugin "ChirpAppIcon" (frontend: native.appIcon in
/// src/native/index.js). Switches between the theme icons bundled as
/// AppIcon-<theme> sets; an empty name goes back to the main icon.
/// iOS shows its own "You have changed the icon" alert after each change.
@objc(ChirpAppIconPlugin)
public class ChirpAppIconPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "ChirpAppIconPlugin"
    public let jsName = "ChirpAppIcon"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "get", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "set", returnType: CAPPluginReturnPromise),
    ]

    @objc func get(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            call.resolve(["supported": UIApplication.shared.supportsAlternateIcons,
                          "name": UIApplication.shared.alternateIconName ?? ""])
        }
    }

    @objc func set(_ call: CAPPluginCall) {
        let raw = call.getString("name") ?? ""
        let name: String? = raw.isEmpty ? nil : raw
        DispatchQueue.main.async { self.apply(name, call) }
    }

    /// iOS only changes the icon while the app is active, so a change asked
    /// for during launch or in the background waits until the app is.
    private func apply(_ name: String?, _ call: CAPPluginCall) {
        let app = UIApplication.shared
        guard app.supportsAlternateIcons else { return call.reject("Alternate icons aren't supported here.") }
        if app.alternateIconName == name { return call.resolve(["changed": false]) }
        guard app.applicationState == .active else {
            var token: NSObjectProtocol?
            token = NotificationCenter.default.addObserver(forName: UIApplication.didBecomeActiveNotification,
                                                           object: nil, queue: .main) { [weak self] _ in
                if let token { NotificationCenter.default.removeObserver(token) }
                // A moment after becoming active, or iOS can still refuse.
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { self?.apply(name, call) }
            }
            return
        }
        app.setAlternateIconName(name) { error in
            if let error { call.reject(error.localizedDescription) } else { call.resolve(["changed": true]) }
        }
    }
}
