import Capacitor

/// Main.storyboard's view controller (build-ios.sh points it here) so the
/// app's own plugins are registered with the bridge.
class ChirpBridgeViewController: CAPBridgeViewController {
    override open func capacitorDidLoad() {
        bridge?.registerPluginInstance(ChirpWatchPlugin())
    }
}
