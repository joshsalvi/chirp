import CoreLocation
import SwiftUI
import UIKit

/// Bird pictures for the birds of your area, kept on the iPhone. Downloaded
/// once from ourchirp.com (POST /api/v1/live-pack with the species BirdNET's
/// location model expects here over a year; no location is sent). One file:
/// b"CHIRPPK1", a 4-byte index length, a JSON index, then the JPEGs; a
/// picture is read from its slice of the file when it's shown.
@MainActor
final class BirdPack: ObservableObject {
    static let shared = BirdPack()
    static let server = URL(string: "https://www.ourchirp.com/api/v1/live-pack")!

    struct Entry: Codable, Hashable {
        let sci: String
        let common: String
        let code: String?
        let credit: String?
        let license: String?
        let source: String?
        let offset: Int?
        let length: Int?
    }
    private struct Index: Codable { let version: Int; let made: String; let species: [Entry] }

    enum State: Equatable { case idle, working(String), failed(String) }

    @Published private(set) var entries: [String: Entry] = [:]
    @Published private(set) var made: Date?
    @Published private(set) var state: State = .idle
    @Published private(set) var fileSize: Int64 = 0

    /// Birds fetched one at a time after the pack ("Fetch pictures of new birds").
    @Published private(set) var extras: [String: Entry] = [:]

    /// All About Birds covers North America; its links show only for packs made there.
    var northAmerica: Bool { UserDefaults.standard.bool(forKey: "packNorthAmerica") }
    var pictures: Int { entries.values.filter { $0.offset != nil }.count + extras.count }

    /// Settings toggles (both on unless turned off).
    static var autoUpdate: Bool { UserDefaults.standard.object(forKey: "packAutoUpdate") as? Bool ?? true }
    static var fetchNew: Bool { UserDefaults.standard.object(forKey: "packFetchNew") as? Bool ?? true }

    private var bodyStart = 0
    private let cache = NSCache<NSString, UIImage>()
    private static let dir: URL = {
        let d = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("BirdPack", isDirectory: true)
        try? FileManager.default.createDirectory(at: d.appendingPathComponent("extra"), withIntermediateDirectories: true)
        return d
    }()
    private let file = BirdPack.dir.appendingPathComponent("birds.chirppack")
    private let extrasFile = BirdPack.dir.appendingPathComponent("extra/index.json")
    private var fetching: Set<String> = []

    private init() {
        load()
        if let d = try? Data(contentsOf: extrasFile), let e = try? JSONDecoder().decode([String: Entry].self, from: d) { extras = e }
    }

    /// The pack's entry for a bird, or the one fetched later.
    func entry(_ sci: String) -> Entry? { entries[sci] ?? extras[sci] }

    /// A pack's index and where its pictures start (b"CHIRPPK1", length, JSON, JPEGs).
    nonisolated static func parse(_ head: Data) -> (index: [Entry], made: String, bodyStart: Int)? {
        guard head.count >= 12, head.prefix(8) == Data("CHIRPPK1".utf8) else { return nil }
        let n = head.dropFirst(8).prefix(4).reduce(0) { $0 << 8 | Int($1) }
        guard head.count >= 12 + n,
              let index = try? JSONDecoder().decode(Index.self, from: head.dropFirst(12).prefix(n)) else { return nil }
        return (index.species, index.made, 12 + n)
    }

    // MARK: Reading

