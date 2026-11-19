import SwiftUI
import UIKit

struct ShellView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    @Environment(\.scenePhase) private var scene
    @State private var tab: PhoneTab = .now
    @State private var nowPath = NavigationPath()
    @State private var clipsPath = NavigationPath()
    @State private var gamesPath = NavigationPath()

    var body: some View {
        let shouldAnimateBg = model.active
            && !model.playback
            && !tone.isStill
            && !ProcessInfo.processInfo.isLowPowerModeEnabled
            && ProcessInfo.processInfo.thermalState != .serious
            && ProcessInfo.processInfo.thermalState != .critical

        ZStack(alignment: .bottom) {
            BackgroundView(
                kind: model.prefs.background,
                seed: model.prefs.planetSeed,
                live: shouldAnimateBg
            )

            ZStack {
                stack(tab: .now, path: $nowPath) { NowView() }
                stack(tab: .clips, path: $clipsPath) { ClipsView() }
                stack(tab: .remote, path: .constant(NavigationPath())) { RemoteView() }
                stack(tab: .games, path: $gamesPath) { GamesView() }
            }
            .opacity(model.link == .connecting ? Theme.Opacity.connectingDim : 1.0)

            tabBar

            if let toast = model.toastText {
                ToastBanner(text: toast)
                    .padding(.bottom, Theme.Space.contentBottomInset - 8)
                    .transition(.opacity)
            }
        }
        .ignoresSafeArea(.keyboard, edges: .bottom)
        .onChange(of: model.requestedTab) { _, next in
            guard let next = next else { return }
            withAnimation(tone.motion) {
                tab = next
            }
            model.requestedTab = nil
        }
        .onChange(of: model.clipRoute) { _, id in
            guard let id = id else { return }
            if tab == .now && model.requestedTab == nil {
                nowPath.append(ClipDest.clip(id))
            } else {
                tab = .clips
                clipsPath.append(ClipDest.clip(id))
            }
            model.clipRoute = nil
        }
        .onChange(of: tab) { _, _ in
            model.watchStats(tab == .now && model.active)
        }
        .onChange(of: scene) { _, phase in
            model.setActive(phase == .active)
            model.watchStats(tab == .now && phase == .active)
        }
        .sheet(isPresented: $model.settingsPresented) {
            ToneReader(stillPref: model.prefs.still) { _ in
                SettingsRoot()
            }
            .environmentObject(model)
            .preferredColorScheme(.dark)
            // One live background, the shell's. A sheet cannot see through to
            // it, so it gets a single still frame of the same art instead of
            // its own 20 fps renderer (and none per pushed page).
            .presentationBackground {
                ZStack {
                    Theme.ground
                    BackgroundView(
                        kind: model.prefs.background,
                        seed: model.prefs.planetSeed,
                        live: false
                    )
                }
            }
        }
        .sheet(item: classifyBinding) { item in
            ToneReader(stillPref: model.prefs.still) { _ in
                ClassifySheet(item: item)
            }
            .environmentObject(model)
            .preferredColorScheme(.dark)
            // Large, not medium: at medium the facts, the capture choice and
            // both answers were crushed into half a screen. Spec §9.6 allows
            // medium only on SE-size screens; this phone is not one.
            .presentationDetents([.large])
            .presentationDragIndicator(.hidden)
            .presentationBackground(Theme.clear)
        }
        .onAppear {
            model.watchStats(true)
        }
    }

    private var classifyBinding: Binding<PendingApp?> {
        return Binding(
            get: { return model.pendingApp },
            set: { model.classifyID = $0?.id }
        )
    }

    private func stack<Content: View>(
        tab item: PhoneTab,
        path: Binding<NavigationPath>,
        @ViewBuilder content: @escaping () -> Content
    ) -> some View {
        NavigationStack(path: path) {
            ScreenChrome(
                tab: item,
                title: item.rawValue,
                subtitle: subtitle(item),
                trailing: item == .games ? .add : .settings
            ) {
                content()
            }
            .navigationDestination(for: ClipDest.self) { dest in
                switch dest {
                case let .clip(id):
                    ClipDetailView(id: id)
                case let .game(id):
                    ScreenChrome(
                        tab: .clips,
                        title: gameTitle(for: id),
                        subtitle: gameSubtitle(for: id),
                        trailing: .settings,
                        showsBack: true
                    ) {
                        ClipsView(lockedGame: id)
                    }
                }
            }
        }
        .background(ClearHostBackground())
        .opacity(tab == item ? 1.0 : 0.0)
        .allowsHitTesting(tab == item)
    }

    private func gameTitle(for id: String) -> String {
        return model.studio?.games.first(where: { $0.id == id })?.name ?? "Clips"
    }

    private func gameSubtitle(for id: String) -> String? {
        guard let game = model.studio?.games.first(where: { $0.id == id }) else { return nil }
        return "\(game.clipCount) clips · \(StudioFormat.bytes(game.bytes))"
    }

    private func subtitle(_ item: PhoneTab) -> String? {
        switch item {
        case .now:
            return nil
        case .clips:
            let clips = model.studio?.clips ?? []
            if clips.isEmpty { return nil }
            let games = Set(clips.map(\.game.id)).count
            let knownBytes = clips.compactMap(\.bytes)
            let bytesText = knownBytes.isEmpty ? "—" : StudioFormat.bytes(knownBytes.reduce(0, +))
            return "\(clips.count) clips · \(bytesText) · \(games) games"
        case .remote:
            return "Moonlight · Tailscale"
        case .games:
            return "When a game launches: \(model.studio?.settings.launchLabel ?? "Record")"
        }
    }

    private var tabBar: some View {
        let pendingCount = model.studio?.pending.count ?? 0
        return HStack(spacing: 0) {
            ForEach(PhoneTab.allCases) { item in
                let isSelected = tab == item
                Button {
                    withAnimation(tone.motion) {
                        tab = item
                    }
                } label: {
                    VStack(spacing: 2) {
                        ZStack(alignment: .topTrailing) {
                            TabGlyph(tab: item)
                                .stroke(isSelected ? Theme.violet : tone.tertiary, lineWidth: 1.5)
                                .frame(width: Theme.Size.tabIcon, height: Theme.Size.tabIcon)
                            if item == .games && pendingCount > 0 {
                                Circle()
                                    .fill(Theme.violetLight)
                                    .frame(width: 7, height: 7)
                                    .offset(x: 3, y: 1)
                            }
                        }
                        Text(item.rawValue)
                            .font(Theme.TypeScale.tabLabel)
                            .tracking(0.2)
                            .foregroundStyle(isSelected ? Theme.ink : tone.tertiary)
                    }
                    .frame(maxWidth: .infinity, minHeight: Theme.Size.minHitTarget)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(item.rawValue)
                .accessibilityAddTraits(isSelected ? .isSelected : [])
            }
        }
        .padding(.horizontal, Theme.Space.tabBarInnerPad)
        .frame(height: Theme.Size.tabBarHeight)
        .background {
            if tone.reduceTransparency {
                Capsule().fill(Theme.card)
            } else {
                // Even glass. A thinner material lets the card underneath print
                // through as a blob behind whichever tab happens to sit on it.
                Capsule().fill(.thinMaterial)
                Capsule().fill(Theme.glassBarBase.opacity(0.62))
            }
        }
        .overlay {
            Capsule().stroke(Theme.specular.opacity(tone.increaseContrast ? Theme.Opacity.highContrastHairline : 0.16), lineWidth: Theme.Stroke.hairline)
            Capsule()
                .stroke(Theme.specular.opacity(0.30), lineWidth: 1)
                .mask(
                    LinearGradient(colors: [Theme.ink, Theme.clear], startPoint: .top, endPoint: .center)
                )
        }
        .shadow(color: Theme.shadow.opacity(0.50), radius: 22, x: 0, y: 12)
        .padding(.horizontal, Theme.Space.tabBarSideInset)
        .padding(.bottom, Theme.Space.tabBarBottomInset)
    }
}

