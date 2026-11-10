import Capacitor
import UIKit

/// Main.storyboard's view controller (build-ios.sh points it here) so the
/// app's own plugins are registered with the bridge: the app icon plugin
/// always, the watch plugin when the build includes the watch app.
class ChirpBridgeViewController: CAPBridgeViewController {
    override open func capacitorDidLoad() {
        // Swipe in from the left edge to go back and from the right edge to go
        // forward, as in Safari. The web app's pages use history.pushState,
        // which these gestures follow.
        webView?.allowsBackForwardNavigationGestures = true
        bridge?.registerPluginInstance(ChirpAppIconPlugin())
        if let watch = (NSClassFromString("ChirpWatchPlugin") as? CAPPlugin.Type)?.init() {
            bridge?.registerPluginInstance(watch)
        }
    }
}
