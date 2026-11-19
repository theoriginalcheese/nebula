import SwiftUI

struct SettingsRoot: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    @State private var path: [SettingsRoute] = []

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    pcTray
                    group([
                        row(.recording, "record.circle", Theme.violet, model.studio?.settings.launchLabel ?? "—"),
                        row(.recording, "clock.arrow.circlepath", Theme.violet, model.studio?.settings.replayLabel ?? "—", title: "Instant replay"),
                        row(.games, "gamecontroller", Theme.violet, "\(model.studio?.games.count ?? 0) games"),
                        row(.hotkey, "keyboard", Theme.violet, model.studio?.settings.hotkey.isEmpty == false ? model.studio?.settings.hotkey ?? "—" : "—"),
                    ])
                    group([
                        row(.sync, "arrow.triangle.2.circlepath", Theme.teal, syncLabel),
                        row(.offload, "externaldrive", Theme.teal, model.studio?.settings.offloadTarget ?? "—"),
                        row(.remote, "play.tv", Theme.teal, model.studio?.settings.tailscale == true ? "Tailscale" : "—"),
                    ])
                    group([
                        row(.appearance, "paintpalette", Theme.amber, model.prefs.background.title),
                        row(.notifications, "bell", Theme.amber, "On this phone"),
                        row(.updates, "arrow.down.circle", Theme.amber, model.studio?.settings.updateAvailable ?? model.studio?.settings.appVersion ?? "—"),
                    ])
                }
                .padding(20)
            }
            .background(Theme.ground)
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { model.settingsPresented = false }
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(Theme.violetLight)
                }
            }
            .navigationDestination(for: SettingsRoute.self) { route in
                SettingsPage(route: route)
            }
        }
        .onAppear {
            if let route = model.settingsRoute {
                path = [route]
                model.settingsRoute = nil
            }
        }
    }

    private var syncLabel: String {
        switch model.studio?.settings.syncProvider {
        case "onedrive": "OneDrive"
        case "none": "Off"
        default: model.studio?.settings.syncProvider ?? "—"
        }
    }

    private var pcTray: some View {
        Button {
            path.append(.pc)
        } label: {
            HStack(spacing: 12) {
                Circle().fill(Theme.violet).frame(width: 42, height: 42)
                    .overlay(Image(systemName: "moon.stars").foregroundStyle(Theme.ink))
                VStack(alignment: .leading, spacing: 2) {
                    Text("Studio PC").font(.system(size: 17, weight: .semibold)).foregroundStyle(Theme.ink)
                    Text(pcStatus).font(.system(size: 13)).foregroundStyle(model.studio?.obsConnected == false ? Theme.coral : Theme.teal)
                }
                Spacer()
                Image(systemName: "chevron.right").foregroundStyle(tone.tertiary)
            }
            .padding(14)
            .background(RoundedRectangle(cornerRadius: 22, style: .continuous).fill(Theme.card.opacity(0.7)))
        }
        .buttonStyle(.plain)
    }

    private var pcStatus: String {
        if model.link != .online { return "Offline" }
        if model.studio?.obsConnected == false { return "Paired · OBS disconnected" }
        return "Paired · OBS connected"
    }

    private func group(_ rows: [SettingsLink]) -> some View {
        VStack(spacing: 0) {
            ForEach(rows) { item in
                Button {
                    path.append(item.route)
                } label: {
                    HStack(spacing: 12) {
                        Image(systemName: item.symbol)
                            .font(.system(size: 15, weight: .light))
                            .foregroundStyle(item.tint)
                            .frame(width: 30, height: 30)
                            .background(RoundedRectangle(cornerRadius: 9, style: .continuous).fill(item.tint.opacity(0.18)))
                        Text(item.title).foregroundStyle(Theme.ink)
                        Spacer()
                        Text(item.value).foregroundStyle(tone.tertiary).lineLimit(1)
                        Image(systemName: "chevron.right").font(.system(size: 12)).foregroundStyle(tone.tertiary)
                    }
                    .font(.system(size: 16))
                    .frame(minHeight: 50)
                    .padding(.horizontal, 12)
                }
                .buttonStyle(.plain)
            }
        }
        .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Theme.card.opacity(0.55)))
    }

    private func row(_ route: SettingsRoute, _ symbol: String, _ tint: Color, _ value: String, title: String? = nil) -> SettingsLink {
        SettingsLink(route: route, title: title ?? route.title, symbol: symbol, tint: tint, value: value)
    }
}

private struct SettingsLink: Identifiable {
    var route: SettingsRoute
    var title: String
    var symbol: String
    var tint: Color
    var value: String
    var id: String { title }
}

