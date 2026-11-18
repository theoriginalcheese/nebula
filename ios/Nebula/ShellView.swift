import SwiftUI

struct ShellView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    @Environment(\.scenePhase) private var scene
    @State private var tab: PhoneTab = .now
    @State private var nowPath = NavigationPath()
    @State private var clipsPath = NavigationPath()
    @State private var gamesPath = NavigationPath()

    var body: some View {
        ZStack(alignment: .bottom) {
            BackgroundView(
                kind: model.prefs.background,
                seed: model.prefs.planetSeed,
                live: model.active && !model.prefs.still && !tone.reduceMotion && !ProcessInfo.processInfo.isLowPowerModeEnabled && ProcessInfo.processInfo.thermalState != .serious && ProcessInfo.processInfo.thermalState != .critical
            )
            ZStack {
                stack(tab: .now, path: $nowPath) { NowView() }
                stack(tab: .clips, path: $clipsPath) { ClipsView() }
                stack(tab: .remote, path: .constant(NavigationPath())) { RemoteView() }
                stack(tab: .games, path: $gamesPath) { GamesView() }
            }
            .opacity(model.link == .connecting ? 0.7 : 1)
            tabBar
            if let toast = model.toastText {
                ToastBanner(text: toast)
                    .padding(.bottom, 96)
                    .transition(.opacity)
            }
        }
        .safeAreaPadding(.bottom, 110)
        .onChange(of: model.requestedTab) { _, next in
            if let next { tab = next; model.requestedTab = nil }
        }
        .onChange(of: model.clipRoute) { _, id in
            guard let id else { return }
            tab = .clips
            clipsPath.append(ClipDest.clip(id))
            model.clipRoute = nil
        }
        .onChange(of: tab) { _, _ in model.watchStats(tab == .now && model.active) }
        .onChange(of: scene) { _, phase in
            model.setActive(phase == .active)
            model.watchStats(tab == .now && phase == .active)
        }
        .sheet(isPresented: $model.settingsPresented) {
            SettingsRoot().environmentObject(model)
        }
        .sheet(item: classifyBinding) { item in
            ClassifySheet(item: item).environmentObject(model)
                .presentationDetents([.large])
        }
        .onAppear { model.watchStats(true) }
    }

    private var classifyBinding: Binding<PendingApp?> {
        Binding(
            get: { model.pendingApp },
            set: { model.classifyID = $0?.id }
        )
    }

    private func stack<Content: View>(tab item: PhoneTab, path: Binding<NavigationPath>, @ViewBuilder content: @escaping () -> Content) -> some View {
        NavigationStack(path: path) {
            ScreenChrome(title: item.rawValue, subtitle: subtitle(item), trailing: item == .games ? .add : .settings) {
                content()
            }
            .navigationDestination(for: ClipDest.self) { dest in
                switch dest {
                case let .clip(id):
                    ClipDetailView(id: id)
                case let .game(id):
                    ClipsView(lockedGame: id)
                }
            }
        }
        .opacity(tab == item ? 1 : 0)
        .allowsHitTesting(tab == item)
    }

    private func subtitle(_ item: PhoneTab) -> String? {
        switch item {
        case .now:
            return nil
        case .clips:
            let clips = model.studio?.clips ?? []
            let games = Set(clips.map(\.game.id)).count
            let bytes = clips.compactMap(\.bytes).reduce(0, +)
            if clips.isEmpty { return nil }
            return "\(clips.count) clips · \(StudioFormat.bytes(bytes)) · \(games) games"
        case .remote:
            return "Moonlight · Tailscale"
        case .games:
            return "When a game launches: \(model.studio?.settings.launchLabel ?? "Record")"
        }
    }

    private var tabBar: some View {
        HStack(spacing: 0) {
            ForEach(PhoneTab.allCases) { item in
                Button {
                    withAnimation(tone.motion) { tab = item }
                } label: {
                    VStack(spacing: 4) {
                        Image(systemName: item.symbol)
                            .font(.system(size: 22, weight: .light))
                            .foregroundStyle(tab == item ? Theme.violet : tone.tertiary)
                        Text(item.rawValue)
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(tab == item ? Theme.ink : tone.tertiary)
                    }
                    .frame(maxWidth: .infinity, minHeight: 44)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(item.rawValue)
                .accessibilityAddTraits(tab == item ? .isSelected : [])
            }
        }
        .padding(.horizontal, 8)
        .frame(height: 62)
        .background {
            if tone.reduceTransparency {
                Capsule().fill(Theme.card)
            } else {
                Capsule().fill(.ultraThinMaterial)
                Capsule().fill(Color(red: 30 / 255, green: 26 / 255, blue: 48 / 255).opacity(0.30))
            }
        }
        .overlay(Capsule().stroke(Color.white.opacity(tone.hairline), lineWidth: 1))
        .padding(.horizontal, 21)
        .padding(.bottom, 28)
    }
}

private enum ChromeButton { case settings, add }

private struct ScreenChrome<Content: View>: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    let title: String
    let subtitle: String?
    var trailing: ChromeButton = .settings
    @ViewBuilder var content: () -> Content

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(title)
                            .font(.system(size: 34, weight: .bold))
                            .tracking(-0.3)
                            .foregroundStyle(Theme.ink)
                        if let subtitle {
                            Button(subtitle) {
                                if title == "Games" {
                                    model.settingsPresented = true
                                    model.settingsRoute = .recording
                                }
                            }
                            .font(.system(size: 13))
                            .foregroundStyle(Theme.ink2)
                            .disabled(title != "Games")
                        }
                    }
                    Spacer()
                    Button {
                        if trailing == .add {
                            model.addGame = true
                        } else {
                            model.settingsPresented = true
                        }
                    } label: {
                        Image(systemName: trailing == .add ? "plus" : "slider.horizontal.3")
                            .font(.system(size: 18, weight: .light))
                            .foregroundStyle(Theme.ink)
                            .frame(width: 42, height: 42)
                            .background {
                                if tone.reduceTransparency {
                                    Circle().fill(Theme.card)
                                } else {
                                    Circle().fill(.ultraThinMaterial)
                                }
                            }
                    }
                    .accessibilityLabel(trailing == .add ? "Add a game" : "Settings")
                }
                if let count = model.studio?.pending.count, count > 0, title == "Games" {
                    Text(count == 1 ? "1 app to classify" : "\(count) apps to classify")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(Theme.violetLight)
                }
                if model.link == .offline {
                    banner(dot: tone.tertiary, title: "Studio PC is offline", detail: lastSeen)
                } else if model.studio?.obsConnected == false {
                    banner(dot: Theme.coral, title: "OBS isn’t connected on Studio PC", detail: nil)
                }
                content()
            }
            .padding(.horizontal, 14)
            .padding(.top, 8)
            .padding(.bottom, 24)
        }
        .scrollContentBackground(.hidden)
    }

    private var lastSeen: String? {
        guard let seen = model.lastSeen else { return nil }
        return "Last seen \(StudioFormat.time(seen))"
    }

    private func banner(dot: Color, title: String, detail: String?) -> some View {
        HStack(spacing: 10) {
            Circle().fill(dot).frame(width: 8, height: 8)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).foregroundStyle(Theme.ink)
                if let detail { Text(detail).foregroundStyle(tone.tertiary) }
            }
            .font(.system(size: 14))
            Spacer()
        }
        .padding(14)
        .background {
            if tone.reduceTransparency {
                RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Theme.card)
            } else {
                RoundedRectangle(cornerRadius: 18, style: .continuous).fill(.ultraThinMaterial)
            }
        }
    }
}
