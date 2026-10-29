#if DEBUG
import Foundation

/// App Store screenshots: launch with -ChirpShots listen|summary|sessions|station|welcome
/// to fill the app with a sample morning walk. Debug builds only.
enum Screenshots {
    static let scene: String? = {
        let a = ProcessInfo.processInfo.arguments
        guard let i = a.firstIndex(of: "-ChirpShots"), i + 1 < a.count else { return nil }
        return a[i + 1]
    }()

    private static func h(_ id: Int, _ common: String, _ sci: String, _ count: Int, _ best: Double, _ minutesAgo: Double,
                          clip: Bool = true) -> Heard {
        let t = Date().addingTimeInterval(-minutesAgo * 60)
        return Heard(id: id, common: common, scientific: sci, count: count, best: best, first: t, last: t,
                     clip: clip ? "\(id).m4a" : nil)
    }

    static var walk: [Heard] {
        [h(1, "Northern Cardinal", "Cardinalis cardinalis", 9, 0.96, 1),
         h(2, "Carolina Wren", "Thryothorus ludovicianus", 6, 0.91, 2),
         h(3, "Blue Jay", "Cyanocitta cristata", 5, 0.88, 3),
         h(4, "Fox Sparrow", "Passerella iliaca", 2, 0.84, 5),
         h(5, "White-throated Sparrow", "Zonotrichia albicollis", 3, 0.79, 7),
         h(6, "Tufted Titmouse", "Baeolophus bicolor", 4, 0.76, 9),
         h(7, "Hermit Thrush", "Catharus guttatus", 1, 0.72, 12),
         h(8, "Black-capped Chickadee", "Poecile atricapillus", 7, 0.93, 14),
         h(9, "Downy Woodpecker", "Dryobates pubescens", 2, 0.81, 18)]
    }

    static let station = Remote.Station(id: "demo", name: "Backyard station", online: true, mic: "USB")

    static func sessions() -> [Session] {
        let cal = Calendar.current
        func at(_ daysAgo: Int, _ hour: Int, _ minute: Int) -> Date {
            let d = cal.date(byAdding: .day, value: -daysAgo, to: Date())!
            return cal.date(bySettingHour: hour, minute: minute, second: 0, of: d)!
        }
        let w = walk
        return [
            Session(id: "demo-1", start: at(0, 7, 42), end: at(0, 8, 31), latitude: 42.2603, longitude: -71.3524,
                    place: "Broadmoor Wildlife Sanctuary", heard: w),
            Session(id: "demo-2", start: at(1, 17, 5), end: at(1, 17, 40), stationID: "demo", stationName: "Backyard station",
                    heard: Array(w[0..<5])),
            Session(id: "demo-3", start: at(3, 6, 50), end: at(3, 7, 35), latitude: 42.2833, longitude: -71.3495,
                    place: "Natick", heard: Array(w[2..<8])),
            Session(id: "demo-4", start: at(6, 8, 10), end: at(6, 9, 2), latitude: 42.3582, longitude: -71.0636,
                    place: "Boston Common", heard: Array(w[0..<4])),
            Session(id: "demo-5", start: at(9, 15, 20), end: at(9, 15, 55), latitude: 42.4626, longitude: -71.0940,
                    place: "Middlesex Fells", heard: Array(w[3..<9])),
        ]
    }

    /// Sets the app up for the scene; returns the tab to show and the session for the summary sheet.
    @MainActor
    static func apply(listener: Listener) -> (tab: Int, summary: Session?) {
        guard let scene else { return (0, nil) }
        let store = SessionStore.shared
        store.demo(sessions())
        let w = walk
        switch scene {
        case "listen":
            listener.demo(heard: Array(w[0..<6]), singing: w[0], place: "Broadmoor Wildlife Sanctuary",
                          stations: [], source: .phone, sent: 0)
            return (0, nil)
        case "station":
            Account.shared.demoSignIn()
            listener.demo(heard: Array(w[1..<5]), singing: w[2], place: nil, stations: [station],
                          source: .station(station), sent: 3)
            return (0, nil)
        case "summary":
            return (0, store.sessions.first)
        case "sessions":
            return (1, nil)
        default:
            return (0, nil)
        }
    }
}
#endif
