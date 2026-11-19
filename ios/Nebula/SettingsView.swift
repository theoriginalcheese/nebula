import SwiftUI

struct SettingsRoot: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    @State private var path: [SettingsRoute] = []

    var body: some View {
        ZStack {
            BackgroundView(
                kind: model.prefs.background,
                seed: model.prefs.planetSeed,
                live: model.active && !tone.isStill && !ProcessInfo.processInfo.isLowPowerModeEnabled
            )

            NavigationStack(path: $path) {
                ScrollView {
                    VStack(alignment: .leading, spacing: Theme.Space.sectionGap) {
                        rootHeader
                            .padding(.horizontal, Theme.Space.headerInset)

                        pcTray

                        settingsGroup(
                            rows: [
                                SettingsLink(
                                    route: .recording,
                                    title: "Recording",
                                    symbol: "folder",
                                    iconFill: Theme.violet.opacity(0.18),
                                    iconStroke: Theme.violetPale,
                                    value: model.studio?.settings.launchLabel ?? "—",
                                    valueColor: nil
                                ),
                                SettingsLink(
                                    route: .recording,
                                    title: "Instant replay",
                                    symbol: "clock.arrow.circlepath",
                                    iconFill: Theme.violet.opacity(0.18),
                                    iconStroke: Theme.violetPale,
                                    value: model.studio?.settings.replayLabel ?? "—",
                                    valueColor: nil
                                ),
                                SettingsLink(
                                    route: .games,
                                    title: "Games & detection",
                                    symbol: "gamecontroller",
                                    iconFill: Theme.violet.opacity(0.18),
                                    iconStroke: Theme.violetPale,
                                    value: model.studio.map { "\($0.games.count) games" } ?? "—",
                                    valueColor: nil
                                ),
                                SettingsLink(
                                    route: .hotkey,
                                    title: "Hotkey",
                                    symbol: "keyboard",
                                    iconFill: Theme.violet.opacity(0.18),
                                    iconStroke: Theme.violetPale,
                                    value: nonEmpty(model.studio?.settings.hotkey),
                                    valueColor: nil
                                ),
                            ]
                        )

                        settingsGroup(
                            rows: [
                                SettingsLink(
                                    route: .sync,
                                    title: "Game list sync",
                                    symbol: "icloud",
                                    iconFill: Theme.teal.opacity(0.16),
                                    iconStroke: Theme.tealPale,
                                    value: syncLabel,
                                    valueColor: nil
                                ),
                                SettingsLink(
                                    route: .offload,
                                    title: "Offload to NAS",
                                    symbol: "externaldrive",
                                    iconFill: Theme.teal.opacity(0.16),
                                    iconStroke: Theme.tealPale,
                                    value: nonEmpty(model.studio?.settings.offloadTarget),
                                    valueColor: nil
                                ),
                                SettingsLink(
                                    route: .remote,
                                    title: "Remote streaming",
                                    symbol: "play.tv",
                                    iconFill: Theme.teal.opacity(0.16),
                                    iconStroke: Theme.tealPale,
                                    value: model.studio?.settings.tailscale == true ? "Tailscale" : "—",
                                    valueColor: nil
                                ),
                            ]
                        )

                        settingsGroup(
                            rows: [
                                SettingsLink(
                                    route: .appearance,
                                    title: "Appearance",
                                    symbol: "paintpalette",
                                    iconFill: Theme.amberDeep.opacity(0.16),
                                    iconStroke: Theme.amberPale,
                                    value: model.prefs.background.title,
                                    valueColor: nil
                                ),
                                SettingsLink(
                                    route: .notifications,
                                    title: "Notifications",
                                    symbol: "bell",
                                    iconFill: Theme.amberDeep.opacity(0.16),
                                    iconStroke: Theme.amberPale,
                                    value: "On",
                                    valueColor: nil
                                ),
                                SettingsLink(
                                    route: .updates,
                                    title: "Updates",
                                    symbol: "arrow.triangle.2.circlepath",
                                    iconFill: Theme.amberDeep.opacity(0.16),
                                    iconStroke: Theme.amberPale,
                                    value: updatesValue,
                                    valueColor: model.studio?.settings.updateAvailable != nil ? Theme.violetLight : nil
                                ),
                            ]
                        )
                    }
                    .padding(.horizontal, Theme.Space.screenMargin)
                    .padding(.top, 18)
                    .padding(.bottom, 36)
                }
                .scrollContentBackground(.hidden)
                .toolbar(.hidden, for: .navigationBar)
                .navigationDestination(for: SettingsRoute.self) { route in
                    SettingsPage(route: route)
                }
            }
        }
        .background(Theme.ground.ignoresSafeArea())
        .onAppear {
            if let route = model.settingsRoute {
                path = [route]
                model.settingsRoute = nil
            }
        }
    }

    private var rootHeader: some View {
        HStack(alignment: .center) {
            Text("Settings")
                .font(Theme.TypeScale.largeTitle)
                .tracking(Theme.TypeScale.largeTitleTracking)
                .foregroundStyle(Theme.ink)
            Spacer()
            Button {
                model.settingsPresented = false
            } label: {
                Text("Done")
                    .font(Theme.TypeScale.controlSemibold)
                    .foregroundStyle(Theme.violetLight)
                    .padding(.horizontal, 14)
                    .frame(minHeight: Theme.Size.minHitTarget)
            }
            .buttonStyle(.plain)
        }
    }

    private var pcTray: some View {
        let obsDisconnected = model.link == .online && model.studio?.obsConnected == false
        let online = model.link == .online
        let statusColor: Color = !online ? tone.tertiary : (obsDisconnected ? Theme.coral : Theme.teal)

        return Button {
            path.append(.pc)
        } label: {
            Tray(role: .tile) {
                ReadingSurface(radius: Theme.Radius.tileCard, kind: .hero) {
                    HStack(spacing: Theme.Space.sectionGap) {
                        ZStack {
                            Circle()
                                .fill(Theme.violet.opacity(0.14))
                                .overlay(Circle().stroke(Theme.violet.opacity(0.30), lineWidth: Theme.Stroke.hairline))
                            NebulaMark(size: 26)
                        }
                        .frame(width: Theme.Size.settingsPCBadge, height: Theme.Size.settingsPCBadge)

                        VStack(alignment: .leading, spacing: 2) {
                            Text("Studio PC")
                                .font(Theme.TypeScale.cardTitle)
                                .foregroundStyle(Theme.ink)
                            HStack(spacing: 6) {
                                Circle()
                                    .fill(statusColor)
                                    .frame(width: 6, height: 6)
                                Text(pcStatusText)
                                    .font(Theme.TypeScale.subtitle)
                                    .foregroundStyle(statusColor)
                            }
                        }

                        Spacer()

                        Image(systemName: "chevron.right")
                            .font(Theme.TypeScale.icon(14, weight: .semibold))
                            .foregroundStyle(tone.tertiary)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 14)
                }
            }
        }
        .buttonStyle(PressScaleStyle())
    }

    private var pcStatusText: String {
        if model.link != .online { return "Offline" }
        if model.studio?.obsConnected == false { return "OBS disconnected" }
        return "Paired · OBS connected"
    }

    private var syncLabel: String {
        guard let provider = model.studio?.settings.syncProvider else { return "—" }
        switch provider {
        case "onedrive":
            return "OneDrive"
        case "none":
            return "Off"
        default:
            return provider.isEmpty ? "—" : provider
        }
    }

    private var updatesValue: String {
        if model.studio?.settings.updateAvailable != nil {
            return "Update available"
        }
        return nonEmpty(model.studio?.settings.appVersion)
    }

    private func nonEmpty(_ text: String?) -> String {
        guard let text = text, !text.isEmpty else { return "—" }
        return text
    }

    private func settingsGroup(rows: [SettingsLink]) -> some View {
        ReadingSurface(radius: Theme.Radius.settingsGroup) {
            VStack(spacing: 0) {
                ForEach(Array(rows.enumerated()), id: \.element.id) { index, item in
                    if index > 0 {
                        GroupDivider()
                    }
                    Button {
                        path.append(item.route)
                    } label: {
                        HStack(spacing: Theme.Space.bentoGap) {
                            ZStack {
                                RoundedRectangle(cornerRadius: Theme.Radius.settingsIcon, style: .continuous)
                                    .fill(item.iconFill)
                                Image(systemName: item.symbol)
                                    .font(Theme.TypeScale.icon(15, weight: .regular))
                                    .foregroundStyle(item.iconStroke)
                            }
                            .frame(width: Theme.Size.settingsIconBox, height: Theme.Size.settingsIconBox)

                            Text(item.title)
                                .font(Theme.TypeScale.rowLabel)
                                .foregroundStyle(Theme.ink)
                                .lineLimit(1)

                            Spacer(minLength: 6)

                            Text(item.value)
                                .font(Theme.TypeScale.rowValue)
                                .foregroundStyle(item.valueColor ?? tone.tertiary)
                                .lineLimit(1)

                            Image(systemName: "chevron.right")
                                .font(Theme.TypeScale.icon(12, weight: .semibold))
                                .foregroundStyle(Theme.inkMuted)
                        }
                        .frame(minHeight: Theme.Size.settingsRowHeight)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 14)
        }
    }
}

private struct SettingsLink: Identifiable {
    var route: SettingsRoute
    var title: String
    var symbol: String
    var iconFill: Color
    var iconStroke: Color
    var value: String
    var valueColor: Color?

    var id: String { return title }
}

// MARK: - Settings Sub-Pages (3g Appearance, 3h Recording, Studio PC, Sync, Offload, etc.)

struct SettingsPage: View {
    var route: SettingsRoute
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            BackgroundView(
                kind: model.prefs.background,
                seed: model.prefs.planetSeed,
                live: model.active && !tone.isStill && !ProcessInfo.processInfo.isLowPowerModeEnabled
            )

            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Space.sectionGap) {
                    subpageHeader

                    switch route {
                    case .pc:
                        pcSubpage
                    case .recording:
                        recordingSubpage
                    case .appearance:
                        appearanceSubpage
                    case .games:
                        gamesSubpage
                    case .hotkey:
                        hotkeySubpage
                    case .sync:
                        syncSubpage
                    case .offload:
                        offloadSubpage
                    case .remote:
                        remoteSubpage
                    case .notifications:
                        notificationsSubpage
                    case .updates:
                        updatesSubpage
                    }
                }
                .padding(.horizontal, Theme.Space.screenMargin)
                .padding(.top, 10)
                .padding(.bottom, 36)
            }
            .scrollContentBackground(.hidden)
        }
        .background(Theme.ground.ignoresSafeArea())
        .toolbar(.hidden, for: .navigationBar)
    }

    private var subpageHeader: some View {
        HStack(alignment: .center) {
            Button {
                dismiss()
            } label: {
                HStack(spacing: 3) {
                    Image(systemName: "chevron.left")
                        .font(Theme.TypeScale.icon(17, weight: .semibold))
                    Text("Settings")
                        .font(Theme.TypeScale.navInlineAction)
                }
                .foregroundStyle(Theme.violetLight)
                .frame(minWidth: 84, minHeight: Theme.Size.minHitTarget, alignment: .leading)
            }
            .buttonStyle(.plain)

            Spacer()

            Text(route.title)
                .font(Theme.TypeScale.cardTitle)
                .foregroundStyle(Theme.ink)
                .lineLimit(1)

            Spacer()

            ZStack(alignment: .trailing) {
                if model.savedFlash && showsSavedIndicator {
                    Text("Saved")
                        .font(Theme.TypeScale.subtitle)
                        .foregroundStyle(Theme.teal)
                        .transition(.opacity)
                }
            }
            .frame(width: 84, height: Theme.Size.minHitTarget, alignment: .trailing)
            .animation(tone.motion, value: model.savedFlash)
        }
    }

    private var showsSavedIndicator: Bool {
        switch route {
        case .recording, .sync, .offload, .appearance:
            return true
        default:
            return false
        }
    }

    // MARK: - 3h: Settings > Recording (§9.9)

    private var recordingSubpage: some View {
        let settings = model.studio?.settings
        let launch = settings?.launchCapture ?? "record"
        let folder = (settings?.recordingRoot.isEmpty == false ? settings?.recordingRoot : nil) ?? "—"

        return VStack(alignment: .leading, spacing: 10) {
            Eyebrow(text: "When a game launches", color: Theme.ink2)
                .padding(.horizontal, 8)

            ReadingSurface(radius: Theme.Radius.settingsGroup) {
                VStack(alignment: .leading, spacing: 10) {
                    NebulaSegments(
                        options: [
                            ("record", "Record"),
                            ("buffer", "Buffer"),
                            ("both", "Both"),
                        ],
                        selection: launch
                    ) { next in
                        model.setSetting("launchCapture", next)
                    }
                    Text(launchExplanation(launch))
                        .font(Theme.TypeScale.subtitle)
                        .foregroundStyle(tone.tertiary)
                }
                .padding(14)
            }

            Eyebrow(text: "Instant replay length", color: Theme.ink2)
                .padding(.horizontal, 8)
                .padding(.top, 4)

            ReadingSurface(radius: Theme.Radius.settingsGroup) {
                NebulaSegments(
                    options: [
                        ("15", "15 s"),
                        ("30", "30 s"),
                        ("60", "60 s"),
                        ("120", "2 min"),
                    ],
                    selection: String(settings?.replaySeconds ?? 30)
                ) { next in
                    model.setSetting("replaySeconds", Int(next) ?? 30)
                }
                .padding(14)
            }

            Eyebrow(text: "Auto-pause & cleanup", color: Theme.ink2)
                .padding(.horizontal, 8)
                .padding(.top, 4)

            ReadingSurface(radius: Theme.Radius.settingsGroup) {
                VStack(alignment: .leading, spacing: 0) {
                    MachinedStepperRow(
                        title: "Pause when idle",
                        subtitle: "No input for this long",
                        value: settings?.idleTimeout ?? 4,
                        range: 1 ... 60,
                        step: 1,
                        suffix: "s",
                        zeroLabel: nil
                    ) { next in
                        model.setSetting("idleTimeout", next)
                    }

                    GroupDivider()

                    MachinedStepperRow(
                        title: "Discard clips under",
                        subtitle: "Deletes accidental flickers",
                        value: settings?.discardUnder ?? 0,
                        range: 0 ... 120,
                        step: 5,
                        suffix: "s",
                        zeroLabel: "Off"
                    ) { next in
                        model.setSetting("discardUnder", next)
                    }

                    GroupDivider()

                    KeepAliveAudioSection(apps: settings?.keepAliveApps ?? []) { updated in
                        model.setSetting("keepAliveApps", updated)
                    }
                }
                .padding(.horizontal, 14)
            }

            ReadingSurface(radius: Theme.Radius.settingsGroup) {
                HStack(spacing: Theme.Space.bentoGap) {
                    Text("Recording folder")
                        .font(Theme.TypeScale.rowLabel)
                        .foregroundStyle(Theme.ink)
                    Spacer(minLength: 8)
                    Text("\(folder) · set on PC")
                        .font(Theme.TypeScale.mono)
                        .foregroundStyle(tone.tertiary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                .padding(.horizontal, 14)
                .frame(minHeight: Theme.Size.folderRowHeight)
            }
        }
    }

    private func launchExplanation(_ mode: String) -> String {
        switch mode {
        case "buffer":
            return "Keeps a rolling instant-replay buffer; save the last moments with the hotkey."
        case "both":
            return "Records in full and keeps the replay buffer running alongside."
        default:
            return "Starts a full recording into the game’s folder as soon as it’s detected."
        }
    }

    // MARK: - 3g: Settings > Appearance (§9.10)

    private var appearanceSubpage: some View {
        VStack(alignment: .leading, spacing: Theme.Space.sectionGap) {
            Eyebrow(text: "Background · live behind every tab", color: Theme.ink2)
                .padding(.horizontal, 8)

            AppearanceGrid(
                selected: model.prefs.background,
                seed: model.prefs.planetSeed,
                still: tone.isStill
            ) { kind in
                withAnimation(tone.motion) {
                    model.updatePrefs { $0.background = kind }
                }
            }

            ReadingSurface(radius: Theme.Radius.settingsGroup) {
                VStack(spacing: 0) {
                    HStack {
                        Text("Motion")
                            .font(Theme.TypeScale.rowLabel)
                            .foregroundStyle(Theme.ink)
                        Spacer()
                        NebulaSegments(
                            options: [("live", "Live"), ("still", "Still")],
                            selection: model.prefs.motion,
                            compact: true
                        ) { choice in
                            model.updatePrefs { $0.motion = choice }
                        }
                        .frame(width: 170)
                    }
                    .frame(minHeight: Theme.Size.settingsRowHeight)

                    GroupDivider()

                    HStack {
                        Text("Random planet")
                            .font(Theme.TypeScale.rowLabel)
                            .foregroundStyle(Theme.ink)
                        Spacer()
                        Button {
                            withAnimation(tone.motion) {
                                model.updatePrefs {
                                    $0.planetSeed = ($0.planetSeed % 9_999) + 1
                                    $0.background = .proc
                                }
                            }
                        } label: {
                            HStack(spacing: 8) {
                                Text("Reroll")
                                    .font(Theme.TypeScale.segment)
                                    .foregroundStyle(Theme.ink)
                                Text(PlanetName.make(model.prefs.planetSeed))
                                    .font(Theme.TypeScale.captionSemibold)
                                    .foregroundStyle(Theme.violetPale)
                                    .padding(.horizontal, 9)
                                    .frame(height: Theme.Size.badgeChipHeight)
                                    .background(Capsule().fill(Theme.violet.opacity(0.16)))
                            }
                            .padding(.leading, 12)
                            .padding(.trailing, 4)
                            .frame(height: Theme.Size.rerollPillHeight)
                            .background(Capsule().fill(Theme.ink.opacity(0.06)))
                            .frame(minHeight: Theme.Size.minHitTarget)
                        }
                        .buttonStyle(PressScaleStyle())
                    }
                    .frame(minHeight: Theme.Size.settingsRowHeight)
                }
                .padding(.horizontal, 14)
            }

            ReadingSurface(radius: Theme.Radius.settingsGroup) {
                VStack(alignment: .leading, spacing: 12) {
                    VStack(alignment: .leading, spacing: 8) {
                        Eyebrow(text: "Surfaces", color: Theme.ink2)
                        NebulaSegments(
                            options: SurfaceStyle.allCases.map { ($0.rawValue, $0.title) },
                            selection: model.prefs.surfaces.rawValue
                        ) { value in
                            if let style = SurfaceStyle(rawValue: value) {
                                model.updatePrefs { $0.surfaces = style }
                            }
                        }
                    }

                    GroupDivider()

                    VStack(alignment: .leading, spacing: 8) {
                        Eyebrow(text: "Now layout", color: Theme.ink2)
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
                .padding(14)
            }
        }
    }

    // MARK: - Other Settings Sub-Pages

    private var pcSubpage: some View {
        VStack(alignment: .leading, spacing: Theme.Space.sectionGap) {
            ConnectionView(done: nil, embedded: true)

            Button {
                model.unpair()
            } label: {
                Text("Unpair Studio PC")
                    .font(Theme.TypeScale.rowTitle)
                    .foregroundStyle(Theme.coralSoft)
                    .frame(maxWidth: .infinity, minHeight: Theme.Size.ghostHeight)
                    .background(
                        RoundedRectangle(cornerRadius: Theme.Radius.ghostPill, style: .continuous)
                            .fill(Theme.coral.opacity(0.12))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: Theme.Radius.ghostPill, style: .continuous)
                            .stroke(Theme.coral.opacity(0.35), lineWidth: Theme.Stroke.hairline)
                    )
            }
            .buttonStyle(PressScaleStyle())
        }
    }

    private var gamesSubpage: some View {
        VStack(alignment: .leading, spacing: Theme.Space.sectionGap) {
            ReadingSurface(radius: Theme.Radius.settingsGroup) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("\(model.studio?.games.count ?? 0) games classified on Studio PC")
                        .font(Theme.TypeScale.rowTitle)
                        .foregroundStyle(Theme.ink)
                    Text("Steam library installs auto-classify. Unknown fullscreen apps trigger a one-time prompt on your PC and this phone.")
                        .font(Theme.TypeScale.rowValue)
                        .foregroundStyle(Theme.ink2)
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            PrimaryPill(title: "Open Games", system: "gamecontroller") {
                model.settingsPresented = false
                model.requestedTab = .games
            }
        }
    }

    private var hotkeySubpage: some View {
        let key = (model.studio?.settings.hotkey.isEmpty == false ? model.studio?.settings.hotkey : nil) ?? "—"
        return ReadingSurface(radius: Theme.Radius.settingsGroup) {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("Toggle monitoring")
                        .font(Theme.TypeScale.rowLabel)
                        .foregroundStyle(Theme.ink)
                    Spacer()
                    Text(key)
                        .font(Theme.TypeScale.monoFolder)
                        .foregroundStyle(Theme.violetPale)
                        .padding(.horizontal, 10)
                        .frame(height: Theme.Size.tagChipHeight)
                        .background(Capsule().fill(Theme.violet.opacity(0.16)))
                }
                Text("Keyboard shortcuts are bound to Studio PC’s low-level input hook and are configured on the desktop.")
                    .font(Theme.TypeScale.subtitle)
                    .foregroundStyle(tone.tertiary)
            }
            .padding(16)
        }
    }

    private var syncSubpage: some View {
        VStack(alignment: .leading, spacing: Theme.Space.bentoGap) {
            ReadingSurface(radius: Theme.Radius.settingsGroup) {
                VStack(alignment: .leading, spacing: 10) {
                    Eyebrow(text: "Provider", color: Theme.ink2)
                    NebulaSegments(
                        options: [("none", "Off"), ("onedrive", "OneDrive")],
                        selection: model.studio?.settings.syncProvider ?? "none"
                    ) { next in
                        model.setSetting("gameListSync.provider", next)
                    }
                    if let syncPath = model.studio?.settings.syncPath, !syncPath.isEmpty {
                        GroupDivider()
                        HStack {
                            Text("Path")
                                .font(Theme.TypeScale.rowValue)
                                .foregroundStyle(Theme.ink2)
                            Spacer()
                            Text(syncPath)
                                .font(Theme.TypeScale.mono)
                                .foregroundStyle(tone.tertiary)
                                .lineLimit(1)
                                .truncationMode(.middle)
                        }
                        .padding(.top, 2)
                    }
                }
                .padding(14)
            }
        }
    }

    private var offloadSubpage: some View {
        let auto = model.studio?.settings.offloadAuto ?? false
        let target = (model.studio?.settings.offloadTarget?.isEmpty == false ? model.studio?.settings.offloadTarget : nil) ?? "—"

        return ReadingSurface(radius: Theme.Radius.settingsGroup) {
            VStack(spacing: 0) {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Offload automatically")
                            .font(Theme.TypeScale.rowLabel)
                            .foregroundStyle(Theme.ink)
                        Text("SHA-256 verifies before removing local copy")
                            .font(Theme.TypeScale.caption)
                            .foregroundStyle(tone.tertiary)
                    }
                    Spacer()
                    NebulaSwitch(isOn: auto) { next in
                        model.setSetting("offload.auto", next)
                    }
                }
                .frame(minHeight: Theme.Size.stepperRowHeight)

                GroupDivider()

                HStack {
                    Text("NAS target")
                        .font(Theme.TypeScale.rowLabel)
                        .foregroundStyle(Theme.ink)
                    Spacer()
                    Text("\(target) · set on PC")
                        .font(Theme.TypeScale.mono)
                        .foregroundStyle(tone.tertiary)
                        .lineLimit(1)
                }
                .frame(minHeight: Theme.Size.settingsRowHeight)
            }
            .padding(.horizontal, 14)
        }
    }

    private var remoteSubpage: some View {
        ReadingSurface(radius: Theme.Radius.settingsGroup) {
            VStack(spacing: 0) {
                HStack {
                    Text("Tailscale")
                        .font(Theme.TypeScale.rowLabel)
                        .foregroundStyle(Theme.ink)
                    Spacer()
                    Text(model.studio?.settings.tailscale == true ? "Connected" : "—")
                        .font(Theme.TypeScale.rowValue)
                        .foregroundStyle(model.studio?.settings.tailscale == true ? Theme.teal : tone.tertiary)
                }
                .frame(minHeight: Theme.Size.settingsRowHeight)

                GroupDivider()

                HStack {
                    Text("Moonlight host")
                        .font(Theme.TypeScale.rowLabel)
                        .foregroundStyle(Theme.ink)
                    Spacer()
                    Text(model.studio?.settings.moonlightInstalled == true ? "Installed" : "—")
                        .font(Theme.TypeScale.rowValue)
                        .foregroundStyle(model.studio?.settings.moonlightInstalled == true ? Theme.teal : tone.tertiary)
                }
                .frame(minHeight: Theme.Size.settingsRowHeight)
            }
            .padding(.horizontal, 14)
        }
    }

    private var notificationsSubpage: some View {
        ReadingSurface(radius: Theme.Radius.settingsGroup) {
            VStack(alignment: .leading, spacing: 8) {
                Text("In-app prompts are active")
                    .font(Theme.TypeScale.rowTitle)
                    .foregroundStyle(Theme.ink)
                Text("While Nebula is foregrounded, unknown fullscreen apps on Studio PC immediately present the “Is this a game?” sheet.")
                    .font(Theme.TypeScale.rowValue)
                    .foregroundStyle(Theme.ink2)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var updatesSubpage: some View {
        let ver = (model.studio?.settings.appVersion.isEmpty == false ? model.studio?.settings.appVersion : nil) ?? "—"
        return ReadingSurface(radius: Theme.Radius.settingsGroup) {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("Studio PC version")
                        .font(Theme.TypeScale.rowLabel)
                        .foregroundStyle(Theme.ink)
                    Spacer()
                    Text(ver)
                        .font(Theme.TypeScale.monoFolder)
                        .foregroundStyle(Theme.ink2)
                }
                if let update = model.studio?.settings.updateAvailable, !update.isEmpty {
                    GroupDivider()
                    HStack {
                        Text("Available")
                            .font(Theme.TypeScale.rowLabel)
                            .foregroundStyle(Theme.ink)
                        Spacer()
                        Text(update)
                            .font(Theme.TypeScale.segment)
                            .foregroundStyle(Theme.violetLight)
                    }
                }
            }
            .padding(16)
        }
    }
}

