import Accelerate
import AVFoundation
import SwiftUI

/// Live Detect through a station: the station's microphone plays on the TV
/// with a scrolling spectrogram, and birds appear as they're identified.
/// Audio: GET /tv/listen/{id} (a few seconds of WAV at a time, played back to
/// back). Identification: POST /live-detect/analyze (source=device), in a loop.
@MainActor
final class LiveSession: ObservableObject {
    struct Station: Decodable, Identifiable, Hashable { let id: String; let name: String; let online: Bool; let mic: String }
    struct Heard: Identifiable { let name: String; var count: Int; var best: Double; let photo: String?; var last: Date; var id: String { name } }
    private struct Analyze: Decodable {
        let detected: Bool
        let detections: [Det]
        struct Det: Decodable { let commonName: String; let confidence: Double; let photoUrl: String? }
    }

    @Published var stations: [Station] = []
    @Published var station: Station?
    @Published private(set) var listening = false
    @Published private(set) var status = "Pick a station, then Listen."
    @Published private(set) var heard: [Heard] = []
    @Published private(set) var latest: Heard?
    @Published var error: String?
    @Published private(set) var image: CGImage?

    private let engine = AVAudioEngine()
    private let node = AVAudioPlayerNode()
    private var connectedFormat: AVAudioFormat?
    private var tasks: [Task<Void, Never>] = []
    private let spectro = Spectrogram()
    private var frameTimer: Timer?

    init() { engine.attach(node) }

    func loadStations() async {
        do {
            stations = try await API.get("api/v1/tv/stations")
            if station == nil || !stations.contains(where: { $0.id == station?.id }) {
                station = stations.first(where: \.online) ?? stations.first
            }
            error = stations.isEmpty ? "No stations with a bird microphone on this site." : nil
        } catch {
            self.error = API.describe(error)
        }
    }

    func toggle() { listening ? stop() : start() }

    func start() {
        guard let station, !listening else { return }
        error = nil
        listening = true
        status = "Listening through \(station.name)…"
        spectro.reset()
        do {
            try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
            try AVAudioSession.sharedInstance().setActive(true)
        } catch {}
        frameTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 15, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self else { return }
                self.spectro.advance(by: 1.0 / 15)
                self.image = self.spectro.render()
            }
        }
        tasks = [Task { await audioLoop(station) }, Task { await analyzeLoop(station) }]
    }

    func stop() {
        tasks.forEach { $0.cancel() }
        tasks = []
        frameTimer?.invalidate()
        frameTimer = nil
        node.stop()
        engine.stop()
        listening = false
        status = heard.isEmpty ? "Pick a station, then Listen." : "Stopped. \(heard.count) species heard."
    }

    // MARK: Audio

    /// Each fetch returns the station's most recent few seconds. The next
    /// fetch starts so that it lands about when the queued clip runs out:
    /// clip length minus how long the last fetch took.
    private func audioLoop(_ station: Station) async {
        var failures = 0
        var fetchTime = 1.0
        while !Task.isCancelled {
            let t0 = Date()
            let buffer = await fetchClip(station)
            if Task.isCancelled { return }
            fetchTime = fetchTime * 0.5 + Date().timeIntervalSince(t0) * 0.5
            guard let buffer else {
                failures += 1
                if failures >= 4 { error = "Can't hear \(station.name) right now. Is it online?" }
                try? await Task.sleep(for: .seconds(1))
                continue
            }
            failures = 0
            if error?.hasPrefix("Can't hear") == true { error = nil }
            await play(buffer, lead: fetchTime)
        }
    }

    private func fetchClip(_ station: Station) async -> AVAudioPCMBuffer? {
        guard let data = try? await API.data("api/v1/tv/listen/\(station.id)") else { return nil }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("live-\(UUID().uuidString).wav")
        defer { try? FileManager.default.removeItem(at: url) }
        do {
            try data.write(to: url)
            let file = try AVAudioFile(forReading: url)
            guard let buf = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: AVAudioFrameCount(file.length)) else { return nil }
            try file.read(into: buf)
            return buf
        } catch {
            return nil
        }
    }

    /// Queues one clip and returns early enough (lead = fetch time) for the
    /// next clip to arrive before this one ends. Timed by the clip's length
    /// rather than the player's completion callback, which never fires when
    /// there is no audio output (and would stall the loop).
    private func play(_ buffer: AVAudioPCMBuffer, lead: Double) async {
        if connectedFormat != buffer.format {
            engine.stop()
            engine.disconnectNodeOutput(node)
            engine.connect(node, to: engine.mainMixerNode, format: buffer.format)
            connectedFormat = buffer.format
        }
        if !engine.isRunning { try? engine.start() }
        spectro.add(buffer)
        node.scheduleBuffer(buffer, completionHandler: nil)
        if !node.isPlaying { node.play() }
        let seconds = Double(buffer.frameLength) / buffer.format.sampleRate
        try? await Task.sleep(for: .seconds(max(0.3, seconds - lead - 0.2)))
    }

    // MARK: Identification

    private func analyzeLoop(_ station: Station) async {
        while !Task.isCancelled {
            do {
                let r: Analyze = try await API.postForm("api/v1/live-detect/analyze",
                                                        fields: ["source": "device", "device_id": station.id, "mic_name": station.mic])
                if Task.isCancelled { return }
                if error?.hasPrefix("Can't hear") != true { error = nil }
                if r.detected {
                    for d in r.detections { record(d.commonName, d.confidence, d.photoUrl) }
                    status = "Heard \(r.detections.first?.commonName ?? "a bird")!"
                } else {
                    status = "Listening through \(station.name)…"
                }
            } catch {
                if Task.isCancelled { return }
                self.error = API.describe(error)
                try? await Task.sleep(for: .seconds(3))
            }
            try? await Task.sleep(for: .milliseconds(500))
        }
    }

    private func record(_ name: String, _ conf: Double, _ photo: String?) {
        if let i = heard.firstIndex(where: { $0.name == name }) {
            var h = heard.remove(at: i)
            h.count += 1; h.best = max(h.best, conf); h.last = Date()
            heard.insert(h, at: 0)
        } else {
            heard.insert(Heard(name: name, count: 1, best: conf, photo: photo, last: Date()), at: 0)
        }
        latest = heard.first
    }
}

