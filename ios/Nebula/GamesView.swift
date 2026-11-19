import SwiftUI
import UIKit

struct GamesView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    @State private var exe = ""

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Space.bentoGap) {
            if let note = model.undoNote {
                undoBanner(note)
                    .transition(.opacity)
            }
            pendingSection
            gamesSection
            nonGamesSection
        }
        .sheet(isPresented: $model.addGame) {
            ToneReader(stillPref: model.prefs.still) { _ in
                addGameSheet
            }
            .environmentObject(model)
            .preferredColorScheme(.dark)
            .presentationDetents([.medium])
        }
    }

    // MARK: - 44pt Glass Undo Confirmation (§9.5)

    private func undoBanner(_ note: String) -> some View {
        ReadingSurface(radius: Theme.Radius.searchBar, kind: .bar) {
            HStack(spacing: Theme.Space.bentoGap) {
                Text(note)
                    .font(Theme.TypeScale.rowValue)
                    .foregroundStyle(Theme.inkSoft)
                    .lineLimit(1)
                Spacer(minLength: 4)
                Button {
                    withAnimation(tone.motion) {
                        model.undoClassify()
                    }
                } label: {
                    Text("Undo")
                        .font(Theme.TypeScale.segment)
                        .foregroundStyle(Theme.violetLight)
                        .padding(.horizontal, 12)
                        .frame(minHeight: Theme.Size.minHitTarget)
                }
                .buttonStyle(.plain)
            }
            .padding(.leading, 16)
            .padding(.trailing, 8)
            .frame(minHeight: Theme.Size.searchHeight)
        }
    }

    // MARK: - Pending App Cards (3c: max 3 visible + "+N more")

    private var pendingSection: some View {
        let rows = model.studio?.pending ?? []
        return Group {
            if !rows.isEmpty {
                VStack(spacing: Theme.Space.gridGap) {
                    ForEach(rows.prefix(3)) { item in
                        pendingCard(item)
                    }
                    if rows.count > 3 {
                        Text("+\(rows.count - 3) more")
                            .font(Theme.TypeScale.segment)
                            .foregroundStyle(tone.tertiary)
                            .frame(maxWidth: .infinity, alignment: .center)
                    }
                }
            }
        }
    }

    private func pendingCard(_ item: PendingApp) -> some View {
        Tray(role: .featured, tint: .violet) {
            ReadingSurface(radius: Theme.Radius.featuredCard, kind: .prompt) {
                VStack(alignment: .leading, spacing: Theme.Space.sectionGap) {
                    HStack(alignment: .center, spacing: Theme.Space.bentoGap) {
                        ZStack {
                            Circle()
                                .fill(Theme.violet.opacity(0.07))
                                .frame(width: Theme.Size.pendingBadge + 10, height: Theme.Size.pendingBadge + 10)
                            Circle()
                                .fill(Theme.violet.opacity(0.18))
                                .overlay(Circle().stroke(Theme.violet.opacity(0.32), lineWidth: Theme.Stroke.hairline))
                                .shadow(color: Theme.violet.opacity(0.35), radius: 9)
                                .frame(width: Theme.Size.pendingBadge, height: Theme.Size.pendingBadge)
                            Text("?")
                                .font(Theme.TypeScale.promptTitle)
                                .foregroundStyle(Theme.violetPale)
                        }

                        VStack(alignment: .leading, spacing: 2) {
                            Eyebrow(text: "New app on Studio PC", color: Theme.violetLight)
                            Text("Is this a game?")
                                .font(Theme.TypeScale.promptTitle)
                                .foregroundStyle(Theme.ink)
                            Text(item.exe)
                                .font(Theme.TypeScale.mono)
                                .foregroundStyle(Theme.ink2)
                                .lineLimit(1)
                                .truncationMode(.middle)
                        }
                    }

                    HStack(spacing: Theme.Space.chipGap) {
                        Button {
                            withAnimation(tone.motion) {
                                model.classify(item, isGame: true, capture: "default")
                            }
                        } label: {
                            Text("It’s a game")
                                .font(Theme.TypeScale.controlSemibold)
                                .foregroundStyle(Theme.ink)
                                .lineLimit(1)
                                .minimumScaleFactor(0.8)
                                .frame(maxWidth: .infinity, minHeight: Theme.Size.compactPillHeight)
                                .background(
                                    RoundedRectangle(cornerRadius: Theme.Radius.actionPill, style: .continuous)
                                        .fill(Theme.violet.opacity(Theme.Opacity.primaryFill))
                                )
                                .overlay(
                                    RoundedRectangle(cornerRadius: Theme.Radius.actionPill, style: .continuous)
                                        .stroke(Theme.violet.opacity(0.50), lineWidth: Theme.Stroke.hairline)
                                )
                        }
                        .buttonStyle(PressScaleStyle())

                        Button {
                            withAnimation(tone.motion) {
                                model.classify(item, isGame: false, capture: "default")
                            }
                        } label: {
                            Text("Not a game")
                                .font(Theme.TypeScale.controlSemibold)
                                .foregroundStyle(Theme.ink2)
                                .lineLimit(1)
                                .minimumScaleFactor(0.8)
                                .frame(maxWidth: .infinity, minHeight: Theme.Size.compactPillHeight)
                                .overlay(
                                    RoundedRectangle(cornerRadius: Theme.Radius.actionPill, style: .continuous)
                                        .stroke(Theme.ink.opacity(0.14), lineWidth: Theme.Stroke.hairline)
                                )
                                .contentShape(RoundedRectangle(cornerRadius: Theme.Radius.actionPill, style: .continuous))
                        }
                        .buttonStyle(PressScaleStyle())
                    }
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    // MARK: - Games · Capture Group (3c: sorted by lastPlayed, 4-segment control)

    private var sortedGames: [Game] {
        return (model.studio?.games ?? []).sorted { left, right in
            let l = left.lastPlayed ?? .distantPast
            let r = right.lastPlayed ?? .distantPast
            if l != r { return l > r }
            return left.name < right.name
        }
    }

    private var gamesSection: some View {
        let games = sortedGames
        return VStack(alignment: .leading, spacing: Theme.Space.chipGap) {
            HStack(alignment: .firstTextBaseline) {
                Eyebrow(text: "Games · capture", color: Theme.ink2)
                Spacer()
                Text("Steam auto-classifies")
                    .font(Theme.TypeScale.caption)
                    .foregroundStyle(tone.tertiary)
            }
            .padding(.horizontal, Theme.Space.headerInset)
            .padding(.top, 2)

            ReadingSurface(radius: Theme.Radius.group) {
                if games.isEmpty {
                    Text("No games classified yet.")
                        .font(Theme.TypeScale.rowValue)
                        .foregroundStyle(tone.tertiary)
                        .padding(16)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    VStack(spacing: 0) {
                        ForEach(Array(games.enumerated()), id: \.element.id) { idx, game in
                            if idx > 0 {
                                GroupDivider()
                            }
                            GameCaptureRow(game: game)
                        }
                    }
                    .padding(.horizontal, 14)
                }
            }
        }
    }

    // MARK: - Not Games · Never Recorded (3c: Wrapping Flow Chips)

    private var nonGamesSection: some View {
        let nonGames = model.studio?.nonGames ?? []
        return VStack(alignment: .leading, spacing: Theme.Space.chipGap) {
            Eyebrow(text: "Not games · never recorded", color: Theme.ink2)
                .padding(.horizontal, Theme.Space.headerInset)
                .padding(.top, 2)

            if nonGames.isEmpty {
                Text("Nothing is filed here.")
                    .font(Theme.TypeScale.rowValue)
                    .foregroundStyle(tone.tertiary)
                    .padding(.horizontal, Theme.Space.headerInset)
            } else {
                FlowLayout(spacing: Theme.Space.tagGap, lineSpacing: Theme.Space.tagGap) {
                    ForEach(nonGames) { item in
                        Text(item.displayName)
                            .font(Theme.TypeScale.subtitle)
                            .foregroundStyle(Theme.ink2)
                            .padding(.horizontal, 12)
                            .frame(height: Theme.Size.tagChipHeight)
                            .background(Capsule().fill(Theme.ink.opacity(0.06)))
                            .overlay(Capsule().stroke(Theme.ink.opacity(0.08), lineWidth: Theme.Stroke.hairline))
                            .padding(.vertical, 4)
                            .contentShape(Rectangle())
                            .contextMenu {
                                Button("Mark as game") {
                                    model.reclassify(exe: item.exe, isGame: true)
                                }
                            }
                    }
                }
                .padding(.horizontal, 4)
            }
        }
    }

    // MARK: - Add a Game Sheet

    private var addGameSheet: some View {
        VStack(alignment: .leading, spacing: Theme.Space.sectionGap) {
            HStack {
                Text("Add a game")
                    .font(Theme.TypeScale.cardTitleLarge)
                    .foregroundStyle(Theme.ink)
                Spacer()
                Button {
                    model.addGame = false
                } label: {
                    Text("Cancel")
                        .font(Theme.TypeScale.controlSemibold)
                        .foregroundStyle(Theme.violetLight)
                        .frame(minWidth: Theme.Size.minHitTarget, minHeight: Theme.Size.minHitTarget)
                }
                .buttonStyle(.plain)
            }

            Text("Type the executable name from Studio PC to classify it permanently as a game.")
                .font(Theme.TypeScale.body)
                .foregroundStyle(Theme.ink2)

            Tray(role: .tile) {
                ReadingSurface(radius: Theme.Radius.tileCard) {
                    VStack(alignment: .leading, spacing: 6) {
                        Eyebrow(text: "Executable")
                        TextField("game.exe", text: $exe)
                            .font(Theme.TypeScale.monoFolder)
                            .foregroundStyle(Theme.ink)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .frame(minHeight: 36)
                    }
                    .padding(16)
                }
            }

            PrimaryPill(title: "Add as a game", system: "plus") {
                let trimmed = exe.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !trimmed.isEmpty else { return }
                model.reclassify(exe: trimmed, isGame: true)
                exe = ""
                model.addGame = false
            }

            Spacer()
        }
        .padding(Theme.Space.sheetMargin)
        .background(Theme.ground.ignoresSafeArea())
    }
}

private struct GameCaptureRow: View {
    var game: Game
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    @State private var swipeOffset: CGFloat = 0

    var body: some View {
        ZStack(alignment: .trailing) {
            if swipeOffset < -10 {
                Button {
                    withAnimation(tone.motion) {
                        swipeOffset = 0
                        model.reclassify(exe: game.name, isGame: false)
                    }
                } label: {
                    Text("Not a game")
                        .font(Theme.TypeScale.captionSemibold)
                        .foregroundStyle(Theme.coralText)
                        .padding(.horizontal, 12)
                        .frame(height: 36)
                        .background(Capsule().fill(Theme.coral.opacity(0.18)))
                        .overlay(Capsule().stroke(Theme.coral.opacity(0.45), lineWidth: Theme.Stroke.hairline))
                }
                .buttonStyle(.plain)
            }

            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Text(game.name)
                        .font(Theme.TypeScale.rowTitle)
                        .foregroundStyle(Theme.ink)
                        .lineLimit(1)
                    Spacer()
                    Text(game.sourceLabel)
                        .font(Theme.TypeScale.caption)
                        .foregroundStyle(game.source == "prompt" ? Theme.violetLight : tone.tertiary)
                }

                NebulaSegments(
                    options: [
                        ("default", "Default"),
                        ("record", "Record"),
                        ("buffer", "Buffer"),
                        ("both", "Both"),
                    ],
                    selection: game.capture,
                    compact: true
                ) { next in
                    model.setCapture(game, next)
                }
            }
            .padding(.vertical, 12)
            .offset(x: swipeOffset)
            .gesture(
                DragGesture(minimumDistance: 24).onChanged { value in
                    if value.translation.width < 0 {
                        swipeOffset = max(-108, value.translation.width)
                    } else if swipeOffset < 0 {
                        swipeOffset = min(0, -108 + value.translation.width)
                    }
                }.onEnded { value in
                    withAnimation(tone.motion) {
                        swipeOffset = value.translation.width < -52 ? -104 : 0
                    }
                }
            )
            .contextMenu {
                Button("Not a game", role: .destructive) {
                    model.reclassify(exe: game.name, isGame: false)
                }
            }
        }
    }
}

// MARK: - Screen 3d: "Is this a game?" Sheet (§9.6)

struct ClassifySheet: View {
    var item: PendingApp
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    @State private var capture: String = "record"

    var body: some View {
        ScrollView {
            ReadingSurface(radius: Theme.Radius.sheetCard, kind: .sheet) {
                VStack(alignment: .leading, spacing: 18) {
                    Capsule()
                        .fill(Theme.ink.opacity(0.28))
                        .frame(width: 38, height: 5)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 2)

                    VStack(alignment: .leading, spacing: Theme.Space.bentoGap) {
                        ZStack {
                            Circle()
                                .fill(Theme.violet.opacity(0.06))
                                .frame(width: Theme.Size.sheetBadge + 16, height: Theme.Size.sheetBadge + 16)
                            Circle()
                                .fill(Theme.violet.opacity(0.18))
                                .overlay(Circle().stroke(Theme.violet.opacity(0.32), lineWidth: Theme.Stroke.hairline))
                                .shadow(color: Theme.violet.opacity(0.40), radius: 15)
                                .frame(width: Theme.Size.sheetBadge, height: Theme.Size.sheetBadge)
                            Text("?")
                                .font(Theme.TypeScale.sheetBadgeGlyph)
                                .foregroundStyle(Theme.violetPale)
                        }

                        VStack(alignment: .leading, spacing: 4) {
                            if let seen = item.seenAt {
                                TimelineView(.periodic(from: .now, by: 1.0)) { context in
                                    Eyebrow(
                                        text: "New app on Studio PC · \(StudioFormat.relative(seen, now: context.date))",
                                        color: Theme.violetLight
                                    )
                                }
                            } else {
                                Eyebrow(text: "New app on Studio PC", color: Theme.violetLight)
                            }
                            Text("Is this a game?")
                                .font(Theme.TypeScale.sheetTitle)
                                .foregroundStyle(Theme.ink)
                        }
                    }

                    ReadingSurface(radius: Theme.Radius.settingsGroup) {
                        VStack(spacing: 0) {
                            sheetFactRow("Process") {
                                Text(item.exe)
                                    .font(Theme.TypeScale.mono)
                                    .foregroundStyle(Theme.ink)
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                            }
                            GroupDivider()
                            sheetFactRow("Window") {
                                Text(windowSummary)
                                    .font(Theme.TypeScale.rowValue)
                                    .foregroundStyle(Theme.ink)
                            }
                            GroupDivider()
                            sheetFactRow("Steam") {
                                Text(item.inSteam ? "In library" : "Not in library")
                                    .font(Theme.TypeScale.rowValue)
                                    .foregroundStyle(item.inSteam ? Theme.teal : Theme.amberDeep)
                            }
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 4)
                    }
                }
                .padding(.horizontal, 22)
                .padding(.top, 10)
                .padding(.bottom, 18)
            }
            .padding(.horizontal, 8)
            .padding(.top, 8)
        }
        .scrollBounceBehavior(.basedOnSize)
        // The capture choice and both answers are pinned, not scrolled: the
        // sheet opens at a medium detent, and anything below the fold there
        // used to sit under the home indicator. safeAreaInset keeps them
        // clear of it at any height or text size.
        .safeAreaInset(edge: .bottom, spacing: 0) {
            actionBar
        }
        .background(Theme.modalBackdrop.opacity(0.65).ignoresSafeArea())
        .onAppear {
            capture = model.studio?.settings.launchCapture ?? "record"
        }
        .onChange(of: item.id) { _, _ in
            capture = model.studio?.settings.launchCapture ?? "record"
        }
    }

    private var actionBar: some View {
        VStack(spacing: Theme.Space.gridGap) {
            VStack(alignment: .leading, spacing: Theme.Space.chipGap) {
                Eyebrow(text: "If it’s a game")
                NebulaSegments(
                    options: [
                        ("record", "Record"),
                        ("buffer", "Buffer"),
                        ("both", "Both"),
                    ],
                    selection: capture
                ) { next in
                    capture = next
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            Button {
                UINotificationFeedbackGenerator().notificationOccurred(.success)
                model.classify(item, isGame: true, capture: capture)
            } label: {
                HStack(spacing: Theme.Space.bentoGap) {
                    Text("It’s a game — \(verb)")
                        .font(Theme.TypeScale.cardTitle)
                        .foregroundStyle(Theme.ink)
                        .lineLimit(2)
                        .minimumScaleFactor(0.8)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 4)
                    Image(systemName: "checkmark")
                        .font(Theme.TypeScale.icon(16, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                        .frame(width: Theme.Size.primaryTrailingCircle, height: Theme.Size.primaryTrailingCircle)
                        .background(Circle().fill(Theme.violet.opacity(Theme.Opacity.primaryBadgeFill)))
                        .overlay(Circle().stroke(Theme.violetLight.opacity(0.32), lineWidth: Theme.Stroke.hairline))
                }
                .padding(.leading, 22)
                .padding(.trailing, 6)
                .padding(.vertical, 4)
                .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryHeight)
                .background(
                    RoundedRectangle(cornerRadius: Theme.Size.primaryHeight / 2.0, style: .continuous)
                        .fill(Theme.violet.opacity(Theme.Opacity.primaryFill))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: Theme.Size.primaryHeight / 2.0, style: .continuous)
                        .stroke(Theme.violet.opacity(Theme.Opacity.primaryRing), lineWidth: Theme.Stroke.hairline)
                )
                .contentShape(RoundedRectangle(cornerRadius: Theme.Size.primaryHeight / 2.0, style: .continuous))
            }
            .buttonStyle(PressScaleStyle())

            Button {
                UINotificationFeedbackGenerator().notificationOccurred(.success)
                model.classify(item, isGame: false, capture: "default")
            } label: {
                Text("Not a game")
                    .font(Theme.TypeScale.rowTitle)
                    .foregroundStyle(Theme.ink2)
                    .frame(maxWidth: .infinity, minHeight: Theme.Size.ghostHeight)
                    .overlay(
                        RoundedRectangle(cornerRadius: Theme.Radius.ghostPill, style: .continuous)
                            .stroke(Theme.ink.opacity(0.14), lineWidth: Theme.Stroke.hairline)
                    )
                    .contentShape(RoundedRectangle(cornerRadius: Theme.Radius.ghostPill, style: .continuous))
            }
            .buttonStyle(PressScaleStyle())

            Text("Asked once, remembered forever. Change any call in Games.")
                .font(Theme.TypeScale.caption)
                .foregroundStyle(tone.tertiary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity)
        }
        .padding(.horizontal, 30)
        .padding(.top, 12)
        .padding(.bottom, 12)
        .background(Theme.modalBackdrop.opacity(0.92))
    }

    private var windowSummary: String {
        let mode = item.fullscreen ? "Fullscreen" : "Windowed"
        if item.width > 0 && item.height > 0 {
            return "\(mode) · \(item.width) × \(item.height)"
        }
        return mode
    }

    private var verb: String {
        switch capture {
        case "buffer":
            return "buffer it"
        case "both":
            return "record + buffer"
        default:
            return "record it"
        }
    }

    private func sheetFactRow<ValueContent: View>(_ label: String, @ViewBuilder value: () -> ValueContent) -> some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 10) {
                Text(label)
                    .font(Theme.TypeScale.rowValue)
                    .foregroundStyle(Theme.ink2)
                    .fixedSize()
                Spacer(minLength: 8)
                value()
                    .multilineTextAlignment(.trailing)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                    .font(Theme.TypeScale.rowValue)
                    .foregroundStyle(Theme.ink2)
                value()
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 8)
        }
        .frame(minHeight: Theme.Size.sheetFactRowHeight)
    }
}
