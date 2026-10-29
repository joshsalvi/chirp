import SwiftUI

// MARK: First launch

struct WelcomeView: View {
    var start: () -> Void
    @State private var signingIn = false
    @EnvironmentObject var account: Account

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 22) {
                Image("LiveIcon").resizable().frame(width: 92, height: 92)
                    .clipShape(RoundedRectangle(cornerRadius: 21, style: .continuous))
                    .accessibilityHidden(true)
                Text("Hear a bird.\nKnow its name.")
                    .font(.system(size: 36, weight: .bold, design: .serif))
                Text("Point your iPhone at the sound and Chirp Live names the birds as they sing. It works on your phone, even without signal, and you don't need an account.")
                    .font(.system(size: 17)).foregroundStyle(Theme.body)
                VStack(alignment: .leading, spacing: 12) {
                    feature("mic", "Knows over 6,000 species, right on the phone")
                    feature("location", "Uses your location to rule out unlikely birds")
                    feature("waveform", "Keeps what you heard, with the sound")
                }
                .padding(.top, 4)
            }
            Spacer()
            Button("Start listening", action: start).buttonStyle(PillButtonStyle())
            Button(account.signedIn ? "Signed in to \(account.siteName)" : "I have a Chirp site: sign in") { signingIn = true }
                .buttonStyle(PillButtonStyle(filled: false)).padding(.top, 12)
                .disabled(account.signedIn)
            Text("Signing in saves sessions to your site too. Powered by BirdNET.")
                .font(.footnote).foregroundStyle(Theme.muted)
                .frame(maxWidth: .infinity).padding(.top, 12)
        }
        .foregroundStyle(Theme.ink)
        .padding(.horizontal, 28).padding(.top, 40).padding(.bottom, 24)
        .background(Theme.bg.ignoresSafeArea())
        .sheet(isPresented: $signingIn) { SignInView() }
    }

    private func feature(_ icon: String, _ text: String) -> some View {
        Label { Text(text).foregroundStyle(Theme.body) } icon: { Image(systemName: icon).foregroundStyle(Theme.amber) }
            .font(.system(size: 15))
    }
}

// MARK: Listening

struct ListenView: View {
    @EnvironmentObject var listener: Listener
    @EnvironmentObject var store: SessionStore
    @EnvironmentObject var account: Account
    @Binding var finished: Session?
    @AppStorage("minConfidence") private var minConfidence = 0.3
    @State private var bird: Heard?
    @ObservedObject private var pack = BirdPack.shared

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Text(listener.listening ? "Listening" : "Chirp Live")
                        .font(.system(size: 28, weight: .bold, design: .serif))
                    Spacer()
                    if listener.listening, let started = listener.started {
                        TimelineView(.periodic(from: .now, by: 1)) { ctx in
                            HStack(spacing: 8) {
                                Circle().fill(Theme.red).frame(width: 9, height: 9)
                                Text(Theme.clock(ctx.date.timeIntervalSince(started)))
                                    .font(.system(size: 15, design: .monospaced)).foregroundStyle(Theme.body)
                            }
                        }
                    }
                }

                if account.signedIn && !listener.stations.isEmpty {
                    SourcePicker()
                }

                LevelBars(levels: listener.levels, active: listener.listening)

                if case .failed(let why) = listener.state {
                    Text(why).foregroundStyle(Theme.orange).font(.callout)
                }

                if let s = listener.singing {
                    Button { bird = s } label: { SingingCard(h: s) }.buttonStyle(.plain)
                } else if listener.listening {
                    Text(listener.heard.isEmpty ? "Listening for birds… the first check comes after 3 seconds."
                                                : "Quiet right now.")
                        .font(.callout).foregroundStyle(Theme.muted)
                }

                if listener.listening, case .phone = listener.source, let place = listener.placeName {
                    Label(place, systemImage: "location").font(.footnote).foregroundStyle(Theme.muted)
                }

                if listener.listening && account.signedIn {
                    Text(listener.sentToSite == 0 ? "Birds you hear are also sent to \(account.siteName)."
                                                  : "\(listener.sentToSite) clip\(listener.sentToSite == 1 ? "" : "s") confirmed by \(account.siteName)")
                        .font(.footnote).foregroundStyle(Theme.muted)
                }

                if !listener.listening && listener.heard.isEmpty && pack.entries.isEmpty {
                    switch pack.state {
                    case .working(let what):
                        HStack(spacing: 10) { ProgressView(); Text(what).font(.footnote).foregroundStyle(Theme.muted) }
                    default:
                        Button { Task { await pack.download() } } label: {
                            Label("Add pictures of the birds around you", systemImage: "photo.on.rectangle")
                                .font(.callout)
                        }
                        if case .failed(let why) = pack.state { Text(why).font(.footnote).foregroundStyle(Theme.orange) }
                    }
                }

                if !listener.heard.isEmpty {
                    VStack(alignment: .leading, spacing: 0) {
                        Text("Heard this session · \(listener.heard.count) species".uppercased())
                            .font(.system(size: 13)).kerning(1).foregroundStyle(Theme.muted).padding(.bottom, 6)
                        ForEach(listener.heard) { h in
                            HStack(spacing: 12) {
                                BirdThumb(sci: h.scientific, common: h.common, size: 32)
                                Text(h.common).font(.system(size: 16))
                                Spacer()
                                Text("\(h.count)×").foregroundStyle(Theme.muted)
                                Text(Theme.percent(h.best)).font(.system(size: 13, design: .monospaced))
                                    .foregroundStyle(Theme.body).frame(width: 44, alignment: .trailing)
                            }
                            .padding(.vertical, 7)
                            .contentShape(Rectangle())
                            .onTapGesture { bird = h }
                            .overlay(alignment: .top) { Rectangle().fill(Theme.line).frame(height: 1) }
                        }
                    }
                }

            }
            .foregroundStyle(Theme.ink)
            .padding(20)
        }
        .safeAreaInset(edge: .bottom) {
            VStack(spacing: 8) {
                RecordButton(on: listener.listening) {
                    if listener.listening {
                        finished = listener.stop()
                    } else {
                        listener.minConfidence = minConfidence
                        listener.start()
                    }
                }
                if !listener.listening {
                    Text(listener.usingLocation ? "Using your location to narrow the list" : "Tap to listen")
                        .font(.footnote).foregroundStyle(Theme.muted)
                }
            }
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity)
            .background(Theme.bg.opacity(0.95))
        }
        .task { await listener.loadStations() }
        .onChange(of: account.signedIn) { Task { await listener.loadStations() } }
        .sheet(item: $bird) { h in BirdDetailView(sci: h.scientific, common: h.common, heard: h) }
        .background(Theme.bg.ignoresSafeArea())
    }
}

