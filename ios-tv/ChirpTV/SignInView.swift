import CoreImage.CIFilterBuiltins
import SwiftUI

/// Sign in by code: the TV shows a code and a QR code; someone signed in on a
/// phone or computer enters it (Profile → Apple TV, or /tv?code=...).
struct SignInView: View {
    @EnvironmentObject var account: Account
    @State private var pairID: String?
    @State private var code = ""
    @State private var error: String?
    @State private var editingServer = false
    @State private var serverText = ""

    private struct Start: Decodable { let pairId: String; let code: String; let expiresIn: Int }
    private struct Poll: Decodable { let status: String; let accessToken: String?; let username: String? }

    var body: some View {
        HStack(alignment: .center, spacing: 90) {
            VStack(alignment: .leading, spacing: 28) {
                HStack(spacing: 20) {
                    ChirpMark(height: 70, animate: true)
                    Text("Chirp").font(.system(size: 76, weight: .semibold, design: .serif))
                }
                Text("Sign in with your phone").font(.title2).foregroundStyle(Theme.ink)
                VStack(alignment: .leading, spacing: 14) {
                    step(1, "On your phone or computer, open", link: Account.typable(account.pageURL("tv")))
                    step(2, "Sign in if asked, then enter this code:")
                }
                Text(code.isEmpty ? "······" : spaced(code))
                    .font(.system(size: 110, weight: .bold, design: .monospaced))
                    .foregroundStyle(Theme.amber)
                    .accessibilityLabel(code.isEmpty ? "Getting a code" : "Code \(code.map(String.init).joined(separator: " "))")
                if let error {
                    Text(error).foregroundStyle(Theme.rose).font(.callout)
                }
                HStack(spacing: 30) {
                    Button("New code") { Task { await start() } }
                    Button("Server: \(displayHost)") {
                        serverText = Account.typable(account.server, keepWWW: true)
                        editingServer = true
                    }
                }
            }
            .frame(maxWidth: 900, alignment: .leading)

            VStack(spacing: 20) {
                if let qr = qrImage {
                    Image(uiImage: qr).interpolation(.none).resizable()
                        .frame(width: 380, height: 380)
                        .padding(26).background(Color.white, in: RoundedRectangle(cornerRadius: 24))
                        .accessibilityLabel("QR code to link this TV")
                }
                Text("Or scan with your iPhone camera").font(.callout).foregroundStyle(Theme.muted)
            }
        }
        .padding(80)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.bg)
        .task(id: account.server) { await start() }
        .task(id: pairID) { await poll() }
        .alert("Chirp server", isPresented: $editingServer) {
            TextField("ourchirp.com", text: $serverText)
            Button("Use this server") {
                if account.setServer(serverText) { Task { await start() } } else { error = "That doesn't look like a server address." }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("The address of your Chirp site, e.g. ourchirp.com, chirp.example.com or 192.168.1.50:8768. Home-network addresses use http://; type https:// or http:// to choose.")
        }
    }

    private var displayHost: String { Account.typable(account.server) }

    private func spaced(_ c: String) -> String { c.count == 6 ? "\(c.prefix(3)) \(c.suffix(3))" : c }

    private func step(_ n: Int, _ text: String, link: String? = nil) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 16) {
            Text("\(n)").font(.headline).frame(width: 44, height: 44)
                .background(Theme.card, in: Circle())
            VStack(alignment: .leading, spacing: 6) {
                Text(text).font(.title3).foregroundStyle(Theme.ink)
                if let link {
                    Text(link).font(.system(.title3, design: .monospaced).weight(.semibold))
                        .foregroundStyle(Theme.amber)
                        .lineLimit(1).minimumScaleFactor(0.6)
                }
            }
        }
    }

    private var qrImage: UIImage? {
        guard !code.isEmpty else { return nil }
        let f = CIFilter.qrCodeGenerator()
        f.message = Data(account.pageURL("tv", query: [URLQueryItem(name: "code", value: code)]).absoluteString.utf8)
        f.correctionLevel = "M"
        guard let img = f.outputImage,
              let cg = CIContext().createCGImage(img, from: img.extent) else { return nil }
        return UIImage(cgImage: cg)
    }

    private func start() async {
        error = nil
        do {
            let s: Start = try await API.post("api/v1/tv/pair/start", json: [:], auth: false)
            code = s.code
            pairID = s.pairId
        } catch {
            self.error = API.describe(error)
        }
    }

    private func poll() async {
        guard let pid = pairID else { return }
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(3))
            guard !Task.isCancelled, pairID == pid else { return }
            do {
                let p: Poll = try await API.post("api/v1/tv/pair/poll", json: ["pair_id": pid], auth: false)
                switch p.status {
                case "approved":
                    if let t = p.accessToken { account.signIn(token: t, username: p.username ?? "") }
                    return
                case "expired":
                    await start()
                    return
                default:
                    continue
                }
            } catch {
                self.error = API.describe(error)
            }
        }
    }
}
