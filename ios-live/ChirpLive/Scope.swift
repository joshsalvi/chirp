import Accelerate
import SwiftUI

/// The sound display while listening: level bars, a running spectrogram, a
/// running waveform, or a live frequency spectrum. Settings picks the view
/// and how many seconds the running views show.
enum ScopeStyle: String, CaseIterable, Identifiable {
    case bars, spectrogram, waveform, spectrum
    var id: String { rawValue }
    var label: String {
        switch self {
        case .bars: return "Level bars"
        case .spectrogram: return "Spectrogram"
        case .waveform: return "Waveform"
        case .spectrum: return "Spectrum"
        }
    }
    var icon: String {
        switch self {
        case .bars: return "chart.bar.fill"
        case .spectrogram: return "waveform.path.ecg.rectangle"
        case .waveform: return "waveform"
        case .spectrum: return "slider.vertical.3"
        }
    }
}

/// Analyses the sound as it's heard (microphone, or a station as it plays)
/// into columns across the chosen window: level, waveform peaks and a
/// spectrum per column, plus the spectrum right now. Fed from the audio
/// thread; the views redraw from `frame` about 30 times a second.
final class ScopeFeed: ObservableObject, @unchecked Sendable {
    static let shared = ScopeFeed()

    static let columns = 240          // across the window
    static let bands = 96             // spectrogram rows, 0 … 12 kHz
    static let spectrumBars = 32      // live spectrum, 300 Hz … 12 kHz on a log scale
    static let topHz: Float = 12_000
    static let fftSize = 1024

    struct Frame {
        var levels: [Float]           // per column, 0…1
        var peaks: [Float]            // per column, 0…1 (waveform)
        var spectrogram: [[Float]]    // per column, `bands` values 0…1, low → high
        var spectrum: [Float]         // `spectrumBars` values 0…1
        var hold: [Float]             // spectrum peak hold
    }

    @Published private(set) var frame = ScopeFeed.empty

    static var empty: Frame {
        Frame(levels: Array(repeating: 0, count: columns), peaks: Array(repeating: 0, count: columns),
              spectrogram: Array(repeating: Array(repeating: 0, count: bands), count: columns),
              spectrum: Array(repeating: 0, count: spectrumBars), hold: Array(repeating: 0, count: spectrumBars))
    }

    private let lock = NSLock()
    private var state = ScopeFeed.empty
    private var pending: [Float] = []
    private var history: [Float] = []        // last fftSize samples
    private var sampleRate: Double = BirdNET.sampleRate
    private var windowSeconds: Double = 10
    private var colSamples = 0               // samples gathered toward the next column
    private var colSum: Float = 0, colPeak: Float = 0
    private var dirty = false
    private var timer: Timer?
    private let fft: vDSP.FFT<DSPSplitComplex>?
    private let hann: [Float]

    init() {
        fft = vDSP.FFT(log2n: vDSP_Length(log2(Float(ScopeFeed.fftSize))), radix: .radix2, ofType: DSPSplitComplex.self)
        hann = vDSP.window(ofType: Float.self, usingSequence: .hanningDenormalized, count: ScopeFeed.fftSize, isHalfWindow: false)
    }

    /// Seconds shown by the running views (Settings).
    func setWindow(_ seconds: Double) {
        lock.lock(); windowSeconds = max(2, min(60, seconds)); lock.unlock()
    }

    func reset(sampleRate: Double = BirdNET.sampleRate) {
        lock.lock()
        state = ScopeFeed.empty; pending = []; history = []; colSamples = 0; colSum = 0; colPeak = 0
        self.sampleRate = sampleRate; dirty = true
        lock.unlock()
        DispatchQueue.main.async { self.frame = ScopeFeed.empty }
    }

    /// The analysis so far (tests).
    func snapshot() -> Frame {
        lock.lock(); defer { lock.unlock() }
        return state
    }

    /// Starts and stops the ~30 Hz redraw.
    func run(_ on: Bool) {
        DispatchQueue.main.async {
            self.timer?.invalidate(); self.timer = nil
            guard on else { return }
            self.timer = Timer.scheduledTimer(withTimeInterval: 1.0 / 30, repeats: true) { [weak self] _ in self?.publish() }
        }
    }

    private func publish() {
        lock.lock()
        guard dirty else { lock.unlock(); return }
        dirty = false
        let f = state
        lock.unlock()
        frame = f
    }