/// This iPhone or one of the site's stations.
struct SourcePicker: View {
    @EnvironmentObject var listener: Listener

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Menu {
                Button { listener.source = .phone } label: {
                    Label("This iPhone", systemImage: listener.source == .phone ? "checkmark" : "iphone")
                }
                Section("Your stations") {
                    ForEach(listener.stations) { st in
                        Button { listener.source = .station(st) } label: {
                            Label(st.online ? st.name : "\(st.name) (offline)",
                                  systemImage: listener.source == .station(st) ? "checkmark" : "dot.radiowaves.left.and.right")
                        }
                    }
                }
            } label: {
                HStack(spacing: 12) {
                    Image(systemName: icon)
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(Theme.amber)
                        .frame(width: 38, height: 38)
                        .background(Theme.amber.opacity(0.14), in: Circle())
                    VStack(alignment: .leading, spacing: 2) {
                        Text("LISTEN WITH").font(.system(size: 11, weight: .semibold)).kerning(1).foregroundStyle(Theme.muted)
                        Text(title).font(.system(size: 17, weight: .semibold)).foregroundStyle(Theme.ink)
                    }
                    Spacer(minLength: 8)
                    if case .station(let st) = listener.source {
                        Circle().fill(st.online ? Theme.leaf : Theme.muted).frame(width: 8, height: 8)
                            .accessibilityLabel(st.online ? "Online" : "Offline")
                    }
                    Image(systemName: "chevron.up.chevron.down")
                        .font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.muted)
                }
                .padding(.horizontal, 14).padding(.vertical, 12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.card, in: RoundedRectangle(cornerRadius: 16))
                .overlay(RoundedRectangle(cornerRadius: 16).stroke(Theme.ink.opacity(0.08)))
                .contentShape(RoundedRectangle(cornerRadius: 16))
            }
            .disabled(listener.listening)
            .opacity(listener.listening ? 0.7 : 1)
            .accessibilityLabel("Listen with \(title)")
            if case .station(let st) = listener.source {
                Text("You'll hear \(st.name)'s microphone, and Chirp Live names the birds on this iPhone.")
                    .font(.footnote).foregroundStyle(Theme.muted)
            }
        }
    }

    private var title: String {
        if case .station(let st) = listener.source { return st.name }
        return "This iPhone"
    }
    private var icon: String {
        if case .station = listener.source { return "dot.radiowaves.left.and.right" }
        return "iphone"
    }
}

