import Foundation

struct GameRef: Codable, Equatable, Hashable {
    var id: String
    var name: String
}

struct Highlight: Codable, Equatable, Hashable {
    var at: Double
    var label: String?
    var kind: String
}

struct Output: Codable, Equatable {
    var resolution: String
    var fps: Int
    var encoder: String

    var line: String {
        let height: String
        if let mark = resolution.split(separator: "x").last, !mark.isEmpty {
            height = String(mark)
        } else {
            height = resolution
        }
        return "\(height)p\(fps) · \(encoder)"
    }
}

enum Offload: Equatable, Codable {
    case none
    case queued
    case done
    case moving(progress: Double, bytesLeft: Int64)
    case failed(String)

    var isActive: Bool {
        switch self {
        case .queued, .moving: true
        default: false
        }
    }

    private enum Key: String, CodingKey {
        case kind, progress, bytesLeft, error
    }

    init(from decoder: Decoder) throws {
        let box = try decoder.container(keyedBy: Key.self)
        switch try box.decode(String.self, forKey: .kind) {
        case "queued": self = .queued
        case "done": self = .done
        case "moving":
            self = .moving(
                progress: try box.decode(Double.self, forKey: .progress),
                bytesLeft: try box.decode(Int64.self, forKey: .bytesLeft)
            )
        case "failed": self = .failed(try box.decode(String.self, forKey: .error))
        default: self = .none
        }
    }

    func encode(to encoder: Encoder) throws {
        var box = encoder.container(keyedBy: Key.self)
        switch self {
        case .none:
            try box.encode("none", forKey: .kind)
        case .queued:
            try box.encode("queued", forKey: .kind)
        case .done:
            try box.encode("done", forKey: .kind)
        case let .moving(progress, bytesLeft):
            try box.encode("moving", forKey: .kind)
            try box.encode(progress, forKey: .progress)
            try box.encode(bytesLeft, forKey: .bytesLeft)
        case let .failed(error):
            try box.encode("failed", forKey: .kind)
            try box.encode(error, forKey: .error)
        }
    }
}

struct LastSession: Codable, Equatable {
    var game: GameRef
    var endedAt: Date
    var duration: Double
    var bytes: Int64
    var highlightCount: Int
    var offload: Offload
}

struct Session: Codable, Equatable {
    var state: String
    var game: GameRef?
    var startedAt: Date?
    var pausedTotal: Double
    var pausedAt: Date?
    var scene: String
    var output: Output
    var bytesWritten: Int64
    var highlights: [Highlight]
    var storageFreeBytes: Int64?
    var estimatedRemaining: Double?
    var lastSession: LastSession?
    var achievement: String?

    var playing: Bool {
        state == "recording" || state == "paused" || state == "bufferOnly"
    }
}

struct AudioLevels: Codable, Equatable {
    var game: Double
    var mic: Double
    var chat: Double
}

struct Stats: Codable, Equatable {
    var bitrateMbps: Double?
    var droppedFrames: Int?
    var gameFps: Int?
    var gpuTempC: Int?
    var audio: AudioLevels?
}

struct Clip: Codable, Equatable, Identifiable {
    var id: String
    var game: GameRef
    var file: String
    var folder: String
    var kind: String
    var createdAt: Date?
    var duration: Double?
    var bytes: Int64?
    var resolution: String
    var fps: Int
    var encoder: String
    var highlights: [Highlight]
    var locations: [String]
    var offload: Offload
    var thumbnailURL: String?
    var writing: Bool

    var label: String {
        if let mark = highlights.first(where: { ($0.label ?? "").isEmpty == false })?.label {
            return mark
        }
        if kind == "replay" { return "Replay" }
        return "Gameplay"
    }
}

struct Game: Codable, Equatable, Identifiable {
    var id: String
    var name: String
    var source: String
    var capture: String
    var clipCount: Int
    var bytes: Int64
    var coverURL: String?
    var lastPlayed: Date?
    var weekPlaytime: [Double]

