import SwiftUI

/// Big screen title with the account button.
struct Header: View {
    let title: String
    var subtitle: String?
    @EnvironmentObject var account: Account
    @Binding var showAccount: Bool

    var body: some View {
        HStack(alignment: .bottom, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                if let subtitle {
                    Text(subtitle).font(.lite(15, .bold)).foregroundStyle(Theme.muted)
                }
                Text(title).font(.lite(34, .black)).foregroundStyle(Theme.ink)
                    .lineLimit(2).minimumScaleFactor(0.7)
                    .accessibilityAddTraits(.isHeader)
            }
            Spacer(minLength: 0)
            Button { showAccount = true } label: {
                Text(String(account.username.prefix(1)).uppercased())
                    .font(.lite(18, .black)).foregroundStyle(.white)
                    .frame(width: 44, height: 44)
                    .background(Theme.green, in: Circle())
                    .shadow(color: .black.opacity(0.1), radius: 6, y: 3)
            }
            .accessibilityLabel("Account")
        }
        .padding(.top, 8)
    }
}

/// Photo tile for a bird (Today, Birds, Guide).
struct BirdTile<Extra: View>: View {
    let name: String
    let photo: String?
    var isNew = false
    var badge: String?
    var subtitle: String?
    @ViewBuilder var extra: () -> Extra

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Color.clear.aspectRatio(1, contentMode: .fit)
                .overlay { Photo(path: photo, name: name) }
                .overlay(alignment: .topLeading) { if isNew { Pill(text: "New", bg: Theme.coral, fg: .white).padding(10) } }
                .overlay(alignment: .topTrailing) { if let badge { Pill(text: badge, bg: .black.opacity(0.65), fg: .white).padding(10) } }
                .clipped()
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(.lite(16, .heavy)).foregroundStyle(Theme.ink).lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                if let subtitle { Text(subtitle).font(.lite(13, .bold)).foregroundStyle(Theme.muted) }
                extra()
            }
            .padding(.horizontal, 12).padding(.vertical, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .card()
        .accessibilityElement(children: .combine)
    }
}

extension BirdTile where Extra == EmptyView {
    init(name: String, photo: String?, isNew: Bool = false, badge: String? = nil, subtitle: String? = nil) {
        self.init(name: name, photo: photo, isNew: isNew, badge: badge, subtitle: subtitle) { EmptyView() }
    }
}

struct Pill: View {
    let text: String
    var bg: Color = Theme.greenSoft
    var fg: Color = Theme.greenDeep
    var body: some View {
        Text(text).font(.lite(12, .heavy)).foregroundStyle(fg)
            .padding(.horizontal, 10).padding(.vertical, 4)
            .background(bg, in: Capsule())
    }
}

struct Tiles<Content: View>: View {
    @ViewBuilder var content: () -> Content
    @Environment(\.horizontalSizeClass) private var size
    var body: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12, alignment: .top), count: size == .regular ? 4 : 2),
                  spacing: 12, content: content)
    }
}

struct EmptyState: View {
    let title: String
    var message: String?
    var action: (title: String, run: () -> Void)?
    var body: some View {
        VStack(spacing: 10) {
            BirdMark(size: 84)
            Text(title).font(.lite(22, .black)).foregroundStyle(Theme.ink).multilineTextAlignment(.center)
            if let message {
                Text(message).font(.lite(16, .semibold)).foregroundStyle(Theme.muted).multilineTextAlignment(.center)
                    .frame(maxWidth: 300)
            }
            if let action {
                Button(action.title, action: action.run).buttonStyle(MainButton()).padding(.top, 6)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
    }
}

struct MainButton: ButtonStyle {
    var soft = false
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.lite(17, .heavy))
            .foregroundStyle(soft ? Theme.ink : .white)
            .padding(.horizontal, 22).padding(.vertical, 14)
            .frame(maxWidth: .infinity)
            .background(soft ? Theme.card : Theme.green, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .shadow(color: (soft ? Color.black : Theme.green).opacity(soft ? 0.07 : 0.3), radius: 10, y: 5)
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .opacity(configuration.isPressed ? 0.9 : 1)
    }
}

/// Skeleton while a screen loads for the first time.
struct LoadingTiles: View {
    @State private var dim = false
    var body: some View {
        VStack(spacing: 16) {
            RoundedRectangle(cornerRadius: 30, style: .continuous).fill(Theme.line).frame(height: 300)
            Tiles { ForEach(0..<4, id: \.self) { _ in
                RoundedRectangle(cornerRadius: 22, style: .continuous).fill(Theme.line).aspectRatio(0.8, contentMode: .fit)
            } }
        }
        .opacity(dim ? 0.5 : 1)
        .onAppear { withAnimation(.easeInOut(duration: 0.9).repeatForever()) { dim = true } }
        .accessibilityLabel("Loading")
    }
}

/// Chips for sorting and filtering.
struct Chips: View {
    let options: [(id: String, label: String)]
    @Binding var selection: String
    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(options, id: \.id) { o in
                    let on = selection == o.id
                    Button { withAnimation(.snappy) { selection = o.id } } label: {
                        Text(o.label).font(.lite(15, .heavy))
                            .foregroundStyle(on ? Theme.bg : Theme.muted)
                            .padding(.horizontal, 16).padding(.vertical, 9)
                            .background(on ? Theme.ink : Theme.card, in: Capsule())
                            .shadow(color: .black.opacity(on ? 0 : 0.06), radius: 6, y: 3)
                    }
                    .accessibilityAddTraits(on ? .isSelected : [])
                }
            }
            .padding(.horizontal, 16).padding(.vertical, 4)
        }
        .padding(.horizontal, -16)
    }
}

/// Where tapping a bird goes.
struct BirdRoute: Hashable { let id: String }