struct SingingCard: View {
    let h: Heard
    var body: some View {
        HStack(spacing: 14) {
            BirdThumb(sci: h.scientific, common: h.common, size: 56)
            VStack(alignment: .leading, spacing: 4) {
                Text("SINGING NOW").font(.system(size: 13)).kerning(1).foregroundStyle(Theme.amber)
                Text(h.common).font(.system(size: 21, weight: .semibold, design: .serif))
                Text("\(Theme.percent(h.best)) sure · \(h.count) time\(h.count == 1 ? "" : "s") so far")
                    .font(.system(size: 14)).foregroundStyle(Theme.muted)
            }
            Spacer(minLength: 0)
        }
        .padding(16)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(Theme.amber.opacity(0.35)))
        .accessibilityElement(children: .combine)
    }
}

/// Recent sound level, newest on the right.
struct LevelBars: View {
    let levels: [Float]
    let active: Bool
    var body: some View {
        HStack(alignment: .bottom, spacing: 3) {
            ForEach(levels.indices, id: \.self) { i in
                let v = CGFloat(levels[i])
                RoundedRectangle(cornerRadius: 2)
                    .fill(v > 0.7 ? Theme.orange : v > 0.45 ? Theme.amber : v > 0.25 ? Theme.amber.opacity(0.55) : Theme.muted.opacity(0.35))
                    .frame(height: max(4, v * 100))
            }
        }
        .frame(height: 100, alignment: .bottom)
        .padding(14)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 16))
        .opacity(active ? 1 : 0.5)
        .accessibilityHidden(true)
    }
}

struct RecordButton: View {
    let on: Bool
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            ZStack {
                Circle().fill(on ? Theme.red : Theme.amber).frame(width: 78, height: 78)
                Circle().stroke((on ? Theme.red : Theme.amber).opacity(0.35), lineWidth: 4).frame(width: 86, height: 86)
                if on {
                    RoundedRectangle(cornerRadius: 5).fill(.white).frame(width: 24, height: 24)
                } else {
                    Image(systemName: "mic.fill").font(.system(size: 28)).foregroundStyle(Color(red: 0.1, green: 0.08, blue: 0.02))
                }
            }
        }
        .accessibilityLabel(on ? "Stop listening" : "Start listening")
    }
}

// MARK: After a session

struct SummaryView: View {
    let initial: Session
    @EnvironmentObject var store: SessionStore
    @EnvironmentObject var player: ClipPlayer
    @State private var bird: Heard?
    @State private var renaming = false
    @State private var newName = ""

    init(session: Session) { initial = session }
    /// The stored copy, which changes as saving to the site goes.
    private var session: Session { store.sessions.first { $0.id == initial.id } ?? initial }