// MARK: - 3g Appearance 3×3 Live Grid (§9.10: Selected Animates @ 20fps, Others Rotate 1-per-Frame)

private struct AppearanceGrid: View {
    var selected: BackgroundKind
    var seed: Int
    var still: Bool
    var onSelect: (BackgroundKind) -> Void

    @Environment(\.tone) private var tone
    @State private var tickCount: Int = 0
    @State private var tileTimes: [BackgroundKind: TimeInterval] = [:]

    var body: some View {
        let kinds = BackgroundKind.allCases
        let columns = [
            GridItem(.flexible(), spacing: Theme.Space.gridGap),
            GridItem(.flexible(), spacing: Theme.Space.gridGap),
            GridItem(.flexible(), spacing: Theme.Space.gridGap),
        ]

        TimelineView(.periodic(from: .now, by: still ? 60.0 : (1.0 / 18.0))) { context in
            let now = still ? 20.0 : context.date.timeIntervalSinceReferenceDate
            LazyVGrid(columns: columns, spacing: Theme.Space.gridGap) {
                ForEach(Array(kinds.enumerated()), id: \.element.id) { idx, kind in
                    let isSelected = kind == selected
                    let displayTime = isSelected ? now : (tileTimes[kind] ?? 20.0)

                    Button {
                        onSelect(kind)
                    } label: {
                        VStack(alignment: .leading, spacing: 6) {
                            ZStack(alignment: .topTrailing) {
                                BackgroundTilePreview(
                                    kind: kind,
                                    seed: seed,
                                    time: displayTime
                                )
                                .frame(height: Theme.Size.appearanceTileHeight)
                                .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.appearanceTile, style: .continuous))
                                .overlay(
                                    RoundedRectangle(cornerRadius: Theme.Radius.appearanceTile, style: .continuous)
                                        .stroke(
                                            isSelected ? Theme.violet : Theme.ink.opacity(0.10),
                                            lineWidth: isSelected ? Theme.Stroke.selectedTile : Theme.Stroke.hairline
                                        )
                                )
                                .shadow(color: isSelected ? Theme.violet.opacity(0.35) : Theme.clear, radius: 11)

                                if isSelected {
                                    ZStack {
                                        Circle()
                                            .fill(Theme.violet)
                                        Image(systemName: "checkmark")
                                            .font(Theme.TypeScale.icon(11, weight: .bold))
                                            .foregroundStyle(Theme.inkDark)
                                    }
                                    .frame(width: Theme.Size.checkBadge, height: Theme.Size.checkBadge)
                                    .padding(8)
                                }
                            }

                            Text(kind.title)
                                .font(Theme.TypeScale.captionSemibold)
                                .foregroundStyle(isSelected ? Theme.ink : tone.tertiary)
                                .padding(.horizontal, 4)
                                .lineLimit(1)
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(kind.title)
                    .accessibilityAddTraits(isSelected ? .isSelected : [])
                    .onChange(of: now) { _, updated in
                        guard !still, !isSelected else { return }
                        if idx == 0 {
                            tickCount = (tickCount + 1) % max(1, kinds.count)
                        }
                        if tickCount == idx {
                            tileTimes[kind] = updated
                        }
                    }
                }
            }
        }
    }
}

