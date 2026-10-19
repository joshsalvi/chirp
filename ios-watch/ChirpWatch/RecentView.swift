import SwiftUI

/// Recent recordings: the site's five newest, newest first. Tap one to play
/// it; tap again to stop.
struct RecentView: View {
    @EnvironmentObject var recent: RecentRecordings
    @EnvironmentObject var live: LiveSession

    var body: some View {
        List {
            switch recent.status {
            case .idle, .loading:
                HStack { Spacer(); ProgressView(); Spacer() }
                    .listRowBackground(Color.clear)
            case .failed(let why):
                VStack(spacing: 6) {
                    Text(why)
                        .font(.footnote)
                        .foregroundStyle(.orange)
                        .multilineTextAlignment(.center)
                    Button("Try again") { Task { await recent.refresh() } }
                }
                .frame(maxWidth: .infinity)
                .listRowBackground(Color.clear)
            case .loaded:
                if recent.items.isEmpty {
                    Text("No recordings yet.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .listRowBackground(Color.clear)
                }
            }

            ForEach(recent.items) { item in
                Button { Task { await recent.toggle(item) } } label: { row(item) }
                    .disabled(!item.has_audio || live.listening)
            }

            if let err = recent.playError {
                Text(err)
                    .font(.footnote)
                    .foregroundStyle(.orange)
                    .listRowBackground(Color.clear)
            }
            if live.listening && !recent.items.isEmpty {
                Text("Stop listening to play recordings.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .listRowBackground(Color.clear)
            }
        }
        .navigationTitle("Recent")
        .task { await recent.refresh() }
        .refreshable { await recent.refresh() }
        .onDisappear { recent.stop() }
    }

    private func row(_ item: RecentRecordings.Item) -> some View {
        HStack(spacing: 8) {
            ZStack {
                Circle()
                    .stroke(Color.white.opacity(0.15), lineWidth: 3)
                if recent.playingID == item.id {
                    Circle()
                        .trim(from: 0, to: recent.progress)
                        .stroke(Color.green, style: StrokeStyle(lineWidth: 3, lineCap: .round))
                        .rotationEffect(.degrees(-90))
                }
                if recent.fetchingID == item.id {
                    ProgressView().scaleEffect(0.6)
                } else {
                    Image(systemName: recent.playingID == item.id ? "stop.fill" : "play.fill")
                        .font(.footnote)
                        .foregroundStyle(item.has_audio ? Color.green : Color.secondary)
                }
            }
            .frame(width: 30, height: 30)

            VStack(alignment: .leading, spacing: 1) {
                Text(item.species)
                    .font(.headline)
                    .lineLimit(2)
                if !item.others.isEmpty {
                    Text("+ " + item.others.joined(separator: ", "))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Text(subtitle(item))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityHint(item.has_audio ? (recent.playingID == item.id ? "Stops playback" : "Plays the recording") : "No audio")
    }

    private func subtitle(_ item: RecentRecordings.Item) -> String {
        var parts = [item.time.formatted(.relative(presentation: .named, unitsStyle: .abbreviated))]
        if let c = item.confidence { parts.append("\(Int((c * 100).rounded()))%") }
        if !item.has_audio { parts.append("no audio") }
        return parts.joined(separator: " · ")
    }
}
