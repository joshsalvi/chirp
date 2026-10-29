import SwiftUI

struct ContentView: View {
    @EnvironmentObject var account: Account
    @EnvironmentObject var live: LiveSession
    @EnvironmentObject var recent: RecentRecordings

    var body: some View {
        NavigationStack {
            #if DEBUG
            if Screenshots.showsRecent { RecentView() } else if account.signedIn { listenView } else { signInView }
            #else
            if account.signedIn { listenView } else { signInView }
            #endif
        }
    }

    private var signInView: some View {
        ScrollView {
            VStack(spacing: 10) {
                ChirpMark(height: 34)
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
    }

    private var listenView: some View {
        ScrollViewReader { proxy in
        List {
            Section {
                VStack(spacing: 6) {
                    Button(action: { recent.stop(); live.toggle() }) {
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
                    if live.state == .listening && live.problem == nil { progress }
                    if let text = savingText {
                        Text(text.0)
                            .font(.footnote)
                            .foregroundStyle(text.1 ? .orange : .green)
                            .multilineTextAlignment(.center)
                            .frame(maxWidth: .infinity)
                    }
                    if live.canRetrySave {
                        Button("Try saving again") { live.save() }
                            .font(.footnote)
                    }
                }
                .listRowBackground(Color.clear)
            }

            Section {
                NavigationLink {
                    RecentView()
                } label: {
                    Label("Recent recordings", systemImage: "waveform")
                }
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
                .id("heard")
                if !live.listening {
                    Button("Clear", role: .destructive) { live.clear() }
                }
            }
        }
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                ChirpMark(height: 22, animate: live.state == .listening)
            }
        }
        #if DEBUG
        .task {
            if Screenshots.scene == "heard" {
                try? await Task.sleep(nanoseconds: 300_000_000)
                proxy.scrollTo("heard", anchor: .top)
            }
        }
        #endif
        }
    }

    /// What the clips are doing: identifying now, the last answer and how
    /// long answers take, and clips skipped on a slow connection.
    private var progress: some View {
        TimelineView(.periodic(from: .now, by: 1)) { ctx in
            VStack(spacing: 2) {
                if live.inFlight > 0 {
                    HStack(spacing: 4) {
                        ProgressView().controlSize(.mini)
                        Text(live.lastAnswer == nil ? "Identifying first clip…" : "Identifying…")
                    }
                    .foregroundStyle(.secondary)
                }
                if let at = live.lastAnswer {
                    let ago = max(0, Int(ctx.date.timeIntervalSince(at)))
                    Text(live.lastFound.isEmpty ? "Last clip: no birds · \(ago)s ago"
                                                : "Last clip: \(live.lastFound.joined(separator: ", "))")
                        .foregroundStyle(live.lastFound.isEmpty ? Color.secondary : Color.green)
                        .lineLimit(2)
                    if let rt = live.lastRoundTrip {
                        Text(String(format: "Answers in %.1f s", rt)).foregroundStyle(.tertiary)
                    }
                }
                if live.skipped > 0 {
                    Text("Slow connection: skipped \(live.skipped) clip\(live.skipped == 1 ? "" : "s")")
                        .foregroundStyle(.orange)
                }
            }
            .font(.caption2)
            .multilineTextAlignment(.center)
            .frame(maxWidth: .infinity)
        }
    }

    /// (text, is a problem)
    private var savingText: (String, Bool)? {
        switch live.saving {
        case .none, .ready: return nil
        case .saving: return ("Saving to Recordings…", false)
        case .saved: return ("Saved to Recordings", false)
        case .failed(let why): return ("Not saved: \(why)", true)
        }
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
            return live.clipsSent == 0 ? "Listening… first check in a few seconds" : "Listening · \(live.clipsSent) clips checked"
        case .idle:
            return live.heard.isEmpty ? "Tap to listen for birds" : "Stopped"
        }
    }
}
