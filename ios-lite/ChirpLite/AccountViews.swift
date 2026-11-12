import SwiftUI

struct SignInView: View {
    @EnvironmentObject var account: Account
    @State private var server = ""
    @State private var username = ""
    @State private var password = ""
    @State private var otherSite = false
    @State private var busy = false
    @State private var demoBusy = false
    @State private var error: String?
    @FocusState private var focus: Field?
    enum Field { case server, user, pass }

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                scene
                VStack(alignment: .leading, spacing: 14) {
                    Text("Chirp Lite").font(.lite(36, .black)).foregroundStyle(Theme.ink)
                    Text("The birds in your backyard, in pictures and sound.")
                        .font(.lite(17, .semibold)).foregroundStyle(Theme.muted)
                    if otherSite {
                        field("Your Chirp's address", text: $server, .server, prompt: "ourchirp.com")
                            .keyboardType(.URL)
                    }
                    field("Username", text: $username, .user)
                        .textContentType(.username)
                    field("Password", text: $password, .pass, secure: true)
                        .textContentType(.password)
                    if let error {
                        Text(error).font(.lite(15, .bold)).foregroundStyle(Theme.coralInk)
                            .padding(12).frame(maxWidth: .infinity, alignment: .leading)
                            .background(Theme.coralSoft, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    }
                    Button { Task { await go() } } label: {
                        if busy { ProgressView().tint(.white) } else { Text("Sign in") }
                    }
                    .buttonStyle(MainButton())
                    .disabled(busy || username.isEmpty || password.isEmpty)
                    .opacity(username.isEmpty || password.isEmpty ? 0.6 : 1)
                    Button(otherSite ? "Use ourchirp.com" : "My Chirp has its own address") {
                        withAnimation { otherSite.toggle() }
                        if !otherSite { server = "" }
                    }
                    .font(.lite(15, .bold)).foregroundStyle(Theme.greenDeep)
                    .frame(maxWidth: .infinity)
                    Text("Use the same account as Chirp. No account? Ask whoever runs your Chirp for an invite.")
                        .font(.lite(13, .semibold)).foregroundStyle(Theme.muted).multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)
                    if !otherSite {
                        Button { Task { await demo() } } label: {
                            if demoBusy { ProgressView() } else { Text("Try the demo") }
                        }
                        .buttonStyle(MainButton(soft: true))
                        .disabled(busy || demoBusy)
                        .padding(.top, 6)
                        Text("Look around a real yard's birds. No account needed.")
                            .font(.lite(13, .semibold)).foregroundStyle(Theme.muted).multilineTextAlignment(.center)
                            .frame(maxWidth: .infinity)
                    }
                }
                .padding(.horizontal, 22).padding(.top, 28).padding(.bottom, 30)
                .background(Theme.card, in: UnevenRoundedRectangle(topLeadingRadius: 32, topTrailingRadius: 32, style: .continuous))
                .offset(y: -30).padding(.bottom, -30)
            }
        }
        .scrollDismissesKeyboard(.interactively)
        .background {
            // Sky behind the scene, the card's color below it (and when pulled past the bottom).
            VStack(spacing: 0) {
                LinearGradient(colors: [Color(light: 0xBFE9FF, dark: 0x12324A), Color(light: 0xE8F7EE, dark: 0x133022)],
                               startPoint: .top, endPoint: .bottom)
                    .frame(height: 380)
                Theme.card
            }
            .ignoresSafeArea()
        }
        .onAppear {
            username = account.isDemo ? "" : account.username
            if account.server != Account.defaultServer { server = account.siteName; otherSite = true }
        }
        .sheet(isPresented: Binding(get: { !account.sites.isEmpty }, set: { if !$0 { account.cancelSitePick() } })) {
            SitePicker()
        }
    }

    /// Sun, hills and the bird. Drawn in an overlay so the shapes, which are
    /// wider than the screen, never widen the page.
    private var scene: some View {
        Color.clear
            .frame(maxWidth: .infinity).frame(height: 300)
            .overlay {
                GeometryReader { g in
                    let w = g.size.width
                    ZStack {
                        Circle().fill(Color(hex: 0xFFE45C)).frame(width: 110, height: 110)
                            .shadow(color: Color(hex: 0xFFE45C), radius: 40)
                            .position(x: w * 0.85, y: 62)
                        Ellipse().fill(Color(hex: 0x7EDB9F)).frame(width: w * 1.3, height: 200).position(x: w * 0.85, y: 290)
                        Ellipse().fill(Theme.green).frame(width: w * 1.5, height: 200).position(x: w * 0.35, y: 310)
                        BirdMark(size: 150, tile: false)
                            .shadow(color: .black.opacity(0.15), radius: 10, y: 8)
                            .phaseAnimator([0.0, 1.0]) { v, p in
                                v.offset(y: -8 * p).rotationEffect(.degrees(-3 * p))
                            } animation: { _ in .easeInOut(duration: 1.2) }
                            .position(x: w / 2, y: 182)
                    }
                }
            }
            .clipped()
    }

    private func field(_ label: String, text: Binding<String>, _ f: Field, prompt: String = "", secure: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(.lite(14, .heavy)).foregroundStyle(Theme.muted)
            Group {
                if secure { SecureField(prompt, text: text) } else { TextField(prompt, text: text) }
            }
            .font(.lite(17, .bold))
            .textInputAutocapitalization(.never).autocorrectionDisabled()
            .focused($focus, equals: f)
            .submitLabel(f == .pass ? .go : .next)
            .onSubmit { if f == .pass { Task { await go() } } else { focus = f == .server ? .user : .pass } }
            .padding(.horizontal, 14).padding(.vertical, 13)
            .background(Theme.bg, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(focus == f ? Theme.green : Theme.line, lineWidth: 2))
        }
    }

    private func demo() async {
        demoBusy = true; error = nil
        defer { demoBusy = false }
        do { try await account.tryDemo() } catch { self.error = error.localizedDescription }
    }

    private func go() async {
        guard !busy, !username.isEmpty, !password.isEmpty else { return }
        busy = true; error = nil
        defer { busy = false }
        do {
            try await account.signIn(server: otherSite && !server.isEmpty ? server : Account.defaultServer.absoluteString,
                                     username: username.trimmingCharacters(in: .whitespaces), password: password)
            password = ""
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct SitePicker: View {
    @EnvironmentObject var account: Account
    @State private var error: String?
    @State private var busy: String?

    var body: some View {
        NavigationStack {
            List {
                Section {
                    ForEach(account.sites) { s in
                        Button { Task { await pick(s) } } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(s.name).font(.lite(17, .heavy)).foregroundStyle(Theme.ink)
                                    if let loc = s.locationName { Text(loc).font(.lite(14, .semibold)).foregroundStyle(Theme.muted) }
                                }
                                Spacer()
                                if busy == s.id { ProgressView() }
                            }
                        }
                    }
                } footer: {
                    if let error { Text(error).foregroundStyle(Theme.coralInk) }
                }
            }
            .navigationTitle("Which yard?")
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { account.cancelSitePick() } } }
        }
        .presentationDetents([.medium, .large])
    }

    private func pick(_ s: Site) async {
        busy = s.id; error = nil
        defer { busy = nil }
        do { try await account.pick(s) } catch { self.error = error.localizedDescription }
    }
}

