import SwiftUI

struct BirdsView: View {
    @Binding var showAccount: Bool
    @EnvironmentObject var account: Account
    @AppStorage("birdsSort") private var sort = "recent"
    @State private var find = ""
    @StateObject private var loader: Loader<BirdList>

    init(showAccount: Binding<Bool>) {
        _showAccount = showAccount
        _loader = StateObject(wrappedValue: Loader { "api/v1/lite/birds?sort=" + (UserDefaults.standard.string(forKey: "birdsSort") ?? "recent") })
    }

    private static let sorts = [(id: "recent", label: "Recent"), (id: "most", label: "Most heard"),
                                (id: "new", label: "Newest"), (id: "az", label: "A–Z")]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Header(title: "Your birds", subtitle: loader.value.map { Words.count($0.count, "kind") + " of bird" } ?? "Your collection",
                       showAccount: $showAccount)
                Chips(options: Self.sorts, selection: $sort)
                if (loader.value?.count ?? 0) > 8 {
                    HStack(spacing: 10) {
                        Image(systemName: "magnifyingglass").foregroundStyle(Theme.muted)
                        TextField("Find a bird", text: $find).font(.lite(16, .bold))
                            .textInputAutocapitalization(.never).autocorrectionDisabled()
                        if !find.isEmpty {
                            Button { find = "" } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(Theme.muted) }
                        }
                    }
                    .padding(.horizontal, 14).padding(.vertical, 12).card(radius: 16)
                }
                if let list = loader.value {
                    let birds = list.birds.filter { find.isEmpty || $0.name.localizedCaseInsensitiveContains(find) }
                    if list.count == 0 {
                        EmptyState(title: "Your collection starts here", message: "Every new bird your Chirp hears gets a card.")
                    } else if birds.isEmpty {
                        EmptyState(title: "No match", message: "Nothing called “\(find)” yet.")
                    } else {
                        Tiles {
                            ForEach(birds) { b in
                                let tile = BirdTile(name: b.name, photo: b.photo, isNew: b.new, subtitle: subtitle(b))
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
        .task(id: sort) { await loader.load(account) }
    }

    private func subtitle(_ b: BirdList.Card) -> String {
        switch sort {
        case "most", "az": return Words.count(b.count, "time")
        case "new": return "First " + Words.when(b.first)
        default: return Words.when(b.last)
        }
    }
}
