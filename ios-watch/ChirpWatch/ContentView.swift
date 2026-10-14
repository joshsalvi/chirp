import SwiftUI

struct ContentView: View {
    @EnvironmentObject var account: Account
    @EnvironmentObject var live: LiveSession

    var body: some View {
        NavigationStack {
            if account.signedIn { listenView } else { signInView }
        }
    }

    private var signInView: some View {
        ScrollView {
            VStack(spacing: 10) {
                Image(systemName: "bird.fill")
                    .font(.system(size: 34))
                    .foregroundStyle(.orange)
                Text("Sign in on your iPhone")
                    .font(.headline)
                    .multilineTextAlignment(.center)
                Text("Open Chirp on your iPhone and sign in. The watch signs in by itself.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                Button(account.asking ? "Asking…" : "Try again") { account.askPhone() }
                    .disabled(account.asking)
            }
            .padding(.horizontal, 4)
        }
        .navigationTitle("Chirp")
    }

    private var listenView: some View {
        List {
            Section {
                VStack(spacing: 6) {
                    Button(action: live.toggle) {
                        ZStack {
                            Circle()
                                .fill(live.listening ? Color.red : Color.green)
                                .frame(width: 64, height: 64)
                            Circle()
                                .stroke(Color.white.opacity(0.5), lineWidth: 3)
                                .frame(width: 64 + CGFloat(live.level) * 24, height: 64 + CGFloat(live.level) * 24)
                                .opacity(live.listening ? 1 : 0)
                            Image(systemName: live.listening ? "stop.fill" : "mic.fill")
                                .font(.title2)
                                .foregroundStyle(.white)
                        }
                        .frame(maxWidth: .infinity, minHeight: 90)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(live.listening ? "Stop listening" : "Start listening")
                    Text(statusText)
                        .font(.footnote)
                        .foregroundStyle(statusIsProblem ? .orange : .secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)
                }
                .listRowBackground(Color.clear)
            }

            if !live.heard.isEmpty {
                Section("Heard") {
                    ForEach(live.heard) { h in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(h.name).font(.headline).lineLimit(2)
                            Text("\(Int((h.best * 100).rounded()))% · \(h.count)× · \(h.last, style: .time)")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                if !live.listening {
                    Button("Clear", role: .destructive) { live.clear() }
                }
            }
        }
        .navigationTitle(account.site.isEmpty ? "Chirp" : account.site)
    }

    private var statusIsProblem: Bool {
        if case .failed = live.state { return true }
        return live.listening && live.problem != nil
    }

    private var statusText: String {
        switch live.state {
        case .failed(let why): return why
        case .starting: return "Starting…"
        case .listening:
            if let p = live.problem { return p }
            return live.clipsSent == 0 ? "Listening…" : "Listening · \(live.clipsSent) clips checked"
        case .idle:
            return live.heard.isEmpty ? "Tap to listen for birds" : "Stopped"
        }
    }
}
