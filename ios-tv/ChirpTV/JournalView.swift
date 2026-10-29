import SwiftUI

/// The site's Daily and Weekly Journal (GET /recordings/statistics/daily-journal
/// and weekly-journal), set for reading across the room.
struct JournalView: View {
    @State private var which = 0
    @State private var daily: Entry?
    @State private var weekly: Entry?
    @State private var error: String?

    struct Entry: Decodable { let enabled: Bool?; let text: String?; let generatedAt: String? }

    var body: some View {
        let e = which == 0 ? daily : weekly
        VStack(alignment: .leading, spacing: 30) {
            HStack {
                Text("Journal").font(.system(size: 54, weight: .semibold, design: .serif))
                Spacer()
                Picker("Journal", selection: $which) {
                    Text("Daily").tag(0)
                    Text("Weekly").tag(1)
                }
                .pickerStyle(.segmented).frame(width: 460)
            }
            if let d = ISO.date(e?.generatedAt) {
                Text(d.formatted(date: .complete, time: .shortened)).font(.callout).foregroundStyle(Theme.muted)
            }
            // The Siri Remote scrolls by moving focus, so each paragraph is
            // focusable; a single focusable Text never scrolls.
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(paragraphs(e).enumerated()), id: \.offset) { _, p in
                        Paragraph(text: p)
                    }
                }
                .frame(maxWidth: 1460, alignment: .leading)
                .padding(.bottom, 60)
            }
            if let error { Text(error).foregroundStyle(Theme.rose) }
        }
        .padding(.horizontal, 80).padding(.vertical, 40)
        .task { await load() }
    }

    private func paragraphs(_ e: Entry?) -> [String] {
        text(e).components(separatedBy: "\n").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
    }

    private func text(_ e: Entry?) -> String {
        guard let e else { return "Loading…" }
        if e.enabled == false { return "The journal isn't turned on for this site. An admin can turn it on in Settings → AI." }
        return (e.text?.isEmpty == false) ? e.text! : "No journal yet. It's written each evening."
    }

    private func load() async {
        do {
            daily = try await API.get("api/v1/recordings/statistics/daily-journal")
            weekly = try await API.get("api/v1/recordings/statistics/weekly-journal")
            error = nil
        } catch {
            self.error = API.describe(error)
        }
    }
}

/// One journal paragraph. Focus shows a soft card so the reader can see
/// where they are while scrolling with the remote.
private struct Paragraph: View {
    let text: String
    @FocusState private var focused: Bool

    var body: some View {
        Text(text)
            .font(.system(size: 34, design: .serif))
            .lineSpacing(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 24).padding(.vertical, 18)
            .background(focused ? Theme.card : Color.clear, in: RoundedRectangle(cornerRadius: 20))
            .focusable()
            .focused($focused)
            .animation(.easeOut(duration: 0.15), value: focused)
    }
}

/// Signed-in account, server and sign out.
struct AccountView: View {
    @EnvironmentObject var account: Account
    @EnvironmentObject var player: Player
    @EnvironmentObject var live: LiveSession

    var body: some View {
        VStack(alignment: .leading, spacing: 30) {
            Text("Account").font(.system(size: 54, weight: .semibold, design: .serif))
            row("Signed in as", account.username.isEmpty ? "—" : account.username)
            row("Server", account.server.absoluteString)
            Text("This TV can view birds, play recordings and listen through your stations. To remove it, sign out here.")
                .foregroundStyle(Theme.muted).frame(maxWidth: 1200, alignment: .leading)
            Button("Sign out", role: .destructive) {
                player.stop()
                live.stop()
                account.signOut()
            }
            Spacer()
            Text("Chirp for Apple TV · \(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "")")
                .font(.caption).foregroundStyle(Theme.muted)
        }
        .padding(.horizontal, 80).padding(.vertical, 40)
    }

    private func row(_ k: String, _ v: String) -> some View {
        HStack(spacing: 20) {
            Text(k).foregroundStyle(Theme.muted).frame(width: 300, alignment: .leading)
            Text(v).font(.title3)
        }
    }
}
