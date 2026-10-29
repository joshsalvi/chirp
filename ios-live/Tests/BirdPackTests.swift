import UIKit
import XCTest
@testable import ChirpLive

final class BirdPackTests: XCTestCase {
    private func pack(_ jpeg: Data) throws -> Data {
        let index: [String: Any] = ["version": 1, "made": "2026-10-28T12:00:00+00:00", "species": [
            ["sci": "Cardinalis cardinalis", "common": "Northern Cardinal", "code": "norcar",
             "credit": "(c) A (CC BY)", "license": "cc-by", "source": "https://www.inaturalist.org/photos/1",
             "offset": 0, "length": jpeg.count],
            ["sci": "Strix varia", "common": "Barred Owl", "code": "brdowl"],
        ]]
        let head = try JSONSerialization.data(withJSONObject: index)
        var d = Data("CHIRPPK1".utf8)
        let n = UInt32(head.count).bigEndian
        withUnsafeBytes(of: n) { d.append(contentsOf: $0) }
        d.append(head); d.append(jpeg)
        return d
    }

    @MainActor
    func testPackLoadsPicturesAndLinks() throws {
        let img = UIGraphicsImageRenderer(size: CGSize(width: 40, height: 30)).image { c in
            UIColor.red.setFill(); c.fill(CGRect(x: 0, y: 0, width: 40, height: 30))
        }
        let jpeg = try XCTUnwrap(img.jpegData(compressionQuality: 0.8))
        let p = BirdPack.shared
        try p.install(try pack(jpeg), northAmerica: true)
        defer { p.remove() }
        XCTAssertEqual(p.entries.count, 2)
        XCTAssertEqual(p.pictures, 1)
        XCTAssertNotNil(p.image("Cardinalis cardinalis"))
        XCTAssertNil(p.image("Strix varia"))
        let titles = p.links(sci: "Cardinalis cardinalis", common: "Northern Cardinal").map(\.title)
        XCTAssertEqual(titles, ["eBird", "All About Birds", "Macaulay Library", "Wikipedia"])
        XCTAssertEqual(p.links(sci: "Cardinalis cardinalis", common: "Northern Cardinal")[1].url.absoluteString,
                       "https://www.allaboutbirds.org/guide/Northern_Cardinal")
        try p.install(try pack(jpeg), northAmerica: false)
        XCTAssertFalse(p.links(sci: "Strix varia", common: "Barred Owl").map(\.title).contains("All About Birds"))
    }
}

final class SessionTitleTests: XCTestCase {
    private func session(hour: Int, minutes: Double, distance: Double?, birds: [String], place: String? = nil, station: String? = nil) -> Session {
        var c = DateComponents(); c.year = 2026; c.month = 10; c.day = 28; c.hour = hour
        let start = Calendar.current.date(from: c)!
        let heard = birds.enumerated().map { Heard(id: $0.offset, common: $0.element, scientific: $0.element, count: 1, best: 0.8,
                                                   first: start, last: start) }
        var s = Session(id: "t", start: start, end: start.addingTimeInterval(minutes * 60), place: place,
                        stationName: station, heard: heard)
        s.distance = distance
        return s
    }

    func testTitles() {
        let five = ["A", "B", "C", "D", "E"]
        XCTAssertEqual(Session.makeTitle(session(hour: 15, minutes: 40, distance: 1200, birds: five, place: "Broadmoor")), "Afternoon walk in Broadmoor")
        XCTAssertEqual(Session.makeTitle(session(hour: 9, minutes: 20, distance: 400, birds: five)), "Morning stroll")
        XCTAssertEqual(Session.makeTitle(session(hour: 8, minutes: 90, distance: 5200, birds: five)), "Morning hike")
        XCTAssertEqual(Session.makeTitle(session(hour: 5, minutes: 30, distance: 0, birds: five)), "Dawn chorus")
        XCTAssertEqual(Session.makeTitle(session(hour: 22, minutes: 30, distance: 0, birds: ["Barred Owl"])), "Owl watch")
        XCTAssertEqual(Session.makeTitle(session(hour: 22, minutes: 30, distance: 900, birds: ["Barred Owl"])), "Owl prowl")
        XCTAssertEqual(Session.makeTitle(session(hour: 18, minutes: 30, distance: nil, birds: ["A"], station: "ChirpPi")), "Quiet evening")
        XCTAssertEqual(Session.makeTitle(session(hour: 15, minutes: 30, distance: nil, birds: ["A", "B"], station: "ChirpPi")), "Afternoon listen")
        XCTAssertEqual(session(hour: 15, minutes: 30, distance: nil, birds: ["A"], station: "ChirpPi").whereLine, "Via ChirpPi")
        XCTAssertEqual(Session.makeTitle(session(hour: 12, minutes: 30, distance: 0, birds: ["A"])), "Quiet midday")
        XCTAssertEqual(Session.makeTitle(session(hour: 17, minutes: 3, distance: 0, birds: ["A", "B"])), "Quick evening listen")
        var s = session(hour: 15, minutes: 40, distance: 0, birds: five)
        s.name = "Walk with Annie"
        XCTAssertEqual(s.title, "Walk with Annie")
    }
}
