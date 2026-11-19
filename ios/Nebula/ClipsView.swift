import SwiftUI

enum ClipDest: Hashable {
    case clip(String)
    case game(String)
}

enum ClipSort: String, CaseIterable, Identifiable {
    case newest = "Newest"
    case largest = "Largest"
    case longest = "Longest"
    case marks = "Most highlights"

    var id: String { return rawValue }
}

struct ClipsView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    var lockedGame: String?
    @State private var query = ""
    @State private var gameID: String?
    @State private var sort: ClipSort = .newest
    @State private var searchTask: Task<Void, Never>?

    var body: some View {
        let clips = shownClips
        let isUnfilteredRoot = lockedGame == nil && gameID == nil && query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty

        VStack(alignment: .leading, spacing: Theme.Space.sectionGap) {
            searchField
            if lockedGame == nil {
                gameFilterChips
            }
            if clips.isEmpty {
                emptyState
            } else if isUnfilteredRoot {
                if let latest = clips.first {
                    latestFeaturedCard(latest)
                }
                byGameSection
            } else {
                filteredClipsSection(clips)
            }
        }
        .onAppear {
            if let lockedGame = lockedGame {
                gameID = lockedGame
            }
        }
        .onChange(of: query) { _, _ in scheduleSearch() }
        .onChange(of: gameID) { _, _ in scheduleSearch() }
    }

    private var shownClips: [Clip] {
        let base = model.listed ?? model.studio?.clips ?? []
        let filtered = base.filter { clip in
            if let activeGame = lockedGame ?? gameID, clip.game.id != activeGame {
                return false
            }
            let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
            if !q.isEmpty && model.listed == nil {
                let matchGame = clip.game.name.localizedCaseInsensitiveContains(q)
                let matchFile = clip.file.localizedCaseInsensitiveContains(q)
                let matchMark = clip.highlights.contains { ($0.label ?? "").localizedCaseInsensitiveContains(q) }
                return matchGame || matchFile || matchMark
            }
            return true
        }

        switch sort {
        case .newest:
            return filtered.sorted { ($0.createdAt ?? .distantPast) > ($1.createdAt ?? .distantPast) }
        case .largest:
            return filtered.sorted { ($0.bytes ?? -1) > ($1.bytes ?? -1) }
        case .longest:
            return filtered.sorted { ($0.duration ?? -1) > ($1.duration ?? -1) }
        case .marks:
            return filtered.sorted { $0.highlights.count > $1.highlights.count }
        }
    }

    // MARK: - Search & Filter Chips (3a)

    private var searchField: some View {
        ReadingSurface(radius: Theme.Radius.searchBar, kind: .bar) {
            HStack(spacing: Theme.Space.chipGap) {
                Image(systemName: "magnifyingglass")
                    .font(Theme.TypeScale.icon(16, weight: .regular))
                    .foregroundStyle(Theme.ink2)

                ZStack(alignment: .leading) {
                    if query.isEmpty {
                        Text("Search clips")
                            .font(Theme.TypeScale.searchField)
                            .foregroundStyle(Theme.ink2)
                    }
                    TextField("", text: $query)
                        .font(Theme.TypeScale.searchField)
                        .foregroundStyle(Theme.ink)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }

                if !query.isEmpty {
                    Button {
                        query = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(Theme.TypeScale.icon(16, weight: .regular))
                            .foregroundStyle(tone.tertiary)
                            .frame(width: Theme.Size.minHitTarget, height: Theme.Size.minHitTarget)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Clear search")
                }
            }
            .padding(.horizontal, 14)
            .frame(height: Theme.Size.searchHeight)
        }
    }

    private var gameFilterChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: Theme.Space.chipGap) {
                filterChip(title: "All", selected: gameID == nil) {
                    withAnimation(tone.motion) { gameID = nil }
                }
                ForEach(gamesByRecent) { game in
                    filterChip(title: game.name, selected: gameID == game.id) {
                        withAnimation(tone.motion) { gameID = game.id }
                    }
                }
            }
            .padding(.horizontal, 2)
        }
    }

    private func filterChip(title: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(Theme.TypeScale.filterChip)
                .foregroundStyle(selected ? Theme.ink : Theme.ink2)
                .padding(.horizontal, 14)
                .frame(height: Theme.Size.filterChipHeight)
                .background(
                    Capsule().fill(
                        selected
                            ? Theme.violet.opacity(0.22)
                            : (tone.reduceTransparency ? Theme.card : Theme.glassBarBase.opacity(Theme.Opacity.searchGlassFill))
                    )
                )
                .overlay(
                    Capsule().stroke(
                        selected ? Theme.violetLight.opacity(0.45) : Theme.ink.opacity(0.08),
                        lineWidth: Theme.Stroke.hairline
                    )
                )
                .frame(minHeight: Theme.Size.minHitTarget)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    // MARK: - Latest Featured Tray (3a: 32/26 concentric tray, 176pt tall)

    private func latestFeaturedCard(_ clip: Clip) -> some View {
        Button {
            model.clipRoute = clip.id
        } label: {
            Tray(role: .featured) {
                ZStack(alignment: .bottomLeading) {
                    ClipStill(reference: clip.thumbnailURL, seed: stillSeed(clip.id))
                    LinearGradient(
                        colors: [Theme.scrimBase.opacity(0.10), Theme.scrimBase.opacity(0.92)],
                        startPoint: UnitPoint(x: 0.5, y: 0.20),
                        endPoint: .bottom
                    )

                    HStack {
                        StatusChip(style: clip.writing ? .writing : .latest)
                        Spacer()
                        Text(clip.writing ? "—" : (clip.duration.map(shortDuration) ?? "—"))
                            .font(Theme.TypeScale.captionTabular)
                            .foregroundStyle(Theme.ink)
                            .padding(.horizontal, 10)
                            .frame(height: Theme.Size.badgeChipHeight)
                            .background {
                                if tone.reduceTransparency {
                                    Capsule().fill(Theme.inkDark)
                                } else {
                                    Capsule().fill(.ultraThinMaterial)
                                    Capsule().fill(Theme.glassHeroBase.opacity(Theme.Opacity.chipGlassFill))
                                }
                            }
                    }
                    .padding(12)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)

                    VStack(alignment: .leading, spacing: 6) {
                        Text("\(clip.game.name) · \(clip.label)")
                            .font(Theme.TypeScale.featuredTitle)
                            .foregroundStyle(Theme.ink)
                            .lineLimit(1)

                        HStack(spacing: 6) {
                            if clip.locations.contains("nas") || clip.offload == .done {
                                metaPill(
                                    text: model.studio?.settings.offloadTarget ?? "nas-vault",
                                    system: "checkmark",
                                    fg: Theme.teal,
                                    bg: Theme.teal.opacity(0.14)
                                )
                            } else if clip.offload.isActive {
                                metaPill(
                                    text: "Offloading",
                                    system: "arrow.up",
                                    fg: Theme.amberDeep,
                                    bg: Theme.amberDeep.opacity(0.16)
                                )
                            }
                            metaPill(
                                text: qualityLabel(clip),
                                system: nil,
                                fg: Theme.inkSoft,
                                bg: Theme.ink.opacity(0.10)
                            )
                            if !clip.highlights.isEmpty {
                                metaPill(
                                    text: "\(clip.highlights.count) marks",
                                    system: nil,
                                    fg: Theme.violetPale,
                                    bg: Theme.violet.opacity(0.16)
                                )
                            }
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.bottom, 14)
                }
                .frame(height: Theme.Size.latestClipHeight)
            }
        }
        .buttonStyle(PressScaleStyle())
    }

    private func metaPill(text: String, system: String?, fg: Color, bg: Color) -> some View {
        HStack(spacing: 4) {
            if let system = system {
                Image(systemName: system)
                    .font(Theme.TypeScale.icon(10, weight: .bold))
            }
            Text(text)
                .font(Theme.TypeScale.captionSemibold)
        }
        .foregroundStyle(fg)
        .padding(.horizontal, 8)
        .frame(height: Theme.Size.metaPillHeight)
        .background(Capsule().fill(bg))
    }

    // MARK: - By Game 2-Column Cover Grid (3a)

    private var byGameSection: some View {
        VStack(alignment: .leading, spacing: Theme.Space.gridGap) {
            HStack(alignment: .firstTextBaseline) {
                Text("By game")
                    .font(Theme.TypeScale.sectionHeading)
                    .foregroundStyle(Theme.ink)
                Spacer()
                sortMenu
            }
            .padding(.horizontal, Theme.Space.headerInset)

            let columns = [
                GridItem(.flexible(), spacing: Theme.Space.gridGap),
                GridItem(.flexible(), spacing: Theme.Space.gridGap),
            ]
            LazyVGrid(columns: columns, spacing: Theme.Space.gridGap) {
                ForEach(gamesByRecent) { game in
                    NavigationLink(value: ClipDest.game(game.id)) {
                        ZStack(alignment: .bottomLeading) {
                            ClipStill(
                                reference: game.coverURL ?? newestThumb(for: game.id),
                                seed: stillSeed(game.id)
                            )
                            LinearGradient(
                                colors: [Theme.scrimBase.opacity(0.05), Theme.scrimBase.opacity(0.90)],
                                startPoint: UnitPoint(x: 0.5, y: 0.20),
                                endPoint: .bottom
                            )
                            VStack(alignment: .leading, spacing: 2) {
                                Text(game.name)
                                    .font(Theme.TypeScale.controlSemibold)
                                    .foregroundStyle(Theme.ink)
                                    .lineLimit(1)
                                Text("\(game.clipCount) clips · \(StudioFormat.bytes(game.bytes))")
                                    .font(Theme.TypeScale.captionRegularTabular)
                                    .foregroundStyle(Theme.ink2)
                                    .lineLimit(1)
                            }
                            .padding(.horizontal, 12)
                            .padding(.bottom, 10)
                        }
                        .frame(maxWidth: .infinity)
                        .frame(height: Theme.Size.gameCoverHeight)
                        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.group, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: Theme.Radius.group, style: .continuous)
                                .stroke(Theme.ink.opacity(0.12), lineWidth: Theme.Stroke.hairline)
                        )
                    }
                    .buttonStyle(PressScaleStyle())
                }
            }
        }
    }

    private var sortMenu: some View {
        Menu {
            ForEach(ClipSort.allCases) { item in
                Button {
                    sort = item
                } label: {
                    if sort == item {
                        Label(item.rawValue, systemImage: "checkmark")
                    } else {
                        Text(item.rawValue)
                    }
                }
            }
        } label: {
            Text("Sort")
                .font(Theme.TypeScale.body)
                .foregroundStyle(Theme.violetLight)
                .frame(minWidth: Theme.Size.minHitTarget, minHeight: Theme.Size.minHitTarget, alignment: .trailing)
        }
    }

    // MARK: - Per-Game / Filtered Clip List (§9.3)

    private func filteredClipsSection(_ clips: [Clip]) -> some View {
        VStack(alignment: .leading, spacing: Theme.Space.gridGap) {
            HStack(alignment: .firstTextBaseline) {
                Eyebrow(text: "\(clips.count) \(clips.count == 1 ? "clip" : "clips")", color: Theme.ink2)
                Spacer()
                sortMenu
            }
            .padding(.horizontal, Theme.Space.headerInset)

            ReadingSurface(radius: Theme.Radius.group) {
                VStack(spacing: 0) {
                    ForEach(Array(clips.enumerated()), id: \.element.id) { index, clip in
                        if index > 0 {
                            GroupDivider()
                        }
                        Button {
                            model.clipRoute = clip.id
                        } label: {
                            HStack(spacing: Theme.Space.bentoGap) {
                                ClipStill(reference: clip.thumbnailURL, seed: stillSeed(clip.id))
                                    .frame(width: 64, height: 36)
                                    .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.clipThumb, style: .continuous))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: Theme.Radius.clipThumb, style: .continuous)
                                            .stroke(Theme.ink.opacity(0.10), lineWidth: Theme.Stroke.divider)
                                    )

                                VStack(alignment: .leading, spacing: 2) {
                                    Text("\(clip.game.name) · \(clip.label)")
                                        .font(Theme.TypeScale.rowLabel)
                                        .foregroundStyle(Theme.ink)
                                        .lineLimit(1)
                                    Text("\(clip.writing ? "—" : (clip.duration.map(shortDuration) ?? "—")) · \(clip.writing ? "—" : StudioFormat.bytes(clip.bytes))")
                                        .font(Theme.TypeScale.captionRegularTabular)
                                        .foregroundStyle(tone.tertiary)
                                        .lineLimit(1)
                                }

                                Spacer(minLength: 4)
                                rowStatusIcon(clip)
                            }
                            .frame(minHeight: Theme.Size.peerRowHeight)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 14)
            }
        }
    }

    @ViewBuilder private func rowStatusIcon(_ clip: Clip) -> some View {
        if clip.writing {
            Circle()
                .fill(Theme.violet)
                .frame(width: 8, height: 8)
                .accessibilityLabel("Writing")
        } else if clip.offload.isActive {
            Image(systemName: "arrow.up")
                .font(Theme.TypeScale.icon(14, weight: .semibold))
                .foregroundStyle(Theme.amber)
                .accessibilityLabel("Offloading")
        } else if clip.locations.contains("nas") || clip.offload == .done {
            Image(systemName: "checkmark")
                .font(Theme.TypeScale.icon(14, weight: .semibold))
                .foregroundStyle(Theme.teal)
                .accessibilityLabel("On NAS")
        }
    }

    // MARK: - Empty State (§9.3)

    private var emptyState: some View {
        Tray(role: .featured) {
            ReadingSurface(radius: Theme.Radius.featuredCard) {
                VStack(spacing: 8) {
                    Image(systemName: "film.stack")
                        .font(Theme.TypeScale.icon(28, weight: .light))
                        .foregroundStyle(tone.tertiary)
                    Text("No clips yet")
                        .font(Theme.TypeScale.cardTitle)
                        .foregroundStyle(Theme.ink)
                    Text("When a game starts, Nebula records it in OBS and files the clip in that game’s own folder.")
                        .font(Theme.TypeScale.body)
                        .foregroundStyle(Theme.ink2)
                        .multilineTextAlignment(.center)
                }
                .padding(24)
                .frame(maxWidth: .infinity)
            }
        }
    }

    private var gamesByRecent: [Game] {
        let clips = model.studio?.clips ?? []
        return (model.studio?.games ?? []).sorted { left, right in
            let leftDate = clips.first(where: { $0.game.id == left.id })?.createdAt ?? left.lastPlayed ?? .distantPast
            let rightDate = clips.first(where: { $0.game.id == right.id })?.createdAt ?? right.lastPlayed ?? .distantPast
            return leftDate > rightDate
        }
    }

    private func newestThumb(for gameID: String) -> String? {
        return model.studio?.clips.first(where: { $0.game.id == gameID })?.thumbnailURL
    }

    private func qualityLabel(_ clip: Clip) -> String {
        if clip.resolution.isEmpty { return "—" }
        let h = clip.resolution.split(separator: "x").last.map(String.init) ?? clip.resolution
        return clip.fps > 0 ? "\(h)p\(clip.fps)" : clip.resolution
    }

    private func shortDuration(_ seconds: Double) -> String {
        let whole = max(0, Int(seconds.rounded(.down)))
        if whole >= 3600 { return StudioFormat.clock(seconds) }
        return String(format: "%d:%02d", whole / 60, whole % 60)
    }

    private func scheduleSearch() {
        searchTask?.cancel()
        searchTask = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 250_000_000)
            guard !Task.isCancelled else { return }
            model.refreshClips(query: query, gameId: lockedGame ?? gameID)
        }
    }
}
