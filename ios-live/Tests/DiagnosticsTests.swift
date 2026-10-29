import XCTest
@testable import ChirpLive

final class DiagnosticsTests: XCTestCase {
    @MainActor
    func testReportHasSectionsAndNoSecrets() throws {
        DiagLog.note("test problem")
        let r = Diagnostics.report(listener: Listener(), store: .shared, account: .shared)
        for section in ["== App ==", "== Device ==", "== Permissions and sound ==", "== Chirp site ==", "== Sessions ==", "== Recent problems =="] {
            XCTAssertTrue(r.contains(section), section)
        }
        XCTAssertTrue(r.contains("test problem"))
        if let token = Account.shared.token { XCTAssertFalse(r.contains(token)) }
        let url = try XCTUnwrap(Diagnostics.file(listener: Listener(), store: .shared, account: .shared))
        XCTAssertTrue(try String(contentsOf: url, encoding: .utf8).hasPrefix("Chirp Live diagnostics"))
    }
}
