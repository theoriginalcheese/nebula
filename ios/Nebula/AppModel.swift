import ActivityKit
import Foundation
import UIKit

enum PhoneTab: String, CaseIterable, Identifiable {
    case now = "Now"
    case clips = "Clips"
    case remote = "Remote"
    case games = "Games"

    var id: String { rawValue }

    var symbol: String {
        switch self {
        case .now: "record.circle"
        case .clips: "film.stack"
        case .remote: "play.tv"
        case .games: "gamecontroller"
        }
    }
}

enum SettingsRoute: String, Hashable, Identifiable {
    case pc, recording, games, hotkey, sync, offload, remote, appearance, notifications, updates

    var id: String { rawValue }

    var title: String {
        switch self {
        case .pc: "Studio PC"
        case .recording: "Recording"
        case .games: "Games & detection"
        case .hotkey: "Hotkey"
        case .sync: "Game list sync"
        case .offload: "Offload to NAS"
        case .remote: "Remote streaming"
        case .appearance: "Appearance"
        case .notifications: "Notifications"
        case .updates: "Updates"
        }
    }
}

@MainActor
final class AppModel: ObservableObject {
    enum Link: Equatable {
        case unpaired
        case connecting
        case online
        case offline
    }

    @Published var link: Link = .unpaired
    @Published var studio: Studio?
    @Published var prefs = PhonePrefs()
    @Published var notice: String?
    @Published var toastText: String?
    @Published var hostField = ""
    @Published var portField = "8770"
    @Published var tokenField = ""
    @Published var settingsPresented = false
    @Published var lastSeen: Date?
    @Published var bitrate: [Double] = []
    @Published var fpsSamples: [Double] = []
    @Published var listed: [Clip]?
    @Published var savedFlash = false
    @Published var streaming = false
    @Published var undoNote: String?
    @Published var classifyID: String?
    @Published var playback = false
    @Published var trimming = false
    @Published var requestedTab: PhoneTab?
    @Published var clipRoute: String?
    @Published var settingsRoute: SettingsRoute?
    @Published var active = true
    @Published var addGame = false

    private let client = AgentClient()
    private var endpoint: StudioEndpoint?
    private var dropGeneration = 0
    private var toastGeneration = 0
    private var undoGeneration = 0
    private var savedGeneration = 0
    private var undoExe: String?
    private var undoWasGame = false
    private var classifyInFlight: Set<String> = []
    private var resolvedPending: [String: Date] = [:]
    private let resolvedHold: TimeInterval = 30
    private var clockOffset: TimeInterval = 0
    private let cacheURL: URL
    private let prefsURL: URL
    private var activityID: String?