struct AccountSheet: View {
    @EnvironmentObject var account: Account
    @EnvironmentObject var player: Player
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL
    @AppStorage(Haptics.offKey) private var hapticsOff = false

    var body: some View {
        NavigationStack {
            List {
                Section {
                    HStack(spacing: 14) {
                        BirdMark(size: 52)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(account.username.isEmpty ? "Chirp Lite" : account.username).font(.lite(20, .black))
                            Text(account.siteTitle.map { "\($0) · \(account.siteName)" } ?? account.siteName)
                                .font(.lite(14, .semibold)).foregroundStyle(Theme.muted)
                        }
                    }
                    .padding(.vertical, 4)
                }
                Section {
                    row("Open Chirp", "Statistics, stations, settings and more", "square.grid.2x2.fill", Theme.green) {
                        openURL(account.isDemo ? URL(string: "https://www.ourchirp.com/login?demo=1")! : account.server)
                    }
                    row("Get Chirp Live", "Name birds by sound, anywhere", "mic.fill", Theme.sky) {
                        openURL(URL(string: "https://apps.apple.com/us/app/chirp-live-bird-sound-id/id6827668744")!)
                    }
                    row("Help", "Guides and answers", "questionmark.circle.fill", Theme.sun) {
                        openURL(URL(string: "https://www.ourchirp.com/support.html")!)
                    }
                    row("Privacy", nil, "hand.raised.fill", Theme.muted) {
                        openURL(URL(string: "https://www.ourchirp.com/privacy.html")!)
                    }
                }
                Section {
                    Toggle(isOn: Binding(get: { !hapticsOff }, set: { hapticsOff = !$0; Haptics.tap() })) {
                        Label("Haptics", systemImage: "iphone.radiowaves.left.and.right")
                            .font(.lite(16, .bold))
                    }
                    .tint(Theme.green)
                } footer: {
                    Text("A light tap when a sound starts or you scrub through it.")
                }
                Section {
                    Button(role: .destructive) { player.stop(); account.signOut(); dismiss() } label: {
                        Label(account.isDemo ? "Leave the demo" : "Sign out", systemImage: "rectangle.portrait.and.arrow.right")
                    }
                } footer: {
                    Text("Chirp Lite \(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "")")
                }
            }
            .navigationTitle("Account")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
        .presentationDetents([.medium, .large])
    }

    private func row(_ title: String, _ sub: String?, _ icon: String, _ color: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 14) {
                Image(systemName: icon).font(.system(size: 17, weight: .bold)).foregroundStyle(.white)
                    .frame(width: 36, height: 36).background(color, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                VStack(alignment: .leading, spacing: 1) {
                    Text(title).font(.lite(17, .heavy)).foregroundStyle(Theme.ink)
                    if let sub { Text(sub).font(.lite(13, .semibold)).foregroundStyle(Theme.muted) }
                }
                Spacer()
                Image(systemName: "arrow.up.right").font(.system(size: 13, weight: .bold)).foregroundStyle(Theme.muted)
            }
        }
    }
}
