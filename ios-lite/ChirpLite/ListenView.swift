import SwiftUI

struct ListenView: View {
    @Binding var showAccount: Bool
    var bird: String?
    @EnvironmentObject var account: Account
    @State private var cards: [SoundPage.Sound] = []
    @State private var next: String?
    @State private var loading = false
    @State private var error: String?

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 12) {
                if bird == nil {
                    Header(title: "Listen", subtitle: "Tap a card to hear it", showAccount: $showAccount).padding(.bottom, 6)
                } else {
                    Text("Recordings of").font(.lite(15, .bold)).foregroundStyle(Theme.muted)
                    Text(bird ?? "").font(.lite(30, .black)).foregroundStyle(Theme.ink).padding(.bottom, 6)
                }
                if cards.isEmpty {
                    if let error {
                        EmptyState(title: "Couldn't reach your Chirp", message: error, action: ("Try again", { Task { await load(nil) } }))
                    } else if loading {
                        LoadingTiles()
                    } else {
                        EmptyState(title: "Nothing to hear yet", message: "Recordings show up here as your Chirp catches birds.")
                    }
                }
                ForEach(cards) { SoundCard(c: $0) }
                if let next {
                    Button(loading ? "Loading…" : "Show older") { Task { await load(next) } }
                        .buttonStyle(MainButton(soft: true)).disabled(loading)
                        .onAppear { if !loading { Task { await load(next) } } }
                }
            }
            .padding(.horizontal, 16).padding(.bottom, 24)
        }
        .background(Theme.bg)
        .toolbar(bird == nil ? .hidden : .visible, for: .navigationBar)
        .refreshable { await load(nil) }
        .task { if cards.isEmpty { await load(nil) } }
    }

    private func load(_ before: String?) async {
        guard !loading else { return }
        loading = true
        defer { loading = false }
        do {
            let path = "api/v1/lite/listen" + API.query(["before": before, "bird": bird, "limit": "20"])
            let page: SoundPage = try await API.get(path, server: account.server, token: account.token)
            cards = before == nil ? page.recordings : cards + page.recordings
            next = page.nextBefore
            error = nil
        } catch API.Failure.signedOut {
            account.signOut()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct SoundCard: View {
    let c: SoundPage.Sound
    @EnvironmentObject var player: Player

    var body: some View {
        let item = c.hasAudio ? Player.Item(key: "rec-\(c.id)", path: "api/v1/watch/audio/\(c.id)", start: c.startsAt ?? 0,
                                            title: c.bird, subtitle: Words.when(c.time), photo: c.photo) : nil
        let active = item.map { player.isActive($0.key) } ?? false
        VStack(spacing: 12) {
            HStack(spacing: 12) {
                photo
                VStack(alignment: .leading, spacing: 2) {
                    Text(c.bird).font(.lite(17, .heavy)).foregroundStyle(Theme.ink).lineLimit(2)
                    Text(Words.when(c.time) + (c.duration.map { " · \(Int($0.rounded()))s" } ?? ""))
                        .font(.lite(14, .bold)).foregroundStyle(Theme.muted)
                    if !c.others.isEmpty {
                        Text("with " + c.others.joined(separator: ", ")).font(.lite(13, .bold)).foregroundStyle(Theme.muted).lineLimit(1)
                    }
                }
                Spacer(minLength: 0)
                PlayButton(item: item)
            }
            if let spec = c.spectrogram {
                Color(hex: 0x0B1A12).frame(height: 64)
                    .overlay { Photo(path: spec, name: "", contentMode: .fill) }
                    .overlay(alignment: .leading) {
                        if active {
                            GeometryReader { g in
                                Rectangle().fill(Theme.sun).frame(width: 3)
                                    .shadow(color: Theme.sun, radius: 6)
                                    .offset(x: g.size.width * player.progress - 1.5)
                                    .animation(.linear(duration: 0.1), value: player.progress)
                            }
                        }
                    }
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .accessibilityHidden(true)
            }
        }
        .padding(12)
        .card()
        .overlay {
            RoundedRectangle(cornerRadius: 22, style: .continuous).stroke(Theme.green, lineWidth: active ? 3 : 0)
        }
    }

    @ViewBuilder private var photo: some View {
        let p = Color.clear.frame(width: 64, height: 64)
            .overlay { Photo(path: c.photo, name: c.bird) }
            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        if let id = c.profileId {
            NavigationLink(value: BirdRoute(id: id)) { p }.buttonStyle(Pressable())
        } else { p }
    }
}
