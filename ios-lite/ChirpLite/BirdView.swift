import SwiftUI

struct ListenRoute: Hashable { let bird: String }

struct BirdView: View {
    let id: String
    @EnvironmentObject var account: Account
    @Environment(\.dismiss) private var dismiss
    @StateObject private var loader: Loader<BirdProfile>

    init(id: String) {
        self.id = id
        _loader = StateObject(wrappedValue: Loader { "api/v1/lite/bird/" + (id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id) })
    }

    var body: some View {
        ZStack(alignment: .topLeading) {
            ScrollView {
                if let b = loader.value {
                    BirdBody(b: b)
                } else if let e = loader.error {
                    EmptyState(title: "Couldn't load this bird", message: e,
                               action: ("Try again", { Task { await loader.load(account) } }))
                        .padding(.top, 80)
                } else {
                    Theme.line.frame(height: 400)
                }
            }
            .ignoresSafeArea(edges: .top)
            Button { dismiss() } label: {
                Image(systemName: "chevron.left").font(.system(size: 17, weight: .bold)).foregroundStyle(Theme.ink)
                    .frame(width: 42, height: 42)
                    .background(.regularMaterial, in: Circle())
                    .shadow(color: .black.opacity(0.15), radius: 8, y: 3)
            }
            .accessibilityLabel("Back")
            .padding(.leading, 16).padding(.top, 4)
        }
        .background(Theme.bg)
        .toolbar(.hidden, for: .navigationBar)
        .task { await loader.load(account) }
    }
}

private struct BirdBody: View {
    let b: BirdProfile
    @State private var page = 0

    var body: some View {
        VStack(spacing: 0) {
            gallery
            VStack(alignment: .leading, spacing: 18) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(b.name).font(.lite(36, .black)).foregroundStyle(Theme.ink)
                            .fixedSize(horizontal: false, vertical: true)
                            .accessibilityAddTraits(.isHeader)
                        if let sci = b.scientific {
                            Text(sci).font(.lite(16, .semibold)).italic().foregroundStyle(Theme.muted)
                        }
                    }
                    Spacer(minLength: 8)
                    if let c = b.conservation { Pill(text: c, bg: Theme.skySoft, fg: Theme.ink) }
                }

                if let song = b.song, let audio = song.audio { songCard(song, audio) }

                HStack(spacing: 10) {
                    if let size = b.size { Fact(icon: "ruler", label: "SIZE", value: size.label, bg: Theme.skySoft, fg: Theme.skyInk) }
                    if let season = b.season { Fact(icon: "calendar", label: "AROUND", value: season, bg: Theme.sunSoft, fg: Theme.sunInk) }
                    Fact(icon: "ear", label: "VISITS", value: b.howOften, bg: Theme.greenSoft, fg: Theme.greenDeep)
                }
                .fixedSize(horizontal: false, vertical: true)

                if b.heardCount > 0 {
                    (Text("Your Chirp has heard it ") + Text(Words.count(b.heardCount, "time")).foregroundColor(Theme.ink)
                        + Text(b.firstHeard.map { " since \(Words.longDate($0))." } ?? "."))
                        .font(.lite(16, .bold)).foregroundStyle(Theme.muted)
                }

                if let blurb = b.blurb {
                    Text(blurb).font(.lite(18, .medium)).foregroundStyle(Theme.ink).lineSpacing(3)
                }

