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
    /// Across the spectrogram (0 = left edge, 1 = right edge): what's playing
    /// right now. Audio to its right has arrived but isn't heard yet.
    @Published private(set) var playheadX: Double?
    /// The marker ◀ ▶ move; Select listens from it.
    @Published private(set) var cursorX: Double?
    /// Seconds the marker sits before what's playing now.
    @Published private(set) var cursorBack: Double = 0
    /// The marker is on the newest clip: Select goes back to live.
    @Published private(set) var cursorAtLive = false
    /// Seconds behind live after listening back from the marker; 0 when live.
    @Published private(set) var behind: Double = 0

    private let engine = AVAudioEngine()
    private let node = AVAudioPlayerNode()
    private var connectedFormat: AVAudioFormat?
    private var tasks: [Task<Void, Never>] = []
    private let spectro = Spectrogram()
    private var frameTimer: Timer?

    // Timeline. "Stream" samples count the station's audio as it arrives;
    // "player" samples are the player node's own clock. Each scheduled piece
    // records both, so the playhead is known exactly, gaps included.
    private var rate: Double = 48_000
    private var streamEnd: Int64 = 0
    private var clips: [(start: Int64, buffer: AVAudioPCMBuffer)] = []
    private var segments: [(player: Int64, stream: Int64, length: Int64)] = []
    private var nextPlayer: Int64 = 0
    private var cursor: Int64?
    private var shifted = false
    private static let keepSeconds = 45.0

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
        resetTimeline()
        do {
            try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
            try AVAudioSession.sharedInstance().setActive(true)
        } catch {}
        frameTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 15, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.frame() }
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
        cursor = nil; cursorX = nil; playheadX = nil; behind = 0; shifted = false
        status = heard.isEmpty ? "Pick a station, then Listen." : "Stopped. \(heard.count) species heard."
    }

    private func resetTimeline() {
        node.stop()
        spectro.reset()
        streamEnd = 0; clips = []; segments = []; nextPlayer = 0
        cursor = nil; cursorX = nil; playheadX = nil; behind = 0; shifted = false
    }

    // MARK: Scrubbing

    /// Moves the marker by `seconds` (negative = back), from the playhead the
    /// first time. It stays within the audio kept (about 45 s).
    func moveCursor(by seconds: Double) {
        guard listening, !clips.isEmpty else { return }
        let base = cursor ?? playheadStream() ?? streamEnd
        cursor = min(streamEnd, max(clips[0].start, base + Int64(seconds * rate)))
        frame()
    }

    func clearCursor() { cursor = nil; frame() }

    /// Select: listen from the marker. At the newest clip, back to live.
    func listenAtCursor() {
        guard listening, let c = cursor, let newest = clips.last else { return }
        cursor = nil
        if c >= newest.start {
            replay(from: newest.start)
            shifted = false
        } else {
            replay(from: c)
            shifted = true
        }
        frame()
    }

    /// Drops what's queued and plays the kept audio from `pos` onward; new
    /// clips keep queueing after it.
    private func replay(from pos: Int64) {
        node.stop()                     // clears the queue; the player clock restarts at 0
        segments = []
        nextPlayer = 0
        if !engine.isRunning { try? engine.start() }
        node.play()
        for c in clips where c.start + Int64(c.buffer.frameLength) > pos {
            let off = max(0, pos - c.start)
            guard let piece = off == 0 ? c.buffer : c.buffer.tail(from: off) else { continue }
            schedule(piece, stream: c.start + off)
        }
    }

    // MARK: Drawing

    private func frame() {
        guard listening else { return }
        let hop = Int64(Spectrogram.hop), span = Int64(Spectrogram.width) * hop
        let playhead = playheadStream()
        // The playhead sits three quarters across; arrived-but-unheard audio
        // fills the rest. Scrubbing far back slides the view to keep the marker on screen.
        var right = (playhead ?? streamEnd) + span / 4
        if let c = cursor {
            if c < right - span * 9 / 10 { right = c + span * 9 / 10 }
            if c > right - hop * 8 { right = c + hop * 8 }
        }
        image = spectro.render(rightColumn: Int(right / hop))
        func x(_ s: Int64) -> Double { min(1, max(0, 1 - Double(right - s) / Double(span))) }
        playheadX = playhead.map(x)
        cursorX = cursor.map(x)
        cursorBack = cursor.map { Double((playhead ?? streamEnd) - $0) / rate } ?? 0
        cursorAtLive = cursor.map { $0 >= (clips.last?.start ?? 0) } ?? false
        behind = shifted ? (playhead.map { Double(streamEnd - $0) / rate } ?? 0) : 0
    }

    private func playerSample() -> Int64? {
        guard node.isPlaying, let t = node.lastRenderTime, let p = node.playerTime(forNodeTime: t) else { return nil }
        return p.sampleTime
    }

    /// Stream position being heard now (held at the end of the last piece if the queue ran dry).
    private func playheadStream() -> Int64? {
        guard let p = playerSample() else { return nil }
        var at: Int64?
        for s in segments where p >= s.player {
            at = p < s.player + s.length ? s.stream + (p - s.player) : s.stream + s.length
        }
        return at
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
            resetTimeline()
            rate = buffer.format.sampleRate
        }
        if !engine.isRunning { try? engine.start() }
        if !node.isPlaying { node.play() }
        let start = streamEnd
        clips.append((start, buffer))
        streamEnd += Int64(buffer.frameLength)
        let keep = Int64(Self.keepSeconds * rate)
        while let first = clips.first, first.start + Int64(first.buffer.frameLength) < streamEnd - keep { clips.removeFirst() }
        spectro.add(buffer, at: start, keepSamples: keep)
        schedule(buffer, stream: start)
        let seconds = Double(buffer.frameLength) / buffer.format.sampleRate
        try? await Task.sleep(for: .seconds(max(0.3, seconds - lead - 0.2)))
    }

    /// Plays `buffer` right after what's queued (or a moment from now if the
    /// queue ran dry), and records where it lands on both clocks.
    private func schedule(_ buffer: AVAudioPCMBuffer, stream: Int64) {
        let now = playerSample() ?? 0
        let start = max(nextPlayer, now + Int64(0.05 * rate))
        node.scheduleBuffer(buffer, at: AVAudioTime(sampleTime: start, atRate: rate), options: [], completionHandler: nil)
        segments.append((start, stream, Int64(buffer.frameLength)))
        if segments.count > 64 { segments.removeFirst(segments.count - 64) }
        nextPlayer = start + Int64(buffer.frameLength)
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

/// Scrolling spectrogram: FFT columns keyed by where they sit in the
/// station's audio, so the view can be drawn around the playhead.
final class Spectrogram {
    static let n = 1024, hop = 512, rows = 128, width = 860   // about 10 s on screen
    private let fft = vDSP.FFT(log2n: 10, radix: .radix2, ofType: DSPSplitComplex.self)!
    private let window = vDSP.window(ofType: Float.self, usingSequence: .hanningDenormalized, count: Spectrogram.n, isHalfWindow: false)
    private var cols: [Int: [Float]] = [:]   // column index (stream sample / hop) → values
    /// Per-row noise floor in dB: drops quickly to quiet frames, rises slowly,
    /// so steady background noise stays dark and calls stand out.
    private var floor = [Float](repeating: .nan, count: Spectrogram.rows)
    static let span: Float = 30   // dB above the floor that maps to full colour

    func reset() { cols = [:]; floor = [Float](repeating: .nan, count: Self.rows) }

    func add(_ buffer: AVAudioPCMBuffer, at streamStart: Int64, keepSamples: Int64) {
        guard let ch = buffer.floatChannelData?[0] else { return }
        let count = Int(buffer.frameLength), sr = buffer.format.sampleRate
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
            // Centre of the FFT window, so a call lines up with the playhead.
            cols[Int((streamStart + Int64(start + Self.n / 2)) / Int64(Self.hop))] = col
            start += Self.hop
        }
        let oldest = Int((streamStart + Int64(count) - keepSamples) / Int64(Self.hop))
        if cols.count > Int(keepSamples) / Self.hop + Self.width { cols = cols.filter { $0.key >= oldest } }
    }

    /// The `width` columns ending at `rightColumn`.
    func render(rightColumn: Int) -> CGImage? {
        let w = Self.width, h = Self.rows
        // Columns with no audio show the quietest colour, so the panel is always full.
        let (br, bg, bb) = Self.color(0)
        var px = [UInt8](repeating: 255, count: w * h * 4)
        for i in stride(from: 0, to: px.count, by: 4) { px[i] = br; px[i + 1] = bg; px[i + 2] = bb }
        for x in 0..<w {
            guard let col = cols[rightColumn - (w - 1 - x)] else { continue }
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

/// Remote: while listening, Down from Listen lands on the spectrogram; ◀ ▶
/// move a marker back through the last 45 s (1 s a step) and Select listens
/// from it; the marker at the right end and Select goes back to live.
struct LiveView: View {
    @EnvironmentObject var live: LiveSession
    @EnvironmentObject var player: Player
    @FocusState private var focus: Focus?
    private enum Focus: Hashable { case listen, panel, heard(String) }

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
                .focused($focus, equals: .listen)
            }
            panel
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
                            .focused($focus, equals: .heard(h.name))
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
        .onPlayPauseCommand { player.stop(); live.toggle() }
        .onChange(of: focus) { _, f in if f != .panel { live.clearCursor() } }
    }

    // MARK: Spectrogram

    private var panel: some View {
        let focused = focus == .panel
        return ZStack(alignment: .bottomLeading) {
            Group {
                if let img = live.image {
                    Image(decorative: img, scale: 1).resizable().interpolation(.medium)
                } else {
                    LinearGradient(colors: [Color(red: 0.1, green: 0.05, blue: 0.2), Color(red: 0.25, green: 0.07, blue: 0.3)], startPoint: .top, endPoint: .bottom)
                }
            }
            .overlay {
                GeometryReader { geo in
                    // Audio right of the playhead has arrived but isn't heard yet: dimmed.
                    if let x = live.playheadX {
                        Rectangle().fill(.black.opacity(0.28))
                            .frame(width: geo.size.width * (1 - x))
                            .offset(x: geo.size.width * x)
                        marker(x: geo.size.width * x, height: geo.size.height, color: Theme.amber)
                            .animation(.linear(duration: 1.0 / 15), value: x)
                    }
                    if let c = live.cursorX {
                        marker(x: geo.size.width * c, height: geo.size.height, color: Theme.ink)
                    }
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
        .frame(height: 430)
        .overlay(alignment: .topTrailing) {
            if let hint {
                Text(hint)
                    .font(.callout.monospacedDigit())
                    .foregroundStyle(focused || live.behind > 0 ? Theme.amber : Theme.muted)
                    .padding(.horizontal, 18).padding(.vertical, 8)
                    .background(.black.opacity(0.6), in: Capsule())
                    .padding(24)
            }
        }
        .overlay(
            RoundedRectangle(cornerRadius: 26)
                .stroke(focused ? Theme.amber : .clear, lineWidth: 4)
        )
        .scaleEffect(focused ? 1.01 : 1)
        .animation(.easeOut(duration: 0.18), value: focused)
        .focusable(live.listening)
        .focused($focus, equals: .panel)
        .onMoveCommand { dir in
            switch dir {
            case .left: live.moveCursor(by: -1)
            case .right: live.moveCursor(by: 1)
            case .up: focus = .listen
            case .down: focus = live.heard.first.map { .heard($0.name) }
            @unknown default: break
            }
        }
        .onTapGesture { live.listenAtCursor() }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Live spectrogram")
        .accessibilityValue(live.cursorX == nil ? (live.behind > 0 ? "\(Int(live.behind)) seconds behind live" : "Live")
                                                : (live.cursorAtLive ? "Back to live" : "\(Int(live.cursorBack.rounded())) seconds back"))
        .accessibilityHint("Left and right pick a moment; select listens from it")
    }

    private var hint: String? {
        if live.cursorX != nil {
            if live.cursorAtLive { return "Select: back to live" }
            let n = Int(live.cursorBack.rounded())
            return n >= 0 ? "Select: listen from \(n) s back" : "Select: skip ahead \(-n) s"
        }
        if live.behind > 0 { return "\(Int(live.behind.rounded())) s behind live · ▶ to the end, then Select" }
        if focus == .panel { return "◀ ▶ go back · Select listens from there" }
        return nil
    }

    private func marker(x: CGFloat, height: CGFloat, color: Color) -> some View {
        ZStack(alignment: .top) {
            Rectangle().fill(color).frame(width: 3, height: height)
                .shadow(color: color.opacity(0.9), radius: 6)
            Circle().fill(color).frame(width: 16, height: 16).offset(y: -2)
        }
        .offset(x: x - 1.5)
    }
}

extension AVAudioPCMBuffer {
    /// A copy from `frame` to the end (float, non-interleaved, as AVAudioFile reads it).
    func tail(from frame: Int64) -> AVAudioPCMBuffer? {
        let n = AVAudioFrameCount(max(0, Int64(frameLength) - frame))
        guard n > 0, let src = floatChannelData,
              let out = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: n), let dst = out.floatChannelData else { return nil }
        out.frameLength = n
        for c in 0..<Int(format.channelCount) {
            dst[c].update(from: src[c] + Int(frame), count: Int(n))
        }
        return out
    }
}
