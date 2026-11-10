import SwiftUI
import UIKit

/// Bird photos, spectrograms and range maps: from the site (with the sign-in)
/// or a photo host, cached in memory and by URLCache on disk.
@MainActor
final class ImageStore {
    static let shared = ImageStore()
    private let cache = NSCache<NSString, UIImage>()
    private var inflight: [String: Task<UIImage?, Never>] = [:]

    init() { cache.countLimit = 300 }

    func image(_ path: String, account: Account) async -> UIImage? {
        let key = path as NSString
        if let hit = cache.object(forKey: key) { return hit }
        if let running = inflight[path] { return await running.value }
        let server = account.server, token = account.token
        let task = Task<UIImage?, Never> {
            guard let data = try? await API.data(path, server: server, token: token) else { return nil }
            return await Task.detached(priority: .userInitiated) { Self.decode(data) }.value
        }
        inflight[path] = task
        let img = await task.value
        inflight[path] = nil
        if let img { cache.setObject(img, forKey: key) }
        return img
    }

    /// Decoded off the main thread, at most 1200 px wide.
    nonisolated static func decode(_ data: Data) -> UIImage? {
        guard let img = UIImage(data: data) else { return nil }
        let maxW: CGFloat = 1200
        guard img.size.width > maxW else { return img.preparingForDisplay() ?? img }
        let size = CGSize(width: maxW, height: img.size.height * maxW / img.size.width)
        return img.preparingThumbnail(of: size) ?? img
    }
}

/// A photo that fills its frame; a soft colored bird while loading or missing.
struct Photo: View {
    let path: String?
    var name: String = ""
    var contentMode: ContentMode = .fill
    @EnvironmentObject var account: Account
    @State private var image: UIImage?
    @State private var failed = false

    var body: some View {
        ZStack {
            if let image {
                Image(uiImage: image).resizable().aspectRatio(contentMode: contentMode)
                    .transition(.opacity)
            } else {
                Placeholder(name: name, loading: path != nil && !failed)
            }
        }
        .clipped()
        .task(id: path) {
            image = nil; failed = false
            guard let path else { return }
            let img = await ImageStore.shared.image(path, account: account)
            withAnimation(.easeOut(duration: 0.25)) { image = img; failed = img == nil }
        }
    }
}

struct Placeholder: View {
    let name: String
    var loading = false
    var body: some View {
        let hue = Self.hue(name)
        LinearGradient(colors: [Color(hue: hue, saturation: 0.35, brightness: 0.95),
                                Color(hue: (hue + 0.07).truncatingRemainder(dividingBy: 1), saturation: 0.45, brightness: 0.85)],
                       startPoint: .topLeading, endPoint: .bottomTrailing)
            .overlay {
                GeometryReader { g in
                    BirdShape().fill(.white.opacity(loading ? 0.55 : 0.9))
                        .frame(width: g.size.width * 0.46, height: g.size.width * 0.46)
                        .position(x: g.size.width / 2, y: g.size.height / 2)
                }
            }
    }

    static func hue(_ s: String) -> Double {
        let hues: [Double] = [0.42, 0.10, 0.56, 0.03, 0.74, 0.27, 0.92, 0.50]
        return hues[s.unicodeScalars.reduce(0) { $0 + Int($1.value) } % hues.count]
    }
}
