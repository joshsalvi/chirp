import AVFoundation
import Combine
import CoreLocation
import Foundation
import WatchKit

/// One species heard during this session.
struct Heard: Identifiable {
    let name: String
    var scientific: String
    var best: Double
    var count: Int
    var last: Date
    var id: String { name }
}

/// Live Detect on the watch: records the microphone, sends overlapping
/// clips to POST /api/v1/live-detect/analyze (the same endpoint as the
/// phone's Live Detect) and lists what comes back. A clip with a bird
/// becomes a recording on the site, as it does from the phone.
@MainActor
final class LiveSession: NSObject, ObservableObject, CLLocationManagerDelegate {
    enum State: Equatable { case idle, starting, listening, failed(String) }

    @Published private(set) var state: State = .idle
    @Published private(set) var heard: [Heard] = []
    @Published private(set) var clipsSent = 0
    @Published private(set) var problem: String?   // shown while listening; clears on the next good reply
    @Published private(set) var level: Float = 0   // 0…1, for the meter

    // Each clip is `window` seconds; a new one starts every `hop` seconds, so
    // a call that falls on a boundary is whole in the next clip.
    private let window = 4.0
    private let hop = 3.0
    private let sampleRate = 32_000.0   // BirdNET listens up to 15 kHz

    private let engine = AVAudioEngine()
    private let collector = SampleCollector()
    private var timer: Timer?
    private var inFlight = 0
    private let maxInFlight = 2
    private var location: CLLocation?
    private let locator = CLLocationManager()

    override init() {
        super.init()
        locator.delegate = self
        locator.desiredAccuracy = kCLLocationAccuracyHundredMeters
    }

    var listening: Bool { state == .listening || state == .starting }

    func toggle() {
        listening ? stop() : start()
    }

    func start() {
        guard !listening else { return }
        state = .starting
        problem = nil
        AVAudioApplication.requestRecordPermission { granted in
            Task { @MainActor in
                guard granted else {
                    self.state = .failed("Microphone access is off. Turn it on in Settings → Privacy → Microphone on the watch.")
                    return
                }
                self.begin()
            }
        }
    }

    func stop() {
        timer?.invalidate()
        timer = nil
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        collector.reset()
        level = 0
        if listening { state = .idle }
        WKInterfaceDevice.current().play(.stop)
    }

    func clear() {
        heard = []
        clipsSent = 0
    }