struct SettingsPage: View {
    var route: SettingsRoute
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                switch route {
                case .pc:
                    ConnectionView(done: nil, embedded: true)
                    Button("Unpair", role: .destructive) { model.unpair() }
                        .frame(maxWidth: .infinity, minHeight: 44)
                case .recording:
                    recording
                case .games:
                    Text("\(model.studio?.games.count ?? 0) games are classified on Studio PC.")
                        .foregroundStyle(Theme.ink2)
                    Button("Open Games") {
                        model.settingsPresented = false
                        model.requestedTab = .games
                    }
                    .foregroundStyle(Theme.violetLight)
                case .hotkey:
                    Text("The hotkey is \(model.studio?.settings.hotkey.isEmpty == false ? model.studio?.settings.hotkey ?? "set on Studio PC" : "set on Studio PC"). Change it on Studio PC.")
                        .foregroundStyle(Theme.ink2)
                case .sync:
                    NebulaSegments(
                        options: [("none", "Off"), ("onedrive", "OneDrive")],
                        selection: model.studio?.settings.syncProvider ?? "none"
                    ) { model.setSetting("gameListSync.provider", $0) }
                    if !(model.studio?.settings.syncPath ?? "").isEmpty {
                        Text(model.studio?.settings.syncPath ?? "")
                            .font(.system(size: 12, design: .monospaced))
                            .foregroundStyle(tone.tertiary)
                    }
                case .offload:
                    Toggle("Copy new clips automatically", isOn: Binding(
                        get: { model.studio?.settings.offloadAuto ?? false },
                        set: { model.setSetting("offload.auto", $0) }
                    ))
                    .tint(Theme.teal)
                    Text(model.studio?.settings.offloadTarget.map { "Target \($0)" } ?? "No NAS target yet.")
                        .foregroundStyle(tone.tertiary)
                case .remote:
                    Text(model.studio?.settings.tailscale == true ? "Tailscale is on." : "Tailscale isn’t reported.")
                        .foregroundStyle(Theme.ink2)
                    Text(model.studio?.settings.moonlightInstalled == true ? "Moonlight is installed on Studio PC." : "Moonlight isn’t reported on Studio PC.")
                        .foregroundStyle(tone.tertiary)
                case .appearance:
                    appearance
                case .notifications:
                    Text("A push relay isn’t set up yet. While Nebula is open, a new app still asks “Is this a game?” on this phone.")
                        .foregroundStyle(Theme.ink2)
                case .updates:
                    Text(model.studio?.settings.appVersion.isEmpty == false ? "Studio PC is on \(model.studio?.settings.appVersion ?? "")." : "Studio PC hasn’t sent a version.")
                        .foregroundStyle(Theme.ink2)
                    if let update = model.studio?.settings.updateAvailable {
                        Text("Update available \(update)")
                            .foregroundStyle(Theme.violetLight)
                        Text("Starting that update from the phone isn’t wired yet.")
                            .foregroundStyle(tone.tertiary)
                    }
                }
            }
            .padding(20)
        }
        .background(Theme.ground)
        .navigationTitle(route.title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if route == .recording || route == .appearance || route == .offload || route == .sync {
                ToolbarItem(placement: .topBarTrailing) {
                    if model.savedFlash {
                        Text("Saved").foregroundStyle(Theme.teal).font(.system(size: 15, weight: .semibold))
                    }
                }
            }
        }
    }

    private var recording: some View {
        let settings = model.studio?.settings
        return VStack(alignment: .leading, spacing: 18) {
            Text("When a game launches")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(Theme.ink)
            NebulaSegments(
                options: [("record", "Record"), ("buffer", "Buffer"), ("both", "Both")],
                selection: settings?.launchCapture ?? "record"
            ) { model.setSetting("launchCapture", $0) }
            Text(launchCopy(settings?.launchCapture ?? "record"))
                .font(.system(size: 14))
                .foregroundStyle(tone.tertiary)
            Text("Instant replay length")
                .font(.system(size: 15, weight: .semibold))
            NebulaSegments(
                options: [("15", "15 s"), ("30", "30 s"), ("60", "60 s"), ("120", "2 min")],
                selection: String(settings?.replaySeconds ?? 30)
            ) { model.setSetting("replaySeconds", Int($0) ?? 30) }
            stepper("Pause when idle", value: settings?.idleTimeout ?? 4, range: 1 ... 60, step: 1, suffix: "s") {
                model.setSetting("idleTimeout", $0)
            }
            stepper("Discard clips under", value: settings?.discardUnder ?? 0, range: 0 ... 120, step: 5, suffix: "s", zero: "Off") {
                model.setSetting("discardUnder", $0)
            }
            Text("Keep recording while these play audio")
                .font(.system(size: 15, weight: .semibold))
            keepAlive
            Text("Recording folder")
                .font(.system(size: 15, weight: .semibold))
            Text(settings?.recordingRoot.isEmpty == false ? settings?.recordingRoot ?? "Set on Studio PC" : "Set on Studio PC")
                .font(.system(size: 12, design: .monospaced))
                .foregroundStyle(tone.tertiary)
            Text("Set on Studio PC")
                .font(.system(size: 13))
                .foregroundStyle(tone.tertiary)
        }
    }

    private var keepAlive: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(model.studio?.settings.keepAliveApps ?? [], id: \.self) { app in
                Text(app)
                    .font(.system(size: 13, design: .monospaced))
                    .foregroundStyle(Theme.tealPale)
                    .padding(.horizontal, 10)
                    .frame(minHeight: 32)
                    .background(Capsule().fill(Theme.teal.opacity(0.15)))
            }
            AddAppField { name in
                var apps = model.studio?.settings.keepAliveApps ?? []
                guard !apps.contains(name) else { return }
                apps.append(name)
                model.setSetting("keepAliveApps", apps)
            }
            Text("Type an exe name. Studio PC hasn’t sent the live audio list.")
                .font(.system(size: 13))
                .foregroundStyle(tone.tertiary)
        }
    }

    private var appearance: some View {
        VStack(alignment: .leading, spacing: 16) {
            Eyebrow(text: "Background · live behind every tab", color: tone.tertiary)
            let columns = [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)]
            LazyVGrid(columns: columns, spacing: 8) {
                ForEach(BackgroundKind.allCases) { kind in
                    Button {
                        model.updatePrefs { $0.background = kind }
                    } label: {
                        BackgroundView(kind: kind, seed: model.prefs.planetSeed, live: kind == model.prefs.background && !model.prefs.still && !tone.reduceMotion)
                            .frame(height: 150)
                            .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                            .overlay(
                                RoundedRectangle(cornerRadius: 20, style: .continuous)
                                    .stroke(model.prefs.background == kind ? Theme.violet : Color.clear, lineWidth: 2)
                            )
                            .overlay(alignment: .bottomLeading) {
                                Text(kind.title)
                                    .font(.system(size: 12, weight: .semibold))
                                    .foregroundStyle(Theme.ink)
                                    .padding(8)
                            }
                    }
                    .buttonStyle(.plain)
                }
            }
            labelled("Motion") {
                NebulaSegments(options: [("live", "Live"), ("still", "Still")], selection: model.prefs.motion) { choice in
                    model.updatePrefs { prefs in prefs.motion = choice }
                }
            }
            labelled("Random planet") {
                HStack {
                    Text(PlanetName.make(model.prefs.planetSeed))
                        .foregroundStyle(Theme.ink)
                    Spacer()
                    Button("Reroll") {
                        model.updatePrefs {
                            $0.planetSeed = Int.random(in: 1 ... 9_999)
                            $0.background = .proc
                        }
                    }
                    .foregroundStyle(Theme.violetLight)
                }
            }
            labelled("Surfaces") {
                NebulaSegments(
                    options: SurfaceStyle.allCases.map { ($0.rawValue, $0.title) },
                    selection: model.prefs.surfaces.rawValue
                ) { value in
                    if let style = SurfaceStyle(rawValue: value) {
                        model.updatePrefs { $0.surfaces = style }
                    }
                }
            }
            labelled("Now layout") {
                NebulaSegments(
                    options: NowLayout.allCases.map { ($0.rawValue, $0.title) },
                    selection: model.prefs.nowLayout.rawValue
                ) { value in
                    if let layout = NowLayout(rawValue: value) {
                        model.updatePrefs { $0.nowLayout = layout }
                    }
                }
            }
        }
    }

    private func labelled<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.system(size: 15, weight: .semibold)).foregroundStyle(Theme.ink)
            content()
        }
    }

    private func launchCopy(_ mode: String) -> String {
        switch mode {
        case "buffer": "Nebula keeps a replay buffer and saves a clip only when you ask."
        case "both": "Nebula records a file and keeps a replay buffer."
        default: "Nebula starts a file when a game launches."
        }
    }

    private func stepper(_ title: String, value: Int, range: ClosedRange<Int>, step: Int, suffix: String, zero: String? = nil, write: @escaping (Int) -> Void) -> some View {
        StepperRow(title: title, value: value, range: range, step: step, suffix: suffix, zero: zero, write: write)
    }
}

