import SwiftUI

struct TodayView: View {
    @Binding var showAccount: Bool
    @EnvironmentObject var account: Account
    @StateObject private var loader = Loader<Today> { "api/v1/lite/today" }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Header(title: Words.greeting(), subtitle: Date().formatted(.dateTime.weekday(.wide).month(.wide).day()),
                       showAccount: $showAccount)
                if let t = loader.value {
                    TodayBody(t: t)
                } else if let e = loader.error {
                    EmptyState(title: "Couldn't reach your Chirp", message: e,
                               action: ("Try again", { Task { await loader.load(account) } }))
                } else {
                    LoadingTiles()
                }
            }
            .padding(.horizontal, 16).padding(.bottom, 24)
        }
        .background(Theme.bg)
        .refreshable { await loader.load(account) }
        .task { await loader.load(account) }
    }
}

private struct TodayBody: View {
    let t: Today

    var body: some View {
        if let hero = t.hero { HeroCard(hero: hero) } else {
            EmptyState(title: "No birds yet", message: "When your Chirp hears its first bird, it shows up here.")
        }

        if t.speciesCount > 0 {
            HStack(spacing: 10) {
                Stat(n: t.speciesCount, label: t.speciesCount == 1 ? "bird today" : "birds today", bg: Theme.greenSoft, fg: Theme.greenDeep)
                // New birds when there are some (rare, so worth a tile); otherwise the day's first song.
                if t.newCount > 0 {
                    Stat(n: t.newCount, label: "new to you", bg: Theme.coralSoft, fg: Theme.coralInk)
                } else if let first = t.firstSong?.time {
                    Stat(value: Words.clockParts(first), label: "first song", bg: Theme.sunSoft, fg: Theme.sunInk)
                }
                Stat(n: t.recordings, label: t.recordings == 1 ? "recording" : "recordings", bg: Theme.skySoft, fg: Theme.skyInk)
            }
        } else if t.hero != nil {
            VStack(alignment: .leading, spacing: 2) {
                Text("Quiet so far today").font(.lite(17, .heavy)).foregroundStyle(Theme.ink)
                Text("Birds sing most around sunrise. The Guide shows who to listen for.")
                    .font(.lite(15, .semibold)).foregroundStyle(Theme.muted)
            }
            .padding(16).frame(maxWidth: .infinity, alignment: .leading).card()
        }

        if let summary = t.summary {
            HStack(spacing: 0) {
                Rectangle().fill(Theme.sun).frame(width: 6)
                VStack(alignment: .leading, spacing: 4) {
                    Text("TODAY'S STORY").font(.lite(12, .black)).tracking(0.9).foregroundStyle(Theme.muted)
                    Text(summary).font(.lite(17, .semibold)).foregroundStyle(Theme.ink)
                }
                .padding(16)
                Spacer(minLength: 0)
            }
            .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
            .card()
        }

        if t.detections > 0 { DayChart(hourly: t.hourly) }

        if !t.species.isEmpty {
            HStack {
                Text("Heard today").font(.lite(21, .black)).foregroundStyle(Theme.ink)
                Spacer()
            }
            Tiles {
                ForEach(t.species) { s in
                    let tile = BirdTile(name: s.name, photo: s.photo, isNew: s.new,
                                        badge: s.count > 1 ? "×\(s.count)" : nil, subtitle: Words.clock(s.last))
                    if let id = s.profileId {
                        NavigationLink(value: BirdRoute(id: id)) { tile }.buttonStyle(Pressable())
                    } else { tile }
                }
            }
        }

        Link(destination: URL(string: "https://apps.apple.com/us/app/chirp-live-bird-sound-id/id6827668744")!) {
            HStack(spacing: 14) {
                Image(systemName: "mic.fill").font(.system(size: 20, weight: .bold)).foregroundStyle(.white)
                    .frame(width: 46, height: 46)
                    .background(LinearGradient(colors: [Theme.sky, Color(hex: 0x6A5CF6)], startPoint: .topLeading, endPoint: .bottomTrailing),
                                in: RoundedRectangle(cornerRadius: 15, style: .continuous))
                VStack(alignment: .leading, spacing: 1) {
                    Text("Out on a walk?").font(.lite(17, .heavy)).foregroundStyle(Theme.ink)
                    Text("Chirp Live names birds by sound, anywhere").font(.lite(14, .semibold)).foregroundStyle(Theme.muted)
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right").font(.system(size: 14, weight: .bold)).foregroundStyle(Theme.muted)
            }
            .padding(14).card()
        }
    }
}

private struct HeroCard: View {
    let hero: Today.Hero

