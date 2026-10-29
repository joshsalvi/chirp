import AVFoundation
import CoreLocation
import Foundation

/// One species heard in a session.
struct Heard: Identifiable, Codable, Hashable {
    var id: Int                 // index into BirdNET.species
    var common: String
    var scientific: String
    var count: Int              // 3 s windows it was heard in
    var best: Double
    var first: Date
    var last: Date
    var clip: String?           // file name of its best window, in the session folder
}

/// The whole session's audio as AAC, written as it's heard.
final class SessionRecorder: @unchecked Sendable {
    private var file: AVAudioFile?
    private var url: URL?
    private let lock = NSLock()

    func begin() {
        lock.lock(); defer { lock.unlock() }
        let u = FileManager.default.temporaryDirectory.appendingPathComponent("session-\(UUID().uuidString).m4a")
        file = try? AVAudioFile(forWriting: u, settings: AAC.settings(BirdNET.sampleRate),
                                commonFormat: .pcmFormatFloat32, interleaved: false)
        url = file == nil ? nil : u
    }

    func write(_ buffer: AVAudioPCMBuffer) {
        lock.lock(); defer { lock.unlock() }
        try? file?.write(from: buffer)
    }

    /// Closes the file and returns it.
    func finish() -> URL? {
        lock.lock(); defer { lock.unlock() }
        file = nil
        defer { url = nil }
        return url
    }
}

/// Listens through the iPhone microphone, or a Chirp station when signed in,
/// and names birds with BirdNET on the phone: it scores 3 s windows of sound,
/// every 1.5 s from the microphone and twice per station clip.
@MainActor
final class Listener: ObservableObject {
    enum State: Equatable { case idle, starting, listening, failed(String) }
    enum Source: Hashable { case phone, station(Remote.Station) }

    @Published var source: Source = .phone
    @Published private(set) var stations: [Remote.Station] = []
    @Published private(set) var placeName: String?

    @Published private(set) var state: State = .idle
    @Published private(set) var heard: [Heard] = []          // most recent first
    @Published private(set) var singing: Heard?              // heard in the last few seconds
    @Published private(set) var levels: [Float] = Array(repeating: 0, count: 48)
    @Published private(set) var started: Date?
    @Published private(set) var usingLocation = false

    /// Lowest score that counts as heard (Settings).
    var minConfidence: Double = 0.3

    private let engine = AVAudioEngine()
    private let ring = AudioRing(capacity: BirdNET.windowSamples)
    private let work = DispatchQueue(label: "chirp.live.birdnet", qos: .userInitiated)
    private var model: BirdNET?
    private var allowed: Set<Int>?
    private var busy = false
    private var clips: [Int: [Float]] = [:]
    private let locator = LocationOnce()
    private let recorder = SessionRecorder()
    private let playEngine = AVAudioEngine()
    private let player = AVAudioPlayerNode()
    private var stationTask: Task<Void, Never>?
    private var stitcher = StationStitcher()
    private var stationSinceAnalysis = 0
    /// Station playback keeps a reserve so late answers don't cut the sound:
    /// it starts once `reserveTarget` seconds are queued, and if the reserve
    /// ever runs out it pauses, waits for a bigger reserve, and carries on.
    private var queuedSeconds = 0.0
    private var reserveTarget = 3.5
    private var stationPlaying = false
    private var answerTimes: [Double] = []      // recent request times, for diagnostics
    /// Phone sessions: how far the phone moved (for titles like "Morning walk").
    private var trackTask: Task<Void, Never>?
    private var lastFix: CLLocation?
    private(set) var distance: Double = 0
    /// Signed in: the site's recording ids for clips it heard a bird in too.
    private var remoteIDs: [String] = []
    private var uploading = 0
    @Published private(set) var sentToSite = 0

    var listening: Bool { state == .listening || state == .starting }

    func start() {
        guard !listening else { return }
        state = .starting
        heard = []; singing = nil; clips = [:]; levels = Array(repeating: 0, count: 48); placeName = nil
        remoteIDs = []; sentToSite = 0; distance = 0; lastFix = nil
        if case .station(let st) = source {
            startStation(st)
            return
        }
        Task {
            guard await AVAudioApplication.requestRecordPermission() else {
                state = .failed("Chirp Live needs the microphone. Turn it on in Settings → Chirp Live."); DiagLog.note("listen: \(self.state)")
                return
            }
            do {
                if model == nil { model = try await Task.detached(priority: .userInitiated) { try BirdNET() }.value }
                try startEngine()
                ClipPlayer.listenerActive = true
                started = Date()
                state = .listening
                await applyLocation()
                startTracking()
            } catch {
                state = .failed("Couldn't start listening: \(error.localizedDescription)"); DiagLog.note("listen: \(self.state)")
            }
        }
    }