                if let fact = b.funFact {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("DID YOU KNOW?").font(.lite(12, .black)).tracking(0.9).foregroundStyle(Theme.sunInk)
                        Text(fact).font(.lite(17, .bold)).foregroundStyle(Theme.ink)
                    }
                    .padding(16).frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.sunSoft, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
                }

                if !b.tags.isEmpty { tags }

                // A picture of the map; SVGs only when the site can't draw them (before 0.5.19.g).
                if let map = b.rangeMapImage ?? (b.rangeMapVector == true ? nil : b.rangeMap) {
                    RangeMap(path: map, source: b.rangeMapSource, name: b.name)
                }

                if b.heardCount > 0 {
                    NavigationLink(value: ListenRoute(bird: b.name)) {
                        Label("All recordings of this bird", systemImage: "waveform")
                    }
                    .buttonStyle(MainButton())
                }
            }
            .padding(.horizontal, 18).padding(.top, 24).padding(.bottom, 40)
            .background(Theme.bg, in: UnevenRoundedRectangle(topLeadingRadius: 30, topTrailingRadius: 30, style: .continuous))
            .offset(y: -Self.cardOverlap)
            .padding(.bottom, -Self.cardOverlap)
        }
    }

    /// How far the details card rides up over the photo.
    static let cardOverlap: CGFloat = 28

    private var gallery: some View {
        let photos = b.photos
        return Color.clear.frame(height: 400)
            .overlay {
                if photos.isEmpty {
                    Photo(path: nil, name: b.name)
                } else {
                    TabView(selection: $page) {
                        ForEach(Array(photos.enumerated()), id: \.offset) { i, p in
                            Color.clear.overlay { Photo(path: p.url, name: b.name) }.clipped().tag(i)
                        }
                    }
                    .tabViewStyle(.page(indexDisplayMode: .never))
                }
            }
            // The system dots sat under the card's overlap; these sit just above it.
            .overlay(alignment: .bottom) {
                if photos.count > 1 {
                    PageDots(count: photos.count, current: page)
                        .padding(.bottom, Self.cardOverlap + 10)
                }
            }
            .overlay(alignment: .topTrailing) {
                if let p = photos[safe: page], let credit = p.credit {
                    Text(p.yours == true ? "Your photo" : "© " + Words.credit(credit))
                        .font(.lite(11, .bold)).foregroundStyle(.white).lineLimit(1)
                        .padding(.horizontal, 8).padding(.vertical, 3)
                        .background(.black.opacity(0.35), in: RoundedRectangle(cornerRadius: 8))
                        .padding(.top, 60).padding(.trailing, 12)
                        .frame(maxWidth: 240, alignment: .trailing)
                }
            }
            .clipped()
    }

    private func songCard(_ song: BirdProfile.Song, _ audio: String) -> some View {
        let yours = song.kind == "yours"
        let path = yours ? song.recordingId.map { "api/v1/watch/audio/\($0)" } ?? audio : audio
        let item = Player.Item(key: yours ? "rec-\(song.recordingId ?? b.id)" : "ref-\(b.id)", path: path,
                               start: yours ? (song.startsAt ?? 0) : 0, title: b.name,
                               subtitle: yours ? "Heard " + Words.when(song.time) : "Reference song", photo: b.photos.first?.url)
        return HStack(spacing: 16) {
            PlayButton(item: item, size: 64, fill: .white, glyph: Theme.greenDeep, ring: Theme.sun)
            VStack(alignment: .leading, spacing: 2) {
                Text(yours ? "Hear it in your yard" : "Hear its song").font(.lite(19, .black))
                Text(yours ? "Recorded " + Words.when(song.time) : (song.credit.map { "Recording © \($0)" } ?? "Reference recording"))
                    .font(.lite(14, .bold)).opacity(0.9).lineLimit(2)
            }
            .foregroundStyle(.white)
            Spacer(minLength: 0)
        }
        .padding(16)
        .background(LinearGradient(colors: [Theme.green, Color(hex: 0x2CC985)], startPoint: .leading, endPoint: .trailing),
                    in: RoundedRectangle(cornerRadius: 22, style: .continuous))
        .shadow(color: Theme.green.opacity(0.32), radius: 14, y: 8)
    }

    private var tags: some View {
        let icons = ["habitat": "tree.fill", "food": "fork.knife", "nesting": "house.fill", "behavior": "bird.fill"]
        return FlowLayout(spacing: 8) {
            ForEach(b.tags, id: \.self) { t in
                Label(t.label, systemImage: icons[t.kind] ?? "circle.fill")
                    .font(.lite(14, .bold)).foregroundStyle(Theme.ink)
                    .padding(.horizontal, 14).padding(.vertical, 8)
                    .card(radius: 999)
            }
        }
    }
}

/// The range map, shown once it has loaded (hidden if it can't be).
private struct RangeMap: View {
    let path: String
    let source: String?
    let name: String
    @EnvironmentObject var account: Account
    @State private var image: UIImage?

    var body: some View {
        Group {
            if let image {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Where it lives").font(.lite(21, .black)).foregroundStyle(Theme.ink)
                    if let source { Text("Map: \(source)").font(.lite(13, .bold)).foregroundStyle(Theme.muted) }
                    Image(uiImage: image).resizable().aspectRatio(contentMode: .fit)
                        .background(Color.white)
                        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
                        .card()
                        .padding(.top, 6)
                        .accessibilityLabel("Range map for \(name)")
                }
                .transition(.opacity)
            }
        }
        .task(id: path) {
            let img = await ImageStore.shared.image(path, account: account)
            withAnimation(.easeOut(duration: 0.25)) { image = img }
        }
    }
}

private struct Fact: View {
    let icon: String, label: String, value: String, bg: Color, fg: Color
    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Image(systemName: icon).font(.system(size: 18, weight: .bold)).padding(.bottom, 3)
            Text(label).font(.lite(11, .black)).tracking(0.6).opacity(0.75)
            Text(value).font(.lite(16, .black)).lineLimit(3).minimumScaleFactor(0.85)
                .fixedSize(horizontal: false, vertical: true)
        }
        .foregroundStyle(fg)
        .padding(14).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(bg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .accessibilityElement(children: .combine)
    }
}

/// Wraps chips onto as many lines as they need.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let w = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, line: CGFloat = 0, widest: CGFloat = 0
        for v in subviews {
            let s = v.sizeThatFits(.unspecified)
            if x > 0 && x + s.width > w { x = 0; y += line + spacing; line = 0 }
            x += s.width + spacing; line = max(line, s.height); widest = max(widest, x - spacing)
        }
        return CGSize(width: min(widest, w), height: y + line)
    }
    func placeSubviews(in b: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = b.minX, y = b.minY, line: CGFloat = 0
        for v in subviews {
            let s = v.sizeThatFits(.unspecified)
            if x > b.minX && x + s.width > b.maxX { x = b.minX; y += line + spacing; line = 0 }
            v.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(s))
            x += s.width + spacing; line = max(line, s.height)
        }
    }
}

extension Array {
    subscript(safe i: Int) -> Element? { indices.contains(i) ? self[i] : nil }
}

/// Photo page dots on a small glass capsule, readable over any picture.
struct PageDots: View {
    let count: Int
    let current: Int
    var body: some View {
        HStack(spacing: 7) {
            ForEach(0..<count, id: \.self) { i in
                Circle().fill(.white.opacity(i == current ? 1 : 0.45))
                    .frame(width: i == current ? 8 : 6, height: i == current ? 8 : 6)
            }
        }
        .padding(.horizontal, 10).padding(.vertical, 6)
        .background(.ultraThinMaterial, in: Capsule())
        .environment(\.colorScheme, .dark)
        .animation(.snappy(duration: 0.2), value: current)
        .accessibilityElement()
        .accessibilityLabel("Photo \(current + 1) of \(count)")
    }
}
