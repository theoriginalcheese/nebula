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
    var id: String { rawValue }
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
        let clips = shown
        VStack(alignment: .leading, spacing: 14) {
            search
            if lockedGame == nil {
                chips
            }
            if clips.isEmpty {
                empty
            } else if lockedGame == nil, gameID == nil, query.trimmingCharacters(in: .whitespaces).isEmpty {
                if let latest = clips.first {
                    latestCard(latest)
                }
                gameGrid
            } else {
                clipList(clips)
            }
        }
        .onAppear {
            gameID = lockedGame ?? gameID
        }
        .onChange(of: query) { _, _ in schedule() }
        .onChange(of: gameID) { _, _ in schedule() }
    }

    private var shown: [Clip] {
        let base = model.listed ?? model.studio?.clips ?? []
        let filtered = base.filter { clip in
            if let gameID, clip.game.id != gameID { return false }
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

    private var search: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass").foregroundStyle(tone.tertiary)
            TextField("Search clips", text: $query)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
            Menu {
                ForEach(ClipSort.allCases) { item in
                    Button(item.rawValue) { sort = item }
                }
            } label: {
                Text("Sort")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Theme.violetLight)
            }
        }
        .padding(.horizontal, 14)
        .frame(height: 44)
        .background {
            if tone.reduceTransparency {
                RoundedRectangle(cornerRadius: 22, style: .continuous).fill(Theme.card)
            } else {
                RoundedRectangle(cornerRadius: 22, style: .continuous).fill(.ultraThinMaterial)
            }
        }
        .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).stroke(Color.white.opacity(0.12), lineWidth: 1))
    }

    private var chips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                chip("All", selected: gameID == nil) { gameID = nil }
                ForEach(gamesByRecent) { game in
                    chip(game.name, selected: gameID == game.id) { gameID = game.id }
                }
            }
        }
    }

    private func chip(_ title: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(selected ? Theme.ink : tone.tertiary)
                .padding(.horizontal, 14)
                .frame(minHeight: 36)
                .background(Capsule().fill(selected ? Theme.violet.opacity(0.24) : Color.white.opacity(0.04)))
                .overlay(Capsule().stroke(selected ? Theme.violetLight.opacity(0.7) : Color.clear, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    private func latestCard(_ clip: Clip) -> some View {
        Button {
            model.clipRoute = clip.id
        } label: {
            Tray(radius: 32) {
                ZStack(alignment: .bottomLeading) {
                    ClipStill(reference: clip.thumbnailURL, seed: stillSeed(clip.id))
                    LinearGradient(
                        colors: [Color(red: 7 / 255, green: 6 / 255, blue: 14 / 255).opacity(0.1), Color(red: 7 / 255, green: 6 / 255, blue: 14 / 255).opacity(0.92)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                    VStack(alignment: .leading, spacing: 6) {
                        Text("\(clip.game.name) · \(clip.label)")
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                        HStack(spacing: 6) {
                            if clip.locations.contains("nas") || clip.offload == .done {
                                statusPill(model.studio?.settings.offloadTarget ?? "nas-vault", color: Theme.teal)
                            } else if clip.writing {
                                statusPill("Writing", color: Theme.violetLight)
                            }
                            if !clip.resolution.isEmpty {
                                statusPill(clip.resolution, color: Theme.ink)
                            }
                            if !clip.highlights.isEmpty {
                                statusPill("\(clip.highlights.count) marks", color: Theme.violetLight)
                            }
                        }
                    }
                    .padding(16)
                    HStack {
                        Text(clip.writing ? "WRITING" : "LATEST")
                            .font(.system(size: 11, weight: .semibold))
                            .tracking(1.6)
                            .foregroundStyle(clip.writing ? Theme.violetLight : Theme.gold)
                            .padding(.horizontal, 10)
                            .frame(height: 24)
                            .background(.ultraThinMaterial, in: Capsule())
                        Spacer()
                        if let duration = clip.duration, !clip.writing {
                            Text(StudioFormat.clock(duration))
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundStyle(Theme.ink)
                                .padding(.horizontal, 10)
                                .frame(height: 24)
                                .background(.ultraThinMaterial, in: Capsule())
                        }
                    }
                    .padding(12)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                }
                .frame(height: 176)
            }
        }
        .buttonStyle(PressScaleStyle())
    }

    private func statusPill(_ title: String, color: Color) -> some View {
        Text(title)
            .font(.system(size: 12, weight: .semibold))
            .foregroundStyle(color)
            .padding(.horizontal, 8)
            .frame(height: 22)
            .background(Capsule().fill(color.opacity(0.16)))
    }

    private var gameGrid: some View {
        let columns = [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)]
        return LazyVGrid(columns: columns, spacing: 12) {
            ForEach(model.studio?.games ?? []) { game in
                NavigationLink(value: ClipDest.game(game.id)) {
                    ZStack(alignment: .bottomLeading) {
                        ClipStill(reference: game.coverURL, seed: stillSeed(game.id))
                        LinearGradient(
                            colors: [.clear, Color(red: 7 / 255, green: 6 / 255, blue: 14 / 255).opacity(0.9)],
                            startPoint: .center,
                            endPoint: .bottom
                        )
                        VStack(alignment: .leading, spacing: 2) {
                            Text(game.name)
                                .font(.system(size: 15, weight: .semibold))
                                .foregroundStyle(Theme.ink)
                            Text("\(game.clipCount) clips · \(StudioFormat.bytes(game.bytes))")
                                .font(.system(size: 12))
                                .foregroundStyle(Theme.ink2)
                        }
                        .padding(12)
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 118)
                    .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).stroke(Color.white.opacity(0.12), lineWidth: 1))
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func clipList(_ clips: [Clip]) -> some View {
        VStack(spacing: 0) {
            ForEach(clips) { clip in
                Button {
                    model.clipRoute = clip.id
                } label: {
                    HStack(spacing: 12) {
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .fill(Theme.violet.opacity(0.3))
                            .frame(width: 64, height: 36)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(clip.label).font(.system(size: 16)).foregroundStyle(Theme.ink)
                            Text(clip.game.name).font(.system(size: 13)).foregroundStyle(tone.tertiary)
                        }
                        Spacer()
                        status(clip)
                    }
                    .frame(minHeight: 58)
                    .padding(.horizontal, 12)
                }
                .buttonStyle(.plain)
                .disabled(model.link == .offline && false)
            }
        }
        .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Theme.card.opacity(0.45)))
    }

    @ViewBuilder private func status(_ clip: Clip) -> some View {
        if clip.writing {
            Circle().fill(Theme.violet).frame(width: 8, height: 8).accessibilityLabel("Writing")
        } else if case .moving = clip.offload {
            Image(systemName: "arrow.up").foregroundStyle(Theme.amber).accessibilityLabel("Offloading")
        } else if clip.offload == .queued {
            Image(systemName: "arrow.up").foregroundStyle(Theme.amber).accessibilityLabel("Offloading")
        } else if clip.locations.contains("nas") || clip.offload == .done {
            Image(systemName: "checkmark").foregroundStyle(Theme.teal).accessibilityLabel("On NAS")
        }
    }

    private var empty: some View {
        Tray {
            VStack(spacing: 8) {
                Image(systemName: "film.stack").font(.system(size: 28, weight: .light)).foregroundStyle(tone.tertiary)
                Text("No clips yet").font(.system(size: 17, weight: .semibold)).foregroundStyle(Theme.ink)
                Text("When a game starts, Nebula records it in OBS and files the clip in that game’s own folder.")
                    .font(.system(size: 15))
                    .foregroundStyle(Theme.ink2)
                    .multilineTextAlignment(.center)
            }
            .padding(24)
            .frame(maxWidth: .infinity)
        }
    }

    private var gamesByRecent: [Game] {
        let clips = model.studio?.clips ?? []
        return (model.studio?.games ?? []).sorted { left, right in
            let leftDate = clips.first { $0.game.id == left.id }?.createdAt ?? .distantPast
            let rightDate = clips.first { $0.game.id == right.id }?.createdAt ?? .distantPast
            return leftDate > rightDate
        }
    }

    private func schedule() {
        searchTask?.cancel()
        searchTask = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 250_000_000)
            guard !Task.isCancelled else { return }
            model.refreshClips(query: query, gameId: gameID)
        }
    }
}
