import XCTest

/// Remote focus on the recording screen. Needs a signed-in session:
///   TEST_RUNNER_CHIRP_SERVER=https://… TEST_RUNNER_CHIRP_TOKEN=… xcodebuild test …
final class FocusTests: XCTestCase {
    func testRecordingScreenFocus() throws {
        let env = ProcessInfo.processInfo.environment
        guard let token = env["CHIRP_TOKEN"], let server = env["CHIRP_SERVER"] else {
            throw XCTSkip("CHIRP_TOKEN and CHIRP_SERVER not set")
        }
        let app = XCUIApplication()
        app.launchArguments = ["-ChirpScreenshots", "recording", "-ChirpServer", server,
                               "-ChirpToken", token, "-ChirpUser", env["CHIRP_USER"] ?? ""]
        app.launch()
        let remote = XCUIRemote.shared
        var n = 0
        let play = app.buttons["Play"]
        XCTAssertTrue(play.waitForExistence(timeout: 20))
        sleep(3)   // detections load

        // From the tab bar, Down lands on Play.
        remote.press(.down)
        XCTAssertTrue(play.hasFocus, "Down from the tab bar should focus Play")
        shot(app, &n)

        // Down: the spectrogram; Right twice moves the playhead to 0:10.
        remote.press(.down)
        let spectrogram = app.descendants(matching: .any)["Spectrogram"]
        XCTAssertTrue(spectrogram.hasFocus, "Down from Play should focus the spectrogram")
        remote.press(.right)
        remote.press(.right)
        XCTAssertEqual((spectrogram.value as? String)?.hasPrefix("0:10"), true, "value: \(String(describing: spectrogram.value))")
        shot(app, &n)

        // Select plays from there.
        remote.press(.select)
        XCTAssertTrue(app.buttons["Stop"].waitForExistence(timeout: 15), "Select should start playback")
        sleep(2)
        shot(app, &n)

        // Down: a species chip shows focus.
        remote.press(.down)
        let chip = app.buttons.matching(NSPredicate(format: "label CONTAINS 'best'")).firstMatch
        XCTAssertTrue(chip.exists)
        XCTAssertTrue(chip.hasFocus, "Down from the spectrogram should focus a species")
        shot(app, &n)

        // Back up through the spectrogram to Stop; Play/Pause stops.
        remote.press(.up)
        XCTAssertTrue(spectrogram.hasFocus)
        remote.press(.up)
        XCTAssertTrue(app.buttons["Stop"].hasFocus)
        remote.press(.playPause)
        XCTAssertTrue(play.waitForExistence(timeout: 5))

        // Up to the tabs, across and back, then Down: Play again.
        remote.press(.up)
        remote.press(.right)
        remote.press(.left)
        remote.press(.down)
        XCTAssertTrue(play.hasFocus, "Down from any tab should focus Play")
    }

    /// Attaches the screen, and saves it to CHIRP_SHOTS when set.
    private func shot(_ app: XCUIApplication, _ n: inout Int) {
        let s = app.screenshot()
        add(XCTAttachment(screenshot: s))
        n += 1
        if let dir = ProcessInfo.processInfo.environment["CHIRP_SHOTS"] {
            try? s.pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("focus-\(n).png"))
        }
    }
}
