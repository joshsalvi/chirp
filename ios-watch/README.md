# Chirp for Apple Watch

Live Detect on the watch. Built into the iPhone app by `WATCH=1 ./build-ios.sh` (see IOS_BUILD.md).

| Path | What it is |
|---|---|
| `ChirpWatch/` | The watchOS app (SwiftUI): records, sends clips to the server, lists what it heard |
| `phone/` | iPhone side: the `ChirpWatch` Capacitor plugin and the WatchConnectivity link that hands the watch its sign-in |
| `add-watch-target.rb` | Adds the watch target to Capacitor's Xcode project (or `--remove`s it) |