    private func load() {
        entries = [:]; made = nil; fileSize = 0; cache.removeAllObjects()
        guard let h = try? FileHandle(forReadingFrom: file) else { return }
        defer { try? h.close() }
        guard let head = try? h.read(upToCount: 12), head.count == 12 else { return }
        let n = head.dropFirst(8).reduce(0) { $0 << 8 | Int($1) }
        guard let json = try? h.read(upToCount: n), let p = Self.parse(head + json) else { return }
        bodyStart = p.bodyStart
        entries = Dictionary(p.index.map { ($0.sci, $0) }, uniquingKeysWith: { a, _ in a })
        made = ISO8601DateFormatter().date(from: String(p.made.prefix(19)) + "Z")
        fileSize = Int64((try? file.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0)
    }

    func image(_ sci: String) -> UIImage? {
        if let c = cache.object(forKey: sci as NSString) { return c }
        if extras[sci] != nil, let img = UIImage(contentsOfFile: Self.dir.appendingPathComponent("extra/\(Self.slug(sci)).jpg").path) {
            cache.setObject(img, forKey: sci as NSString)
            return img
        }
        guard let e = entries[sci], let off = e.offset, let len = e.length,
              let h = try? FileHandle(forReadingFrom: file) else { return nil }
        defer { try? h.close() }
        try? h.seek(toOffset: UInt64(bodyStart + off))
        guard let data = try? h.read(upToCount: len), let img = UIImage(data: data) else { return nil }
        cache.setObject(img, forKey: sci as NSString)
        return img
    }

    struct Link: Identifiable { let title: String; let detail: String; let url: URL; var id: String { title } }

    /// eBird, All About Birds (North America), Macaulay Library and Wikipedia.
    func links(sci: String, common: String) -> [Link] {
        var out: [Link] = []
        let code = entry(sci)?.code
        if let code, let u = URL(string: "https://ebird.org/species/\(code)") {
            out.append(Link(title: "eBird", detail: "Range, sightings near you", url: u))
        }
        if northAmerica, code != nil {
            let slug = common.replacingOccurrences(of: "'", with: "").replacingOccurrences(of: " ", with: "_")
            if let u = URL(string: "https://www.allaboutbirds.org/guide/\(slug)") {
                out.append(Link(title: "All About Birds", detail: "ID tips and sounds, Cornell Lab", url: u))
            }
        }
        if let code, let u = URL(string: "https://search.macaulaylibrary.org/catalog?taxonCode=\(code)&mediaType=audio&sort=rating_rank_desc") {
            out.append(Link(title: "Macaulay Library", detail: "Recordings, Cornell Lab", url: u))
        }
        if let u = URL(string: "https://en.wikipedia.org/wiki/\(sci.replacingOccurrences(of: " ", with: "_"))") {
            out.append(Link(title: "Wikipedia", detail: sci, url: u))
        }
        return out
    }

    func remove() {
        try? FileManager.default.removeItem(at: file)
        try? FileManager.default.removeItem(at: Self.dir.appendingPathComponent("extra"))
        try? FileManager.default.createDirectory(at: Self.dir.appendingPathComponent("extra"), withIntermediateDirectories: true)
        extras = [:]
        UserDefaults.standard.removeObject(forKey: "packLat")
        load()
    }

    nonisolated static func slug(_ sci: String) -> String {
        sci.lowercased().map { $0.isLetter || $0.isNumber ? $0 : "-" }.reduce(into: "") { $0.append($1) }
    }

    /// "Fetch pictures of new birds": a bird heard that has no picture yet.
    func wantPicture(sci: String) {
        guard Self.fetchNew, entries[sci] == nil else { return }   // in the pack, with or without a photo
        guard extras[sci] == nil, !fetching.contains(sci) else { return }
        fetching.insert(sci)
        Task {
            defer { fetching.remove(sci) }
            var req = URLRequest(url: Self.server)
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.setValue("ChirpLive/1", forHTTPHeaderField: "User-Agent")
            req.httpBody = try? JSONSerialization.data(withJSONObject: ["species": [sci]])
            for _ in 0..<12 {
                guard let (data, resp) = try? await URLSession.shared.data(for: req) else { return }
                let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
                if code == 202 { try? await Task.sleep(for: .seconds(10)); continue }
                guard code == 200, let p = Self.parse(data), let e = p.index.first else { return }
                if let off = e.offset, let len = e.length, p.bodyStart + off + len <= data.count {
                    let jpg = data.subdata(in: (p.bodyStart + off)..<(p.bodyStart + off + len))
                    try? jpg.write(to: Self.dir.appendingPathComponent("extra/\(Self.slug(sci)).jpg"))
                }
                extras[sci] = e
                if let d = try? JSONEncoder().encode(extras) { try? d.write(to: extrasFile) }
                return
            }
        }
    }

    /// "Keep pictures up to date": a new pack when this one is two months
    /// old or made more than 150 km from here. Quiet; runs on app start.
    func updateIfNeeded() async {
        guard Self.autoUpdate, !entries.isEmpty, state == .idle,
              CLLocationManager().authorizationStatus == .authorizedWhenInUse
                || CLLocationManager().authorizationStatus == .authorizedAlways else { return }
        let old = (made ?? .distantPast) < Date().addingTimeInterval(-60 * 86_400)
        var moved = false
        let d = UserDefaults.standard
        if d.object(forKey: "packLat") != nil, let here = await LocationOnce().place() {
            moved = here.distance(from: CLLocation(latitude: d.double(forKey: "packLat"), longitude: d.double(forKey: "packLon"))) > 150_000
        }
        if old || moved { await download() }
    }

    #if DEBUG
    /// Tests: installs a pack as if it was downloaded.
    func install(_ data: Data, northAmerica: Bool) throws {
        try data.write(to: file, options: .atomic)
        UserDefaults.standard.set(northAmerica, forKey: "packNorthAmerica")
        load()
    }
    #endif

    // MARK: Download

    /// Works out the birds of this area for the whole year and fetches their pictures.
    func download() async {
        guard state == .idle || { if case .failed = state { return true }; return false }() else { return }
        state = .working("Finding the birds of your area…")
        guard let place = await LocationOnce().place() else {
            state = .failed("Allow location so Chirp Live knows which birds to fetch (Settings → Chirp Live → Location).")
            return
        }
        let lat = place.coordinate.latitude, lon = place.coordinate.longitude
        let names: [String]
        do {
            names = try await Task.detached(priority: .userInitiated) { () -> [String] in
                let model = try BirdNET()
                var set = Set<Int>()
                var c = DateComponents(); c.year = 2026; c.month = 1
                for w in 0..<48 {
                    c.day = 1 + Int((Double(w) + 0.5) / 48 * 365)
                    if let d = Calendar(identifier: .gregorian).date(from: c) {
                        set.formUnion(try model.likely(latitude: lat, longitude: lon, on: d))
                    }
                }
                return set.map { model.species[$0].scientific }.sorted()
            }.value
        } catch {
            state = .failed("Couldn't work out the local birds: \(error.localizedDescription)")
            DiagLog.note("bird pack: \(error.localizedDescription)")
            return
        }
        guard !names.isEmpty else { state = .failed("BirdNET expects no birds here."); return }

        var req = URLRequest(url: Self.server)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("ChirpLive/1", forHTTPHeaderField: "User-Agent")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["species": names])
        req.timeoutInterval = 120
        let deadline = Date().addingTimeInterval(30 * 60)
        do {
            while true {
                let (data, resp) = try await URLSession.shared.data(for: req)
                let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
                if code == 200, data.prefix(8) == Data("CHIRPPK1".utf8) {
                    let tmp = file.appendingPathExtension("part")
                    try data.write(to: tmp, options: .atomic)
                    _ = try? FileManager.default.removeItem(at: file)
                    try FileManager.default.moveItem(at: tmp, to: file)
                    UserDefaults.standard.set((7...84).contains(lat) && (-170 ... -50).contains(lon), forKey: "packNorthAmerica")
                    UserDefaults.standard.set(lat, forKey: "packLat"); UserDefaults.standard.set(lon, forKey: "packLon")
                    load()
                    state = .idle
                    return
                }
                if code == 202, let j = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let ready = j["ready"] as? Int, let total = j["total"] as? Int {
                    state = .working("Preparing pictures: \(ready) of \(total) birds ready…")
                    guard Date() < deadline else { throw URLError(.timedOut) }
                    try await Task.sleep(for: .seconds(5))
                    continue
                }
                let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
                throw NSError(domain: "ChirpLive", code: code, userInfo: [NSLocalizedDescriptionKey: detail ?? "ourchirp.com answered \(code)."])
            }
        } catch {
            state = .failed("Couldn't download the pictures: \(error.localizedDescription)")
            DiagLog.note("bird pack download: \(error.localizedDescription)")
        }
    }
}

