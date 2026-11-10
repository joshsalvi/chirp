import SwiftUI

struct GuideView: View {
    @Binding var showAccount: Bool
    @EnvironmentObject var account: Account
    @StateObject private var loader = Loader<Guide> { "api/v1/lite/guide" }
    @State private var show = "all"

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Header(title: "Bird guide", subtitle: "Around you in " + Date().formatted(.dateTime.month(.wide)),
                       showAccount: $showAccount)
                if let g = loader.value {
                    if g.count == 0 {
                        EmptyState(title: "Set your location", message: "Add your location in Chirp's Settings to see which birds are around this month.")
                    } else {
                        progress(g)
                        Chips(options: [("all", "All"), ("todo", "Not heard yet"), ("heard", "Heard")], selection: $show)
                        let birds = g.birds.filter { show == "all" || (show == "todo" ? !$0.heard : $0.heard) }
                        if birds.isEmpty {
                            EmptyState(title: show == "todo" ? "You've heard them all!" : "None yet",
                                       message: show == "todo" ? "Every bird on this month's list has visited." : "Birds you hear show up here.")
                        }
                        Tiles {
                            ForEach(birds) { b in
                                let colors = Theme.chance(b.likely)
                                let tile = BirdTile(name: b.name, photo: b.photo) {
                                    HStack(spacing: 6) {
                                        Pill(text: Chance(rawValue: b.likely)?.label ?? b.likely, bg: colors.bg, fg: colors.ink)
                                        if b.heard {
                                            Label("Heard", systemImage: "checkmark").font(.lite(12, .heavy)).foregroundStyle(Theme.greenDeep)
                                                .labelStyle(.titleAndIcon)
                                        }
                                    }
                                    .padding(.top, 4)
                                }
                                if let id = b.profileId {
                                    NavigationLink(value: BirdRoute(id: id)) { tile }.buttonStyle(Pressable())
                                } else { tile }
                            }
                        }
                    }
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

    private func progress(_ g: Guide) -> some View {
        let frac = g.count > 0 ? Double(g.heard) / Double(g.count) : 0
        return VStack(alignment: .leading, spacing: 10) {
            Text("\(g.heard) of \(g.count)").font(.lite(26, .black)).foregroundStyle(Theme.ink)
            Text("birds seen near you this month have visited your yard").font(.lite(15, .bold)).foregroundStyle(Theme.muted)
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Theme.greenSoft)
                    Capsule().fill(LinearGradient(colors: [Theme.green, Color(hex: 0x7EDB9F)], startPoint: .leading, endPoint: .trailing))
                        .frame(width: max(12, geo.size.width * frac))
                }
            }
            .frame(height: 12)
        }
        .padding(16).card()
        .accessibilityElement(children: .combine)
    }
}