    var body: some View {
        let item = hero.hasAudio ? hero.recordingId.map {
            Player.Item(key: "rec-\($0)", path: "api/v1/watch/audio/\($0)", title: hero.name,
                        subtitle: Words.when(hero.time), photo: hero.photo)
        } : nil
        let card = Color.clear
            .frame(maxWidth: .infinity).frame(height: 340)
            .overlay { Photo(path: hero.photo, name: hero.name) }
            .overlay {
                LinearGradient(stops: [.init(color: .black.opacity(0.25), location: 0), .init(color: .clear, location: 0.28),
                                       .init(color: .clear, location: 0.48), .init(color: Color(hex: 0x06180E).opacity(0.85), location: 1)],
                               startPoint: .top, endPoint: .bottom)
            }
            .overlay(alignment: .bottomLeading) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(hero.name).font(.lite(34, .black)).foregroundStyle(.white)
                        .shadow(color: .black.opacity(0.3), radius: 8, y: 2)
                        .lineLimit(2).minimumScaleFactor(0.7)
                    Text(hero.today ? Words.clock(hero.time) : Words.when(hero.time))
                        .font(.lite(17, .heavy)).foregroundStyle(.white.opacity(0.9))
                }
                .padding(20).padding(.trailing, 90)
            }
        .overlay(alignment: .topLeading) {
            Text(hero.today ? "Latest visitor" : "Last heard").font(.lite(13, .heavy)).foregroundStyle(.white)
                .padding(.horizontal, 11).padding(.vertical, 5)
                .background(.ultraThinMaterial.opacity(0.9), in: Capsule())
                .environment(\.colorScheme, .dark)
                .padding(16)
        }
        .overlay(alignment: .bottomTrailing) {
            PlayButton(item: item, size: 68, fill: Theme.sun, glyph: Color(hex: 0x3A2A00), ring: .white).padding(20)
        }
        .clipShape(RoundedRectangle(cornerRadius: 30, style: .continuous))
        .shadow(color: .black.opacity(0.18), radius: 22, y: 12)

        if let id = hero.profileId {
            NavigationLink(value: BirdRoute(id: id)) { card }.buttonStyle(.plain)
        } else { card }
    }
}

private struct Stat: View {
    let value: (main: String, unit: String), label: String, bg: Color, fg: Color

    init(n: Int, label: String, bg: Color, fg: Color) {
        self.init(value: (n.formatted(), ""), label: label, bg: bg, fg: fg)
    }
    init(value: (main: String, unit: String), label: String, bg: Color, fg: Color) {
        self.value = value; self.label = label; self.bg = bg; self.fg = fg
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            (Text(value.main).font(.lite(30, .black)) + Text(value.unit.isEmpty ? "" : " " + value.unit).font(.lite(14, .black)))
                .lineLimit(1).minimumScaleFactor(0.7)
            Text(label).font(.lite(13, .heavy)).opacity(0.85).lineLimit(1).minimumScaleFactor(0.8)
        }
        .foregroundStyle(fg)
        .padding(14).frame(maxWidth: .infinity, alignment: .leading)
        .background(bg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .accessibilityElement(children: .combine)
    }
}

private struct DayChart: View {
    let hourly: [Int]
    var body: some View {
        let peak = max(1, hourly.max() ?? 1)
        let busiest = hourly.firstIndex(of: hourly.max() ?? 0) ?? 0
        let nowH = Calendar.current.component(.hour, from: Date())
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                Text("Your day").font(.lite(21, .black)).foregroundStyle(Theme.ink)
                Spacer()
                Text("Busiest around \(Words.hour(busiest))").font(.lite(14, .bold)).foregroundStyle(Theme.muted)
            }
            HStack(alignment: .bottom, spacing: 3) {
                ForEach(Array(hourly.enumerated()), id: \.offset) { h, v in
                    UnevenRoundedRectangle(topLeadingRadius: 4, bottomLeadingRadius: 2, bottomTrailingRadius: 2, topTrailingRadius: 4)
                        .fill(h == nowH ? Theme.sun : h > nowH ? Theme.line : Theme.green.opacity(0.85))
                        .frame(height: max(v > 0 ? 12 : 4, 84 * CGFloat(v) / CGFloat(peak)))
                }
            }
            .frame(height: 84, alignment: .bottom)
            HStack {
                ForEach(["12a", "6a", "12p", "6p", "11p"], id: \.self) { Text($0); if $0 != "11p" { Spacer() } }
            }
            .font(.lite(12, .bold)).foregroundStyle(Theme.muted)
        }
        .padding(16).card()
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Bird activity by hour. Busiest around \(Words.hour(busiest)).")
    }
}
