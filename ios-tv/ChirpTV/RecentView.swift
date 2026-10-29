import SwiftUI

/// The newest recordings (GET /tv/recent); pick one for its spectrogram and
/// sound. Refreshes every 30 seconds, so new birds show up as they're heard.
struct RecentView: View {
    @EnvironmentObject var account: Account
    @State private var items: [Item] = []
    @State private var error: String?
    @State private var loaded = false
    @State private var path: [Item] = []

    struct Item: Decodable, Identifiable, Hashable {
        let id: String
        let time: String
        let duration: Double
        let species: String
        let others: [String]
        let confidence: Double?
        let hasAudio: Bool
        let photoUrl: String?
        let scientific: String?
        var date: Date? { ISO.date(time) }
    }

    private let columns = Array(repeating: GridItem(.flexible(), spacing: 40), count: 4)

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 36) {
                    Text("Recent recordings").font(.system(size: 54, weight: .semibold, design: .serif))
                    if let error { Text(error).foregroundStyle(Theme.rose) }
                    if loaded && items.isEmpty && error == nil {
                        Text("No recordings yet.").foregroundStyle(Theme.muted)
                    }
                    LazyVGrid(columns: columns, spacing: 50) {
                        ForEach(items) { item in
                            NavigationLink(value: item) { card(item) }.buttonStyle(.card)
                        }
                    }
                }
                .padding(.horizontal, 80).padding(.vertical, 40)
            }
            .navigationDestination(for: Item.self) { RecordingView(item: $0) }
        }
        .task { await refreshLoop() }
    }

    private func card(_ it: Item) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            BirdPhoto(path: it.photoUrl).frame(width: 380, height: 240).clipped()
            VStack(alignment: .leading, spacing: 6) {
                Text(it.species).font(.headline).lineLimit(1).minimumScaleFactor(0.75)
                if !it.others.isEmpty {
                    Text("+ " + it.others.joined(separator: ", ")).font(.caption).foregroundStyle(Theme.muted).lineLimit(1)
                }
                Text([it.date.map { $0.formatted(.relative(presentation: .named)) }, it.confidence.map(Theme.confidence)]
                    .compactMap { $0 }.joined(separator: " · "))
                    .font(.caption).foregroundStyle(Theme.amber)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(20)
        }
        .frame(width: 380)
    }

    private func refreshLoop() async {
        while !Task.isCancelled {
            await load()
            try? await Task.sleep(for: .seconds(30))
        }
    }

    private func load() async {
        do {
            items = try await API.get("api/v1/tv/recent?limit=24")
            error = nil
            #if DEBUG
            if Screenshots.scene == "recording", path.isEmpty, let first = items.first(where: { !$0.others.isEmpty }) ?? items.first {
                path = [first]
            }
            #endif
        } catch {
            self.error = API.describe(error)
        }
        loaded = true
    }
}

/// One recording: its spectrogram with a scrubbable playhead, play/stop, and
/// every bird found in it (GET /recordings/{id}). Remote: Down from the tabs
/// lands on Play; on the spectrogram ◀ ▶ move the playhead (5 s a step) and
/// Select plays from it; Play/Pause works anywhere on the screen.
struct RecordingView: View {
    let item: RecentView.Item
    @EnvironmentObject var account: Account
    @EnvironmentObject var player: Player
    @State private var detections: [Detection] = []
    @State private var fullDuration: Double?
    @State private var cursor: Double = 0
    @FocusState private var focus: Focus?
    private enum Focus: Hashable { case play, scrubber, species(String) }

    struct Detail: Decodable { let durationSeconds: Double?; let detections: [Detection] }
    struct Detection: Decodable, Identifiable {
        let id: String
        let commonName: String
        let confidence: Double
        let startTime: Double
        let endTime: Double
        let birdPhotoUrl: String?
    }