    /// Sound as it's heard. Any thread.
    func append(_ samples: [Float], sampleRate rate: Double? = nil) {
        lock.lock(); defer { lock.unlock() }
        if let rate, rate > 0, rate != sampleRate { sampleRate = rate }
        let perColumn = max(256, Int(windowSeconds * sampleRate) / ScopeFeed.columns)
        for s in samples {
            colSum += s * s
            colPeak = max(colPeak, abs(s))
            colSamples += 1
            history.append(s)
            if colSamples >= perColumn { closeColumn(count: colSamples) }
        }
        if history.count > ScopeFeed.fftSize { history.removeFirst(history.count - ScopeFeed.fftSize) }
        dirty = true
    }

    private func closeColumn(count: Int) {
        let rms = (colSum / Float(count)).squareRoot()
        let db = 20 * log10(max(rms, 1e-6))
        state.levels.removeFirst(); state.levels.append(min(1, max(0, (db + 60) / 60)))
        state.peaks.removeFirst(); state.peaks.append(min(1, colPeak * 2))
        colSum = 0; colPeak = 0; colSamples = 0
        let tail = history.suffix(ScopeFeed.fftSize)
        let mags = tail.count == ScopeFeed.fftSize ? spectrum(Array(tail)) : nil
        state.spectrogram.removeFirst()
        state.spectrogram.append(mags.map { ScopeFeed.rows($0, sampleRate: Float(sampleRate)) } ?? Array(repeating: 0, count: ScopeFeed.bands))
        if let mags {
            let now = ScopeFeed.logBars(mags, sampleRate: Float(sampleRate))
            for i in now.indices {
                state.spectrum[i] = max(now[i], state.spectrum[i] * 0.82)         // falls back smoothly
                state.hold[i] = max(now[i], state.hold[i] - 0.012)
            }
        }
    }

    /// Magnitudes (dB scaled to 0…1) of the newest fftSize samples.
    private func spectrum(_ x: [Float]) -> [Float]? {
        guard let fft else { return nil }
        let n = ScopeFeed.fftSize, half = n / 2
        let windowed = vDSP.multiply(x, hann)
        var re = [Float](repeating: 0, count: half), im = [Float](repeating: 0, count: half)
        var mags = [Float](repeating: 0, count: half)
        re.withUnsafeMutableBufferPointer { rp in
            im.withUnsafeMutableBufferPointer { ip in
                var split = DSPSplitComplex(realp: rp.baseAddress!, imagp: ip.baseAddress!)
                windowed.withUnsafeBufferPointer { wp in
                    wp.baseAddress!.withMemoryRebound(to: DSPComplex.self, capacity: half) { vDSP_ctoz($0, 2, &split, 1, vDSP_Length(half)) }
                }
                var out = DSPSplitComplex(realp: rp.baseAddress!, imagp: ip.baseAddress!)   // in place
                fft.forward(input: split, output: &out)
                vDSP.absolute(out, result: &mags)
            }
        }
        return mags.map { m in
            let db = 20 * log10(max(m / Float(n), 1e-9))
            return min(1, max(0, (db + 100) / 70))     // -100 … -30 dB
        }
    }

    /// Spectrogram rows: FFT bins up to topHz averaged into `bands` rows.
    static func rows(_ mags: [Float], sampleRate: Float) -> [Float] {
        let binHz = sampleRate / Float(fftSize)
        let top = min(mags.count, Int(topHz / binHz))
        return (0..<bands).map { b in
            let lo = b * top / bands, hi = max(lo + 1, (b + 1) * top / bands)
            return mags[lo..<min(hi, mags.count)].max() ?? 0
        }
    }

    /// Live spectrum bars, log-spaced 300 Hz … topHz.
    static func logBars(_ mags: [Float], sampleRate: Float) -> [Float] {
        let binHz = sampleRate / Float(fftSize)
        let lo: Float = 300, ratio = topHz / lo
        return (0..<spectrumBars).map { i in
            let f0 = lo * pow(ratio, Float(i) / Float(spectrumBars)), f1 = lo * pow(ratio, Float(i + 1) / Float(spectrumBars))
            let a = min(mags.count - 1, Int(f0 / binHz)), b = min(mags.count, max(a + 1, Int(f1 / binHz)))
            return mags[a..<b].max() ?? 0
        }
    }
}

// MARK: Views

/// The sound display with its view switcher. Tap the display to try the next view.
struct ScopeCard: View {
    let active: Bool
    @ObservedObject private var feed = ScopeFeed.shared
    @AppStorage("scopeStyle") private var styleRaw = ScopeStyle.bars.rawValue
    @AppStorage("scopeWindow") private var window = 10.0