enum ChromeTrailing {
    case settings
    case add
}

struct ScreenChrome<Content: View>: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    @Environment(\.dismiss) private var dismiss
    let tab: PhoneTab
    let title: String
    let subtitle: String?
    var trailing: ChromeTrailing = .settings
    var showsBack: Bool = false
    @ViewBuilder var content: () -> Content

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Space.sectionGap) {
                header
                    .padding(.horizontal, Theme.Space.headerInset)

                if model.link == .offline {
                    statusBanner(
                        dot: tone.tertiary,
                        title: "Studio PC is offline",
                        detail: lastSeenText,
                        coralTint: false
                    )
                } else if model.studio?.obsConnected == false {
                    statusBanner(
                        dot: Theme.coral,
                        title: "OBS isn’t connected on Studio PC",
                        detail: nil,
                        coralTint: true
                    )
                }

                content()
            }
            .padding(.horizontal, Theme.Space.screenMargin)
            .padding(.top, 16)
            .padding(.bottom, Theme.Space.contentBottomInset)
        }
        .scrollContentBackground(.hidden)
        .background(ClearHostBackground())
        .toolbar(.hidden, for: .navigationBar)
    }

    private var header: some View {
        HStack(alignment: .center, spacing: Theme.Space.bentoGap) {
            if showsBack {
                Button {
                    dismiss()
                } label: {
                    GlassCircle(system: "chevron.left", size: Theme.Size.chromeButton)
                }
                .buttonStyle(PressScaleStyle())
                .accessibilityLabel("Back")
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(Theme.TypeScale.largeTitle)
                    .tracking(Theme.TypeScale.largeTitleTracking)
                    .foregroundStyle(Theme.ink)
                    .lineLimit(1)

                if tab == .games {
                    Button {
                        model.settingsRoute = .recording
                        model.settingsPresented = true
                    } label: {
                        HStack(spacing: 4) {
                            Text("When a game launches:")
                                .foregroundStyle(Theme.ink2)
                            Text(model.studio?.settings.launchLabel ?? "Record")
                                .foregroundStyle(Theme.ink)
                        }
                        .font(Theme.TypeScale.subtitle)
                    }
                    .buttonStyle(.plain)
                } else if let subtitle = subtitle {
                    Text(subtitle)
                        .font(Theme.TypeScale.subtitle)
                        .foregroundStyle(Theme.ink2)
                        .lineLimit(1)
                }
            }

            Spacer(minLength: 4)

            Button {
                if trailing == .add {
                    model.addGame = true
                } else {
                    model.settingsPresented = true
                }
            } label: {
                GlassCircle(
                    system: trailing == .add ? "plus" : "slider.horizontal.3",
                    size: Theme.Size.chromeButton
                )
            }
            .buttonStyle(PressScaleStyle())
            .accessibilityLabel(trailing == .add ? "Add a game" : "Settings")
        }
    }

    private var lastSeenText: String? {
        guard let seen = model.lastSeen else { return nil }
        return "Last seen \(StudioFormat.time(seen))"
    }

    private func statusBanner(dot: Color, title: String, detail: String?, coralTint: Bool) -> some View {
        HStack(spacing: 10) {
            Circle()
                .fill(dot)
                .frame(width: 8, height: 8)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(Theme.TypeScale.rowValue)
                    .foregroundStyle(coralTint ? Theme.coralText : Theme.ink)
                if let detail = detail {
                    Text(detail)
                        .font(Theme.TypeScale.caption)
                        .foregroundStyle(tone.tertiary)
                }
            }
            Spacer()
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background {
            if coralTint {
                RoundedRectangle(cornerRadius: Theme.Radius.banner, style: .continuous)
                    .fill(Theme.coral.opacity(0.12))
            } else if tone.reduceTransparency {
                RoundedRectangle(cornerRadius: Theme.Radius.banner, style: .continuous)
                    .fill(Theme.card)
            } else {
                RoundedRectangle(cornerRadius: Theme.Radius.banner, style: .continuous)
                    .fill(.ultraThinMaterial)
                RoundedRectangle(cornerRadius: Theme.Radius.banner, style: .continuous)
                    .fill(Theme.glassBarBase.opacity(Theme.Opacity.searchGlassFill))
            }
        }
        .overlay(
            RoundedRectangle(cornerRadius: Theme.Radius.banner, style: .continuous)
                .stroke(
                    coralTint ? Theme.coral.opacity(0.35) : Theme.ink.opacity(tone.hairline),
                    lineWidth: Theme.Stroke.hairline
                )
        )
    }
}