    private func begin() {
        do {
            let audio = AVAudioSession.sharedInstance()
            try audio.setCategory(.record, mode: .measurement, options: [])
            try audio.setActive(true)

            let input = engine.inputNode
            let inFormat = input.outputFormat(forBus: 0)
            guard inFormat.sampleRate > 0,
                  collector.prepare(from: inFormat, sampleRate: sampleRate, seconds: window) else {
                throw NSError(domain: "Chirp", code: 1, userInfo: [NSLocalizedDescriptionKey: "No microphone input"])
            }
            collector.onLevel = { [weak self] lvl in
                Task { @MainActor in
                    guard let self else { return }
                    self.level = max(lvl, self.level * 0.6)
                }
            }
            let collector = self.collector
            input.installTap(onBus: 0, bufferSize: 4096, format: inFormat) { buffer, _ in
                collector.receive(buffer)
            }
            engine.prepare()
            try engine.start()
        } catch {
            state = .failed("Couldn't start the microphone: \(error.localizedDescription)")
            return
        }
        state = .listening
        WKInterfaceDevice.current().play(.start)
        if locator.authorizationStatus == .notDetermined { locator.requestWhenInUseAuthorization() }
        locator.requestLocation()
        timer = Timer.scheduledTimer(withTimeInterval: hop, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.sendClip() }
        }
    }

    private func sendClip() {
        guard state == .listening else { return }
        let samples = collector.snapshot()
        guard samples.count >= Int(window * sampleRate * 0.9) else { return }
        // On a slow link, skip a clip rather than fall further behind.
        guard inFlight < maxInFlight else { return }
        guard let server = Account.shared.server else {
            stop()
            state = .failed("Sign in on your iPhone first.")
            return
        }
        let wav = WAV.encode(samples, sampleRate: Int(sampleRate))
        let token = Account.shared.token
        let here = location
        inFlight += 1
        Task {
            defer { inFlight -= 1 }
            do {
                let found = try await Analyzer.analyze(wav: wav, server: server, token: token, location: here)
                clipsSent += 1
                problem = nil
                record(found)
            } catch Analyzer.Failure.signedOut {
                problem = "Signed out. Open Chirp on your iPhone."
                Account.shared.tokenRejected()
            } catch {
                problem = Analyzer.describe(error)
            }
        }
    }

    private func record(_ found: [Analyzer.Detection]) {
        guard !found.isEmpty else { return }
        var newSpecies = false
        let now = Date()
        for d in found {
            if let i = heard.firstIndex(where: { $0.name == d.common_name }) {
                heard[i].count += 1
                heard[i].best = max(heard[i].best, d.confidence)
                heard[i].last = now
            } else {
                heard.append(Heard(name: d.common_name, scientific: d.scientific_name ?? "",
                                   best: d.confidence, count: 1, last: now))
                newSpecies = true
            }
        }
        heard.sort { $0.last > $1.last }
        WKInterfaceDevice.current().play(newSpecies ? .notification : .click)
    }

    // MARK: CLLocationManagerDelegate

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        let loc = locations.last
        Task { @MainActor in self.location = loc }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {}

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        if status == .authorizedWhenInUse || status == .authorizedAlways { manager.requestLocation() }
    }
}

/// Audio-thread side: converts the microphone to mono 16-bit at the
/// clip rate and keeps the last `seconds` of it for the main thread to read.
final class SampleCollector: @unchecked Sendable {
    private let lock = NSLock()
    private var buf: [Int16] = []
    private var capacity = 0
    private var converter: AVAudioConverter?
    var onLevel: ((Float) -> Void)?

    func prepare(from input: AVAudioFormat, sampleRate: Double, seconds: Double) -> Bool {
        guard let out = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: sampleRate, channels: 1, interleaved: true),
              let conv = AVAudioConverter(from: input, to: out) else { return false }
        lock.lock(); defer { lock.unlock() }
        converter = conv
        capacity = Int(sampleRate * seconds)
        buf.removeAll(keepingCapacity: true)
        return true
    }

    func receive(_ buffer: AVAudioPCMBuffer) {
        lock.lock()
        let conv = converter
        lock.unlock()
        guard let conv, buffer.frameLength > 0 else { return }
        let ratio = conv.outputFormat.sampleRate / buffer.format.sampleRate
        guard let out = AVAudioPCMBuffer(pcmFormat: conv.outputFormat,
                                         frameCapacity: AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 64)
        else { return }
        var fed = false
        var err: NSError?
        _ = conv.convert(to: out, error: &err) { _, status in
            if fed { status.pointee = .noDataNow; return nil }
            fed = true
            status.pointee = .haveData
            return buffer
        }
        guard err == nil, let p = out.int16ChannelData?[0], out.frameLength > 0 else { return }
        let samples = UnsafeBufferPointer(start: p, count: Int(out.frameLength))
        var peak = 0
        for v in samples { peak = max(peak, abs(Int(v))) }
        lock.lock()
        buf.append(contentsOf: samples)
        if capacity > 0, buf.count > capacity { buf.removeFirst(buf.count - capacity) }
        lock.unlock()
        onLevel?(Float(min(peak, Int(Int16.max))) / Float(Int16.max))
    }

    func snapshot() -> [Int16] {
        lock.lock(); defer { lock.unlock() }
        return buf
    }

    func reset() {
        lock.lock(); defer { lock.unlock() }
        buf.removeAll(keepingCapacity: true)
    }
}