    var sourceLabel: String {
        switch source {
        case "steam": "Steam"
        case "prompt": "Added just now"
        default: "Added by you"
        }
    }
}

struct PendingApp: Codable, Equatable, Identifiable {
    var id: String
    var exe: String
    var fullscreen: Bool
    var width: Int
    var height: Int
    var inSteam: Bool
    var seenAt: Date?
}

struct NonGame: Codable, Equatable, Identifiable {
    var exe: String
    var displayName: String
    var id: String { exe }
}

struct Peer: Codable, Equatable, Identifiable {
    var name: String
    var online: Bool
    var isHost: Bool
    var id: String { name }
}

struct StudioSettings: Codable, Equatable {
    var launchCapture: String = "record"
    var replaySeconds: Int = 30
    var idleTimeout: Int = 4
    var discardUnder: Int = 0
    var keepAliveApps: [String] = []
    var recordingRoot: String = ""
    var syncProvider: String = "none"
    var syncPath: String = ""
    var offloadTarget: String?
    var offloadAuto: Bool = false
    var tailscale: Bool = false
    var moonlightInstalled: Bool = false
    var hotkey: String = ""
    var appVersion: String = ""
    var updateAvailable: String?

    var launchLabel: String {
        switch launchCapture {
        case "buffer": "Buffer"
        case "both": "Both"
        default: "Record"
        }
    }

    var replayLabel: String {
        switch replaySeconds {
        case 15: "15 s"
        case 60: "60 s"
        case 120: "2 min"
        default: "30 s"
        }
    }
}

struct Studio: Codable, Equatable {
    var serverNow: Date?
    var session: Session
    var games: [Game]
    var nonGames: [NonGame]
    var pending: [PendingApp]
    var clips: [Clip]
    var settings: StudioSettings
    var peers: [Peer]
    var obsConnected: Bool
    var stats: Stats?
}

enum StudioJSON {
    static func studio(_ data: [String: Any]) -> Studio {
        Studio(
            serverNow: date(data["serverNow"]),
            session: session(data["session"] as? [String: Any] ?? [:]),
            games: (data["games"] as? [Any] ?? []).compactMap { game($0) },
            nonGames: (data["nonGames"] as? [Any] ?? []).compactMap { nonGame($0) },
            pending: (data["pending"] as? [Any] ?? []).compactMap { pending($0) },
            clips: (data["clips"] as? [Any] ?? []).compactMap { clip($0) },
            settings: settings(data["settings"] as? [String: Any] ?? [:]),
            peers: (data["peers"] as? [Any] ?? []).compactMap { peer($0) },
            obsConnected: (data["obs"] as? [String: Any])?["connected"] as? Bool ?? true,
            stats: nil
        )
    }

    static func session(_ data: [String: Any]) -> Session {
        let output = data["output"] as? [String: Any] ?? [:]
        return Session(
            state: data["state"] as? String ?? "idle",
            game: ref(data["game"]),
            startedAt: date(data["startedAt"]),
            pausedTotal: number(data["pausedTotal"]) ?? 0,
            pausedAt: date(data["pausedAt"]),
            scene: data["scene"] as? String ?? "",
            output: Output(
                resolution: output["resolution"] as? String ?? "",
                fps: Int(number(output["fps"]) ?? 0),
                encoder: output["encoder"] as? String ?? ""
            ),
            bytesWritten: whole(data["bytesWritten"]) ?? 0,
            highlights: highlights(data["highlights"]),
            storageFreeBytes: whole(data["storageFreeBytes"]),
            estimatedRemaining: number(data["estimatedRemaining"]),
            lastSession: last(data["lastSession"]),
            achievement: data["achievement"] as? String
        )
    }

