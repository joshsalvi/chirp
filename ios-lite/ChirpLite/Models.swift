import Foundation

// The /api/v1/lite screens (chirp-server app/api/lite.py). Decoded with
// .convertFromSnakeCase, so profile_id arrives as profileId.

struct Today: Decodable {
    let date: String
    let speciesCount: Int
    let detections: Int
    let recordings: Int
    let newCount: Int
    let firstSong: FirstSong?
    let hero: Hero?
    let species: [Species]
    let hourly: [Int]
    let summary: String?

    struct Hero: Decodable {
        let name: String
        let recordingId: String?
        let time: Date?
        let today: Bool
        let hasAudio: Bool
        let profileId: String?
        let photo: String?
    }

    struct FirstSong: Decodable {
        let name: String
        let time: Date?
    }

    struct Species: Decodable, Identifiable {
        var id: String { name }
        let name: String
        let profileId: String?
        let photo: String?
        let count: Int
        let last: Date?
        let new: Bool
    }
}

struct BirdList: Decodable {
    let count: Int
    let birds: [Card]

    struct Card: Decodable, Identifiable {
        var id: String { name }
        let name: String
        let profileId: String?
        let photo: String?
        let count: Int
        let first: Date?
        let last: Date?
        let new: Bool
    }
}

struct SoundPage: Decodable {
    let recordings: [Sound]
    let nextBefore: String?

    struct Sound: Decodable, Identifiable {
        let id: String
        let time: Date?
        let duration: Double?
        let bird: String
        let others: [String]
        let startsAt: Double?
        let hasAudio: Bool
        let audio: String?
        let spectrogram: String?
        let profileId: String?
        let photo: String?
        let otherPhotos: [String?]?
    }
}

struct Guide: Decodable {
    let month: String
    let count: Int
    let heard: Int
    let birds: [Entry]

    struct Entry: Decodable, Identifiable {
        var id: String { name }
        let name: String
        let photo: String?
        let chance: Double
        let likely: String
        let heard: Bool
        let profileId: String?
    }
}

struct BirdProfile: Decodable {
    let id: String
    let name: String
    let scientific: String?
    let photos: [Photo]
    let song: Song?
    let size: Size?
    let season: String?
    let howOften: String
    let heardCount: Int
    let firstHeard: Date?
    let lastHeard: Date?
    let blurb: String?
    let funFact: String?
    let tags: [Tag]
    let rangeMap: String?
    let rangeMapSource: String?
    let rangeMapVector: Bool?
    let rangeMapImage: String?       // the map as PNG/JPEG (Wikipedia SVGs drawn by the server)
    let conservation: String?

    struct Photo: Decodable, Hashable {
        let url: String
        let credit: String?
        let yours: Bool?
    }
    struct Song: Decodable {
        let kind: String            // "yours" | "reference"
        let audio: String?
        let startsAt: Double?
        let recordingId: String?
        let time: Date?
        let credit: String?
    }
    struct Size: Decodable {
        let label: String
        let cm: Int?
        let detail: String?
    }
    struct Tag: Decodable, Hashable {
        let kind: String
        let label: String
    }
}

/// A site the account belongs to (multi-site servers, GET /instances).
struct Site: Decodable, Identifiable, Hashable {
    let id: String
    let name: String
    let locationName: String?
}

enum Chance: String {
    case common, uncommon, rare
    var label: String { rawValue.capitalized }
}

extension JSONDecoder {
    /// Snake case, and the server's ISO times ("2026-11-03T14:05:00.123456Z").
    static let chirp: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        d.dateDecodingStrategy = .custom { decoder in
            let s = try decoder.singleValueContainer().decode(String.self)
            if let date = ChirpDate.parse(s) { return date }
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "Bad date \(s)"))
        }
        return d
    }()
}

enum ChirpDate {
    private static let fractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]; return f
    }()
    private static let plain: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime]; return f
    }()

    /// Microseconds are cut to milliseconds; a time without a zone is UTC.
    static func parse(_ s: String) -> Date? {
        var t = s
        if !(t.hasSuffix("Z") || t.contains("+") || t.dropFirst(19).contains("-")) { t += "Z" }
        if let dot = t.firstIndex(of: ".") {
            let digits = t[t.index(after: dot)...].prefix { $0.isNumber }
            let rest = t[t.index(after: dot)...].dropFirst(digits.count)
            t = String(t[..<dot]) + "." + String((digits + "000").prefix(3)) + rest
        }
        return fractional.date(from: t) ?? plain.date(from: t)
    }

    static func string(_ d: Date) -> String { fractional.string(from: d) }
}

/// GET /lite/recording/{id}/songline: the clip's loudness as bars, where each
/// bird was identified, and call marks for the chosen bird (seconds).
struct SongLine: Decodable, Equatable {
    let duration: Double
    let bird: String?
    let bars: [Double]
    let segments: [String: [[Double]]]
    let calls: [Double]

    /// Stretches where `bird` was identified.
    var spans: [ClosedRange<Double>] {
        (bird.flatMap { segments[$0] } ?? []).compactMap { $0.count == 2 && $0[1] > $0[0] ? $0[0]...$0[1] : nil }
    }
}
