import XCTest
@testable import ChirpLite

final class LiteTests: XCTestCase {
    func testDates() {
        let d = ChirpDate.parse("2026-11-03T14:05:06.123456Z")
        XCTAssertNotNil(d)
        XCTAssertEqual(ChirpDate.parse("2026-11-03T14:05:06")?.timeIntervalSince1970, ChirpDate.parse("2026-11-03T14:05:06Z")?.timeIntervalSince1970)
        XCTAssertEqual(d!.timeIntervalSince1970, ChirpDate.parse("2026-11-03T14:05:06.123Z")!.timeIntervalSince1970, accuracy: 0.001)
        XCTAssertNil(ChirpDate.parse("yesterday"))
    }

    func testToday() throws {
        let json = """
        {"date":"2026-11-03","species_count":2,"detections":4,"recordings":3,"new_count":1,
         "first_song":{"name":"Blue Jay","time":"2026-11-03T11:02:00Z"},
         "hero":{"name":"Northern Cardinal","recording_id":"r1","time":"2026-11-03T13:00:00.5Z","today":true,"has_audio":true,"profile_id":"bp-1","photo":"/api/v1/birds/bp-1/photo"},
         "species":[{"name":"Northern Cardinal","profile_id":"bp-1","photo":null,"count":3,"last":"2026-11-03T13:00:00Z","new":true}],
         "hourly":[0,0,0,0,0,0,1,2,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],"summary":null,"can_listen_live":true}
        """
        let t = try JSONDecoder.chirp.decode(Today.self, from: Data(json.utf8))
        XCTAssertEqual(t.hero?.recordingId, "r1")
        XCTAssertEqual(t.species.first?.count, 3)
        XCTAssertTrue(t.species.first?.new == true)
        XCTAssertEqual(t.hourly.count, 24)
        XCTAssertEqual(t.firstSong?.name, "Blue Jay")
    }

    func testListenGuideBird() throws {
        let listen = """
        {"recordings":[{"id":"r1","time":"2026-11-03T13:00:00Z","duration":12.0,"bird":"Blue Jay","others":["Tufted Titmouse"],
          "starts_at":2.5,"has_audio":true,"audio":"/api/v1/recordings/r1/audio","spectrogram":"/api/v1/recordings/r1/spectrogram",
          "profile_id":null,"photo":null,"other_photos":[null]}],"next_before":"2026-11-03T13:00:00Z"}
        """
        let page = try JSONDecoder.chirp.decode(SoundPage.self, from: Data(listen.utf8))
        XCTAssertEqual(page.recordings.first?.startsAt, 2.5)
        XCTAssertEqual(page.nextBefore, "2026-11-03T13:00:00Z")

        let guide = """
        {"month":"Nov","count":1,"heard":0,"birds":[{"name":"Fox Sparrow","photo":null,"chance":0.12,"likely":"uncommon","heard":false,"profile_id":"bp-9"}]}
        """
        let g = try JSONDecoder.chirp.decode(Guide.self, from: Data(guide.utf8))
        XCTAssertEqual(Chance(rawValue: g.birds[0].likely)?.label, "Uncommon")

        let bird = """
        {"id":"bp-1","name":"Northern Cardinal","scientific":"Cardinalis cardinalis","photos":[{"url":"https://x/y.jpg","credit":"A"}],
         "song":{"kind":"yours","audio":"/api/v1/recordings/r1/audio","starts_at":2,"recording_id":"r1","time":"2026-11-03T13:00:00Z"},
         "size":{"label":"Smaller than a robin","cm":22,"detail":null},"season":"All year","how_often":"Most days","heard_count":12,
         "first_heard":"2026-01-02T00:00:00Z","last_heard":null,"blurb":"Red.","fun_fact":null,"tags":[{"kind":"food","label":"Seeds"}],
         "range_map":"/api/v1/birds/bp-1/range-map/ebird_st","range_map_source":"eBird Status & Trends","range_map_vector":false,"range_map_image":"/api/v1/birds/bp-1/range-map/ebird_st","conservation":null}
        """
        let b = try JSONDecoder.chirp.decode(BirdProfile.self, from: Data(bird.utf8))
        XCTAssertEqual(b.song?.recordingId, "r1")
        XCTAssertEqual(b.size?.label, "Smaller than a robin")
        XCTAssertEqual(b.howOften, "Most days")
        XCTAssertEqual(b.rangeMapSource, "eBird Status & Trends")
        XCTAssertEqual(b.rangeMapVector, false)
        XCTAssertEqual(b.rangeMapImage, "/api/v1/birds/bp-1/range-map/ebird_st")
    }