    static func settings(_ data: [String: Any]) -> StudioSettings {
        let sync = data["gameListSync"] as? [String: Any] ?? [:]
        let offload = data["offload"] as? [String: Any] ?? [:]
        let remote = data["remote"] as? [String: Any] ?? [:]
        var value = StudioSettings()
        value.launchCapture = data["launchCapture"] as? String ?? value.launchCapture
        value.replaySeconds = Int(number(data["replaySeconds"]) ?? Double(value.replaySeconds))
        value.idleTimeout = Int(number(data["idleTimeout"]) ?? Double(value.idleTimeout))
        value.discardUnder = Int(number(data["discardUnder"]) ?? Double(value.discardUnder))
        value.keepAliveApps = data["keepAliveApps"] as? [String] ?? []
        value.recordingRoot = data["recordingRoot"] as? String ?? ""
        value.syncProvider = sync["provider"] as? String ?? "none"
        value.syncPath = sync["path"] as? String ?? ""
        value.offloadTarget = offload["target"] as? String
        value.offloadAuto = offload["auto"] as? Bool ?? false
        value.tailscale = remote["tailscale"] as? Bool ?? false
        value.moonlightInstalled = remote["moonlightInstalled"] as? Bool ?? false
        value.hotkey = data["hotkey"] as? String ?? ""
        value.appVersion = data["appVersion"] as? String ?? ""
        value.updateAvailable = data["updateAvailable"] as? String
        return value
    }

    static func clip(_ any: Any) -> Clip? {
        guard let data = any as? [String: Any], let id = data["id"] as? String, let game = ref(data["game"]) else {
            return nil
        }
        return Clip(
            id: id,
            game: game,
            file: data["file"] as? String ?? "",
            folder: data["folder"] as? String ?? game.name,
            kind: data["kind"] as? String ?? "recording",
            createdAt: date(data["createdAt"]),
            duration: number(data["duration"]),
            bytes: whole(data["bytes"]),
            resolution: data["resolution"] as? String ?? "",
            fps: Int(number(data["fps"]) ?? 0),
            encoder: data["encoder"] as? String ?? "",
            highlights: highlights(data["highlights"]),
            locations: data["locations"] as? [String] ?? [],
            offload: offload(data["offload"]),
            thumbnailURL: data["thumbnailURL"] as? String,
            writing: data["writing"] as? Bool ?? false
        )
    }

    static func game(_ any: Any) -> Game? {
        guard let data = any as? [String: Any], let id = data["id"] as? String, let name = data["name"] as? String else {
            return nil
        }
        let week = (data["weekPlaytime"] as? [Any] ?? []).compactMap { number($0) }
        return Game(
            id: id,
            name: name,
            source: data["source"] as? String ?? "user",
            capture: data["capture"] as? String ?? "default",
            clipCount: Int(number(data["clipCount"]) ?? 0),
            bytes: whole(data["bytes"]) ?? 0,
            coverURL: data["coverURL"] as? String,
            lastPlayed: date(data["lastPlayed"]),
            weekPlaytime: week
        )
    }

    static func pending(_ any: Any) -> PendingApp? {
        guard let data = any as? [String: Any], let id = data["id"] as? String, let exe = data["exe"] as? String else {
            return nil
        }
        let window = data["window"] as? [String: Any] ?? [:]
        return PendingApp(
            id: id,
            exe: exe,
            fullscreen: window["fullscreen"] as? Bool ?? false,
            width: Int(number(window["width"]) ?? 0),
            height: Int(number(window["height"]) ?? 0),
            inSteam: data["inSteam"] as? Bool ?? false,
            seenAt: date(data["seenAt"])
        )
    }

    static func nonGame(_ any: Any) -> NonGame? {
        guard let data = any as? [String: Any], let exe = data["exe"] as? String else { return nil }
        return NonGame(exe: exe, displayName: data["displayName"] as? String ?? exe)
    }

    static func peer(_ any: Any) -> Peer? {
        guard let data = any as? [String: Any], let name = data["name"] as? String, !name.isEmpty else { return nil }
        return Peer(name: name, online: data["online"] as? Bool ?? false, isHost: data["isHost"] as? Bool ?? false)
    }