    var body: some View {
        let earlier = Set(store.sessions.filter { $0.id != session.id }.flatMap { $0.heard.map(\.scientific) })
        let newOnes = session.heard.filter { !earlier.contains($0.scientific) }.count
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(dateLine).font(.system(size: 14)).foregroundStyle(Theme.muted)
                    Button { newName = session.title; renaming = true } label: {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(session.title).font(.system(size: 28, weight: .bold, design: .serif)).foregroundStyle(Theme.ink)
                                .multilineTextAlignment(.leading)
                            Image(systemName: "pencil").font(.system(size: 15)).foregroundStyle(Theme.muted)
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityHint("Rename this session")
                    if let w = session.whereLine {
                        Label(w, systemImage: session.stationName == nil ? "location" : "dot.radiowaves.left.and.right")
                            .font(.system(size: 14)).foregroundStyle(Theme.body)
                            .textSelection(.enabled)
                    }
                }
                HStack(spacing: 10) {
                    stat("\(session.heard.count)", "species")
                    stat("\(newOnes)", "new to you")
                    stat(minutes, "listening")
                }
                recordingRow
                VStack(spacing: 0) {
                    ForEach(session.heard) { h in
                        let url = store.clipURL(session, h)
                        HStack(spacing: 12) {
                            Button { if let url { player.toggle(url) } } label: {
                                Image(systemName: player.playing == url && url != nil ? "pause.fill" : "play.fill")
                                    .frame(width: 40, height: 40)
                                    .background(Theme.amber.opacity(0.14), in: Circle())
                            }
                            .disabled(url == nil)
                            .accessibilityLabel("Play \(h.common)")
                            Button { bird = h } label: {
                                HStack(spacing: 10) {
                                    BirdThumb(sci: h.scientific, common: h.common, size: 40)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(h.common).font(.system(size: 16)).foregroundStyle(Theme.ink)
                                        Text("\(h.count) call\(h.count == 1 ? "" : "s") · best \(Theme.percent(h.best))")
                                            .font(.system(size: 13)).foregroundStyle(Theme.muted)
                                    }
                                    Spacer(minLength: 0)
                                }
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                            Spacer()
                            if !earlier.contains(h.scientific) {
                                Text("New").font(.system(size: 12, weight: .semibold))
                                    .padding(.horizontal, 8).padding(.vertical, 4)
                                    .background(Theme.leaf.opacity(0.14), in: Capsule()).foregroundStyle(Theme.leaf)
                            }
                        }
                        .padding(.vertical, 10)
                        .overlay(alignment: .top) { Rectangle().fill(Theme.line).frame(height: 1) }
                        .contentShape(Rectangle())
                        .contextMenu {
                            if let url {
                                ShareLink(item: SharedSound(url: url, name: "\(h.common), \(fileDate)"),
                                          preview: SharePreview("\(h.common) (Chirp Live)")) {
                                    Label("Share \(h.common)'s sound", systemImage: "square.and.arrow.up")
                                }
                            }
                        }
                    }
                }
                if let problem = player.problem {
                    Text(problem).font(.footnote).foregroundStyle(Theme.orange)
                }
                HStack(spacing: 10) {
                    if let audio = store.audioURL(session) {
                        ShareLink(item: SharedSound(url: audio, name: "\(session.title), \(fileDate)"),
                                  preview: SharePreview("\(session.title) (Chirp Live)")) {
                            Label("Share sound", systemImage: "waveform").frame(maxWidth: .infinity)
                        }
                        .buttonStyle(PillButtonStyle(filled: false))
                    }
                    ShareLink(item: shareText) { Label("Share list", systemImage: "list.bullet").frame(maxWidth: .infinity) }
                        .buttonStyle(PillButtonStyle(filled: false))
                }
                siteStatus.font(.footnote).multilineTextAlignment(.center).frame(maxWidth: .infinity)
            }
            .foregroundStyle(Theme.ink)
            .padding(20)
        }
        .background(Theme.bg.ignoresSafeArea())
        .onDisappear { player.stop() }
        .sheet(item: $bird) { h in BirdDetailView(sci: h.scientific, common: h.common, heard: h) }
        .alert("Rename session", isPresented: $renaming) {
            TextField(session.autoName ?? "Name", text: $newName)
            Button("Save") { store.rename(session, to: newName) }
            if session.name != nil { Button("Use \"\(session.autoName ?? Session.makeTitle(session))\"") { store.rename(session, to: "") } }
            Button("Cancel", role: .cancel) {}
        }
    }

    /// The whole session's sound: play it here, share it below.
    @ViewBuilder private var recordingRow: some View {
        let url = store.audioURL(session)
        HStack(spacing: 12) {
            Button { if let url { player.toggle(url) } } label: {
                Image(systemName: player.playing == url && url != nil ? "pause.fill" : "play.fill")
                    .frame(width: 40, height: 40)
                    .background(Theme.amber, in: Circle())
                    .foregroundStyle(Theme.bg)
            }
            .disabled(url == nil)
            .opacity(url == nil ? 0.35 : 1)
            .accessibilityLabel("Play the whole session")
            VStack(alignment: .leading, spacing: 2) {
                Text("Whole session").font(.system(size: 16))
                Text(url == nil ? (store.preparing.contains(session.id) ? "Preparing the sound…" : "No sound saved")
                                : "\(minutes) · \(fileSize(url!))")
                    .font(.system(size: 13)).foregroundStyle(Theme.muted)
            }
            Spacer()
        }
        .padding(12)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 14))
    }

    private func fileSize(_ url: URL) -> String {
        let n = (try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
        return ByteCountFormatter.string(fromByteCount: Int64(n), countStyle: .file)
    }

    private var fileDate: String {
        let d = DateFormatter(); d.dateFormat = "MMM d yyyy h.mm a"
        return d.string(from: session.start)
    }

    @ViewBuilder private var siteStatus: some View {
        if let site = session.site {
            switch session.savedToSite {
            case .some(true):
                Text("Saved on this iPhone and to \(site).").foregroundStyle(Theme.leaf)
            case .some(false):
                VStack(spacing: 8) {
                    Text("Saved on this iPhone. Not saved to \(site): \(session.siteError ?? "it didn't answer.")")
                        .foregroundStyle(Theme.orange)
                    if !(session.remoteIDs ?? []).isEmpty {
                        Button("Try again") { store.upload(session) }
                    }
                }
            case .none:
                if let why = session.siteError {
                    Text("Saved on this iPhone. \(why)").foregroundStyle(Theme.muted)
                } else if store.uploading.contains(session.id) || store.preparing.contains(session.id) {
                    HStack(spacing: 6) { ProgressView().controlSize(.small); Text("Saving to \(site)…") }
                        .foregroundStyle(Theme.muted)
                } else {
                    VStack(spacing: 8) {
                        Text("Saved on this iPhone, not yet on \(site).").foregroundStyle(Theme.muted)
                        Button("Save to \(site) now") { store.upload(session) }
                    }
                }
            }
        } else {
            Text("Saved on this iPhone.").foregroundStyle(Theme.muted)
        }
    }

    private var dateLine: String {
        let d = DateFormatter(); d.dateFormat = "EEE, MMM d"
        let t = DateFormatter(); t.timeStyle = .short
        return "\(d.string(from: session.start)) · \(t.string(from: session.start)) to \(t.string(from: session.end))"
    }
    private var minutes: String {
        let m = Int(session.duration / 60)
        return m < 1 ? "\(Int(session.duration))s" : "\(m)m"
    }
    private var shareText: String {
        "\(session.title), \(dateLine): " + session.heard.map(\.common).joined(separator: ", ") + ". Heard with Chirp Live."
    }

    private func stat(_ value: String, _ label: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value).font(.system(size: 26, weight: .bold, design: .serif)).foregroundStyle(Theme.amber)
            Text(label).font(.system(size: 13)).foregroundStyle(Theme.muted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 14))
    }
}

