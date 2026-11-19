import SwiftUI

struct NowView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.tone) private var tone

    var body: some View {
        let session = model.studio?.session
        let playing = session?.playing == true
        VStack(alignment: .leading, spacing: 14) {
            if playing, let session {
                hero(session)
                if model.prefs.nowLayout == .clips {
                    clipsLedTiles(session)
                } else {
                    tileRow(session, playing: true)
                }
                if model.prefs.nowLayout == .game {
                    highlights(session.highlights, duration: model.elapsed(at: Date()), live: true)
                }
            } else if let last = session?.lastSession {
                idleHero(last)
                tileRow(session, playing: false)
                if model.prefs.nowLayout == .game {
                    highlights([], duration: last.duration, live: false)
                }
            } else {
                ready
            }
            if session?.lastSession != nil || playing {
                recent
            }
        }
    }

    private var ready: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Ready when you are")
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(Theme.ink)
            Text("Nebula starts recording when a game launches on Studio PC.")
                .font(.system(size: 15))
                .foregroundStyle(Theme.ink2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 12)
    }

    private func hero(_ session: Session) -> some View {
        let compact = model.prefs.nowLayout == .clips
        return Tray(radius: compact ? 28 : 34) {
            VStack(alignment: .leading, spacing: compact ? 8 : 14) {
                HStack {
                    chip(session)
                    Spacer()
                    if !session.output.line.isEmpty {
                        Text(session.output.line)
                            .font(.system(size: 13))
                            .foregroundStyle(tone.tertiary)
                    }
                }
                if compact {
                    HStack {
                        Text(session.game?.name ?? "Studio PC")
                            .font(.system(size: 17, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                        Spacer()
                        TimelineView(.periodic(from: .now, by: 1)) { context in
                            RollingClock(seconds: model.elapsed(at: context.date), paused: session.state == "paused", size: 38)
                        }
                        buttons(session)
                    }
                } else {
                    HStack(alignment: .bottom) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(session.game?.name ?? "Studio PC")
                                .font(.system(size: 17, weight: .semibold))
                                .foregroundStyle(Theme.ink)
                            if session.state == "bufferOnly" {
                                Text("Replay buffer · \(model.studio?.settings.replayLabel ?? "30 s")")
                                    .font(.system(size: 22, weight: .medium))
                                    .foregroundStyle(Theme.violetLight)
                            } else {
                                TimelineView(.periodic(from: .now, by: 1)) { context in
                                    RollingClock(seconds: model.elapsed(at: context.date), paused: session.state == "paused")
                                }
                            }
                        }
                        Spacer()
                        buttons(session)
                    }
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background {
                if tone.reduceTransparency {
                    Theme.card
                } else {
                    Rectangle().fill(.ultraThinMaterial)
                    Color(red: 16 / 255, green: 13 / 255, blue: 28 / 255).opacity(0.50)
                }
            }
        }
    }

    private func idleHero(_ last: LastSession) -> some View {
        Tray {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    chipDot(Theme.ink3, "IDLE")
                    Spacer()
                    Text(model.link == .online ? "Studio PC online" : "Studio PC is offline")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(model.link == .online ? Theme.teal : tone.tertiary)
                }
                if model.prefs.nowLayout == .game {
                    Eyebrow(text: "Last played · \(StudioFormat.relative(last.endedAt, now: Date()))")
                    Text(last.game.name)
                        .font(.system(size: 30, weight: .bold))
                        .foregroundStyle(Theme.ink)
                    if let line = model.studio?.session.achievement {
                        Text(line).font(.system(size: 15)).foregroundStyle(Theme.ink2)
                    }
                } else {
                    Eyebrow(text: "Last session · \(StudioFormat.time(last.endedAt))")
                    Text("\(last.game.name) · \(StudioFormat.clock(last.duration))")
                        .font(.system(size: 20, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                    Text("\(last.highlightCount) highlights · \(StudioFormat.bytes(last.bytes)) · \(offloadLine(last.offload))")
                        .font(.system(size: 14))
                        .foregroundStyle(tone.tertiary)
                }
                HStack(spacing: 10) {
                    Button {
                        model.session("session.start")
                    } label: {
                        HStack {
                            Text("Start recording")
                                .font(.system(size: 16, weight: .semibold))
                            Spacer()
                            Circle().fill(Theme.coral).frame(width: 38, height: 38)
                                .overlay(Circle().fill(Theme.ink).frame(width: 10, height: 10))
                        }
                        .foregroundStyle(Theme.ink)
                        .padding(.leading, 16)
                        .padding(.trailing, 6)
                        .frame(height: 46)
                        .background(RoundedRectangle(cornerRadius: 23, style: .continuous).fill(Theme.coral.opacity(0.18)))
                    }
                    .buttonStyle(PressScaleStyle())
                    .disabled(!model.controlsEnabled)
                    .opacity(model.controlsEnabled ? 1 : 0.45)
                    if model.prefs.nowLayout == .game {
                        Button {} label: {
                            Text("Launch on PC")
                                .font(.system(size: 15, weight: .semibold))
                                .frame(minHeight: 46)
                        }
                        .disabled(true)
                        .opacity(0.45)
                        .accessibilityHint("Coming soon")
                    }
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background {
                if tone.reduceTransparency {
                    Theme.card
                } else {
                    Rectangle().fill(.ultraThinMaterial)
                    Color(red: 16 / 255, green: 13 / 255, blue: 28 / 255).opacity(0.50)
                }
            }
        }
    }

    @ViewBuilder private func buttons(_ session: Session) -> some View {
        let dim = model.controlsEnabled ? 1.0 : 0.45
        HStack(spacing: 10) {
            if session.state == "bufferOnly" {
                Button {
                    model.command("replay.save")
                } label: {
                    Text("Save replay")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                        .padding(.horizontal, 12)
                        .frame(height: 48)
                        .background(Capsule().stroke(Theme.violet.opacity(0.55), lineWidth: 1))
                }
                .buttonStyle(PressScaleStyle())
            } else {
                Button {
                    model.session(session.state == "paused" ? "session.resume" : "session.pause")
                } label: {
                    GlassCircle(system: session.state == "paused" ? "play.fill" : "")
                        .overlay {
                            if session.state != "paused" {
                                HStack(spacing: 3) {
                                    RoundedRectangle(cornerRadius: 1.5, style: .continuous).frame(width: 3.4, height: 14)
                                    RoundedRectangle(cornerRadius: 1.5, style: .continuous).frame(width: 3.4, height: 14)
                                }
                                .foregroundStyle(Theme.ink)
                            }
                        }
                }
                .buttonStyle(PressScaleStyle())
                .accessibilityLabel(session.state == "paused" ? "Resume recording" : "Pause recording")
            }
            Button {
                model.session("session.stop")
            } label: {
                RoundedRectangle(cornerRadius: 3, style: .continuous)
                    .fill(Theme.inkDark)
                    .frame(width: 13, height: 13)
                    .frame(width: 48, height: 48)
                    .background(Circle().fill(Theme.coral))
            }
            .buttonStyle(PressScaleStyle())
            .accessibilityLabel("Stop recording")
        }
        .disabled(!model.controlsEnabled)
        .opacity(dim)
    }

    private func tileRow(_ session: Session?, playing: Bool) -> some View {
        let stack = typeSize >= .accessibility1
        return Group {
            if stack {
                VStack(spacing: 12) { tiles(session, playing: playing) }
            } else {
                HStack(alignment: .top, spacing: 12) { tiles(session, playing: playing) }
            }
        }
    }

    @ViewBuilder private func tiles(_ session: Session?, playing: Bool) -> some View {
        storageTile(session)
        if playing, model.prefs.nowLayout == .game {
            gameTile
        } else if playing {
            encoderTile
        } else if model.prefs.nowLayout == .clips {
            libraryTile
        } else if model.prefs.nowLayout == .game {
            weekTile
        } else {
            offloadTile
        }
    }

    private func clipsLedTiles(_ session: Session) -> some View {
        HStack(alignment: .top, spacing: 12) {
            tile(title: "Highlights") {
                Text("\(session.highlights.count)")
                    .font(.system(size: 28, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                Text(session.highlights.isEmpty ? "No marks yet" : "This session")
                    .font(.system(size: 13))
                    .foregroundStyle(tone.tertiary)
            }
            tile(title: "Audio") {
                if let audio = model.studio?.stats?.audio {
                    meter("Game", audio.game, Theme.violet)
                    meter("Mic", audio.mic, Theme.teal)
                    meter("Chat", audio.chat, Theme.magenta)
                } else {
                    Text("—").foregroundStyle(tone.tertiary)
                }
            }
        }
    }

    private func storageTile(_ session: Session?) -> some View {
        let free = session?.storageFreeBytes
        let days = StudioFormat.remaining(session?.estimatedRemaining)
        return tile(title: "Storage") {
            HStack(spacing: 12) {
                Circle()
                    .stroke(Theme.violet, style: StrokeStyle(lineWidth: 6, lineCap: .round))
                    .frame(width: 52, height: 52)
                VStack(alignment: .leading, spacing: 2) {
                    Text(StudioFormat.bytes(free))
                        .font(.system(size: 20, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                    if let days {
                        Text(days).font(.system(size: 13)).foregroundStyle(tone.tertiary)
                    }
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Storage, \(StudioFormat.bytes(free)) free\(days.map { ", \($0)" } ?? "")")
    }

    private var encoderTile: some View {
        let drops = model.studio?.stats?.droppedFrames
        let rate = model.studio?.stats?.bitrateMbps
        return tile(title: "Encoder") {
            HStack {
                Spacer()
                Text(dropsText(drops))
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(dropsColor(drops))
            }
            Text(rate.map { String(format: "%.1f Mb/s", $0) } ?? "—")
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(Theme.ink)
            spark(model.bitrate)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Encoder, \(dropsText(drops)), \(rate.map { String(format: "%.1f megabits per second", $0) } ?? "bitrate unknown")")
    }

    private var gameTile: some View {
        tile(title: "Game") {
            if let fps = model.studio?.stats?.gameFps {
                Text("\(fps) fps")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                spark(model.fpsSamples)
            } else {
                Text("—").foregroundStyle(tone.tertiary)
            }
            if let temp = model.studio?.stats?.gpuTempC {
                Text("\(temp) °C").font(.system(size: 13)).foregroundStyle(tone.tertiary)
            }
        }
    }

    private var offloadTile: some View {
        let active = (model.studio?.clips ?? []).filter { $0.offload.isActive }
        return tile(title: "Offload") {
            if active.isEmpty {
                Text("All synced")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(Theme.teal)
            } else {
                let target = model.studio?.settings.offloadTarget ?? "NAS"
                Text("To \(target)")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                let progress = active.compactMap { item -> Double? in
                    if case let .moving(progress, _) = item.offload { return progress }
                    return nil
                }.max() ?? 0
                ProgressView(value: progress).tint(Theme.amber)
                Text("\(active.count) clips left")
                    .font(.system(size: 13))
                    .foregroundStyle(tone.tertiary)
            }
        }
    }

    private var libraryTile: some View {
        tile(title: "Library") {
            Text(StudioFormat.bytes(model.studio?.session.storageFreeBytes) + " free")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Theme.ink)
            let pending = (model.studio?.clips ?? []).contains { $0.offload.isActive }
            Text(pending ? "Offload in progress" : "All synced\(model.studio?.settings.offloadTarget.map { " to \($0)" } ?? "")")
                .font(.system(size: 13))
                .foregroundStyle(pending ? Theme.amber : Theme.teal)
        }
    }

    private var weekTile: some View {
        let week = model.studio?.games.first?.weekPlaytime ?? []
        let hours = week.reduce(0, +) / 3600
        return tile(title: "This week") {
            Text(String(format: "%.1f h", hours))
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(Theme.ink)
            HStack(alignment: .bottom, spacing: 4) {
                ForEach(Array(week.enumerated()), id: \.offset) { index, value in
                    RoundedRectangle(cornerRadius: 2, style: .continuous)
                        .fill(index == week.count - 1 ? Theme.gold : Theme.violet.opacity(0.7))
                        .frame(width: 8, height: max(4, CGFloat(value / 3600) * 8))
                }
            }
        }
    }

    private func tile<Content: View>(title: String, @ViewBuilder content: @escaping () -> Content) -> some View {
        Tray(radius: 30) {
            VStack(alignment: .leading, spacing: 8) {
                Eyebrow(text: title, color: tone.tertiary)
                content()
            }
            .padding(14)
            .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
            .background {
                ReadingFill()
            }
        }
    }

    private func highlights(_ marks: [Highlight], duration: Double, live: Bool) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Eyebrow(text: "Highlights", color: tone.tertiary)
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Theme.ink.opacity(0.12)).frame(height: 6)
                    if live, duration > 0 {
                        Capsule().fill(Theme.gold).frame(width: 8, height: 18)
                            .offset(x: 0)
                    }
                    ForEach(Array(marks.enumerated()), id: \.offset) { _, mark in
                        Capsule().fill(Theme.amber)
                            .frame(width: 4, height: 14)
                            .offset(x: duration > 0 ? geo.size.width * mark.at / duration : 0)
                    }
                }
            }
            .frame(height: 18)
            if marks.isEmpty {
                Text(live ? "No highlights yet" : "Last session")
                    .font(.system(size: 13))
                    .foregroundStyle(tone.tertiary)
            }
        }
        .padding(14)
    }

    private var recent: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Recent clips")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                Spacer()
                Button("See all") { model.requestedTab = .clips }
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(Theme.violetLight)
            }
            ClipStack(clips: Array((model.studio?.clips ?? []).prefix(3)))
        }
    }

    private func chip(_ session: Session) -> some View {
        switch session.state {
        case "paused":
            chipDot(Theme.ink2, "PAUSED", hollow: true)
        case "bufferOnly":
            chipDot(Theme.violet, "BUFFER")
        default:
            chipDot(Theme.gold, "REC")
        }
    }

    private func chipDot(_ color: Color, _ title: String, hollow: Bool = false) -> some View {
        HStack(spacing: 7) {
            Circle()
                .strokeBorder(color, lineWidth: hollow ? 1.5 : 0)
                .background(Circle().fill(hollow ? .clear : color))
                .frame(width: 7, height: 7)
            Text(title)
                .font(.system(size: 11, weight: .semibold))
                .tracking(1.6)
                .foregroundStyle(hollow ? Theme.ink2 : color)
        }
        .padding(.horizontal, 11)
        .frame(height: 26)
        .background(Capsule().fill(color.opacity(hollow ? 0.08 : 0.10)))
        .overlay(Capsule().stroke(color.opacity(hollow ? 0.18 : 0.32), lineWidth: 0.5))
    }

    private func dropsText(_ drops: Int?) -> String {
        guard let drops else { return "—" }
        return drops == 1 ? "1 drop" : "\(drops) drops"
    }

    private func dropsColor(_ drops: Int?) -> Color {
        guard let drops else { return tone.tertiary }
        if drops == 0 { return Theme.teal }
        return Theme.amber
    }

    private func spark(_ samples: [Double]) -> some View {
        GeometryReader { geo in
            let maxValue = max(samples.max() ?? 1, 0.1)
            Path { path in
                guard samples.count > 1 else { return }
                for (index, sample) in samples.enumerated() {
                    let x = geo.size.width * CGFloat(index) / CGFloat(samples.count - 1)
                    let y = geo.size.height * (1 - CGFloat(sample / maxValue))
                    if index == 0 { path.move(to: CGPoint(x: x, y: y)) } else { path.addLine(to: CGPoint(x: x, y: y)) }
                }
            }
            .stroke(Theme.violet, lineWidth: 1.5)
        }
        .frame(height: 28)
    }

    private func meter(_ title: String, _ level: Double, _ color: Color) -> some View {
        HStack(spacing: 8) {
            Text(title).font(.system(size: 11, weight: .semibold)).foregroundStyle(tone.tertiary).frame(width: 36, alignment: .leading)
            GeometryReader { geo in
                Capsule().fill(Theme.ink.opacity(0.12))
                Capsule().fill(color).frame(width: geo.size.width * CGFloat(min(max(level, 0), 1)))
            }
            .frame(height: 6)
        }
    }

    private func offloadLine(_ offload: Offload) -> String {
        switch offload {
        case .done: "on \(model.studio?.settings.offloadTarget ?? "NAS")"
        case .queued: "queued"
        case let .moving(progress, _): "offloading \(Int(progress * 100))%"
        case let .failed(error): error
        case .none: "on Studio PC"
        }
    }
}

private struct ReadingFill: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone

    var body: some View {
        if tone.reduceTransparency || model.prefs.surfaces == .solid {
            Theme.card
        } else if model.prefs.surfaces == .lively {
            LinearGradient(colors: [Theme.livelyTop, Theme.livelyBottom], startPoint: .topLeading, endPoint: .bottomTrailing)
        } else {
            Theme.card.opacity(0.55)
        }
    }
}

struct ClipStack: View {
    var clips: [Clip]
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    @State private var index = 0

    var body: some View {
        if clips.isEmpty {
            EmptyView()
        } else {
            let front = clips[index % clips.count]
            ZStack {
                ForEach(Array(clips.enumerated()), id: \.element.id) { offset, clip in
                    let depth = (offset - index + clips.count) % clips.count
                    if depth < 3 {
                        card(clip)
                            .scaleEffect(depth == 0 ? 1 : (depth == 1 ? 0.92 : 0.84))
                            .opacity(depth == 0 ? 1 : (depth == 1 ? 0.72 : 0.45))
                            .offset(y: depth == 0 ? 0 : (depth == 1 ? -22 : -48))
                            .zIndex(Double(3 - depth))
                            .allowsHitTesting(depth == 0)
                    }
                }
            }
            .frame(height: 210)
            .contentShape(Rectangle())
            .gesture(DragGesture(minimumDistance: 20).onEnded { value in
                guard clips.count > 1 else { return }
                withAnimation(tone.motion) {
                    if value.translation.width < -30 {
                        index = (index + 1) % clips.count
                    } else if value.translation.width > 30 {
                        index = (index - 1 + clips.count) % clips.count
                    }
                }
            })
            .onTapGesture { model.clipRoute = front.id }
        }
    }

    private func card(_ clip: Clip) -> some View {
        ZStack(alignment: .bottomLeading) {
            ClipStill(reference: clip.thumbnailURL, seed: stillSeed(clip.id))
            LinearGradient(colors: [.clear, Color(red: 7 / 255, green: 6 / 255, blue: 14 / 255).opacity(0.9)], startPoint: .center, endPoint: .bottom)
            VStack(alignment: .leading, spacing: 6) {
                Text("\(clip.game.name) · \(clip.label)")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                HStack(spacing: 12) {
                    if clip.locations.contains("nas") || clip.offload == .done {
                        Label(model.studio?.settings.offloadTarget ?? "nas-vault", systemImage: "checkmark")
                            .foregroundStyle(Theme.teal)
                    }
                    Label(clip.resolution.isEmpty ? "—" : clip.resolution, systemImage: "rectangle")
                    Label("\(clip.highlights.count) marks", systemImage: "star")
                }
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Theme.ink2)
            }
            .padding(16)
            if clip.writing {
                durationChip("WRITING", gold: false)
            } else if let duration = clip.duration {
                durationChip(StudioFormat.clock(duration), gold: false)
            }
        }
        .frame(height: 180)
        .clipShape(RoundedRectangle(cornerRadius: 26, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 26, style: .continuous).stroke(Color.white.opacity(0.12), lineWidth: 1))
    }

    private func durationChip(_ title: String, gold: Bool) -> some View {
        Text(title)
            .font(.system(size: 12, weight: .semibold))
            .foregroundStyle(gold ? Theme.gold : Theme.ink)
            .padding(.horizontal, 10)
            .frame(height: 26)
            .background(.ultraThinMaterial, in: Capsule())
            .padding(12)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
    }
}