    static func offload(_ any: Any?) -> Offload {
        if let text = any as? String {
            switch text {
            case "queued": return .queued
            case "done": return .done
            default: return .none
            }
        }
        guard let data = any as? [String: Any] else { return .none }
        if let error = data["error"] as? String { return .failed(error) }
        return .moving(progress: number(data["progress"]) ?? 0, bytesLeft: whole(data["bytesLeft"]) ?? 0)
    }

    private static func last(_ any: Any?) -> LastSession? {
        guard let data = any as? [String: Any], let game = ref(data["game"]), let ended = date(data["endedAt"]) else {
            return nil
        }
        return LastSession(
            game: game,
            endedAt: ended,
            duration: number(data["duration"]) ?? 0,
            bytes: whole(data["bytes"]) ?? 0,
            highlightCount: Int(number(data["highlightCount"]) ?? 0),
            offload: offload(data["offload"])
        )
    }

    private static func ref(_ any: Any?) -> GameRef? {
        guard let data = any as? [String: Any], let id = data["id"] as? String, let name = data["name"] as? String else {
            return nil
        }
        return GameRef(id: id, name: name)
    }

    private static func highlights(_ any: Any?) -> [Highlight] {
        (any as? [Any] ?? []).compactMap { item in
            guard let data = item as? [String: Any] else { return nil }
            return Highlight(at: number(data["at"]) ?? 0, label: data["label"] as? String, kind: data["kind"] as? String ?? "manual")
        }
    }

    private static let stamp: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    static func date(_ any: Any?) -> Date? {
        guard let text = any as? String else { return nil }
        return stamp.date(from: text)
    }

    static func number(_ any: Any?) -> Double? {
        switch any {
        case let value as Double: return value
        case let value as Int: return Double(value)
        case let value as NSNumber: return value.doubleValue
        default: return nil
        }
    }

    static func whole(_ any: Any?) -> Int64? {
        switch any {
        case let value as Int: return Int64(value)
        case let value as Double: return Int64(value)
        case let value as NSNumber: return value.int64Value
        default: return nil
        }
    }
}

enum StudioFormat {
    static func bytes(_ value: Int64?) -> String {
        guard let value else { return "—" }
        let gb = Double(value) / 1_000_000_000
        if gb < 10 {
            return String(format: "%.1f GB", gb)
        }
        return String(format: "%.0f GB", gb.rounded())
    }

    static func clock(_ seconds: TimeInterval) -> String {
        let whole = max(0, Int(seconds.rounded(.down)))
        return String(format: "%02d:%02d:%02d", whole / 3600, (whole / 60) % 60, whole % 60)
    }

    static func spoken(_ seconds: TimeInterval) -> String {
        let whole = max(0, Int(seconds.rounded(.down)))
        return "\(whole / 3600) hours \((whole / 60) % 60) minutes \(whole % 60) seconds"
    }

    static func time(_ date: Date) -> String {
        date.formatted(date: .omitted, time: .shortened)
    }

    static func dayAndTime(_ date: Date, now: Date) -> String {
        if Calendar.current.isDate(date, inSameDayAs: now) {
            return "Today, \(time(date))"
        }
        return date.formatted(date: .abbreviated, time: .shortened)
    }

    static func relative(_ date: Date, now: Date) -> String {
        let delta = now.timeIntervalSince(date)
        if delta < 60 { return "\(max(0, Int(delta))) s ago" }
        if delta < 3600 { return "\(Int(delta / 60)) m ago" }
        if delta < 86_400 { return "\(Int(delta / 3600)) h ago" }
        return time(date)
    }

    static func remaining(_ seconds: Double?) -> String? {
        guard let seconds, seconds.isFinite, seconds > 0 else { return nil }
        if seconds >= 86_400 {
            return "≈ \(max(1, Int((seconds / 86_400).rounded()))) days"
        }
        return "≈ \(max(1, Int((seconds / 3600).rounded()))) h"
    }
}