// MARK: - 3h Machined Stepper & Keep-Alive Chips (§9.9)

private struct MachinedStepperRow: View {
    var title: String
    var subtitle: String
    var value: Int
    var range: ClosedRange<Int>
    var step: Int
    var suffix: String
    var zeroLabel: String?
    var onWrite: (Int) -> Void

    @Environment(\.tone) private var tone
    @State private var draft: Int = 0
    @State private var debounceTask: Task<Void, Never>?

    var body: some View {
        HStack(spacing: Theme.Space.bentoGap) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(Theme.TypeScale.rowLabel)
                    .foregroundStyle(Theme.ink)
                Text(subtitle)
                    .font(Theme.TypeScale.caption)
                    .foregroundStyle(tone.tertiary)
            }

            Spacer(minLength: 4)

            HStack(spacing: 4) {
                stepperButton("−") {
                    bump(-step)
                }

                Text(formattedValue)
                    .font(Theme.TypeScale.factMediumTabular)
                    .foregroundStyle(Theme.ink)
                    .frame(width: 44, alignment: .center)

                stepperButton("+") {
                    bump(step)
                }
            }
            .padding(2)
            .frame(height: Theme.Size.stepperHeight)
            .background(
                RoundedRectangle(cornerRadius: Theme.Radius.stepperTrack, style: .continuous)
                    .fill(tone.reduceTransparency ? Theme.inkDark : Theme.segmentTrackBase.opacity(Theme.Opacity.segmentTrackFill))
            )
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.stepperTrack, style: .continuous)
                    .stroke(Theme.ink.opacity(tone.hairline), lineWidth: Theme.Stroke.hairline)
            )
        }
        .frame(minHeight: Theme.Size.stepperRowHeight)
        .onAppear { draft = value }
        .onChange(of: value) { _, next in draft = next }
    }

    private func stepperButton(_ symbol: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(symbol)
                .font(Theme.TypeScale.stepperSymbol)
                .foregroundStyle(Theme.ink)
                .frame(width: Theme.Size.stepperButton, height: Theme.Size.stepperButton)
                .background(
                    Circle().fill(Theme.ink.opacity(0.06))
                )
                .frame(minWidth: Theme.Size.minHitTarget, minHeight: Theme.Size.minHitTarget)
                .contentShape(Rectangle())
        }
        .buttonStyle(PressScaleStyle())
        .accessibilityLabel(symbol == "+" ? "Increase \(title)" : "Decrease \(title)")
    }

    private var formattedValue: String {
        if draft == 0, let zeroLabel = zeroLabel {
            return zeroLabel
        }
        return "\(draft) \(suffix)"
    }

    private func bump(_ delta: Int) {
        let next = min(range.upperBound, max(range.lowerBound, draft + delta))
        guard next != draft else { return }
        draft = next
        debounceTask?.cancel()
        debounceTask = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 600_000_000)
            guard !Task.isCancelled else { return }
            onWrite(next)
        }
    }
}