    private var style: ScopeStyle { ScopeStyle(rawValue: styleRaw) ?? .bars }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Menu {
                    Picker("View", selection: $styleRaw) {
                        ForEach(ScopeStyle.allCases) { s in Label(s.label, systemImage: s.icon).tag(s.rawValue) }
                    }
                } label: {
                    HStack(spacing: 5) {
                        Image(systemName: style.icon)
                        Text(style.label)
                        Image(systemName: "chevron.down").font(.system(size: 10, weight: .semibold))
                    }
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(Theme.body)
                }
                Spacer()
                Text(style == .spectrum ? "0.3–12 kHz" : style == .spectrogram ? "\(Int(window)) s · 0–12 kHz" : "\(Int(window)) s")
                    .font(.system(size: 12, design: .monospaced)).foregroundStyle(Theme.muted)
            }
            Group {
                switch style {
                case .bars: LevelBars(levels: Self.bars(feed.frame.levels, count: 48), active: active, framed: false)
                case .spectrogram: Spectrogram(columns: feed.frame.spectrogram)
                case .waveform: Waveform(peaks: feed.frame.peaks)
                case .spectrum: Spectrum(bars: feed.frame.spectrum, hold: feed.frame.hold)
                }
            }
            .frame(height: 100)
            .contentShape(Rectangle())
            .onTapGesture { next() }
            .accessibilityElement()
            .accessibilityLabel("\(style.label). Double-tap for the next view.")
            .accessibilityAddTraits(.isButton)
        }
        .padding(14)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 16))
        .opacity(active ? 1 : 0.5)
        .onAppear { feed.setWindow(window) }
        .onChange(of: window) { feed.setWindow(window) }
    }

    private func next() {
        let all = ScopeStyle.allCases
        let i = all.firstIndex(of: style) ?? 0
        withAnimation(.easeInOut(duration: 0.2)) { styleRaw = all[(i + 1) % all.count].rawValue }
        Haptics.select()
    }

    /// Column levels → `count` bars (the loudest column in each group).
    static func bars(_ levels: [Float], count: Int) -> [Float] {
        let per = max(1, levels.count / count)
        return (0..<count).map { i in levels[(i * per)..<min(levels.count, (i + 1) * per)].max() ?? 0 }
    }
}

/// Running spectrogram, newest on the right, low pitches at the bottom.
struct Spectrogram: View {
    let columns: [[Float]]
    var body: some View {
        if let image = Self.image(columns) {
            Image(decorative: image, scale: 1)
                .resizable()
                .interpolation(.medium)
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .accessibilityHidden(true)
        } else {
            RoundedRectangle(cornerRadius: 8).fill(Theme.bg)
        }
    }

    /// Dark green → amber → orange → near-white, Chirp's palette.
    static let palette: [(Float, Float, Float)] = (0..<256).map { i in
        let t = Float(i) / 255
        let stops: [(Float, (Float, Float, Float))] = [
            (0.00, (0.039, 0.086, 0.047)), (0.35, (0.10, 0.30, 0.18)), (0.60, (0.98, 0.75, 0.14)),
            (0.82, (0.98, 0.57, 0.24)), (1.00, (1.00, 0.95, 0.85))]
        let k = max(1, stops.firstIndex { $0.0 >= t } ?? stops.count - 1)
        let (t0, c0) = stops[k - 1], (t1, c1) = stops[k]
        let u = (t - t0) / max(0.0001, t1 - t0)
        return (c0.0 + (c1.0 - c0.0) * u, c0.1 + (c1.1 - c0.1) * u, c0.2 + (c1.2 - c0.2) * u)
    }

    static func image(_ columns: [[Float]]) -> CGImage? {
        let w = columns.count, h = columns.first?.count ?? 0
        guard w > 0, h > 0 else { return nil }
        var px = [UInt8](repeating: 255, count: w * h * 4)
        for x in 0..<w {
            let col = columns[x]
            for y in 0..<h {
                let v = col[h - 1 - y]                        // top row = high pitch
                let c = palette[Int(min(1, max(0, v)) * 255)]
                let o = (y * w + x) * 4
                px[o] = UInt8(c.0 * 255); px[o + 1] = UInt8(c.1 * 255); px[o + 2] = UInt8(c.2 * 255)
            }
        }
        guard let provider = CGDataProvider(data: Data(px) as CFData) else { return nil }
        return CGImage(width: w, height: h, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: w * 4,
                       space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipLast.rawValue),
                       provider: provider, decode: nil, shouldInterpolate: true, intent: .defaultIntent)
    }
}