/// Scrolling spectrogram: FFT columns from each clip, revealed at playback speed.
final class Spectrogram {
    static let n = 1024, hop = 512, rows = 128, width = 860   // about 10 s on screen
    private let fft = vDSP.FFT(log2n: 10, radix: .radix2, ofType: DSPSplitComplex.self)!
    private let window = vDSP.window(ofType: Float.self, usingSequence: .hanningDenormalized, count: Spectrogram.n, isHalfWindow: false)
    private var shown: [[Float]] = []
    private var pending: [[Float]] = []
    private var colsPerSecond: Double = 86
    private var carry: Double = 0
    /// Per-row noise floor in dB: drops quickly to quiet frames, rises slowly,
    /// so steady background noise stays dark and calls stand out.
    private var floor = [Float](repeating: .nan, count: Spectrogram.rows)
    static let span: Float = 30   // dB above the floor that maps to full colour

    func reset() { shown = []; pending = []; carry = 0; floor = [Float](repeating: .nan, count: Self.rows) }

    func add(_ buffer: AVAudioPCMBuffer) {
        guard let ch = buffer.floatChannelData?[0] else { return }
        let count = Int(buffer.frameLength), sr = buffer.format.sampleRate
        colsPerSecond = sr / Double(Self.hop)
        let maxBin = min(Self.n / 2, Int(12_000 / (sr / Double(Self.n))))   // up to 12 kHz
        var start = 0
        var real = [Float](repeating: 0, count: Self.n / 2), imag = real, mags = real
        while start + Self.n <= count {
            var seg = Array(UnsafeBufferPointer(start: ch + start, count: Self.n))
            vDSP.multiply(seg, window, result: &seg)
            real.withUnsafeMutableBufferPointer { rp in
                imag.withUnsafeMutableBufferPointer { ip in
                    var split = DSPSplitComplex(realp: rp.baseAddress!, imagp: ip.baseAddress!)
                    seg.withUnsafeBytes { raw in
                        vDSP_ctoz(raw.bindMemory(to: DSPComplex.self).baseAddress!, 2, &split, 1, vDSP_Length(Self.n / 2))
                    }
                    fft.forward(input: split, output: &split)
                    mags.withUnsafeMutableBufferPointer { mp in
                        vDSP_zvmags(&split, 1, mp.baseAddress!, 1, vDSP_Length(Self.n / 2))
                    }
                }
            }
            var col = [Float](repeating: 0, count: Self.rows)
            for r in 0..<Self.rows {
                let lo = 1 + r * (maxBin - 1) / Self.rows, hi = max(lo + 1, 1 + (r + 1) * (maxBin - 1) / Self.rows)
                var m: Float = 0
                for b in lo..<min(hi, Self.n / 2) { m = max(m, mags[b]) }
                let db = 10 * log10f(m + 1e-12)
                var f = floor[r]
                if f.isNaN { f = db }
                f = db < f ? f + (db - f) * 0.2 : f + 0.03
                floor[r] = f
                let v = min(1, max(0, (db - f - 6) / Self.span))
                col[r] = powf(v, 0.8)
            }
            pending.append(col)
            start += Self.hop
        }
    }

    func advance(by seconds: Double) {
        carry += seconds * colsPerSecond
        let take = min(Int(carry), pending.count)
        guard take > 0 else { return }
        carry -= Double(take)
        shown.append(contentsOf: pending.prefix(take))
        pending.removeFirst(take)
        if shown.count > Self.width { shown.removeFirst(shown.count - Self.width) }
        if pending.count > Int(colsPerSecond * 8) { pending.removeFirst(pending.count - Int(colsPerSecond * 8)) }
    }

