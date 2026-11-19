import SwiftUI

struct NowView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.tone) private var tone

    var body: some View {
        let session = model.studio?.session
        let isPlaying = session?.playing == true
        let layout = model.prefs.nowLayout

        VStack(alignment: .leading, spacing: Theme.Space.bentoGap) {
            if isPlaying, let session = session {
                playingHero(session, layout: layout)
                tileContainer {
                    playingTiles(session, layout: layout)
                }
                if layout == .game {
                    TimelineView(.periodic(from: .now, by: 1.0)) { context in
                        highlightsStrip(
                            marks: session.highlights,
                            duration: max(1.0, model.elapsed(at: context.date)),
                            playhead: model.elapsed(at: context.date),
                            live: true
                        )
                    }
                }
                recentSection(layout: layout)
            } else if let last = session?.lastSession {
                idleHero(last, layout: layout)
                tileContainer {
                    idleTiles(session: session, last: last, layout: layout)
                }
                if layout == .game {
                    highlightsStrip(
                        marks: session?.highlights ?? [],
                        duration: max(1.0, last.duration),
                        playhead: last.duration,
                        live: false
                    )
                }
                recentSection(layout: layout)
            } else {
                readyHero
            }
        }
    }

    // MARK: - First-Run / Empty Session (§9.2)

    private var readyHero: some View {
        Tray(role: .hero) {
            ReadingSurface(radius: Theme.Radius.heroCard, kind: .hero) {
                VStack(alignment: .leading, spacing: 8) {
                    StatusChip(style: .idle)
                    Text("Ready when you are")
                        .font(Theme.TypeScale.cardTitleLarge)
                        .foregroundStyle(Theme.ink)
                    Text("Nebula starts recording when a game launches on Studio PC.")
                        .font(Theme.TypeScale.body)
                        .foregroundStyle(Theme.ink2)
                }
                .padding(18)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    // MARK: - Playing Heroes (2f Bento, 2g Game-aware, 2h Clips-led)

    private func playingHero(_ session: Session, layout: NowLayout) -> some View {
        Tray(role: .hero) {
            ReadingSurface(radius: Theme.Radius.heroCard, kind: .hero) {
                ZStack(alignment: .trailing) {
                    if layout == .game {
                        heroCoverArt(gameID: session.game?.id)
                    }
                    Group {
                        switch layout {
                        case .bento:
                            bentoPlayingBody(session)
                        case .game:
                            gamePlayingBody(session)
                        case .clips:
                            clipsPlayingBody(session)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private func bentoPlayingBody(_ session: Session) -> some View {
        VStack(alignment: .leading, spacing: Theme.Space.bentoGap) {
            HStack {
                sessionStatusChip(session)
                Spacer()
                Text(outputLabel(session.output))
                    .font(Theme.TypeScale.subtitle)
                    .foregroundStyle(Theme.ink2)
            }
            HStack(alignment: .bottom, spacing: 10) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(session.game?.name ?? "Studio PC")
                        .font(Theme.TypeScale.cardTitle)
                        .foregroundStyle(Theme.ink)
                        .lineLimit(1)
                    if session.state == "bufferOnly" {
                        Text("Replay buffer · \(model.studio?.settings.replayLabel ?? "30 s")")
                            .font(Theme.TypeScale.bufferLine)
                            .foregroundStyle(Theme.violetLight)
                    } else {
                        TimelineView(.periodic(from: .now, by: 1.0)) { context in
                            RollingClock(
                                seconds: model.elapsed(at: context.date),
                                paused: session.state == "paused",
                                size: Theme.Size.clockBento
                            )
                        }
                    }
                }
                Spacer(minLength: 4)
                transportControls(session)
            }
        }
        .padding(18)
    }

    private func gamePlayingBody(_ session: Session) -> some View {
        VStack(alignment: .leading, spacing: Theme.Space.bentoGap) {
            HStack(spacing: 10) {
                sessionStatusChip(session)
                Text(gameAndSceneLabel(session))
                    .font(Theme.TypeScale.subtitle)
                    .foregroundStyle(Theme.inkSoft)
                    .lineLimit(1)
                Spacer(minLength: 0)
            }
            HStack(alignment: .bottom, spacing: 10) {
                if session.state == "bufferOnly" {
                    Text("Replay buffer · \(model.studio?.settings.replayLabel ?? "30 s")")
                        .font(Theme.TypeScale.bufferLine)
                        .foregroundStyle(Theme.violetLight)
                } else {
                    TimelineView(.periodic(from: .now, by: 1.0)) { context in
                        RollingClock(
                            seconds: model.elapsed(at: context.date),
                            paused: session.state == "paused",
                            size: Theme.Size.clockGame
                        )
                    }
                }
                Spacer(minLength: 4)
                transportControls(session)
            }
        }
        .padding(18)
    }

    private func clipsPlayingBody(_ session: Session) -> some View {
        HStack(alignment: .center, spacing: Theme.Space.bentoGap) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 7) {
                    Circle()
                        .fill(session.state == "paused" ? Theme.ink2 : Theme.gold)
                        .frame(width: 6, height: 6)
                    Eyebrow(
                        text: "\(session.state == "paused" ? "PAUSED" : (session.state == "bufferOnly" ? "BUFFER" : "REC")) · \(session.game?.name ?? "Studio PC")",
                        color: session.state == "paused" ? Theme.ink2 : Theme.gold
                    )
                }
                if session.state == "bufferOnly" {
                    Text("Replay buffer · \(model.studio?.settings.replayLabel ?? "30 s")")
                        .font(Theme.TypeScale.cardTitle)
                        .foregroundStyle(Theme.violetLight)
                } else {
                    TimelineView(.periodic(from: .now, by: 1.0)) { context in
                        RollingClock(
                            seconds: model.elapsed(at: context.date),
                            paused: session.state == "paused",
                            size: Theme.Size.clockClips
                        )
                    }
                }
            }
            Spacer(minLength: 4)
            transportControls(session)
        }
        .padding(.vertical, 16)
        .padding(.leading, 18)
        .padding(.trailing, 14)
    }

    private func coverReference(gameID: String?) -> String? {
        guard let gameID = gameID, let studio = model.studio else { return nil }
        if let cover = studio.games.first(where: { $0.id == gameID })?.coverURL, !cover.isEmpty {
            return cover
        }
        for clip in studio.clips where clip.game.id == gameID {
            if let still = clip.thumbnailURL, !still.isEmpty { return still }
        }
        return nil
    }

    @ViewBuilder private func heroCoverArt(gameID: String?) -> some View {
        // A real cover wins; with none, the game's newest clip still. Neither
        // means ClipStill's abstract backdrop, never an invented picture.
        let cover = coverReference(gameID: gameID)
        ClipStill(reference: cover, seed: stillSeed(gameID ?? "game"))
            .frame(width: 210)
            .opacity(0.50)
            .mask(
                LinearGradient(
                    colors: [Theme.clear, Theme.ink],
                    startPoint: .leading,
                    endPoint: UnitPoint(x: 0.70, y: 0.50)
                )
            )
            .allowsHitTesting(false)
    }

    // MARK: - Transport Controls (48pt Glass Pause Bars + Only Solid Coral Stop Circle)

    private func transportControls(_ session: Session) -> some View {
        let enabled = model.controlsEnabled
        return HStack(spacing: Theme.Space.chipGap) {
            if session.state == "bufferOnly" {
                Button {
                    model.command("replay.save")
                } label: {
                    Text("Save replay")
                        .font(Theme.TypeScale.segment)
                        .foregroundStyle(Theme.ink)
                        .padding(.horizontal, 14)
                        .frame(height: Theme.Size.transportButton)
                        .background(Capsule().fill(Theme.violet.opacity(Theme.Opacity.primaryFill)))
                        .overlay(Capsule().stroke(Theme.violet.opacity(Theme.Opacity.primaryRing), lineWidth: Theme.Stroke.hairline))
                }
                .buttonStyle(PressScaleStyle())
                .accessibilityLabel("Save replay")
            } else {
                Button {
                    model.session(session.state == "paused" ? "session.resume" : "session.pause")
                } label: {
                    GlassCircle(
                        system: session.state == "paused" ? "play.fill" : "",
                        size: Theme.Size.transportButton
                    )
                    .overlay {
                        if session.state != "paused" {
                            HStack(spacing: 4.5) {
                                RoundedRectangle(cornerRadius: Theme.Radius.pauseBar, style: .continuous)
                                    .frame(width: 4.4, height: 15)
                                RoundedRectangle(cornerRadius: Theme.Radius.pauseBar, style: .continuous)
                                    .frame(width: 4.4, height: 15)
                            }
                            .foregroundStyle(Theme.ink)
                        }
                    }
                }
                .buttonStyle(PressScaleStyle())
                .accessibilityLabel(session.state == "paused" ? "Resume recording" : "Pause recording")
            }

            // Stop is the ONLY solid coral circle in the entire app.
            Button {
                model.session("session.stop")
            } label: {
                ZStack {
                    Circle()
                        .fill(Theme.coral)
                    RoundedRectangle(cornerRadius: Theme.Radius.stopGlyph, style: .continuous)
                        .fill(Theme.inkDark)
                        .frame(width: 13, height: 13)
                }
                .frame(width: Theme.Size.transportButton, height: Theme.Size.transportButton)
            }
            .buttonStyle(PressScaleStyle())
            .accessibilityLabel("Stop recording")
        }
        .disabled(!enabled)
        .opacity(enabled ? 1.0 : Theme.Opacity.disabled)
    }

    // MARK: - Idle Heroes (§9.2)

    private func idleHero(_ last: LastSession, layout: NowLayout) -> some View {
        Tray(role: .hero) {
            ReadingSurface(radius: Theme.Radius.heroCard, kind: .hero) {
                ZStack(alignment: .trailing) {
                    if layout == .game {
                        heroCoverArt(gameID: last.game.id)
                    }
                    if layout == .game {
                        gameIdleBody(last)
                    } else {
                        standardIdleBody(last)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private func standardIdleBody(_ last: LastSession) -> some View {
        let online = model.link == .online
        return VStack(alignment: .leading, spacing: Theme.Space.bentoGap) {
            HStack {
                StatusChip(style: .idle)
                Spacer()
                HStack(spacing: 6) {
                    Circle()
                        .fill(online ? Theme.teal : tone.tertiary)
                        .frame(width: 6, height: 6)
                    Text(online ? "Studio PC online" : "Studio PC is offline")
                        .font(Theme.TypeScale.subtitle)
                        .foregroundStyle(online ? Theme.teal : tone.tertiary)
                }
            }

            VStack(alignment: .leading, spacing: 3) {
                Eyebrow(text: "Last session · \(StudioFormat.time(last.endedAt))")
                HStack(alignment: .firstTextBaseline, spacing: 0) {
                    Text(last.game.name)
                        .font(Theme.TypeScale.cardTitleLarge)
                        .foregroundStyle(Theme.ink)
                    Text(last.duration > 1 ? " · \(StudioFormat.clock(last.duration))" : " · —")
                        .font(Theme.TypeScale.bufferLine)
                        .foregroundStyle(tone.tertiary)
                }
                .lineLimit(1)

                Text("\(last.highlightCount) highlights · \(StudioFormat.bytes(last.bytes)) · \(offloadLine(last.offload))")
                    .font(Theme.TypeScale.subtitle)
                    .foregroundStyle(Theme.ink2)
                    .lineLimit(1)
            }

            PrimaryPill(
                title: "Start recording",
                system: "record.circle",
                toneStyle: .coralTint,
                compact: true
            ) {
                model.session("session.start")
            }
            .disabled(!model.controlsEnabled)
            .opacity(model.controlsEnabled ? 1.0 : Theme.Opacity.disabled)
        }
        .padding(18)
    }

    private func gameIdleBody(_ last: LastSession) -> some View {
        VStack(alignment: .leading, spacing: Theme.Space.bentoGap) {
            HStack(spacing: 10) {
                StatusChip(style: .idle, customTitle: "Last played")
                Text(StudioFormat.relative(last.endedAt, now: Date()))
                    .font(Theme.TypeScale.subtitle)
                    .foregroundStyle(Theme.inkSoft)
                Spacer(minLength: 0)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(last.game.name)
                    .font(Theme.TypeScale.gameHeroTitle)
                    .foregroundStyle(Theme.ink)
                    .lineLimit(1)
                if let achievement = model.studio?.session.achievement, !achievement.isEmpty {
                    Text(achievement)
                        .font(Theme.TypeScale.subtitle)
                        .foregroundStyle(Theme.inkSoft)
                        .lineLimit(1)
                }
            }

            HStack(spacing: Theme.Space.chipGap) {
                Button {
                    model.session("session.start")
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "record.circle")
                            .font(Theme.TypeScale.icon(14, weight: .semibold))
                            .foregroundStyle(Theme.coral)
                        Text("Record")
                            .font(Theme.TypeScale.controlSemibold)
                            .foregroundStyle(Theme.coralText)
                    }
                    .frame(maxWidth: .infinity, minHeight: Theme.Size.compactPillHeight)
                    .background(
                        RoundedRectangle(cornerRadius: Theme.Radius.actionPill, style: .continuous)
                            .fill(Theme.coral.opacity(0.14))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: Theme.Radius.actionPill, style: .continuous)
                            .stroke(Theme.coral.opacity(0.45), lineWidth: Theme.Stroke.hairline)
                    )
                }
                .buttonStyle(PressScaleStyle())
                .disabled(!model.controlsEnabled)
                .opacity(model.controlsEnabled ? 1.0 : Theme.Opacity.disabled)

                Button {} label: {
                    VStack(spacing: 1) {
                        Text("Launch on PC")
                            .font(Theme.TypeScale.segment)
                            .foregroundStyle(Theme.ink)
                        Text("Coming soon")
                            .font(Theme.TypeScale.tabLabel)
                            .foregroundStyle(tone.tertiary)
                    }
                    .frame(maxWidth: .infinity, minHeight: Theme.Size.compactPillHeight)
                    .background(
                        RoundedRectangle(cornerRadius: Theme.Radius.actionPill, style: .continuous)
                            .fill(Theme.ink.opacity(0.10))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: Theme.Radius.actionPill, style: .continuous)
                            .stroke(Theme.specular.opacity(0.16), lineWidth: Theme.Stroke.hairline)
                    )
                }
                .disabled(true)
                .opacity(Theme.Opacity.disabled)
                .accessibilityLabel("Launch on PC, Coming soon")
            }
        }
        .padding(18)
    }

    // MARK: - Bento Tiles (§9.1, §9.2)

    private func tileContainer<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        Group {
            if typeSize >= .accessibility1 {
                VStack(spacing: Theme.Space.bentoGap) {
                    content()
                }
            } else {
                HStack(alignment: .top, spacing: Theme.Space.bentoGap) {
                    content()
                }
            }
        }
    }

    @ViewBuilder private func playingTiles(_ session: Session, layout: NowLayout) -> some View {
        switch layout {
        case .bento:
            storageTile(session)
            encoderTile
        case .game:
            gameStatsTile
            storageTile(session)
        case .clips:
            highlightsCountTile(marks: session.highlights, subtitle: "this session")
            audioMetersTile
        }
    }

    @ViewBuilder private func idleTiles(session: Session?, last: LastSession, layout: NowLayout) -> some View {
        switch layout {
        case .bento:
            storageTile(session)
            offloadTile
        case .game:
            weekPlaytimeTile(gameID: last.game.id)
            storageTile(session)
        case .clips:
            highlightsCountTile(
                marks: Array(repeating: Highlight(at: 0, label: nil, kind: "manual"), count: max(0, last.highlightCount)),
                subtitle: "last session"
            )
            libraryTile(session)
        }
    }

    private func tileCard<Content: View>(@ViewBuilder content: @escaping () -> Content) -> some View {
        Tray(role: .tile) {
            ReadingSurface(radius: Theme.Radius.tileCard) {
                VStack(alignment: .leading, spacing: 6) {
                    content()
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
                .frame(maxWidth: .infinity, minHeight: 112, alignment: .topLeading)
            }
        }
    }

    /// The used fraction, only when the PC sent both numbers and the total is real.
    /// Anything else is unknown: no arc, an em dash, never a guessed percent.
    private func usedFraction(_ session: Session?) -> Double? {
        guard let free = session?.storageFreeBytes,
              let total = session?.storageTotalBytes,
              total > 0, free >= 0
        else { return nil }
        let used = Double(total - min(free, total)) / Double(total)
        return min(1.0, max(0.0, used))
    }

    /// Storage tile: the ring is drawn from storageFreeBytes + storageTotalBytes
    /// when both are known; otherwise it stays an empty track with an em dash.
    private func storageTile(_ session: Session?) -> some View {
        let freeBytes = session?.storageFreeBytes
        let freeText = StudioFormat.bytes(freeBytes)
        let daysText = StudioFormat.remaining(session?.estimatedRemaining) ?? "—"
        let fraction = usedFraction(session)
        let percentText = fraction.map { "\(Int(($0 * 100).rounded()))%" } ?? "—"
        let usedSpoken = fraction == nil ? "used unknown" : "\(percentText) used"

        return tileCard {
            HStack(spacing: Theme.Space.bentoGap) {
                ZStack {
                    Circle()
                        .stroke(Theme.ink.opacity(0.08), lineWidth: Theme.Stroke.storageRing)
                    if let fraction = fraction {
                        Circle()
                            .trim(from: 0, to: CGFloat(fraction))
                            .stroke(
                                Theme.violet,
                                style: StrokeStyle(lineWidth: Theme.Stroke.storageRing, lineCap: .round)
                            )
                            .rotationEffect(.degrees(-90))
                    }
                    Text(percentText)
                        .font(Theme.TypeScale.ringPercent)
                        .foregroundStyle(fraction == nil ? tone.tertiary : Theme.ink)
                }
                .frame(width: Theme.Size.storageRing, height: Theme.Size.storageRing)

                VStack(alignment: .leading, spacing: 2) {
                    Eyebrow(text: "Storage")
                    Text(freeText)
                        .font(Theme.TypeScale.controlSemibold)
                        .foregroundStyle(Theme.ink)
                        .lineLimit(1)
                    Text(daysText)
                        .font(Theme.TypeScale.caption)
                        .foregroundStyle(tone.tertiary)
                        .lineLimit(1)
                }
            }
            .frame(maxHeight: .infinity, alignment: .center)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Storage, \(freeText) free, \(usedSpoken), \(daysText)")
    }

    private var encoderTile: some View {
        let drops = model.studio?.stats?.droppedFrames
        let rate = model.studio?.stats?.bitrateMbps

        return tileCard {
            HStack(alignment: .firstTextBaseline) {
                Eyebrow(text: "Encoder")
                Spacer(minLength: 4)
                Text(dropsText(drops))
                    .font(Theme.TypeScale.captionSemibold)
                    .foregroundStyle(dropsColor(drops))
            }
            if let rate = rate {
                HStack(alignment: .firstTextBaseline, spacing: 3) {
                    Text(String(format: "%.1f", rate))
                        .font(Theme.TypeScale.cardTitle)
                        .foregroundStyle(Theme.ink)
                    Text("Mb/s")
                        .font(Theme.TypeScale.captionMedium)
                        .foregroundStyle(tone.tertiary)
                }
            } else {
                Text("—")
                    .font(Theme.TypeScale.cardTitle)
                    .foregroundStyle(tone.tertiary)
            }
            sparkline(model.bitrate)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Encoder, \(dropsText(drops)), \(rate.map { String(format: "%.1f megabits per second", $0) } ?? "bitrate unknown")")
    }

    private var gameStatsTile: some View {
        let fps = model.studio?.stats?.gameFps
        let gpu = model.studio?.stats?.gpuTempC
        let bars = Array(model.fpsSamples.suffix(16))

        return tileCard {
            HStack(alignment: .firstTextBaseline) {
                Eyebrow(text: "Game")
                Spacer(minLength: 4)
                Text(gpu.map { "GPU \($0)°" } ?? "GPU —")
                    .font(Theme.TypeScale.captionRegularTabular)
                    .foregroundStyle(tone.tertiary)
            }
            if let fps = fps {
                HStack(alignment: .firstTextBaseline, spacing: 3) {
                    Text("\(fps)")
                        .font(Theme.TypeScale.statMetric)
                        .foregroundStyle(Theme.ink)
                    Text("fps")
                        .font(Theme.TypeScale.subtitle)
                        .foregroundStyle(tone.tertiary)
                }
            } else {
                Text("—")
                    .font(Theme.TypeScale.statMetric)
                    .foregroundStyle(tone.tertiary)
            }
            barStrip(values: bars)
        }
    }

    private func weekPlaytimeTile(gameID: String) -> some View {
        let game = model.studio?.games.first(where: { $0.id == gameID }) ?? model.studio?.games.first
        let week = game?.weekPlaytime ?? []
        let totalSeconds = week.reduce(0, +)
        let hours = Int(totalSeconds) / 3600
        let mins = (Int(totalSeconds) % 3600) / 60
        let clipCount = game?.clipCount

        return tileCard {
            HStack(alignment: .firstTextBaseline) {
                Eyebrow(text: "This week")
                Spacer(minLength: 4)
                Text(clipCount.map { "\($0) clips" } ?? "—")
                    .font(Theme.TypeScale.caption)
                    .foregroundStyle(tone.tertiary)
            }
            if week.isEmpty {
                Text("—")
                    .font(Theme.TypeScale.statMetric)
                    .foregroundStyle(tone.tertiary)
            } else {
                HStack(alignment: .firstTextBaseline, spacing: 2) {
                    Text("\(hours)h \(mins)")
                        .font(Theme.TypeScale.statMetric)
                        .foregroundStyle(Theme.ink)
                    Text("m")
                        .font(Theme.TypeScale.subtitle)
                        .foregroundStyle(tone.tertiary)
                }
            }
            barStrip(values: week)
        }
    }

    private var offloadTile: some View {
        let active = (model.studio?.clips ?? []).filter { $0.offload.isActive }
        let known = model.studio?.settings.offloadTarget.flatMap { $0.isEmpty ? nil : $0 }
        let target = known ?? "—"

        return tileCard {
            if active.isEmpty {
                Eyebrow(text: "Offload")
                if known != nil {
                    Text("All synced")
                        .font(Theme.TypeScale.cardTitle)
                        .foregroundStyle(Theme.teal)
                    Text("To \(target)")
                        .font(Theme.TypeScale.caption)
                        .foregroundStyle(tone.tertiary)
                } else {
                    Text("—")
                        .font(Theme.TypeScale.cardTitle)
                        .foregroundStyle(tone.tertiary)
                }
            } else {
                let movingProgress = active.compactMap { clip -> Double? in
                    if case let .moving(progress, _) = clip.offload { return progress }
                    return nil
                }.max()
                let bytesRemaining: Int64? = {
                    let values = active.compactMap { clip -> Int64? in
                        if case let .moving(_, left) = clip.offload { return left }
                        return nil
                    }
                    return values.isEmpty ? nil : values.reduce(0, +)
                }()

                HStack(alignment: .firstTextBaseline) {
                    Eyebrow(text: "Offload")
                    Spacer(minLength: 4)
                    Text(movingProgress.map { "\(Int(($0 * 100).rounded()))%" } ?? "—")
                        .font(Theme.TypeScale.captionTabular)
                        .foregroundStyle(Theme.amberDeep)
                }
                Text("To \(target)")
                    .font(Theme.TypeScale.controlSemibold)
                    .foregroundStyle(Theme.ink)
                    .lineLimit(1)
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule()
                            .fill(Theme.ink.opacity(0.06))
                        if let progress = movingProgress {
                            Capsule()
                                .fill(LinearGradient(colors: [Theme.amberDeep, Theme.amberPale], startPoint: .leading, endPoint: .trailing))
                                .frame(width: max(4, geo.size.width * CGFloat(min(1.0, max(0.0, progress)))))
                        }
                    }
                }
                .frame(height: 5)

                Text("\(active.count) clips · \(StudioFormat.bytes(bytesRemaining)) left")
                    .font(Theme.TypeScale.caption)
                    .foregroundStyle(tone.tertiary)
                    .lineLimit(1)
            }
        }
    }

    private func highlightsCountTile(marks: [Highlight], subtitle: String) -> some View {
        tileCard {
            Eyebrow(text: "Highlights")
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text("\(marks.count)")
                    .font(Theme.TypeScale.statMetric)
                    .foregroundStyle(Theme.ink)
                Text(subtitle)
                    .font(Theme.TypeScale.subtitle)
                    .foregroundStyle(tone.tertiary)
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Theme.ink.opacity(0.06))
                        .frame(height: 6)
                    ForEach(Array(marks.prefix(6).enumerated()), id: \.offset) { idx, mark in
                        let frac = marks.count == 1 ? 0.5 : Double(idx + 1) / Double(marks.count + 1)
                        Circle()
                            .fill(mark.kind == "manual" ? Theme.amber : Theme.violetLight)
                            .frame(width: 10, height: 10)
                            .offset(x: max(0, geo.size.width * CGFloat(frac) - 5))
                    }
                }
            }
            .frame(height: 10)
        }
    }

    private var audioMetersTile: some View {
        tileCard {
            Eyebrow(text: "Audio")
            if let audio = model.studio?.stats?.audio {
                VStack(spacing: 7) {
                    audioBar(label: "Game", level: audio.game, start: Theme.violet, end: Theme.violetLight)
                    audioBar(label: "Mic", level: audio.mic, start: Theme.teal, end: Theme.tealPale)
                    audioBar(label: "Chat", level: audio.chat, start: Theme.magenta, end: Theme.magentaLight)
                }
            } else {
                Text("—")
                    .font(Theme.TypeScale.statMetric)
                    .foregroundStyle(tone.tertiary)
            }
        }
    }

    private func libraryTile(_ session: Session?) -> some View {
        let free = session?.storageFreeBytes
        let pending = (model.studio?.clips ?? []).contains { $0.offload.isActive }
        let known = model.studio?.settings.offloadTarget.flatMap { $0.isEmpty ? nil : $0 }
        let target = known ?? "—"

        return tileCard {
            Eyebrow(text: "Library")
            if let free = free {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text(StudioFormat.bytes(free))
                        .font(Theme.TypeScale.cardTitleLarge)
                        .foregroundStyle(Theme.ink)
                    Text("free")
                        .font(Theme.TypeScale.subtitle)
                        .foregroundStyle(tone.tertiary)
                }
            } else {
                Text("—")
                    .font(Theme.TypeScale.statMetric)
                    .foregroundStyle(tone.tertiary)
            }
            if pending || known != nil {
                HStack(spacing: 6) {
                    Circle()
                        .fill(pending ? Theme.amber : Theme.teal)
                        .frame(width: 6, height: 6)
                    Text(pending ? "Offloading to \(target)" : "All synced to \(target)")
                        .font(Theme.TypeScale.caption)
                        .foregroundStyle(pending ? Theme.amber : Theme.teal)
                        .lineLimit(1)
                }
            } else {
                Text("—")
                    .font(Theme.TypeScale.caption)
                    .foregroundStyle(tone.tertiary)
            }
        }
    }

    // MARK: - 2g Highlights Strip (§9.1)

    private func highlightsStrip(marks: [Highlight], duration: Double, playhead: Double, live: Bool) -> some View {
        Tray(role: .tile) {
            ReadingSurface(radius: Theme.Radius.tileCard) {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(alignment: .firstTextBaseline) {
                        Eyebrow(text: live ? "Highlights · auto-marked" : "Last session highlights")
                        Spacer()
                        Text("\(marks.count)")
                            .font(Theme.TypeScale.controlSemibold)
                            .foregroundStyle(Theme.violetPale)
                    }

                    GeometryReader { geo in
                        let w = geo.size.width
                        let fillFrac = live ? min(1.0, max(0.0, playhead / max(duration, 1.0))) : 1.0
                        ZStack(alignment: .leading) {
                            RoundedRectangle(cornerRadius: Theme.Radius.highlightStrip, style: .continuous)
                                .fill(Theme.ink.opacity(0.04))
                                .frame(height: 24)
                            RoundedRectangle(cornerRadius: Theme.Radius.highlightStrip, style: .continuous)
                                .fill(
                                    LinearGradient(
                                        colors: [Theme.violet.opacity(0.06), Theme.violet.opacity(0.22)],
                                        startPoint: .leading,
                                        endPoint: .trailing
                                    )
                                )
                                .frame(width: w * CGFloat(fillFrac), height: 24)

                            ForEach(Array(marks.enumerated()), id: \.offset) { _, mark in
                                let x = min(max(2, w * CGFloat(mark.at / max(duration, 1.0))), max(2, w - 4))
                                RoundedRectangle(cornerRadius: Theme.Radius.bar, style: .continuous)
                                    .fill(mark.kind == "manual" ? Theme.amber : Theme.violetLight)
                                    .frame(width: 3, height: 18)
                                    .offset(x: x)
                            }

                            if live {
                                RoundedRectangle(cornerRadius: Theme.Radius.playhead, style: .continuous)
                                    .fill(Theme.gold)
                                    .frame(width: 2, height: 30)
                                    .shadow(color: Theme.gold.opacity(0.75), radius: 4)
                                    .offset(x: min(max(0, w * CGFloat(fillFrac) - 1), max(0, w - 2)))
                            }
                        }
                    }
                    .frame(height: 28)

                    if let first = marks.first {
                        HStack {
                            Text("\(first.label ?? "Mark") · \(shortDuration(first.at))")
                            Spacer()
                            if marks.count > 1, let last = marks.last {
                                Text("\(last.label ?? "Mark") · \(shortDuration(last.at))")
                            }
                        }
                        .font(Theme.TypeScale.caption)
                        .foregroundStyle(tone.tertiary)
                        .lineLimit(1)
                    } else {
                        Text(live ? "No marks yet" : "Last session")
                            .font(Theme.TypeScale.caption)
                            .foregroundStyle(tone.tertiary)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
            }
        }
    }

    // MARK: - Recent Clips (Stack for 2f/2h, Two-up Row for 2g)

    private func recentSection(layout: NowLayout) -> some View {
        let clips = Array((model.studio?.clips ?? []).prefix(3))
        return Group {
            if !clips.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(alignment: .firstTextBaseline) {
                        Text("Recent clips")
                            .font(Theme.TypeScale.sectionHeading)
                            .foregroundStyle(Theme.ink)
                        Spacer()
                        Button {
                            model.requestedTab = .clips
                        } label: {
                            Text("See all")
                                .font(Theme.TypeScale.body)
                                .foregroundStyle(Theme.violetLight)
                                .frame(minHeight: Theme.Size.minHitTarget)
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.horizontal, Theme.Space.headerInset)

                    if layout == .game {
                        twoUpClips(Array(clips.prefix(2)))
                    } else {
                        ClipStack(clips: clips, richFront: layout == .clips)
                    }
                }
                .padding(.top, 4)
            }
        }
    }

    private func twoUpClips(_ clips: [Clip]) -> some View {
        HStack(spacing: Theme.Space.gridGap) {
            ForEach(clips) { clip in
                Button {
                    model.clipRoute = clip.id
                } label: {
                    ZStack(alignment: .bottomLeading) {
                        ClipStill(reference: clip.thumbnailURL, seed: stillSeed(clip.id))
                        LinearGradient(
                            colors: [Theme.clear, Theme.scrimBase.opacity(0.90)],
                            startPoint: UnitPoint(x: 0.5, y: 0.25),
                            endPoint: .bottom
                        )
                        VStack(alignment: .leading, spacing: 3) {
                            Text("\(clip.game.name) · \(clip.duration.map(shortDuration) ?? "—")")
                                .font(Theme.TypeScale.filterChip)
                                .foregroundStyle(Theme.ink)
                                .lineLimit(1)
                            clipLocationBadge(clip)
                        }
                        .padding(12)
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: Theme.Size.gameCoverHeight)
                    .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.settingsGroup, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: Theme.Radius.settingsGroup, style: .continuous)
                            .stroke(Theme.ink.opacity(0.12), lineWidth: Theme.Stroke.hairline)
                    )
                }
                .buttonStyle(PressScaleStyle())
            }
        }
    }

    @ViewBuilder private func clipLocationBadge(_ clip: Clip) -> some View {
        let target = model.studio?.settings.offloadTarget ?? "—"
        if clip.writing {
            Text("Writing")
                .font(Theme.TypeScale.captionSemibold)
                .foregroundStyle(Theme.violetPale)
        } else if clip.offload.isActive {
            HStack(spacing: 4) {
                Image(systemName: "arrow.up")
                Text("Offloading")
            }
            .font(Theme.TypeScale.captionSemibold)
            .foregroundStyle(Theme.amberDeep)
        } else if clip.locations.contains("nas") || clip.offload == .done {
            HStack(spacing: 4) {
                Image(systemName: "checkmark")
                Text(target)
            }
            .font(Theme.TypeScale.captionSemibold)
            .foregroundStyle(Theme.teal)
        } else {
            Text("Studio PC")
                .font(Theme.TypeScale.caption)
                .foregroundStyle(Theme.ink2)
        }
    }

    // MARK: - Helpers & Charts

    private func sessionStatusChip(_ session: Session) -> some View {
        switch session.state {
        case "paused":
            return StatusChip(style: .paused)
        case "bufferOnly":
            return StatusChip(style: .buffer)
        default:
            return StatusChip(style: .rec)
        }
    }

    private func outputLabel(_ output: Output) -> String {
        if output.resolution.isEmpty || output.fps <= 0 || output.encoder.isEmpty {
            return "—"
        }
        return output.line
    }

    private func gameAndSceneLabel(_ session: Session) -> String {
        let game = session.game?.name ?? "Studio PC"
        if session.scene.isEmpty { return game }
        return "\(game) · \(session.scene)"
    }

    private func dropsText(_ drops: Int?) -> String {
        guard let drops = drops else { return "—" }
        return drops == 1 ? "1 drop" : "\(drops) drops"
    }

    private func dropsColor(_ drops: Int?) -> Color {
        guard let drops = drops else { return tone.tertiary }
        if drops == 0 { return Theme.teal }
        if drops > 30 { return Theme.coral }
        return Theme.amber
    }

    private func sparkline(_ samples: [Double]) -> some View {
        GeometryReader { geo in
            let w = geo.size.width
            let h = geo.size.height
            let minVal = (samples.min() ?? 0.0) * 0.92
            let maxVal = max((samples.max() ?? 1.0) * 1.05, minVal + 1.0)

            ZStack {
                if samples.count > 1 {
                    Path { path in
                        path.move(to: CGPoint(x: 0, y: h))
                        for (index, sample) in samples.enumerated() {
                            let x = w * CGFloat(index) / CGFloat(samples.count - 1)
                            let norm = (sample - minVal) / (maxVal - minVal)
                            let y = h * (1.0 - CGFloat(min(1.0, max(0.0, norm))))
                            path.addLine(to: CGPoint(x: x, y: y))
                        }
                        path.addLine(to: CGPoint(x: w, y: h))
                        path.closeSubpath()
                    }
                    .fill(
                        LinearGradient(
                            colors: [Theme.violet.opacity(0.45), Theme.clear],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )

                    Path { path in
                        for (index, sample) in samples.enumerated() {
                            let x = w * CGFloat(index) / CGFloat(samples.count - 1)
                            let norm = (sample - minVal) / (maxVal - minVal)
                            let y = h * (1.0 - CGFloat(min(1.0, max(0.0, norm))))
                            if index == 0 {
                                path.move(to: CGPoint(x: x, y: y))
                            } else {
                                path.addLine(to: CGPoint(x: x, y: y))
                            }
                        }
                    }
                    .stroke(Theme.violetLight, style: StrokeStyle(lineWidth: Theme.Stroke.sparkline, lineCap: .round, lineJoin: .round))
                } else {
                    Rectangle()
                        .fill(Theme.ink.opacity(0.06))
                        .frame(height: 2)
                }
            }
        }
        .frame(height: Theme.Size.sparklineHeight)
    }

    private func barStrip(values: [Double]) -> some View {
        let peak = max(values.max() ?? 1.0, 0.1)
        return HStack(alignment: .bottom, spacing: 3) {
            if values.isEmpty {
                ForEach(0 ..< 7, id: \.self) { _ in
                    RoundedRectangle(cornerRadius: Theme.Radius.bar, style: .continuous)
                        .fill(Theme.ink.opacity(0.08))
                        .frame(maxWidth: .infinity)
                        .frame(height: 4)
                }
            } else {
                ForEach(Array(values.enumerated()), id: \.offset) { idx, value in
                    let isLast = idx == values.count - 1
                    let h = max(4.0, 22.0 * CGFloat(min(1.0, max(0.0, value / peak))))
                    RoundedRectangle(cornerRadius: Theme.Radius.bar, style: .continuous)
                        .fill(isLast ? Theme.gold : Theme.violetLight.opacity(0.55))
                        .frame(maxWidth: .infinity)
                        .frame(height: h)
                }
            }
        }
        .frame(height: 22)
    }

    private func audioBar(label: String, level: Double, start: Color, end: Color) -> some View {
        let clamped = CGFloat(min(1.0, max(0.0, level)))
        return HStack(spacing: 8) {
            Text(label)
                .font(Theme.TypeScale.caption)
                .foregroundStyle(Theme.ink2)
                .frame(width: 34, alignment: .leading)
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Theme.ink.opacity(0.06))
                    Capsule()
                        .fill(LinearGradient(colors: [start, end], startPoint: .leading, endPoint: .trailing))
                        .frame(width: geo.size.width * clamped)
                        .animation(tone.isStill ? nil : Theme.spring, value: clamped)
                }
            }
            .frame(height: 5)
        }
    }

    private func offloadLine(_ offload: Offload) -> String {
        let target = model.studio?.settings.offloadTarget ?? "—"
        switch offload {
        case .done:
            return "on \(target)"
        case .queued:
            return "queued"
        case let .moving(progress, _):
            return "offloading \(Int((progress * 100).rounded()))%"
        case let .failed(error):
            return error
        case .none:
            return "on Studio PC"
        }
    }

    private func shortDuration(_ seconds: Double) -> String {
        let whole = max(0, Int(seconds.rounded(.down)))
        if whole >= 3600 {
            return StudioFormat.clock(seconds)
        }
        return String(format: "%d:%02d", whole / 60, whole % 60)
    }
}