    func testServerAndURLs() {
        XCTAssertEqual(Account.parseServer("ourchirp.com")?.absoluteString, "https://ourchirp.com")
        XCTAssertEqual(Account.parseServer("192.168.1.50:8768/")?.absoluteString, "http://192.168.1.50:8768")
        XCTAssertNil(Account.parseServer("  "))
        let s = URL(string: "https://www.ourchirp.com")!
        XCTAssertEqual(API.url("/api/v1/lite/today", server: s)?.absoluteString, "https://www.ourchirp.com/api/v1/lite/today")
        XCTAssertEqual(API.url("api/v1/lite/listen?bird=Blue%20Jay", server: s)?.absoluteString, "https://www.ourchirp.com/api/v1/lite/listen?bird=Blue%20Jay")
        XCTAssertEqual(API.url("https://inat.example/p.jpg", server: s)?.host, "inat.example")
        // The sign-in only goes to the site.
        XCTAssertNotNil(API.request("/api/v1/lite/today", server: s, token: "t")?.value(forHTTPHeaderField: "Authorization"))
        XCTAssertNil(API.request("https://inat.example/p.jpg", server: s, token: "t")?.value(forHTTPHeaderField: "Authorization"))
        XCTAssertEqual(API.query(["bird": "Blue Jay", "before": nil, "limit": "20"]), "?bird=Blue%20Jay&limit=20")
    }

    func testClaims() {
        // header.{"sub":"josh","active_instance_id":"i1"}.sig
        let jwt = "e30.eyJzdWIiOiJqb3NoIiwiYWN0aXZlX2luc3RhbmNlX2lkIjoiaTEifQ.x"
        XCTAssertEqual(Account.claims(jwt)["active_instance_id"] as? String, "i1")
        XCTAssertTrue(Account.claims("nope").isEmpty)
    }

    func testClockParts() {
        let p = Words.clockParts(Date())
        XCTAssertFalse(p.main.isEmpty)
        XCTAssertFalse(p.main.hasSuffix(" "))
    }

    func testWords() {
        let now = Date()
        XCTAssertEqual(Words.when(now.addingTimeInterval(-30), now: now), "Just now")
        if Calendar.current.isDate(now.addingTimeInterval(-600), inSameDayAs: now) {
            XCTAssertEqual(Words.when(now.addingTimeInterval(-600), now: now), "10 min ago")
        }
        XCTAssertEqual(Words.count(1, "time"), "1 time")
        XCTAssertEqual(Words.count(3, "time"), "3 times")
    }
}

final class CreditTests: XCTestCase {
    func testCleanCredit() {
        XCTAssertEqual(Words.credit("(c) Donna Pomeroy, some rights reserved"), "Donna Pomeroy, some rights reserved")
        XCTAssertEqual(Words.credit("© Sam"), "Sam")
        XCTAssertEqual(Words.credit("Sam"), "Sam")
    }

    func testSongLine() throws {
        let json = """
        {"duration":35.1,"bird":"Tufted Titmouse","bars":[0.1,0.9,0.2],
         "segments":{"Tufted Titmouse":[[0.0,12.5],[20.0,32.5]],"Blue Jay":[[0.0,5.0]]},"calls":[]}
        """
        let l = try JSONDecoder.chirp.decode(SongLine.self, from: Data(json.utf8))
        XCTAssertEqual(l.spans, [0...12.5, 20...32.5])
        XCTAssertEqual(l.segments["Blue Jay"]?.first, [0, 5])
        // A tap jumps to that point of the clip.
        XCTAssertEqual(SongLineView.target(x: 32, width: 351, line: l), 3.2, accuracy: 0.001)
        XCTAssertEqual(SongLineView.target(x: 175.5, width: 351, line: l), 17.55, accuracy: 0.01)
        XCTAssertEqual(SongLineView.target(x: -5, width: 351, line: l), 0)
    }
}