    init() {
        let base = (try? FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )) ?? FileManager.default.temporaryDirectory
        cacheURL = base.appendingPathComponent("nebula-studio.json")
        prefsURL = base.appendingPathComponent("nebula-phone-prefs.json")
        prefs = PhonePrefs.load(prefsURL)
        studio = Self.readCache(cacheURL)
        client.onEvent = { [weak self] type, data in self?.apply(type, data) }
        client.onRejected = { [weak self] in self?.reject() }
        client.onDrop = { [weak self] in self?.noteDrop() }
        client.onRecovered = { [weak self] in self?.noteRecovered() }
        if let saved = EndpointStore.load() {
            endpoint = saved
            hostField = saved.host
            portField = String(saved.port)
            link = .connecting
            client.start(saved)
            armOfflineTimer()
        }
    }

    var hasSavedToken: Bool { endpoint != nil }
    var controlsEnabled: Bool { link == .online && studio?.obsConnected != false }
    var pendingApp: PendingApp? { studio?.pending.first { $0.id == classifyID } }

    func elapsed(at now: Date) -> TimeInterval {
        guard let session = studio?.session, let started = session.startedAt else { return 0 }
        let end: Date
        if session.state == "paused", let paused = session.pausedAt {
            end = paused
        } else {
            end = now.addingTimeInterval(-clockOffset)
        }
        return max(0, end.timeIntervalSince(started) - session.pausedTotal)
    }

    func http(_ path: String) -> URL? {
        guard let endpoint, path.hasPrefix("/") else { return nil }
        var parts = URLComponents()
        parts.scheme = "http"
        parts.host = endpoint.host
        parts.port = endpoint.port
        parts.path = path
        return parts.url
    }

    func connectFromFields() {
        let result = EndpointDraft.make(
            hostField: hostField,
            portField: portField,
            token: tokenField,
            keepToken: endpoint?.token
        )
        switch result {
        case let .failure(message):
            notice = message
        case let .success(next):
            if let problem = EndpointStore.save(next) {
                notice = problem
                return
            }
            tokenField = ""
            notice = nil
            endpoint = next
            hostField = next.host
            portField = String(next.port)
            settingsPresented = false
            link = .connecting
            client.start(next)
            armOfflineTimer()
        }
    }

    func unpair() {
        dropGeneration += 1
        client.stop()
        EndpointStore.delete()
        endpoint = nil
        tokenField = ""
        link = .unpaired
        notice = nil
        settingsPresented = false
        endActivity()
    }

    func setActive(_ value: Bool) {
        active = value
        if value, classifyID == nil, !playback, !trimming {
            classifyID = studio?.pending.first?.id
        }
    }

    func watchStats(_ on: Bool) {
        guard link == .online else { return }
        client.send(on ? "stats.subscribe" : "stats.unsubscribe")
    }

    func command(_ type: String, _ data: [String: Any] = [:], saved: Bool = false, done: ((Bool) -> Void)? = nil) {
        guard link == .online else {
            toast("Studio PC is offline.")
            done?(false)
            return
        }
        client.send(type, data: data) { [weak self] result in
            guard let self else { return }
            switch result {
            case let .failure(message):
                if type == "session.start", message.localizedCaseInsensitiveContains("foreground") {
                    self.toast("No game in the foreground on Studio PC")
                } else {
                    self.toast(message)
                }
                done?(false)
            case let .success(payload):
                if type == "clips.list" {
                    let rows = payload["clips"] as? [Any] ?? []
                    self.listed = rows.compactMap { StudioJSON.clip($0) }
                }
                if saved { self.flashSaved() }
                done?(true)
            }
        }
    }

    func session(_ type: String) {
        guard var studio, link == .online else {
            toast("Studio PC is offline.")
            return
        }
        if studio.obsConnected == false {
            toast("OBS isn’t connected on Studio PC")
            return
        }
        let before = studio
        if type == "session.pause" {
            studio.session.state = "paused"
            studio.session.pausedAt = Date().addingTimeInterval(-clockOffset)
        } else if type == "session.resume" {
            studio.session.state = "recording"
            studio.session.pausedAt = nil
        } else if type == "session.stop" {
            studio.session.state = "idle"
            studio.session.game = nil
        }
        if type != "session.start" {
            self.studio = studio
        }
        client.send(type) { [weak self] result in
            guard let self else { return }
            if case let .failure(message) = result {
                self.studio = before
                if type == "session.start", message.localizedCaseInsensitiveContains("foreground") {
                    self.toast("No game in the foreground on Studio PC")
                } else {
                    self.toast(message)
                }
            } else if type == "session.stop" {
                self.streaming = false
            }
        }
    }

    func classify(_ item: PendingApp, isGame: Bool, capture: String) {
        let pendingID = item.id
        guard !classifyInFlight.contains(pendingID) else { return }
        classifyInFlight.insert(pendingID)
        command("app.classify", ["pendingId": pendingID, "isGame": isGame, "capture": isGame ? capture : "default"]) { [weak self] ok in
            guard let self else { return }
            self.classifyInFlight.remove(pendingID)
            guard ok else { return }
            let name = Self.pretty(item.exe)
            self.undoExe = item.exe
            self.undoWasGame = isGame
            self.undoNote = isGame ? "\(name) added — it’ll record" : "\(name) marked not a game"
            self.armUndo()
            // The answer is final on this phone: drop the row now rather than
            // waiting for app.resolved, and close the sheet (the old code
            // re-pointed it at pending.first, which was still this item).
            self.resolvedPending[pendingID] = Date()
            self.studio?.pending.removeAll { $0.id == pendingID || $0.exe == item.exe }
            if self.classifyID == pendingID {
                self.classifyID = nil
            }
        }
    }

    /// True while a just-answered id may still be echoed back by a stale
    /// snapshot or a late app.pending event.
    private func recentlyResolved(_ id: String) -> Bool {
        let now = Date()
        resolvedPending = resolvedPending.filter { now.timeIntervalSince($0.value) < resolvedHold }
        return resolvedPending[id] != nil
    }

    func reclassify(exe: String, isGame: Bool) {
        command("app.reclassify", ["exe": exe, "isGame": isGame])
    }

    func undoClassify() {
        guard let exe = undoExe else { return }
        command("app.reclassify", ["exe": exe, "isGame": !undoWasGame])
        undoNote = nil
        undoExe = nil
    }

    func setCapture(_ game: Game, _ capture: String) {
        command("game.setCapture", ["gameId": game.id, "capture": capture])
    }

    func setSetting(_ key: String, _ value: Any) {
        command("settings.set", ["key": key, "value": value], saved: true)
    }

    func refreshClips(query: String, gameId: String?) {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty, gameId == nil {
            listed = nil
            return
        }
        var data: [String: Any] = [:]
        if !trimmed.isEmpty { data["query"] = trimmed }
        if let gameId { data["gameId"] = gameId }
        command("clips.list", data)
    }

    func deleteClip(_ id: String) {
        command("clip.delete", ["id": id])
    }

    func trimClip(_ id: String, start: Double, end: Double) {
        command("clip.trim", ["id": id, "in": start, "out": end])
    }

    /// Opens Moonlight on this phone first. A slow or offline Studio PC must
    /// not stand between the tap and the app.
    func stream(openMoonlight: @escaping () -> Void) {
        openMoonlight()
        command("remote.stream") { [weak self] ok in
            guard ok else { return }
            self?.streaming = true
        }
    }

    func updatePrefs(_ edit: (inout PhonePrefs) -> Void) {
        edit(&prefs)
        prefs.save(prefsURL)
    }

    func toast(_ text: String) {
        toastGeneration += 1
        let generation = toastGeneration
        toastText = text
        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 2_600_000_000)
            guard generation == self.toastGeneration else { return }
            self.toastText = nil
        }
    }

    func open(_ url: URL) {
        guard url.scheme == "nebula" else { return }
        let host = url.host ?? ""
        let piece = url.path.split(separator: "/").first.map(String.init)
        switch host {
        case "now":
            requestedTab = .now
            if piece == "pause" {
                session(studio?.session.state == "paused" ? "session.resume" : "session.pause")
            } else if piece == "stop" {
                session("session.stop")
            }
        case "clip":
            requestedTab = .clips
            clipRoute = piece
        case "pending":
            requestedTab = .games
            classifyID = piece
        case "settings":
            settingsPresented = true
            if let piece, let route = SettingsRoute(rawValue: piece) {
                settingsRoute = route
            }
        default:
            break
        }
    }

    private func apply(_ type: String, _ data: [String: Any]) {
        switch type {
        case "snapshot":
            var next = StudioJSON.studio(data)
            next.stats = studio?.stats
            if let server = next.serverNow {
                clockOffset = Date().timeIntervalSince(server)
            }
            next.pending.removeAll { recentlyResolved($0.id) }
            studio = next
            cache()
            syncActivity()
        case "session":
            studio?.session = StudioJSON.session(data)
            cache()
            syncActivity()
        case "stats":
            let audio = data["audio"] as? [String: Any]
            studio?.stats = Stats(
                bitrateMbps: StudioJSON.number(data["bitrateMbps"]),
                droppedFrames: StudioJSON.number(data["droppedFrames"]).map { Int($0) },
                gameFps: StudioJSON.number(data["gameFps"]).map { Int($0) },
                gpuTempC: StudioJSON.number(data["gpuTempC"]).map { Int($0) },
                audio: audio == nil ? nil : AudioLevels(
                    game: StudioJSON.number(audio?["game"]) ?? 0,
                    mic: StudioJSON.number(audio?["mic"]) ?? 0,
                    chat: StudioJSON.number(audio?["chat"]) ?? 0
                )
            )
            if let rate = studio?.stats?.bitrateMbps {
                bitrate.append(rate)
                if bitrate.count > 28 { bitrate.removeFirst(bitrate.count - 28) }
            }
            if let frames = studio?.stats?.gameFps {
                fpsSamples.append(Double(frames))
                if fpsSamples.count > 28 { fpsSamples.removeFirst(fpsSamples.count - 28) }
            }
        case "app.pending":
            if let item = StudioJSON.pending(data), !recentlyResolved(item.id) {
                studio?.pending.removeAll { $0.id == item.id }
                studio?.pending.insert(item, at: 0)
                if active, !playback, !trimming, classifyID == nil {
                    classifyID = item.id
                }
            }
        case "app.resolved":
            if let id = data["id"] as? String {
                studio?.pending.removeAll { $0.id == id || $0.exe == id }
                if classifyID == id { classifyID = nil }
            }
        case "clip.added":
            if let clip = StudioJSON.clip(data) {
                studio?.clips.removeAll { $0.id == clip.id }
                studio?.clips.insert(clip, at: 0)
                cache()
            }
        case "clip.updated":
            if let clip = StudioJSON.clip(data), let index = studio?.clips.firstIndex(where: { $0.id == clip.id }) {
                studio?.clips[index] = clip
                cache()
            }
        case "clip.removed":
            if let id = data["id"] as? String {
                studio?.clips.removeAll { $0.id == id }
                cache()
            }
        case "games":
            studio?.games = (data["games"] as? [Any] ?? []).compactMap { StudioJSON.game($0) }
            studio?.nonGames = (data["nonGames"] as? [Any] ?? []).compactMap { StudioJSON.nonGame($0) }
            cache()
        case "settings":
            studio?.settings = StudioJSON.settings(data)
            cache()
        case "peers":
            if let rows = data["peers"] as? [Any] {
                studio?.peers = rows.compactMap { StudioJSON.peer($0) }
            }
        case "obs":
            if let connected = data["connected"] as? Bool {
                studio?.obsConnected = connected
            }
        default:
            break
        }
    }

    private func flashSaved() {
        savedGeneration += 1
        let generation = savedGeneration
        savedFlash = true
        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            guard generation == self.savedGeneration else { return }
            self.savedFlash = false
        }
    }

    private func armUndo() {
        undoGeneration += 1
        let generation = undoGeneration
        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 8_000_000_000)
            guard generation == self.undoGeneration else { return }
            self.undoNote = nil
            self.undoExe = nil
        }
    }

    private func reject() {
        dropGeneration += 1
        client.stop()
        link = .unpaired
        notice = "Device token was rejected."
        settingsPresented = false
    }

    private func noteDrop() {
        guard link != .unpaired else { return }
        link = .connecting
        streaming = false
        armOfflineTimer()
    }

    private func noteRecovered() {
        dropGeneration += 1
        link = .online
        lastSeen = Date()
    }

    private func armOfflineTimer() {
        dropGeneration += 1
        let generation = dropGeneration
        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            guard generation == self.dropGeneration, self.link == .connecting else { return }
            self.link = .offline
        }
    }

    private func cache() {
        guard let studio, let data = try? JSONEncoder().encode(studio) else { return }
        try? data.write(to: cacheURL, options: .atomic)
    }

    private static func readCache(_ url: URL) -> Studio? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(Studio.self, from: data)
    }

    private static func pretty(_ exe: String) -> String {
        exe.lowercased().hasSuffix(".exe") ? String(exe.dropLast(4)) : exe
    }

    private func syncActivity() {
        guard let session = studio?.session else { return }
        guard session.playing else {
            endActivity()
            return
        }
        let frozen = session.state == "paused" ? StudioFormat.clock(elapsed(at: Date())) : nil
        let start = Date().addingTimeInterval(-(frozen == nil ? elapsed(at: Date()) : 0))
        let state = RecordingActivity.ContentState(
            state: session.state,
            game: session.game?.name ?? "Studio PC",
            output: session.output.line,
            clockStart: start,
            frozen: frozen
        )
        let content = ActivityContent(state: state, staleDate: nil)
        if let current = Activity<RecordingActivity>.activities.first {
            Task { await current.update(content) }
            return
        }
        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return }
        do {
            let activity = try Activity.request(
                attributes: RecordingActivity(name: "Nebula"),
                content: content,
                pushType: nil
            )
            activityID = activity.id
        } catch {
            activityID = nil
        }
    }

    private func endActivity() {
        let current = Activity<RecordingActivity>.activities
        activityID = nil
        Task {
            for activity in current {
                await activity.end(nil as ActivityContent<RecordingActivity.ContentState>?, dismissalPolicy: .immediate)
            }
        }
    }
}