// MARK: Views

/// A bird's picture in a circle, or its initials without a pack.
struct BirdThumb: View {
    let sci: String
    let common: String
    var size: CGFloat = 40
    @ObservedObject private var pack = BirdPack.shared

    var body: some View {
        Group {
            if let img = pack.image(sci) {
                Image(uiImage: img).resizable().scaledToFill()
            } else {
                Text(initials).font(.system(size: size * 0.36, weight: .semibold, design: .serif))
                    .foregroundStyle(Theme.amber)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Theme.amber.opacity(0.16))
            }
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        .accessibilityHidden(true)
    }

    private var initials: String {
        common.split(whereSeparator: { $0 == " " || $0 == "-" }).prefix(2).compactMap(\.first).map(String.init).joined()
    }
}

/// One bird: its picture and credit, and where to learn more.
struct BirdDetailView: View {
    let sci: String
    let common: String
    var heard: Heard?
    @ObservedObject private var pack = BirdPack.shared
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    if let img = pack.image(sci) {
                        Image(uiImage: img).resizable().scaledToFill()
                            .frame(maxWidth: .infinity).frame(height: 260).clipped()
                            .clipShape(RoundedRectangle(cornerRadius: 18))
                        if let credit = pack.entry(sci)?.credit, !credit.isEmpty {
                            Group {
                                if let s = pack.entry(sci)?.source, let u = URL(string: s) {
                                    Link(destination: u) { Text("Photo \(credit), via iNaturalist") }
                                } else {
                                    Text("Photo \(credit), via iNaturalist")
                                }
                            }
                            .font(.caption2).foregroundStyle(Theme.muted)
                        }
                    } else {
                        BirdThumb(sci: sci, common: common, size: 96)
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        Text(common).font(.system(size: 28, weight: .bold, design: .serif))
                        Text(sci).font(.system(size: 16)).italic().foregroundStyle(Theme.body)
                    }
                    if let h = heard {
                        Text("\(h.count) call\(h.count == 1 ? "" : "s") this session · best \(Theme.percent(h.best))")
                            .font(.callout).foregroundStyle(Theme.muted)
                    }
                    VStack(spacing: 0) {
                        ForEach(pack.links(sci: sci, common: common)) { l in
                            Link(destination: l.url) {
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(l.title).font(.system(size: 16)).foregroundStyle(Theme.ink)
                                        Text(l.detail).font(.system(size: 13)).foregroundStyle(Theme.muted)
                                    }
                                    Spacer()
                                    Image(systemName: "arrow.up.right").foregroundStyle(Theme.amber)
                                }
                                .padding(.vertical, 12)
                            }
                            .overlay(alignment: .top) { Rectangle().fill(Theme.line).frame(height: 1) }
                        }
                    }
                    if pack.entries.isEmpty {
                        Text("Add bird pictures for your area in Settings.").font(.footnote).foregroundStyle(Theme.muted)
                    }
                }
                .foregroundStyle(Theme.ink)
                .padding(20)
            }
            .background(Theme.bg.ignoresSafeArea())
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }
}