    /// Stops and returns the session, or nil when nothing was heard.
    @discardableResult
    func stop() -> Session? {
        guard listening else { return nil }
        if stationTask != nil {
            stationTask?.cancel(); stationTask = nil
            stationPlaying = false
            playEngine.mainMixerNode.removeTap(onBus: 0)
            player.stop(); playEngine.stop()
        } else {
            engine.inputNode.removeTap(onBus: 0)
            engine.stop()
        }
        ClipPlayer.listenerActive = false
        trackTask?.cancel(); trackTask = nil
        let audio = recorder.finish()
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        state = .idle
        singing = nil
        guard let started, !heard.isEmpty else {
            if let audio { try? FileManager.default.removeItem(at: audio) }
            return nil
        }
        let store = SessionStore.shared
        var station: Remote.Station?
        if case .station(let st) = source { station = st }
        let session = store.save(start: started, end: Date(), heard: heard, clips: clips, audio: audio,
                                 place: locator.lastPlace, placeName: placeName, station: station,
                                 remoteIDs: Account.shared.signedIn ? remoteIDs : nil, distance: station == nil ? distance : nil)
        return session   // saved to the site once its sound is ready (SessionStore.save)
    }

    private func startEngine() throws {
        let session = AVAudioSession.sharedInstance()
        // playAndRecord so a clip can be played while listening (ClipPlayer).
        try session.setCategory(.playAndRecord, mode: .measurement, options: [.defaultToSpeaker, .allowBluetoothA2DP])
        try session.setActive(true)
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0,
              let target = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: BirdNET.sampleRate, channels: 1, interleaved: false),
              let converter = AVAudioConverter(from: format, to: target) else {
            throw NSError(domain: "ChirpLive", code: 1, userInfo: [NSLocalizedDescriptionKey: "No microphone input."])
        }
        ring.reset()
        recorder.begin()
        let ring = ring, recorder = recorder
        let hop = BirdNET.windowSamples / 2
        var sinceLast = 0
        input.installTap(onBus: 0, bufferSize: 4096, format: format) { [weak self] buffer, _ in
            let ratio = BirdNET.sampleRate / format.sampleRate
            let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 64
            guard let out = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: capacity) else { return }
            var fed = false
            var err: NSError?
            converter.convert(to: out, error: &err) { _, status in
                if fed { status.pointee = .noDataNow; return nil }
                fed = true; status.pointee = .haveData; return buffer
            }
            guard err == nil, let ch = out.floatChannelData?[0], out.frameLength > 0 else { return }
            let samples = Array(UnsafeBufferPointer(start: ch, count: Int(out.frameLength)))
            ring.append(samples)
            recorder.write(out)
            sinceLast += samples.count
            var rms: Float = 0
            for s in samples { rms += s * s }
            rms = (rms / Float(samples.count)).squareRoot()
            let window: [Float]? = (sinceLast >= hop && ring.isFull) ? ring.snapshot() : nil
            if window != nil { sinceLast = 0 }
            Task { @MainActor [weak self] in
                self?.push(level: rms)
                if let window { self?.analyze(window) }
            }
        }
        engine.prepare()
        try engine.start()
    }

    // MARK: Through a station

    /// Stations on the signed-in site (refreshed when the Listen tab opens).
    func loadStations() async {
        #if DEBUG
        if Screenshots.scene != nil { return }
        #endif
        let account = Account.shared
        guard account.signedIn, let token = account.token else {
            stations = []; if case .station = source { source = .phone }; return
        }
        do {
            let list = try await Remote.stations(server: account.server, token: token)
            stations = list
            if case .station(let st) = source, !list.contains(where: { $0.id == st.id }) { source = .phone }
        } catch Remote.Failure.signedOut {
            account.rejected(); stations = []
        } catch {
            // Keep the last list.
        }
    }

    /// Fetches the station's clips back to back, plays them and scores each.
    private func startStation(_ st: Remote.Station) {
        let account = Account.shared
        guard account.signedIn, let token = account.token else {
            state = .failed("Sign in to your Chirp site to listen through a station."); DiagLog.note("listen: \(self.state)"); return
        }
        let server = account.server
        Task {
            do {
                if model == nil { model = try await Task.detached(priority: .userInitiated) { try BirdNET() }.value }
                let session = AVAudioSession.sharedInstance()
                try session.setCategory(.playback, mode: .default)
                try session.setActive(true)
                guard let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: BirdNET.sampleRate,
                                                 channels: 1, interleaved: false) else { return }
                if player.engine == nil { playEngine.attach(player) }
                playEngine.connect(player, to: playEngine.mainMixerNode, format: format)
                // Level bars from the sound as it plays, so they move smoothly.
                playEngine.mainMixerNode.removeTap(onBus: 0)
                playEngine.mainMixerNode.installTap(onBus: 0, bufferSize: 2048, format: nil) { [weak self] buffer, _ in
                    guard let ch = buffer.floatChannelData?[0], buffer.frameLength > 0 else { return }
                    var sum: Float = 0
                    for i in 0..<Int(buffer.frameLength) { sum += ch[i] * ch[i] }
                    let rms = (sum / Float(buffer.frameLength)).squareRoot()
                    Task { @MainActor [weak self] in
                        guard let self, self.stationPlaying else { return }
                        self.push(level: rms)
                    }
                }
                try playEngine.start()
                ClipPlayer.listenerActive = true
                queuedSeconds = 0; reserveTarget = 3.5; stationPlaying = false; answerTimes = []
                recorder.begin()
                ring.reset(); stitcher.reset(); stationSinceAnalysis = 0
                started = Date()
                state = .listening
                Task { await applyLocation() }
                stationTask = Task { [weak self] in
                    var failures = 0
                    var next = Date()
                    var lastAsked: Date?
                    while !Task.isCancelled {
                        do {
                            // The station answers at once with the last few seconds it
                            // heard. Ask every second and keep only what's new
                            // (StationStitcher), so playback is continuous and the
                            // saved session is as long as the listening.
                            let wait = next.timeIntervalSinceNow
                            if wait > 0 { try await Task.sleep(for: .seconds(wait)) }
                            let asked = Date()
                            next = asked.addingTimeInterval(1)
                            let wav = try await Remote.listen(st, server: server, token: token)
                            await self?.noteAnswer(Date().timeIntervalSince(asked))
                            failures = 0
                            guard !Task.isCancelled else { break }
                            let expected = lastAsked.map { Int(asked.timeIntervalSince($0) * BirdNET.sampleRate) } ?? .max
                            lastAsked = asked
                            await self?.take(wav, expected: expected, format: format)
                        } catch Remote.Failure.signedOut {
                            Account.shared.rejected()
                            self?.state = .failed("Your sign-in has ended. Sign in again in Settings."); DiagLog.note("listen: \(String(describing: self?.state))")
                            break
                        } catch {
                            failures += 1
                            if failures >= 3 {
                                self?.state = .failed("Can't hear \(st.name): \(error.localizedDescription)"); DiagLog.note("listen: \(String(describing: self?.state))")
                                break
                            }
                            try? await Task.sleep(for: .seconds(1))
                        }
                    }
                }
            } catch {
                state = .failed("Couldn't start: \(error.localizedDescription)"); DiagLog.note("listen: \(self.state)")
            }
        }
    }

    /// One station clip: keep only the sound not heard yet, play it, save it,
    /// show its level, and score a 3 s window every 1.5 s like the phone mic.
    private func take(_ wav: Data, expected: Int, format: AVAudioFormat) async {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("st-\(UUID().uuidString).wav")
        defer { try? FileManager.default.removeItem(at: url) }
        guard (try? wav.write(to: url)) != nil, let clip = try? WAV.read(url), clip.count > 4_800 else { return }
        let samples = stitcher.newPart(of: clip, expected: expected)
        guard !samples.isEmpty,
              let buf = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(samples.count)),
              let ch = buf.floatChannelData?[0] else { return }
        buf.frameLength = AVAudioFrameCount(samples.count)
        samples.withUnsafeBufferPointer { ch.update(from: $0.baseAddress!, count: samples.count) }
        let seconds = Double(samples.count) / BirdNET.sampleRate
        queuedSeconds += seconds
        player.scheduleBuffer(buf, completionCallbackType: .dataPlayedBack) { [weak self] _ in
            Task { @MainActor [weak self] in self?.played(seconds) }
        }
        if !stationPlaying, queuedSeconds >= reserveTarget {
            stationPlaying = true
            player.play()
        }
        recorder.write(buf)
        ring.append(samples)
        stationSinceAnalysis += samples.count
        if ring.isFull, stationSinceAnalysis >= BirdNET.windowSamples / 2 {
            stationSinceAnalysis = 0
            analyze(ring.snapshot())
        }
    }

    /// A station buffer finished playing. Out of sound: pause and build a
    /// bigger reserve rather than stutter.
    private func played(_ seconds: Double) {
        queuedSeconds = max(0, queuedSeconds - seconds)
        guard stationTask != nil, stationPlaying, queuedSeconds < 0.05 else { return }
        stationPlaying = false
        player.pause()
        reserveTarget = min(9, reserveTarget + 1.5)
        let recent = answerTimes.suffix(5).map { String(format: "%.1f", $0) }.joined(separator: ", ")
        DiagLog.note("station sound ran out; waiting for \(reserveTarget) s. Recent answers took \(recent) s")
    }

    private func noteAnswer(_ seconds: Double) {
        answerTimes.append(seconds)
        if answerTimes.count > 20 { answerTimes.removeFirst() }
    }

    private func push(level rms: Float) {
        // Roughly -60...0 dBFS → 0...1
        let db = 20 * log10(max(rms, 1e-6))
        levels.removeFirst()
        levels.append(min(1, max(0, (db + 60) / 60)))
    }

    private func analyze(_ window: [Float]) {
        guard !busy, let model else { return }
        busy = true
        let allowed = allowed, minimum = Float(minConfidence)
        work.async { [weak self] in
            let found: [(Int, Float)] = (try? model.scores(window))?.enumerated()
                .filter { $0.element >= minimum && (allowed?.contains($0.offset) ?? true) }
                .map { ($0.offset, $0.element) }
                .sorted { $0.1 > $1.1 } ?? []
            Task { @MainActor [weak self] in
                self?.busy = false
                self?.record(found, window: window)
            }
        }
    }

    private func record(_ found: [(Int, Float)], window: [Float]) {
        guard state == .listening, let model else { return }
        let now = Date()
        for (i, score) in found {
            let s = Double(score)
            if let k = heard.firstIndex(where: { $0.id == i }) {
                var h = heard.remove(at: k)
                h.count += 1; h.last = now
                if s > h.best { h.best = s; clips[i] = window }
                heard.insert(h, at: 0)
            } else {
                let sp = model.species[i]
                heard.insert(Heard(id: i, common: sp.common, scientific: sp.scientific, count: 1, best: s,
                                   first: now, last: now), at: 0)
                BirdPack.shared.wantPicture(sci: sp.scientific)
                clips[i] = window
            }
        }
        if !found.isEmpty { sendToSite(window) }
        if let top = found.first, let h = heard.first(where: { $0.id == top.0 }) {
            singing = h
        } else if let s = singing, now.timeIntervalSince(s.last) > 6 {
            singing = nil
        }
    }

    /// Signed in: the site checks the clip too and keeps it for the session.
    private func sendToSite(_ window: [Float]) {
        let account = Account.shared
        guard account.signedIn, let token = account.token, uploading < 2 else { return }
        uploading += 1
        let server = account.server, place = locator.lastPlace, name = placeName
        var stationID: String?
        if case .station(let st) = source { stationID = st.id }
        Task {
            defer { uploading -= 1 }
            do {
                if let id = try await Remote.analyze(window, server: server, token: token,
                                                     lat: place?.coordinate.latitude, lon: place?.coordinate.longitude,
                                                     place: name, station: stationID) {
                    remoteIDs.append(id)
                    sentToSite = remoteIDs.count
                }
            } catch Remote.Failure.signedOut {
                account.rejected()
            } catch {
                // A dropped clip only means one fewer on the site.
            }
        }
    }

    /// A location fix every minute while listening, adding up the distance.
    private func startTracking() {
        trackTask?.cancel()
        trackTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(60))
                guard let self, self.listening, !Task.isCancelled else { return }
                self.addFix(await self.locator.place())
            }
        }
    }

    private func addFix(_ p: CLLocation?) {
        guard let p, p.horizontalAccuracy >= 0, p.horizontalAccuracy < 100 else { return }
        if let last = lastFix {
            let d = p.distance(from: last)
            guard d > 25 else { return }      // GPS wander, not a step
            distance += d
        }
        lastFix = p
    }

    private func applyLocation() async {
        guard let place = await locator.place(), let model else { return }
        addFix(place)
        if case .phone = source { placeName = await Self.placeName(for: place) }
        let set = await Task.detached { try? model.likely(latitude: place.coordinate.latitude, longitude: place.coordinate.longitude) }.value
        if let set, !set.isEmpty { allowed = set; usingLocation = true }
    }
}