/// Running waveform (peak per column, mirrored), newest on the right.
struct Waveform: View {
    let peaks: [Float]

    /// Outdoor sound usually peaks at well under 1% of full scale, so raw
    /// amplitude draws a flat line. Scale to the loudest peak in the window
    /// (never louder than `floor`, so near-silence stays small) and compress
    /// a little (power 0.6) so quiet calls still show beside loud ones.
    static let floor: Float = 0.02
    static func scaled(_ peaks: [Float]) -> [Float] {
        let ref = max((peaks.max() ?? 0) * 1.1, floor)
        return peaks.map { min(1, pow(max(0, $0) / ref, 0.6)) }
    }

    var body: some View {
        Canvas { ctx, size in
            let peaks = Self.scaled(self.peaks)
            let n = peaks.count
            guard n > 1 else { return }
            let mid = size.height / 2, dx = size.width / CGFloat(n - 1)
            var top = Path(), all = Path()
            for (i, p) in peaks.enumerated() {
                let x = CGFloat(i) * dx, y = mid - CGFloat(p) * mid * 0.95
                i == 0 ? top.move(to: CGPoint(x: x, y: y)) : top.addLine(to: CGPoint(x: x, y: y))
            }
            all.addPath(top)
            for (i, p) in peaks.enumerated().reversed() {
                all.addLine(to: CGPoint(x: CGFloat(i) * dx, y: mid + CGFloat(p) * mid * 0.95))
            }
            all.closeSubpath()
            ctx.fill(all, with: .linearGradient(Gradient(colors: [Theme.amber.opacity(0.85), Theme.orange.opacity(0.55), Theme.amber.opacity(0.85)]),
                                                startPoint: .zero, endPoint: CGPoint(x: 0, y: size.height)))
            ctx.stroke(Path { $0.move(to: CGPoint(x: 0, y: mid)); $0.addLine(to: CGPoint(x: size.width, y: mid)) },
                       with: .color(Theme.muted.opacity(0.25)), lineWidth: 1)
        }
        .accessibilityHidden(true)
    }
}

/// Live spectrum: log-spaced bars with a falling peak marker.
struct Spectrum: View {
    let bars: [Float]
    let hold: [Float]
    var body: some View {
        Canvas { ctx, size in
            let n = bars.count
            guard n > 0 else { return }
            let gap: CGFloat = 3, w = (size.width - gap * CGFloat(n - 1)) / CGFloat(n)
            for i in 0..<n {
                let x = CGFloat(i) * (w + gap)
                let v = CGFloat(bars[i]), h = max(3, v * size.height)
                let color = v > 0.7 ? Theme.orange : v > 0.45 ? Theme.amber : v > 0.25 ? Theme.amber.opacity(0.55) : Theme.muted.opacity(0.35)
                ctx.fill(Path(roundedRect: CGRect(x: x, y: size.height - h, width: w, height: h), cornerRadius: 2), with: .color(color))
                let hy = size.height - CGFloat(hold[i]) * size.height
                ctx.fill(Path(CGRect(x: x, y: max(0, hy - 2), width: w, height: 2)), with: .color(Theme.ink.opacity(0.7)))
            }
        }
        .accessibilityHidden(true)
    }
}

/// Settings → Sound display.
struct ScopeSettings: View {
    @AppStorage("scopeStyle") private var styleRaw = ScopeStyle.bars.rawValue
    @AppStorage("scopeWindow") private var window = 10.0
    var body: some View {
        Section {
            Picker("View", selection: $styleRaw) {
                ForEach(ScopeStyle.allCases) { s in Label(s.label, systemImage: s.icon).tag(s.rawValue) }
            }
            VStack(alignment: .leading) {
                Text("Time shown: \(Int(window)) seconds")
                Slider(value: $window, in: 3...30, step: 1)
            }
        } header: {
            Text("Sound display")
        } footer: {
            Text("What the display shows while listening. Tap the display to switch views. Time shown applies to the level bars, spectrogram and waveform; the spectrum is always the sound right now.")
        }
        .listRowBackground(Theme.card)
        .onChange(of: window) { ScopeFeed.shared.setWindow(window) }
    }
}

extension ScopeFeed {
    /// App Store screenshots: level bars without sound.
    func show(levels: [Float]) {
        lock.lock()
        let per = ScopeFeed.columns / max(1, levels.count)
        state.levels = levels.flatMap { Array(repeating: $0, count: per) } + Array(repeating: 0, count: max(0, ScopeFeed.columns - per * levels.count))
        dirty = true
        lock.unlock()
        DispatchQueue.main.async { self.publish() }
    }
}
