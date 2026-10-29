import SwiftUI

/// Today so far: totals, activity by hour and every species heard
/// (GET /recordings/statistics/digest?date=today). Refreshes every minute.
struct TodayView: View {
    @EnvironmentObject var account: Account
    @EnvironmentObject var player: Player
    @State private var digest: Digest?
    @State private var error: String?
    @State private var day = Date()

    struct Digest: Decodable {
        let day: String
        let partial: Bool?
        let quiet: Bool?
        let recordings: Int?
        let detections: Int?
        let speciesCount: Int?
        let busiestHour: String?
        let hours: [Int]?
        let species: [Species]?
    }
    struct Species: Decodable, Identifiable {
        let name: String
        let count: Int
        let new: Bool?
        let best: Double?
        let firstHeard: String?
        let photoUrl: String?
        let bestRecordingId: String?
        var id: String { name }
    }

    private let columns = Array(repeating: GridItem(.flexible(), spacing: 40), count: 5)

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 40) {
                header
                if let d = digest, d.quiet != true {
                    HStack(alignment: .top, spacing: 40) {
                        stat(d.speciesCount ?? 0, "species")
                        stat(d.recordings ?? 0, "recordings")
                        stat(d.detections ?? 0, "detections")
                        if let h = d.hours { HourBars(hours: h, busiest: d.busiestHour) }
                    }
                    LazyVGrid(columns: columns, spacing: 50) {
                        ForEach(d.species ?? []) { sp in speciesCard(sp) }
                    }
                } else if digest?.quiet == true {
                    Text("No birds yet today. Check back once the station hears something.")
                        .font(.title3).foregroundStyle(Theme.muted)
                } else if error == nil {
                    ProgressView().frame(maxWidth: .infinity)
                }
                if let error { Text(error).foregroundStyle(Theme.rose) }
            }
            .padding(.horizontal, 80).padding(.vertical, 40)
        }
        .task { await refreshLoop() }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("TODAY").font(.caption).tracking(3).foregroundStyle(Theme.amber)
            Text(digest?.day ?? day.formatted(date: .complete, time: .omitted))
                .font(.system(size: 54, weight: .semibold, design: .serif))
        }
    }

    private func stat(_ n: Int, _ label: String) -> some View {
        VStack(spacing: 4) {
            Text(n.formatted()).font(.system(size: 64, weight: .bold, design: .serif)).foregroundStyle(Theme.amber)
            Text(label.uppercased()).font(.caption).tracking(2).foregroundStyle(Theme.muted)
        }
        .frame(width: 260, height: HourBars.height)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 28))
    }

    private func speciesCard(_ sp: Species) -> some View {
        Button {
            if let rid = sp.bestRecordingId { Task { await player.toggle(id: rid, title: sp.name) } }
        } label: {
            VStack(alignment: .leading, spacing: 0) {
                ZStack(alignment: .topTrailing) {
                    BirdPhoto(path: sp.photoUrl).frame(width: 300, height: 230).clipped()
                    if sp.new == true {
                        Text("NEW").font(.caption2.bold()).padding(.horizontal, 12).padding(.vertical, 6)
                            .background(Theme.amber, in: Capsule()).foregroundStyle(.black).padding(14)
                    }
                    if let rid = sp.bestRecordingId, player.playingID == rid || player.loadingID == rid {
                        Image(systemName: player.loadingID == rid ? "hourglass" : "speaker.wave.2.fill")
                            .font(.title3).padding(14).background(.black.opacity(0.55), in: Circle()).padding(14)
                            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)
                    }
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text(sp.name).font(.headline).lineLimit(1).minimumScaleFactor(0.7)
                    Text(sp.firstHeard.map { "first \($0)" } ?? " ")
                        .font(.caption).foregroundStyle(Theme.muted).lineLimit(1)
                    Text(["\(sp.count) detections", sp.best.map { "best \(Theme.confidence($0))" }]
                        .compactMap { $0 }.joined(separator: " · "))
                        .font(.caption).foregroundStyle(Theme.amber).lineLimit(1).minimumScaleFactor(0.8)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(20)
            }
            .frame(width: 300)
        }
        .buttonStyle(.card)
        .accessibilityHint(sp.bestRecordingId == nil ? "" : "Plays the best recording")
    }

    private func refreshLoop() async {
        while !Task.isCancelled {
            await load()
            try? await Task.sleep(for: .seconds(60))
        }
    }

    private func load() async {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        day = Date()
        do {
            digest = try await API.get("api/v1/recordings/statistics/digest?date=\(f.string(from: day))")
            error = nil
        } catch {
            self.error = API.describe(error)
        }
    }
}

/// Activity by hour, busiest hour highlighted.
struct HourBars: View {
    let hours: [Int]
    let busiest: String?
    /// The stat cards beside it use the same height.
    static let height: CGFloat = 230

    var body: some View {
        let peak = max(hours.max() ?? 1, 1)
        let top = hours.firstIndex(of: peak)
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                Text("Activity by hour").font(.headline)
                Spacer()
                if let busiest { Text("busiest \(busiest)").font(.caption).foregroundStyle(Theme.muted) }
            }
            HStack(alignment: .bottom, spacing: 5) {
                ForEach(Array(hours.enumerated()), id: \.offset) { i, v in
                    RoundedRectangle(cornerRadius: 4)
                        .fill(i == top ? Theme.amber : Theme.amber.opacity(0.4))
                        .frame(height: max(4, 90 * CGFloat(v) / CGFloat(peak)))
                }
            }
            .frame(height: 90, alignment: .bottom)
            HStack {
                Text("12a"); Spacer(); Text("6a"); Spacer(); Text("12p"); Spacer(); Text("6p"); Spacer(); Text("11p")
            }
            .font(.caption2).foregroundStyle(Theme.muted)
        }
        .padding(.horizontal, 26).padding(.vertical, 22)
        .frame(maxWidth: .infinity)
        .frame(height: Self.height)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 28))
        .accessibilityElement(children: .combine)
    }
}