/// Settings: download, update or remove the pack.
struct BirdPackSection: View {
    @ObservedObject private var pack = BirdPack.shared
    @AppStorage("packAutoUpdate") private var autoUpdate = true
    @AppStorage("packFetchNew") private var fetchNew = true

    var body: some View {
        Section {
            if pack.entries.isEmpty {
                Text("No pictures yet.").foregroundStyle(Theme.muted)
            } else {
                LabeledContent("Birds", value: "\(pack.entries.count) (\(pack.pictures) with pictures)")
                LabeledContent("Size", value: ByteCountFormatter.string(fromByteCount: pack.fileSize, countStyle: .file))
                if let d = pack.made { LabeledContent("Updated", value: d.formatted(date: .abbreviated, time: .omitted)) }
            }
            switch pack.state {
            case .working(let what):
                HStack(spacing: 10) { ProgressView(); Text(what).font(.footnote).foregroundStyle(Theme.muted) }
            default:
                Button(pack.entries.isEmpty ? "Download pictures for my area" : "Update for where I am now") {
                    Task { await pack.download() }
                }
                if !pack.entries.isEmpty {
                    Button("Remove pictures", role: .destructive) { pack.remove() }
                }
            }
            if case .failed(let why) = pack.state {
                Text(why).font(.footnote).foregroundStyle(Theme.orange)
            }
            Toggle("Keep pictures up to date", isOn: $autoUpdate)
            Toggle("Fetch pictures of new birds", isOn: $fetchNew)
        } header: {
            Text("Bird pictures")
        } footer: {
            Text("A one-time download from ourchirp.com of a photo of each bird likely where you are over the year, usually 5 to 15 MB. Chirp Live works out the list on this iPhone and sends only bird names, not your location. Photos are from iNaturalist photographers, credited with each one. Up to date: a new pack when this one is two months old or you're 150 km away. New birds: a bird you hear that isn't in the pack gets its picture when you're online. Links to eBird, All About Birds and Macaulay Library open in Safari.")
        }
        .listRowBackground(Theme.card)
    }
}