private struct StepperRow: View {
    var title: String
    var value: Int
    var range: ClosedRange<Int>
    var step: Int
    var suffix: String
    var zero: String?
    var write: (Int) -> Void
    @State private var draft: Int = 0
    @State private var task: Task<Void, Never>?

    var body: some View {
        HStack {
            VStack(alignment: .leading) {
                Text(title).foregroundStyle(Theme.ink)
                Text(label).font(.system(size: 13)).foregroundStyle(Theme.ink3)
            }
            Spacer()
            Button("–") { bump(-step) }.frame(width: 44, height: 44)
            Button("+") { bump(step) }.frame(width: 44, height: 44)
        }
        .onAppear { draft = value }
        .onChange(of: value) { _, next in draft = next }
    }

    private var label: String {
        if draft == 0, let zero { return zero }
        return "\(draft) \(suffix)"
    }

    private func bump(_ delta: Int) {
        let next = min(range.upperBound, max(range.lowerBound, draft + delta))
        draft = next
        task?.cancel()
        task = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 600_000_000)
            guard !Task.isCancelled else { return }
            write(next)
        }
    }
}

private struct AddAppField: View {
    var add: (String) -> Void
    @State private var text = ""

    var body: some View {
        HStack {
            TextField("app.exe", text: $text)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
            Button("+ Add app") {
                let name = text.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !name.isEmpty else { return }
                add(name)
                text = ""
            }
            .foregroundStyle(Theme.teal)
        }
        .frame(minHeight: 44)
    }
}
