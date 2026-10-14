import Foundation
import Security

/// The last sign-in sent to the watch, so it can be sent again when the watch asks.
enum ChirpKeychain {
    private static let service = "com.joshuasalvimd.chirp.watch"

    static func get(_ key: String) -> String? {
        var out: AnyObject?
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                kSecAttrService as String: service,
                                kSecAttrAccount as String: key,
                                kSecReturnData as String: true]
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess,
              let data = out as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func set(_ key: String, _ value: String?) {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                kSecAttrService as String: service,
                                kSecAttrAccount as String: key]
        _ = SecItemDelete(q as CFDictionary)
        guard let value, !value.isEmpty else { return }
        var add = q
        add[kSecValueData as String] = Data(value.utf8)
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        _ = SecItemAdd(add as CFDictionary, nil)
    }
}