// MARK: - Physically Stacked Recent Clips (§9.1: 1.0 / 0.92 / 0.84 scale, 1.0 / 0.72 / 0.45 opacity)

struct ClipStack: View {
    var clips: [Clip]
    var richFront: Bool = false
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    @State private var index = 0

    var body: some View {
        if clips.isEmpty {
            EmptyView()
        } else {
            let safeIndex = index % clips.count
            let front = clips[safeIndex]
            let depthCount = min(3, clips.count)

            ZStack(alignment: .top) {
                ForEach(0 ..< depthCount, id: \.self) { rev in
                    let depth = (depthCount - 1) - rev
                    let clip = clips[(safeIndex + depth) % clips.count]
                    stackCard(clip, isFront: depth == 0)
                        .scaleEffect(scale(for: depth), anchor: .top)
                        .opacity(opacity(for: depth))
                        .offset(y: yOffset(for: depth, total: depthCount))
                        .zIndex(Double(3 - depth))
                        .allowsHitTesting(depth == 0)
                }
            }
            .frame(height: containerHeight(total: depthCount), alignment: .top)
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 20).onEnded { value in
                    guard clips.count > 1 else { return }
                    withAnimation(tone.motion) {
                        if value.translation.width < -30 {
                            index = (index + 1) % clips.count
                        } else if value.translation.width > 30 {
                            index = (index - 1 + clips.count) % clips.count
                        }
                    }
                }
            )
            .onTapGesture {
                model.clipRoute = front.id
            }
        }
    }

    private func scale(for depth: Int) -> CGFloat {
        switch depth {
        case 0: return Theme.ClipStack.frontScale
        case 1: return Theme.ClipStack.middleScale
        default: return Theme.ClipStack.backScale
        }
    }

    private func opacity(for depth: Int) -> Double {
        switch depth {
        case 0: return Theme.Opacity.stackFront
        case 1: return Theme.Opacity.stackMiddle
        default: return Theme.Opacity.stackBack
        }
    }

    private func yOffset(for depth: Int, total: Int) -> CGFloat {
        if total == 1 { return 0 }
        if total == 2 {
            return depth == 0 ? 22 : 0
        }
        switch depth {
        case 0: return Theme.ClipStack.frontOffset
        case 1: return Theme.ClipStack.middleOffset
        default: return Theme.ClipStack.backOffset
        }
    }

    private func containerHeight(total: Int) -> CGFloat {
        if total == 1 { return Theme.Size.clipStackCardHeight }
        if total == 2 { return Theme.Size.clipStackCardHeight + 22 }
        return Theme.Size.clipStackContainerHeight
    }

    private func stackCard(_ clip: Clip, isFront: Bool) -> some View {
        ZStack(alignment: .bottomLeading) {
            ClipStill(reference: clip.thumbnailURL, seed: stillSeed(clip.id))

            // The scrim only sits under the front card's text; the cards behind
            // it stay clean so the stack reads as pictures, not a dark slab.
            if isFront {
                LinearGradient(
                    colors: [Theme.clear, Theme.scrimBase.opacity(0.92)],
                    startPoint: UnitPoint(x: 0.5, y: 0.28),
                    endPoint: .bottom
                )
            }

            if isFront {
                if richFront {
                    GlassCircle(system: "play.fill", size: 40)
                        .padding(14)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                }

                durationBadge(clip)
                    .padding(12)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)

                VStack(alignment: .leading, spacing: 6) {
                    Text(clip.label)
                        .font(richFront ? Theme.TypeScale.promptTitle : Theme.TypeScale.cardTitle)
                        .foregroundStyle(Theme.ink)
                        .lineLimit(1)

                    if richFront, let created = clip.createdAt {
                        Text(StudioFormat.dayAndTime(created, now: Date()))
                            .font(Theme.TypeScale.subtitle)
                            .foregroundStyle(Theme.ink2)
                    }

                    HStack(spacing: 10) {
                        if clip.locations.contains("nas") || clip.offload == .done {
                            HStack(spacing: 4) {
                                Image(systemName: "checkmark")
                                Text(model.studio?.settings.offloadTarget ?? "—")
                            }
                            .foregroundStyle(Theme.teal)
                        }
                        HStack(spacing: 4) {
                            Image(systemName: "rectangle")
                            Text(qualityChip(clip))
                        }
                        if richFront {
                            Text(StudioFormat.bytes(clip.bytes))
                        }
                        if !clip.highlights.isEmpty {
                            HStack(spacing: 4) {
                                Image(systemName: "star")
                                Text("\(clip.highlights.count) marks")
                            }
                        }
                    }
                    .font(Theme.TypeScale.captionSemibold)
                    .foregroundStyle(Theme.ink2)
                    .lineLimit(1)
                }
                .padding(16)
            }
        }
        .frame(height: Theme.Size.clipStackCardHeight)
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.featuredCard, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: Theme.Radius.featuredCard, style: .continuous)
                .stroke(Theme.ink.opacity(0.12), lineWidth: Theme.Stroke.hairline)
        )
        .shadow(color: Theme.shadow.opacity(isFront ? 0.50 : 0.30), radius: 16, x: 0, y: -6)
    }

    private func durationBadge(_ clip: Clip) -> some View {
        let label: String
        let fg: Color
        if clip.writing {
            label = "WRITING"
            fg = Theme.violetPale
        } else if let dur = clip.duration {
            let whole = max(0, Int(dur.rounded(.down)))
            label = whole >= 3600 ? StudioFormat.clock(dur) : String(format: "%d:%02d", whole / 60, whole % 60)
            fg = Theme.ink
        } else {
            label = "—"
            fg = Theme.ink2
        }

        return Text(label)
            .font(Theme.TypeScale.captionTabular)
            .foregroundStyle(fg)
            .padding(.horizontal, 10)
            .frame(height: Theme.Size.statusChipHeight)
            .background {
                if tone.reduceTransparency {
                    Capsule().fill(Theme.inkDark)
                } else {
                    Capsule().fill(.ultraThinMaterial)
                    Capsule().fill(Theme.glassHeroBase.opacity(Theme.Opacity.chipGlassFill))
                }
            }
    }

    private func qualityChip(_ clip: Clip) -> String {
        if clip.resolution.isEmpty { return "—" }
        let h = clip.resolution.split(separator: "x").last.map(String.init) ?? clip.resolution
        if clip.fps > 0 { return "\(h)p\(clip.fps)" }
        return clip.resolution
    }
}
