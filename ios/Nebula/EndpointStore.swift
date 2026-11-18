import Foundation
import Security

struct StudioEndpoint: Equatable {
    var host: String
    var port: Int
    var token: String

    var socketURL: URL? {
        var parts = URLComponents()
        parts.scheme = "ws"
        parts.host = host
        parts.port = port
        parts.path = "/nebula"
        return parts.url
    }
}

enum EndpointDraft {
    /// A bare host, or a pasted ws://host:port URL. A user or password in the
    /// URL is refused so a credential cannot hide in the address field.
    static func make(hostField: String, portField: String, token: String, keepToken: String?) -> Result<StudioEndpoint, String> {
        var host = hostField.trimmingCharacters(in: .whitespacesAndNewlines)
        var portText = portField.trimmingCharacters(in: .whitespacesAndNewlines)
        let typed = token.trimmingCharacters(in: .whitespacesAndNewlines)
        let secret = typed.isEmpty ? (keepToken ?? "") : typed
        if secret.isEmpty {
            return .failure("The token is required.")
        }
        if host.isEmpty {
            return .failure("The address is required.")
        }
        if host.contains("@") {
            return .failure("The address cannot contain a password.")
        }
        if let url = URL(string: host), let scheme = url.scheme?.lowercased(), scheme == "ws" || scheme == "wss" {
            if url.user != nil || url.password != nil {
                return .failure("The address cannot contain a password.")
            }
            host = url.host ?? ""
            if let urlPort = url.port {
                portText = String(urlPort)
            }
        }
        if host.isEmpty || host.contains("/") || host.contains(" ") || host.contains(":") {
            return .failure("The address should be a host name, with no path.")
        }
        if portText.isEmpty {
            portText = "8770"
        }
        guard let port = Int(portText), (1 ... 65535).contains(port) else {
            return .failure("The port should be a number from 1 to 65535.")
        }
        return .success(StudioEndpoint(host: host, port: port, token: secret))
    }
}

enum EndpointStore {
    private static let service = "app.nebula.mobile"
    private static let account = "studio"

    static func load() -> StudioEndpoint? {
        guard let data = read(),
              let stored = try? JSONDecoder().decode(Stored.self, from: data),
              !stored.host.isEmpty, !stored.token.isEmpty
        else {
            return nil
        }
        return StudioEndpoint(host: stored.host, port: stored.port, token: stored.token)
    }

    static func save(_ endpoint: StudioEndpoint) -> String? {
        let stored = Stored(host: endpoint.host, port: endpoint.port, token: endpoint.token)
        guard let data = try? JSONEncoder().encode(stored) else {
            return "Could not store the connection."
        }
        delete()
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        ]
        let status = SecItemAdd(query as CFDictionary, nil)
        return status == errSecSuccess ? nil : "The phone could not save the connection."
    }

    static func delete() {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
    }

    private static func read() -> Data? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess else {
            return nil
        }
        return item as? Data
    }
}

private struct Stored: Codable {
    var host: String
    var port: Int
    var token: String
}