struct SessionsView: View {
    @EnvironmentObject var store: SessionStore
    @State private var renaming: Session?
    @State private var newName = ""
    var body: some View {
        List {
            ForEach(store.sessions) { s in
                NavigationLink { SummaryView(session: s) } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(s.title)
                        Text("\(s.start.formatted(date: .abbreviated, time: .shortened)) · \(s.heard.count) species"
                             + (s.place.map { " · \($0)" } ?? s.stationName.map { " · via \($0)" } ?? ""))
                            .font(.footnote).foregroundStyle(Theme.muted)
                    }
                }
                .listRowBackground(Theme.card)
                .swipeActions(edge: .leading) {
                    Button { newName = s.title; renaming = s } label: { Label("Rename", systemImage: "pencil") }
                        .tint(Theme.amber)
                }
                .contextMenu {
                    Button { newName = s.title; renaming = s } label: { Label("Rename", systemImage: "pencil") }
                }
            }
            .onDelete { idx in idx.map { store.sessions[$0] }.forEach(store.delete) }
        }
        .overlay {
            if store.sessions.isEmpty {
                ContentUnavailableView("No sessions yet", systemImage: "waveform",
                                       description: Text("Sessions you listen to show up here, with the birds and their sounds."))
            }
        }
        .scrollContentBackground(.hidden)
        .background(Theme.bg.ignoresSafeArea())
        .navigationTitle("Sessions")
        .alert("Rename session", isPresented: Binding(get: { renaming != nil }, set: { if !$0 { renaming = nil } })) {
            TextField("Name", text: $newName)
            Button("Save") { if let s = renaming { store.rename(s, to: newName) }; renaming = nil }
            Button("Cancel", role: .cancel) { renaming = nil }
        }
    }
}