    private static let step = 5.0
    private var total: Double { max(fullDuration ?? item.duration, 1) }
    private var isPlaying: Bool { player.playingID == item.id }
    /// The TV gets the first minute of audio.
    private var audible: Double {
        isPlaying && player.duration > 0 ? min(player.duration, total) : min(total, 60)
    }
    /// Where the playhead sits: playback time while playing, else the cursor.
    private var now: Double { isPlaying ? player.progress * player.duration : cursor }
    private var singing: Set<String> {
        guard isPlaying else { return [] }
        return Set(detections.filter { $0.startTime <= now && now <= $0.endTime }.map(\.commonName))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 30) {
            header.focusSection()
            scrubber
            if let e = player.error { Text(e).foregroundStyle(Theme.rose) }
            speciesRow.focusSection()
        }
        .padding(.horizontal, 80).padding(.vertical, 40)
        .background(backdrop)
        .defaultFocus($focus, item.hasAudio ? .play : grouped.first.map { .species($0.name) })
        .onPlayPauseCommand { Task { await togglePlay() } }
        .task { await load() }
        .onAppear { player.onScreenID = item.id }
        .onDisappear {
            if player.onScreenID == item.id { player.onScreenID = nil }
            if isPlaying { player.stop() }
        }
    }

    // MARK: Header

    private var header: some View {
        HStack(alignment: .center, spacing: 34) {
            BirdPhoto(path: item.photoUrl, size: 170)
                .clipShape(Circle())
                .overlay(Circle().stroke(Theme.amber.opacity(0.55), lineWidth: 3))
                .shadow(color: .black.opacity(0.5), radius: 18, y: 8)
            VStack(alignment: .leading, spacing: 8) {
                Text(item.species).font(.system(size: 56, weight: .semibold, design: .serif))
                if let s = item.scientific { Text(s).italic().foregroundStyle(Theme.muted) }
                HStack(spacing: 18) {
                    if let d = item.date {
                        Label(d.formatted(date: .complete, time: .shortened), systemImage: "calendar")
                    }
                    Label(Theme.clock(total), systemImage: "waveform")
                }
                .font(.callout).foregroundStyle(Theme.muted)
            }
            Spacer()
            Button { Task { await togglePlay() } } label: {
                Label(isPlaying ? "Stop" : (player.loadingID == item.id ? "Loading…" : "Play"),
                      systemImage: isPlaying ? "stop.fill" : "play.fill")
                    .font(.title3).padding(.horizontal, 20)
            }
            .disabled(!item.hasAudio)
            .focused($focus, equals: .play)
        }
    }

    // MARK: Spectrogram and playhead

    private var scrubber: some View {
        let focused = focus == .scrubber
        return VStack(alignment: .leading, spacing: 12) {
            GeometryReader { geo in
                let w = geo.size.width
                let x = w * min(now, total) / total
                ZStack(alignment: .topLeading) {
                    AsyncImage(url: account.mediaURL("/api/v1/recordings/\(item.id)/spectrogram")) { phase in
                        switch phase {
                        case .success(let img): img.resizable()
                        case .failure: Theme.card.overlay(Text("No spectrogram").foregroundStyle(Theme.muted))
                        default: Theme.card.overlay(ProgressView())
                        }
                    }
                    // Beyond the first minute the TV has no audio: dim it.
                    if audible < total {
                        Rectangle().fill(.black.opacity(0.45))
                            .frame(width: w * (1 - audible / total))
                            .offset(x: w * audible / total)
                    }
                    // Played so far: a soft amber wash.
                    if isPlaying {
                        LinearGradient(colors: [Theme.amber.opacity(0), Theme.amber.opacity(0.16)],
                                       startPoint: .leading, endPoint: .trailing)
                            .frame(width: max(0, x))
                    }
                    if isPlaying || focused || cursor > 0 {
                        playhead(x: x, height: geo.size.height, live: isPlaying)
                    }
                }
                .clipShape(RoundedRectangle(cornerRadius: 22))
            }
            .frame(height: 380)
            .overlay(
                RoundedRectangle(cornerRadius: 22)
                    .stroke(focused ? Theme.amber : Theme.line, lineWidth: focused ? 4 : 1.5)
            )
            .shadow(color: focused ? Theme.amber.opacity(0.35) : .black.opacity(0.4), radius: focused ? 28 : 14, y: 8)
            .scaleEffect(focused ? 1.015 : 1)
            .animation(.easeOut(duration: 0.18), value: focused)
            .focusable(item.hasAudio)
            .focused($focus, equals: .scrubber)
            .onMoveCommand(perform: move)
            .onTapGesture { Task { await playFromCursor() } }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Spectrogram")
            .accessibilityValue("\(Theme.clock(now)) of \(Theme.clock(total))")
            .accessibilityHint("Left and right move the playhead; select plays from it")

            timeline
        }
    }

    private func playhead(x: CGFloat, height: CGFloat, live: Bool) -> some View {
        let color = live ? Theme.amber : Theme.ink
        return ZStack(alignment: .top) {
            Rectangle().fill(color).frame(width: 3, height: height)
                .shadow(color: color.opacity(0.9), radius: 6)
            Circle().fill(color).frame(width: 18, height: 18).offset(y: -2)
                .shadow(color: .black.opacity(0.5), radius: 4)
        }
        .offset(x: x - 1.5)
        .animation(live ? .linear(duration: 0.1) : .easeOut(duration: 0.15), value: x)
    }

    /// Time labels under the spectrogram, plus where the playhead is.
    private var timeline: some View {
        let marks = Self.marks(total)
        return ZStack(alignment: .topLeading) {
            GeometryReader { geo in
                ForEach(marks, id: \.self) { t in
                    VStack(spacing: 4) {
                        Rectangle().fill(Theme.line).frame(width: 2, height: 8)
                        Text(Theme.clock(t)).font(.caption2.monospacedDigit()).foregroundStyle(Theme.muted)
                    }
                    .fixedSize()
                    .position(x: geo.size.width * t / total, y: 20)
                }
            }
            .frame(height: 40)
            HStack {
                Spacer()
                Text(focus == .scrubber
                     ? "◀ ▶ move · Select plays from \(Theme.clock(now))"
                     : (isPlaying ? "\(Theme.clock(now)) / \(Theme.clock(audible))" : "Select the spectrogram to pick a spot"))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(isPlaying || focus == .scrubber ? Theme.amber : Theme.muted)
                    .padding(.horizontal, 16).padding(.vertical, 6)
                    .background(Theme.card.opacity(0.9), in: Capsule())
            }
            .offset(y: 46)
        }
        .frame(height: 80, alignment: .top)
    }

    /// Evenly spaced labels: every 5, 10, 15, 30 or 60 s, about six of them.
    static func marks(_ total: Double) -> [Double] {
        let step = [5.0, 10, 15, 30, 60, 120, 300].first { total / $0 <= 6 } ?? 600
        return stride(from: 0, through: total, by: step).filter { $0 < total - step * 0.3 } + [total]
    }

    // MARK: Species

    private var speciesRow: some View {
        ScrollView(.horizontal) {
            HStack(spacing: 24) {
                ForEach(grouped, id: \.name) { g in
                    let on = singing.contains(g.name)
                    Button {
                        Task { cursor = g.start; await player.play(id: item.id, title: item.species, at: g.start) }
                    } label: {
                        HStack(spacing: 14) {
                            BirdPhoto(path: g.photo, size: 64).clipShape(Circle())
                                .overlay(Circle().stroke(Theme.amber, lineWidth: on ? 3 : 0))
                            VStack(alignment: .leading, spacing: 2) {
                                HStack(spacing: 8) {
                                    Text(g.name).font(.headline)
                                    if on {
                                        Image(systemName: "waveform").font(.caption).foregroundStyle(Theme.amber)
                                            .symbolEffect(.variableColor.iterative, isActive: on)
                                    }
                                }
                                Text("\(g.count)× · best \(Theme.confidence(g.best)) · \(Theme.clock(g.start))")
                                    .font(.caption).foregroundStyle(Theme.muted)
                            }
                        }
                        .padding(18)
                    }
                    .buttonStyle(.card)
                    .disabled(!item.hasAudio)
                    .focused($focus, equals: .species(g.name))
                    .accessibilityHint("Plays from this bird's first call")
                }
            }
            .padding(.vertical, 30).padding(.horizontal, 10)
        }
    }

    // MARK: Backdrop

    private var backdrop: some View {
        ZStack {
            Theme.bg
            BirdPhoto(path: item.photoUrl)
                .blur(radius: 80)
                .opacity(0.22)
                .overlay(LinearGradient(colors: [.clear, Theme.bg], startPoint: .top, endPoint: .bottom))
        }
        .ignoresSafeArea()
    }

    // MARK: Actions

    private func move(_ dir: MoveCommandDirection) {
        switch dir {
        case .left, .right:
            let delta = dir == .right ? Self.step : -Self.step
            let to = min(max(0, now + delta), max(0, audible - 0.5))
            cursor = to
            if isPlaying { player.seek(to: to) }
        case .up: focus = item.hasAudio ? .play : nil
        case .down: focus = grouped.first.map { .species($0.name) }
        @unknown default: break
        }
    }

    private func togglePlay() async {
        if isPlaying { cursor = now; player.stop() }
        else { await player.play(id: item.id, title: item.species, at: cursor) }
    }

    private func playFromCursor() async {
        if isPlaying { player.seek(to: cursor) }
        else { await player.play(id: item.id, title: item.species, at: cursor) }
    }

    private struct Group { let name: String; let count: Int; let best: Double; let photo: String?; let start: Double }
    private var grouped: [Group] {
        var order: [String] = []
        var map: [String: Group] = [:]
        for d in detections {
            if let g = map[d.commonName] {
                map[d.commonName] = Group(name: g.name, count: g.count + 1, best: max(g.best, d.confidence),
                                          photo: g.photo ?? d.birdPhotoUrl, start: min(g.start, d.startTime))
            } else {
                order.append(d.commonName)
                map[d.commonName] = Group(name: d.commonName, count: 1, best: d.confidence,
                                          photo: d.birdPhotoUrl, start: d.startTime)
            }
        }
        return order.compactMap { map[$0] }.sorted { $0.best > $1.best }
    }

    private func load() async {
        if let d: Detail = try? await API.get("api/v1/recordings/\(item.id)") {
            detections = d.detections
            fullDuration = d.durationSeconds
        }
    }
}