    func render() -> CGImage? {
        let w = Self.width, h = Self.rows
        // Columns not filled yet show the quietest colour, so the panel is full from the start.
        let (br, bg, bb) = Self.color(0)
        var px = [UInt8](repeating: 255, count: w * h * 4)
        for i in stride(from: 0, to: px.count, by: 4) { px[i] = br; px[i + 1] = bg; px[i + 2] = bb }
        let offset = w - shown.count
        for (ci, col) in shown.enumerated() {
            let x = offset + ci
            for r in 0..<h {
                let (cr, cg, cb) = Self.color(col[r])
                let i = ((h - 1 - r) * w + x) * 4
                px[i] = cr; px[i + 1] = cg; px[i + 2] = cb; px[i + 3] = 255
            }
        }
        let cs = CGColorSpaceCreateDeviceRGB()
        return px.withUnsafeMutableBytes { raw in
            CGContext(data: raw.baseAddress, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
                      space: cs, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)?.makeImage()
        }
    }

    /// Dark purple → magenta → amber, like the web Live Detect waterfall.
    static func color(_ v: Float) -> (UInt8, UInt8, UInt8) {
        let stops: [(Float, Float, Float)] = [(0.04, 0.03, 0.12), (0.33, 0.07, 0.42), (0.78, 0.22, 0.42), (0.98, 0.62, 0.22), (1.0, 0.95, 0.65)]
        let t = max(0, min(1, v)) * Float(stops.count - 1)
        let i = min(Int(t), stops.count - 2), f = t - Float(i)
        let a = stops[i], b = stops[i + 1]
        return (UInt8((a.0 + (b.0 - a.0) * f) * 255), UInt8((a.1 + (b.1 - a.1) * f) * 255), UInt8((a.2 + (b.2 - a.2) * f) * 255))
    }
}

struct LiveView: View {
    @EnvironmentObject var live: LiveSession
    @EnvironmentObject var player: Player

    var body: some View {
        VStack(alignment: .leading, spacing: 30) {
            HStack(alignment: .center, spacing: 30) {
                ChirpMark(height: 56, animate: live.listening)
                Text("Live Detect").font(.system(size: 54, weight: .semibold, design: .serif))
                Spacer()
                Picker("Station", selection: $live.station) {
                    ForEach(live.stations) { s in
                        Text(s.online ? s.name : "\(s.name) (offline)").tag(Optional(s))
                    }
                }
                .frame(width: 520)
                .disabled(live.listening)
                Button {
                    player.stop()
                    live.toggle()
                } label: {
                    Label(live.listening ? "Stop" : "Listen", systemImage: live.listening ? "stop.fill" : "waveform")
                        .font(.title3).padding(.horizontal, 20)
                }
                .disabled(live.station == nil)
            }
            ZStack(alignment: .bottomLeading) {
                Group {
                    if let img = live.image {
                        Image(decorative: img, scale: 1).resizable().interpolation(.medium)
                    } else {
                        LinearGradient(colors: [Color(red: 0.1, green: 0.05, blue: 0.2), Color(red: 0.25, green: 0.07, blue: 0.3)], startPoint: .top, endPoint: .bottom)
                    }
                }
                .frame(height: 430)
                .clipShape(RoundedRectangle(cornerRadius: 26))
                HStack(spacing: 22) {
                    if let l = live.latest {
                        BirdPhoto(path: l.photo, size: 110).clipShape(Circle())
                    }
                    Text(live.status).font(.title2.weight(.semibold))
                }
                .padding(.horizontal, 26).padding(.vertical, 16)
                .background(.black.opacity(0.55), in: Capsule())
                .padding(24)
            }
            if let e = live.error { Text(e).foregroundStyle(Theme.rose) }
            if !live.heard.isEmpty {
                Text("Heard this session").font(.headline).foregroundStyle(Theme.muted)
                ScrollView(.horizontal) {
                    HStack(spacing: 26) {
                        ForEach(live.heard) { h in
                            HStack(spacing: 14) {
                                BirdPhoto(path: h.photo, size: 70).clipShape(Circle())
                                VStack(alignment: .leading) {
                                    Text(h.name).font(.headline)
                                    Text("\(h.count)× · best \(Theme.confidence(h.best))").font(.caption).foregroundStyle(Theme.muted)
                                }
                            }
                            .padding(18).background(Theme.card, in: RoundedRectangle(cornerRadius: 20)).focusable()
                        }
                    }
                    .padding(.vertical, 20)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 80).padding(.vertical, 40)
        .task {
            await live.loadStations()
            #if DEBUG
            if Screenshots.scene == "listen" { live.start() }
            #endif
        }
        .onDisappear { live.stop() }
    }
}