struct SettingsView: View {
    @AppStorage("minConfidence") private var minConfidence = 0.3
    @EnvironmentObject var account: Account
    @EnvironmentObject var listener: Listener
    @EnvironmentObject var store: SessionStore
    @State private var signingIn = false
    @State private var diagnostics: SharedFile?
    var body: some View {
        Form {
            Section {
                if account.signedIn {
                    LabeledContent("Signed in", value: account.username)
                    LabeledContent("Site", value: account.siteName)
                    Button("Sign out", role: .destructive) { account.signOut() }
                } else {
                    Button("Sign in to a Chirp site") { signingIn = true }
                }
            } header: {
                Text("Chirp site")
            } footer: {
                Text(account.signedIn
                     ? "Birds you hear are also checked by your site, and each session is saved there as a Live Detect recording. The sign-in lasts 30 days."
                     : "Optional, for people who already have a Chirp site account. Sessions are then saved there too, with your site's second opinion.")
            }
            .listRowBackground(Theme.card)
            Section {
                VStack(alignment: .leading) {
                    Text("Lowest confidence: \(Theme.percent(minConfidence))")
                    Slider(value: $minConfidence, in: 0.1...0.9, step: 0.05)
                }
            } footer: {
                Text("Lower finds more birds, and more mistakes.")
            }
            .listRowBackground(Theme.card)
            BirdPackSection()
            Section {
                Link(destination: URL(string: "https://ourchirp.com/privacy.html")!) {
                    Label("Privacy policy", systemImage: "hand.raised")
                }
                Link(destination: URL(string: "https://ourchirp.com/support.html")!) {
                    Label("Help and privacy questions", systemImage: "questionmark.circle")
                }
            } header: {
                Text("Privacy")
            } footer: {
                Text("No account is needed to use Chirp Live. Sound is analyzed on this iPhone, and sessions stay on it unless you sign in to a Chirp site. Chirp Live doesn't create or delete accounts: Chirp site accounts are made and removed on the site itself. Questions about your data: ourchirp.com.")
            }
            .listRowBackground(Theme.card)
            Section {
                Button {
                    diagnostics = Diagnostics.file(listener: listener, store: store, account: account).map(SharedFile.init)
                } label: {
                    Label("Export diagnostics", systemImage: "stethoscope")
                }
            } header: {
                Text("Troubleshooting")
            } footer: {
                Text("A text file about this app, its permissions, sound and recent sessions, to send with a problem report. It has no passwords or sign-in.")
            }
            .listRowBackground(Theme.card)
            Section {
                Text("Bird identification by BirdNET (K. Lisa Yang Center for Conservation Bioacoustics, Cornell Lab of Ornithology, and Chemnitz University of Technology), CC BY-NC-SA 4.0.")
                    .font(.footnote).foregroundStyle(Theme.muted)
                LabeledContent("Version", value: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "")
                    .font(.footnote)
            }
            .listRowBackground(Theme.card)
        }
        .scrollContentBackground(.hidden)
        .background(Theme.bg.ignoresSafeArea())
        .navigationTitle("Settings")
        .sheet(isPresented: $signingIn) { SignInView() }
        .sheet(item: $diagnostics) { f in ShareSheet(items: [f.url]).presentationDetents([.medium, .large]) }
    }
}

struct SharedFile: Identifiable { let url: URL; var id: String { url.path } }

// MARK: Sign in

struct SignInView: View {
    @EnvironmentObject var account: Account
    @Environment(\.dismiss) private var dismiss
    @State private var server = Account.shared.server.host == "www.ourchirp.com" ? "ourchirp.com" : (Account.shared.server.host ?? "")
    @State private var username = Account.shared.username
    @State private var password = ""
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("ourchirp.com", text: $server)
                        .textContentType(.URL).keyboardType(.URL).autocorrectionDisabled().textInputAutocapitalization(.never)
                } header: { Text("Chirp site") } footer: {
                    Text("ourchirp.com, or your own server's address (for example 192.168.1.50:8768).")
                }
                .listRowBackground(Theme.card)
                Section {
                    TextField("Username", text: $username)
                        .textContentType(.username).autocorrectionDisabled().textInputAutocapitalization(.never)
                    SecureField("Password", text: $password).textContentType(.password)
                }
                .listRowBackground(Theme.card)
                if let error {
                    Text(error).foregroundStyle(Theme.orange).listRowBackground(Theme.card)
                }
                Section {
                    Button {
                        Task { await go() }
                    } label: {
                        HStack { Spacer(); if busy { ProgressView() } else { Text("Sign in").bold() }; Spacer() }
                    }
                    .disabled(busy || server.isEmpty || username.isEmpty || password.isEmpty)
                } footer: {
                    Text("For people who already have an account on a Chirp site. You don't need one to use Chirp Live, and accounts can't be created or deleted here. Chirp Live keeps a Live Detect-only sign-in for 30 days, never your password.")
                }
                .listRowBackground(Theme.card)
            }
            .scrollContentBackground(.hidden)
            .background(Theme.bg.ignoresSafeArea())
            .navigationTitle("Sign in")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
        }
        .preferredColorScheme(.dark)
    }

    private func go() async {
        busy = true; error = nil
        defer { busy = false }
        do {
            try await account.signIn(server: server, username: username, password: password)
            password = ""
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
