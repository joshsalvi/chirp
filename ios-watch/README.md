# Chirp for Apple Watch

Live Detect and recent recordings on the watch. Built into the iPhone app by `WATCH=1 ./build-ios.sh` (see IOS_BUILD.md).

| Path | What it is |
|---|---|
| `ChirpWatch/` | The watchOS app (SwiftUI): Live Detect (records, sends clips, lists what it heard) and the site's five newest recordings with playback. `Screenshots.swift` fills it with sample data for App Store screenshots (Debug builds, `-ChirpScreenshots` followed by listen, listening, recent or playing) |
| `phone/` | iPhone side: the `ChirpWatch` Capacitor plugin and the WatchConnectivity link that hands the watch its sign-in |
| `add-watch-target.rb` | Adds the watch target to Capacitor's Xcode project (or `--remove`s it) |