/// The page stacks sit in a navigation controller that paints an opaque
/// plate. Settings is a sheet with the planet inside it, so it showed
/// through; the tabs did not. Clearing those host views lets the one
/// background behind the shell show on every page.
struct ClearHostBackground: UIViewRepresentable {
    func makeUIView(context: Context) -> UIView {
        let view = UIView()
        view.backgroundColor = .clear
        view.isOpaque = false
        view.isUserInteractionEnabled = false
        return view
    }

    func updateUIView(_ view: UIView, context: Context) {
        DispatchQueue.main.async {
            var current: UIView? = view
            for _ in 0 ..< 6 {
                current?.backgroundColor = .clear
                current?.isOpaque = false
                current = current?.superview
            }
        }
    }
}

/// The four tab marks from the design frames: 1.5 pt line, round caps, no fill.
struct TabGlyph: Shape {
    var tab: PhoneTab

    func path(in rect: CGRect) -> Path {
        let scale = min(rect.width, rect.height) / 24.0
        var unit = Path()
        switch tab {
        case .now:
            unit.addEllipse(in: CGRect(x: 3.4, y: 3.4, width: 17.2, height: 17.2))
            unit.addEllipse(in: CGRect(x: 9.2, y: 9.2, width: 5.6, height: 5.6))
        case .clips:
            unit.addRoundedRect(
                in: CGRect(x: 3.5, y: 5, width: 17, height: 14),
                cornerSize: CGSize(width: 2.6, height: 2.6)
            )
            unit.move(to: CGPoint(x: 7.6, y: 5))
            unit.addLine(to: CGPoint(x: 7.6, y: 19))
            unit.move(to: CGPoint(x: 16.4, y: 5))
            unit.addLine(to: CGPoint(x: 16.4, y: 19))
        case .remote:
            unit.addRoundedRect(
                in: CGRect(x: 2.8, y: 4.2, width: 18.4, height: 12.6),
                cornerSize: CGSize(width: 2.4, height: 2.4)
            )
            unit.move(to: CGPoint(x: 9, y: 20.2))
            unit.addLine(to: CGPoint(x: 15, y: 20.2))
            unit.move(to: CGPoint(x: 12, y: 16.8))
            unit.addLine(to: CGPoint(x: 12, y: 20.2))
            unit.move(to: CGPoint(x: 10.6, y: 8.4))
            unit.addLine(to: CGPoint(x: 10.6, y: 12.8))
            unit.addLine(to: CGPoint(x: 14.4, y: 10.6))
            unit.closeSubpath()
        case .games:
            unit.move(to: CGPoint(x: 7.6, y: 7.4))
            unit.addLine(to: CGPoint(x: 16.4, y: 7.4))
            unit.addCurve(
                to: CGPoint(x: 20.9, y: 11.8),
                control1: CGPoint(x: 18.9, y: 7.4),
                control2: CGPoint(x: 20.5, y: 9.3)
            )
            unit.addLine(to: CGPoint(x: 21.5, y: 16))
            unit.addCurve(
                to: CGPoint(x: 18.5, y: 18),
                control1: CGPoint(x: 21.8, y: 17.8),
                control2: CGPoint(x: 19.9, y: 19)
            )
            unit.addLine(to: CGPoint(x: 16.3, y: 16.4))
            unit.addQuadCurve(to: CGPoint(x: 14.9, y: 15.9), control: CGPoint(x: 15.6, y: 15.9))
            unit.addLine(to: CGPoint(x: 9.1, y: 15.9))
            unit.addQuadCurve(to: CGPoint(x: 7.7, y: 16.4), control: CGPoint(x: 8.4, y: 15.9))
            unit.addLine(to: CGPoint(x: 5.5, y: 18))
            unit.addCurve(
                to: CGPoint(x: 2.5, y: 16),
                control1: CGPoint(x: 4.1, y: 19),
                control2: CGPoint(x: 2.2, y: 17.8)
            )
            unit.addLine(to: CGPoint(x: 3.1, y: 11.8))
            unit.addCurve(
                to: CGPoint(x: 7.6, y: 7.4),
                control1: CGPoint(x: 3.5, y: 9.3),
                control2: CGPoint(x: 5.1, y: 7.4)
            )
            unit.closeSubpath()
            unit.move(to: CGPoint(x: 7.6, y: 10.2))
            unit.addLine(to: CGPoint(x: 7.6, y: 13.4))
            unit.move(to: CGPoint(x: 6, y: 11.8))
            unit.addLine(to: CGPoint(x: 9.2, y: 11.8))
        }
        let fitted = CGAffineTransform(translationX: rect.minX, y: rect.minY).scaledBy(x: scale, y: scale)
        return unit.applying(fitted)
    }
}