#if DEBUG
extension Listener {
    /// App Store screenshots: a session in progress.
    func demo(heard: [Heard], singing: Heard?, place: String?, stations: [Remote.Station], source: Source, sent: Int) {
        self.heard = heard; self.singing = singing; self.placeName = place
        self.stations = stations; self.source = source; self.sentToSite = sent
        started = Date().addingTimeInterval(-192)
        state = .listening
        var r = SystemRandomNumberGenerator()
        levels = (0..<48).map { i in
            let burst = (i % 11 > 5) ? Float.random(in: 0.55...0.92, using: &r) : Float.random(in: 0.18...0.42, using: &r)
            return burst
        }
    }
}
#endif

extension Listener {
    /// A short name for where the phone is: a park or landmark, else the
    /// neighborhood or town ("Broadmoor Wildlife Sanctuary", "Natick").
    static func placeName(for loc: CLLocation) async -> String? {
        guard let p = try? await CLGeocoder().reverseGeocodeLocation(loc).first else { return nil }
        return p.areasOfInterest?.first ?? p.subLocality ?? p.locality ?? p.administrativeArea
    }
}

/// The last `capacity` samples, shared between the audio thread and the app.
final class AudioRing: @unchecked Sendable {
    private var data: [Float]
    private var count = 0
    private let lock = NSLock()
    init(capacity: Int) { data = []; data.reserveCapacity(capacity * 2); self.capacity = capacity }
    let capacity: Int
    var isFull: Bool { lock.lock(); defer { lock.unlock() }; return count >= capacity }
    func reset() { lock.lock(); data.removeAll(keepingCapacity: true); count = 0; lock.unlock() }
    func append(_ s: [Float]) {
        lock.lock(); defer { lock.unlock() }
        data.append(contentsOf: s)
        if data.count > capacity { data.removeFirst(data.count - capacity) }
        count = data.count
    }
    func snapshot() -> [Float] { lock.lock(); defer { lock.unlock() }; return data }
}