private struct KeepAliveAudioSection: View {
    var apps: [String]
    var onUpdate: ([String]) -> Void

    @Environment(\.tone) private var tone
    @State private var adding = false
    @State private var draft = ""

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Space.chipGap) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Keep recording while these play audio")
                    .font(Theme.TypeScale.rowLabel)
                    .foregroundStyle(Theme.ink)
                Text("Idle pause waits while they’re making sound")
                    .font(Theme.TypeScale.caption)
                    .foregroundStyle(tone.tertiary)
            }

            FlowLayout(spacing: Theme.Space.tagGap, lineSpacing: Theme.Space.tagGap) {
                ForEach(apps, id: \.self) { app in
                    Button {
                        onUpdate(apps.filter { $0 != app })
                    } label: {
                        Text(app)
                            .font(Theme.TypeScale.mono)
                            .foregroundStyle(Theme.tealPale)
                            .padding(.horizontal, 12)
                            .frame(height: Theme.Size.tagChipHeight)
                            .background(Capsule().fill(Theme.teal.opacity(0.12)))
                            .overlay(Capsule().stroke(Theme.teal.opacity(0.30), lineWidth: Theme.Stroke.hairline))
                            .frame(minHeight: Theme.Size.minHitTarget)
                    }
                    .buttonStyle(.plain)
                    .accessibilityHint("Tap to remove")
                }

                Button {
                    withAnimation(tone.motion) {
                        adding.toggle()
                    }
                } label: {
                    Text("+ Add app")
                        .font(Theme.TypeScale.subtitle)
                        .foregroundStyle(Theme.violetLight)
                        .padding(.horizontal, 12)
                        .frame(height: Theme.Size.tagChipHeight)
                        .overlay(Capsule().stroke(Theme.violet.opacity(0.35), lineWidth: Theme.Stroke.hairline))
                        .frame(minHeight: Theme.Size.minHitTarget)
                }
                .buttonStyle(.plain)
            }

            if adding {
                HStack(spacing: Theme.Space.chipGap) {
                    TextField("Discord.exe", text: $draft)
                        .font(Theme.TypeScale.mono)
                        .foregroundStyle(Theme.ink)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .padding(.horizontal, 12)
                        .frame(height: 36)
                        .background(
                            RoundedRectangle(cornerRadius: Theme.Radius.field, style: .continuous)
                                .fill(Theme.segmentTrackBase.opacity(Theme.Opacity.segmentTrackFill))
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: Theme.Radius.field, style: .continuous)
                                .stroke(Theme.ink.opacity(tone.hairline), lineWidth: Theme.Stroke.hairline)
                        )

                    Button {
                        let name = draft.trimmingCharacters(in: .whitespacesAndNewlines)
                        guard !name.isEmpty else { return }
                        if !apps.contains(name) {
                            onUpdate(apps + [name])
                        }
                        draft = ""
                        adding = false
                    } label: {
                        Text("Add")
                            .font(Theme.TypeScale.segment)
                            .foregroundStyle(Theme.ink)
                            .padding(.horizontal, 14)
                            .frame(height: 36)
                            .background(Capsule().fill(Theme.violet.opacity(Theme.Opacity.primaryFill)))
                            .overlay(Capsule().stroke(Theme.violet.opacity(Theme.Opacity.primaryRing), lineWidth: Theme.Stroke.hairline))
                            .frame(minHeight: Theme.Size.minHitTarget)
                    }
                    .buttonStyle(PressScaleStyle())
                }
            }
        }
        .padding(.vertical, 12)
    }
}

private struct NebulaSwitch: View {
    var isOn: Bool
    var onToggle: (Bool) -> Void
    @Environment(\.tone) private var tone

    var body: some View {
        Button {
            withAnimation(tone.motion) {
                onToggle(!isOn)
            }
        } label: {
            ZStack(alignment: isOn ? .trailing : .leading) {
                Capsule()
                    .fill(isOn ? Theme.teal.opacity(0.32) : Theme.segmentTrackBase.opacity(Theme.Opacity.segmentTrackFill))
                    .overlay(
                        Capsule().stroke(
                            isOn ? Theme.teal.opacity(0.65) : Theme.ink.opacity(tone.hairline),
                            lineWidth: Theme.Stroke.hairline
                        )
                    )
                    .frame(width: 50, height: 30)

                Circle()
                    .fill(isOn ? Theme.teal : Theme.ink2)
                    .frame(width: 24, height: 24)
                    .padding(3)
            }
            .frame(minWidth: Theme.Size.minHitTarget, minHeight: Theme.Size.minHitTarget)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityValue(isOn ? "On" : "Off")
    }
}
