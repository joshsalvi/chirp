#if DEBUG
import Foundation

/// App Store screenshots in the simulator (Debug builds only). Launch with
/// `-ChirpScreenshots <scene>`: listen, listening, heard (scrolled to the
/// birds heard), recent or playing.
/// Shows sample birds and recordings instead of signing in.
enum Screenshots {
    static let scene: String? = {
        let a = ProcessInfo.processInfo.arguments
        guard let i = a.firstIndex(of: "-ChirpScreenshots"), i + 1 < a.count else { return nil }
        return a[i + 1]
    }()

    static var showsRecent: Bool { scene == "recent" || scene == "playing" }

    static func heard(_ now: Date = Date()) -> [Heard] {
        [
            Heard(name: "Carolina Wren", scientific: "Thryothorus ludovicianus", best: 0.94, count: 6, last: now.addingTimeInterval(-40)),
            Heard(name: "Blue Jay", scientific: "Cyanocitta cristata", best: 0.88, count: 3, last: now.addingTimeInterval(-150)),
            Heard(name: "Tufted Titmouse", scientific: "Baeolophus bicolor", best: 0.81, count: 2, last: now.addingTimeInterval(-260)),
            Heard(name: "Northern Cardinal", scientific: "Cardinalis cardinalis", best: 0.77, count: 1, last: now.addingTimeInterval(-420)),
        ]
    }

    static func recent(_ now: Date = Date()) -> [RecentRecordings.Item] {
        [
            .init(id: "s1", time: now.addingTimeInterval(-180), duration: 24, species: "Eastern Phoebe", others: ["Black-capped Chickadee"], confidence: 0.89, has_audio: true),
            .init(id: "s2", time: now.addingTimeInterval(-1500), duration: 31, species: "Blue Jay", others: [], confidence: 0.92, has_audio: true),
            .init(id: "s3", time: now.addingTimeInterval(-3900), duration: 18, species: "Ruby-crowned Kinglet", others: [], confidence: 0.84, has_audio: true),
            .init(id: "s4", time: now.addingTimeInterval(-7600), duration: 27, species: "Downy Woodpecker", others: ["White-breasted Nuthatch"], confidence: 0.78, has_audio: true),
            .init(id: "s5", time: now.addingTimeInterval(-11200), duration: 22, species: "Barred Owl", others: [], confidence: 0.71, has_audio: true),
        ]
    }
}
#endif