/// One location fix for the species list; remembers the last one for when
/// there's no fix (indoors, airplane mode).
@MainActor
final class LocationOnce: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private var waiting: [CheckedContinuation<CLLocation?, Never>] = []
    private(set) var lastPlace: CLLocation? = {
        let d = UserDefaults.standard
        guard d.object(forKey: "lastLat") != nil else { return nil }
        return CLLocation(latitude: d.double(forKey: "lastLat"), longitude: d.double(forKey: "lastLon"))
    }()

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyKilometer
    }

    func place() async -> CLLocation? {
        switch manager.authorizationStatus {
        case .denied, .restricted: return lastPlace
        case .notDetermined: manager.requestWhenInUseAuthorization()
        default: break
        }
        return await withCheckedContinuation { c in
            waiting.append(c)
            manager.requestLocation()
            Task { [weak self] in
                try? await Task.sleep(for: .seconds(10))
                self?.finish(nil)
            }
        }
    }

    private func finish(_ loc: CLLocation?) {
        if let loc {
            lastPlace = loc
            UserDefaults.standard.set(loc.coordinate.latitude, forKey: "lastLat")
            UserDefaults.standard.set(loc.coordinate.longitude, forKey: "lastLon")
        }
        let w = waiting; waiting = []
        w.forEach { $0.resume(returning: loc ?? lastPlace) }
    }

    nonisolated func locationManager(_ m: CLLocationManager, didUpdateLocations locs: [CLLocation]) {
        Task { @MainActor in self.finish(locs.last) }
    }
    nonisolated func locationManager(_ m: CLLocationManager, didFailWithError error: Error) {
        Task { @MainActor in self.finish(nil) }
    }
    nonisolated func locationManagerDidChangeAuthorization(_ m: CLLocationManager) {
        Task { @MainActor in
            if m.authorizationStatus == .authorizedWhenInUse || m.authorizationStatus == .authorizedAlways, !self.waiting.isEmpty {
                m.requestLocation()
            } else if m.authorizationStatus == .denied { self.finish(nil) }
        }
    }
}
