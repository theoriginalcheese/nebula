import AVKit
import Photos
import SwiftUI
import UIKit

struct ClipDetailView: View {
    var id: String
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    @Environment(\.dismiss) private var dismiss

    @State private var player: AVPlayer?
    @State private var position: Double = 0
    @State private var playing = false
    @State private var fullScreen = false
    @State private var confirmDelete = false
    @State private var showTrim = false
    @State private var trimIn: Double = 0
    @State private var trimOut: Double = 1
    @State private var shareItem: ShareItem?
    @State private var busy = false
    @State private var lastHighlightHit: Int?

    private var clip: Clip? {
        return model.studio?.clips.first(where: { $0.id == id }) ?? model.listed?.first(where: { $0.id == id })
    }

    var body: some View {
        Group {
            if let clip = clip {
                detailScroll(clip)
            } else {
                missingClipState
            }
        }
        .background(Theme.ground.ignoresSafeArea())
        .toolbar(.hidden, for: .navigationBar)
        .onAppear {
            model.playback = true
        }
        .onDisappear {
            player?.pause()
            model.playback = false
            model.trimming = false
        }
    }

    private var missingClipState: some View {
        VStack(alignment: .leading, spacing: Theme.Space.sectionGap) {
            Button {
                dismiss()
            } label: {
                GlassCircle(system: "chevron.left", size: Theme.Size.chromeButton)
            }
            .buttonStyle(PressScaleStyle())
            .accessibilityLabel("Back")

            Tray(role: .tile) {
                ReadingSurface(radius: Theme.Radius.tileCard) {
                    Text("That clip is no longer on Studio PC.")
                        .font(Theme.TypeScale.body)
                        .foregroundStyle(Theme.ink2)
                        .padding(20)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            Spacer()
        }
        .padding(.horizontal, Theme.Space.screenMargin)
        .padding(.top, 16)
    }

    private func detailScroll(_ clip: Clip) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                stage(clip)

                VStack(alignment: .leading, spacing: Theme.Space.sectionGap) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(clip.label)
                            .font(Theme.TypeScale.detailTitle)
                            .tracking(Theme.TypeScale.detailTitleTracking)
                            .foregroundStyle(Theme.ink)
                        Text(metaLine(clip))
                            .font(Theme.TypeScale.rowValue)
                            .foregroundStyle(Theme.ink2)
                    }
                    .padding(.horizontal, 4)

                    scrubber(clip)
                        .padding(.horizontal, 4)

                    factsTray(clip)

                    actionsRow(clip)
                }
                .padding(.horizontal, 16)
                .offset(y: -48)
                .padding(.bottom, Theme.Space.contentBottomInset - 36)
            }
        }
        .ignoresSafeArea(edges: .top)
        .confirmationDialog(deleteDialogTitle(clip), isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Delete", role: .destructive) {
                model.deleteClip(clip.id)
                dismiss()
            }
            Button("Cancel", role: .cancel) {}
        }
        .sheet(isPresented: $showTrim) {
            ToneReader(stillPref: model.prefs.still) { _ in
                trimSheet(clip)
            }
            .environmentObject(model)
            .preferredColorScheme(.dark)
            .presentationDetents([.medium, .large])
        }
        .sheet(item: $shareItem) { item in
            ShareSheet(url: item.url)
        }
        .fullScreenCover(isPresented: $fullScreen) {
            if let player = player {
                VideoPlayer(player: player)
                    .ignoresSafeArea()
                    .onTapGesture(count: 2) {
                        fullScreen = false
                    }
            }
        }
    }

    // MARK: - Top 360pt Full-Bleed Stage (3b)

    private func stage(_ clip: Clip) -> some View {
        let canStream = model.link != .offline && model.http("/files/clip/\(clip.id)") != nil

        return ZStack {
            ClipStill(reference: clip.thumbnailURL, seed: stillSeed(clip.id))

            if playing, let player = player {
                VideoPlayer(player: player)
            }

            LinearGradient(
                stops: [
                    .init(color: Theme.scrimBase.opacity(0.45), location: 0.0),
                    .init(color: Theme.clear, location: 0.25),
                    .init(color: Theme.clear, location: 0.55),
                    .init(color: Theme.ground, location: 1.0),
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            .allowsHitTesting(false)

            HStack {
                Button {
                    dismiss()
                } label: {
                    GlassCircle(system: "chevron.left", size: Theme.Size.chromeButton)
                }
                .buttonStyle(PressScaleStyle())
                .accessibilityLabel("Back")

                Spacer()

                Menu {
                    Button("Rename label") {
                        model.toast("Rename is set on Studio PC.")
                    }
                    Button("Open on PC") {
                        model.toast("Open on PC is set on Studio PC.")
                    }
                    Button("Copy file path") {
                        copyFilePath(clip)
                    }
                } label: {
                    GlassCircle(system: "ellipsis", size: Theme.Size.chromeButton)
                }
                .accessibilityLabel("More actions")
            }
            .padding(.horizontal, 16)
            .padding(.top, 58)
            .frame(maxHeight: .infinity, alignment: .top)

            VStack(spacing: 8) {
                Button {
                    togglePlayback(clip)
                } label: {
                    GlassCircle(
                        system: playing ? "pause.fill" : "play.fill",
                        size: Theme.Size.stagePlayButton
                    )
                }
                .buttonStyle(PressScaleStyle())
                .disabled(!canStream)
                .opacity(canStream ? 1.0 : Theme.Opacity.disabled)
                .accessibilityLabel(playing ? "Pause clip" : "Play clip")

                if model.link == .offline {
                    Text("Playback is off while Studio PC is offline.")
                        .font(Theme.TypeScale.caption)
                        .foregroundStyle(Theme.ink2)
                }
            }
        }
        .frame(height: Theme.Size.clipStageHeight)
        .onTapGesture(count: 2) {
            if player != nil {
                fullScreen = true
            }
        }
    }

    // MARK: - Scrubber with Highlight Ticks & Haptics (§9.4)

    private func scrubber(_ clip: Clip) -> some View {
        let total = clip.duration ?? 0
        let safeTotal = max(total, 0.1)

        return VStack(spacing: 8) {
            GeometryReader { geo in
                let width = max(1, geo.size.width)
                let progress = total > 0 ? min(1.0, max(0.0, position / safeTotal)) : 0.0

                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Theme.ink.opacity(0.10))
                        .frame(height: 6)

                    Capsule()
                        .fill(LinearGradient(colors: [Theme.violet, Theme.violetLight], startPoint: .leading, endPoint: .trailing))
                        .frame(width: max(6, width * CGFloat(progress)), height: 6)

                    if total > 0 {
                        ForEach(Array(clip.highlights.enumerated()), id: \.offset) { _, mark in
                            let x = min(max(0, width * CGFloat(mark.at / safeTotal) - 2), max(0, width - 4))
                            RoundedRectangle(cornerRadius: Theme.Radius.bar, style: .continuous)
                                .fill(Theme.amber)
                                .frame(width: 4, height: 18)
                                .shadow(color: Theme.amber.opacity(0.60), radius: 4)
                                .offset(x: x)
                                .accessibilityLabel(mark.label ?? "Highlight")
                                .onTapGesture {
                                    position = mark.at
                                    player?.seek(to: CMTime(seconds: mark.at, preferredTimescale: 600))
                                    UIImpactFeedbackGenerator(style: .light).impactOccurred()
                                }
                        }
                    }

                    Circle()
                        .fill(Theme.ink)
                        .frame(width: 20, height: 20)
                        .shadow(color: Theme.shadow.opacity(0.50), radius: 5, x: 0, y: 2)
                        .offset(x: min(max(0, width * CGFloat(progress) - 10), max(0, width - 20)))
                }
                .frame(height: 30)
                .contentShape(Rectangle())
                .gesture(
                    DragGesture(minimumDistance: 0)
                        .onChanged { value in
                            guard total > 0, !clip.writing, model.link != .offline else { return }
                            let next = min(total, max(0, total * Double(value.location.x / width)))
                            checkHighlightCrossing(clip: clip, next: next, total: total)
                            position = next
                        }
                        .onEnded { _ in
                            lastHighlightHit = nil
                            player?.seek(to: CMTime(seconds: position, preferredTimescale: 600))
                        }
                )
            }
            .frame(height: 30)

            HStack {
                Text(shortDuration(position))
                    .foregroundStyle(tone.tertiary)
                Spacer()
                Text("\(clip.highlights.count) highlights")
                    .foregroundStyle(tone.tertiary)
                Spacer()
                Text(clip.duration == nil ? "—" : shortDuration(total))
                    .foregroundStyle(tone.tertiary)
            }
            .font(Theme.TypeScale.captionRegularTabular)
        }
    }

    private func checkHighlightCrossing(clip: Clip, next: Double, total: Double) {
        let tolerance = max(0.5, total * 0.015)
        for (idx, mark) in clip.highlights.enumerated() {
            if abs(next - mark.at) <= tolerance {
                if lastHighlightHit != idx {
                    lastHighlightHit = idx
                    UIImpactFeedbackGenerator(style: .light).impactOccurred()
                }
                return
            }
        }
        lastHighlightHit = nil
    }

    // MARK: - Facts Tray (3b: 30/24 concentric Tray + ReadingSurface)

    private func factsTray(_ clip: Clip) -> some View {
        Tray(role: .tile) {
            ReadingSurface(radius: Theme.Radius.tileCard) {
                VStack(spacing: 0) {
                    factRow("Quality") {
                        Text(qualitySummary(clip))
                            .font(Theme.TypeScale.factMedium)
                            .foregroundStyle(Theme.ink)
                    }
                    GroupDivider()
                    factRow("Size") {
                        Text(clip.writing ? "—" : StudioFormat.bytes(clip.bytes))
                            .font(Theme.TypeScale.factMediumTabular)
                            .foregroundStyle(Theme.ink)
                    }
                    GroupDivider()
                    factRow("Stored") {
                        storedBadge(clip)
                    }
                    GroupDivider()
                    factRow("Folder") {
                        Text(clip.folder.isEmpty ? "—" : clip.folder)
                            .font(Theme.TypeScale.monoFolder)
                            .foregroundStyle(Theme.inkSoft)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 4)
            }
        }
    }

    private func factRow<ValueContent: View>(_ label: String, @ViewBuilder value: () -> ValueContent) -> some View {
        HStack(spacing: Theme.Space.bentoGap) {
            Text(label)
                .font(Theme.TypeScale.body)
                .foregroundStyle(Theme.ink2)
            Spacer(minLength: 8)
            value()
        }
        .frame(minHeight: Theme.Size.factRowHeight)
    }

    @ViewBuilder private func storedBadge(_ clip: Clip) -> some View {
        let target = model.studio?.settings.offloadTarget ?? "—"
        switch clip.offload {
        case let .moving(progress, _):
            HStack(spacing: 6) {
                Circle().fill(Theme.amberDeep).frame(width: 7, height: 7)
                Text("Offloading \(Int((progress * 100).rounded()))%")
                    .font(Theme.TypeScale.factMediumTabular)
                    .foregroundStyle(Theme.amberDeep)
            }
        case .queued:
            HStack(spacing: 6) {
                Circle().fill(Theme.amberDeep).frame(width: 7, height: 7)
                Text("Queued")
                    .font(Theme.TypeScale.factMedium)
                    .foregroundStyle(Theme.amberDeep)
            }
        case .done:
            HStack(spacing: 6) {
                Circle().fill(Theme.teal).frame(width: 7, height: 7)
                Text(clip.locations.contains("pc") ? "\(target) + Studio PC" : target)
                    .font(Theme.TypeScale.factMedium)
                    .foregroundStyle(Theme.teal)
            }
        case let .failed(reason):
            Text(reason)
                .font(Theme.TypeScale.factMedium)
                .foregroundStyle(Theme.coralSoft)
                .lineLimit(1)
        case .none:
            if clip.locations.contains("nas") {
                HStack(spacing: 6) {
                    Circle().fill(Theme.teal).frame(width: 7, height: 7)
                    Text(clip.locations.contains("pc") ? "\(target) + Studio PC" : target)
                        .font(Theme.TypeScale.factMedium)
                        .foregroundStyle(Theme.teal)
                }
            } else {
                Text("Studio PC")
                    .font(Theme.TypeScale.factMedium)
                    .foregroundStyle(Theme.ink)
            }
        }
    }

    // MARK: - 4 Round 56pt Actions (3b)

    private func actionsRow(_ clip: Clip) -> some View {
        let trimBlocked = clip.writing || clip.offload.isActive
        return VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: Theme.Space.chipGap) {
                actionButton(system: "square.and.arrow.up", title: "Share", coral: false) {
                    share(clip)
                }
                actionButton(system: "arrow.down.to.line", title: "Save", coral: false) {
                    saveToPhotos(clip)
                }
                actionButton(system: "scissors", title: "Trim", coral: false) {
                    trimIn = 0
                    trimOut = max(clip.duration ?? 1.0, 0.1)
                    model.trimming = true
                    showTrim = true
                }
                .disabled(trimBlocked)
                .opacity(trimBlocked ? Theme.Opacity.disabled : 1.0)

                actionButton(system: "trash", title: "Delete", coral: true) {
                    confirmDelete = true
                }
            }

            if trimBlocked {
                Text(clip.writing ? "Trim waits until OBS finalises this recording." : "Trim waits until offloading to NAS finishes.")
                    .font(Theme.TypeScale.caption)
                    .foregroundStyle(tone.tertiary)
                    .padding(.horizontal, 4)
            }
        }
    }

    private func actionButton(system: String, title: String, coral: Bool, action: @escaping () -> Void) -> some View {
        let unavailable = model.link == .offline || busy
        return Button(action: action) {
            VStack(spacing: 8) {
                GlassCircle(
                    system: system,
                    size: Theme.Size.clipActionCircle,
                    tint: Theme.ink,
                    coralTint: coral
                )
                Text(title)
                    .font(Theme.TypeScale.captionMedium)
                    .foregroundStyle(coral ? Theme.coralSoft : Theme.ink2)
            }
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(PressScaleStyle())
        .disabled(unavailable)
        .opacity(unavailable ? Theme.Opacity.disabled : 1.0)
    }

    // MARK: - Custom Trim Sheet (§9.4)

    private func trimSheet(_ clip: Clip) -> some View {
        let total = max(clip.duration ?? 1.0, 0.1)
        return VStack(alignment: .leading, spacing: Theme.Space.sectionGap) {
            HStack {
                Text("Trim")
                    .font(Theme.TypeScale.cardTitleLarge)
                    .foregroundStyle(Theme.ink)
                Spacer()
                Button {
                    showTrim = false
                    model.trimming = false
                } label: {
                    Text("Done")
                        .font(Theme.TypeScale.controlSemibold)
                        .foregroundStyle(Theme.violetLight)
                        .frame(minWidth: Theme.Size.minHitTarget, minHeight: Theme.Size.minHitTarget)
                }
                .buttonStyle(.plain)
            }

            Text("Drag the two handles, then save the selection as a new clip. Your original recording is kept untouched.")
                .font(Theme.TypeScale.body)
                .foregroundStyle(Theme.ink2)

            Tray(role: .tile) {
                ReadingSurface(radius: Theme.Radius.tileCard) {
                    VStack(alignment: .leading, spacing: Theme.Space.bentoGap) {
                        HStack {
                            Eyebrow(text: "In · \(StudioFormat.clock(min(trimIn, trimOut)))", color: Theme.violetLight)
                            Spacer()
                            Eyebrow(text: "Out · \(StudioFormat.clock(max(trimIn, trimOut)))", color: Theme.gold)
                        }

                        TrimRangeBar(start: $trimIn, end: $trimOut, total: total)
                            .frame(height: Theme.Size.minHitTarget)
                    }
                    .padding(16)
                }
            }

            PrimaryPill(title: "Save as new clip", system: "checkmark") {
                let start = min(trimIn, trimOut)
                let end = max(trimIn, trimOut)
                model.trimClip(clip.id, start: start, end: end)
                showTrim = false
                model.trimming = false
            }

            Spacer()
        }
        .padding(Theme.Space.sheetMargin)
        .background(Theme.ground.ignoresSafeArea())
    }

    // MARK: - Playback, Share & Photos

    private func togglePlayback(_ clip: Clip) {
        guard model.link != .offline, let url = model.http("/files/clip/\(clip.id)") else { return }
        if player == nil {
            player = AVPlayer(url: url)
        }
        if playing {
            player?.pause()
            playing = false
        } else {
            player?.play()
            playing = true
        }
    }

    private func metaLine(_ clip: Clip) -> String {
        let when = clip.createdAt.map { StudioFormat.dayAndTime($0, now: Date()) } ?? "—"
        let length = clip.writing ? "—" : (clip.duration.map(shortDuration) ?? "—")
        return "\(when) · \(length)"
    }

    private func qualitySummary(_ clip: Clip) -> String {
        if clip.resolution.isEmpty { return "—" }
        let h = clip.resolution.split(separator: "x").last.map(String.init) ?? clip.resolution
        let ratePart = clip.fps > 0 ? "\(h)p\(clip.fps)" : clip.resolution
        if clip.encoder.isEmpty { return ratePart }
        return "\(ratePart) · \(clip.encoder)"
    }

    private func shortDuration(_ seconds: Double) -> String {
        let whole = max(0, Int(seconds.rounded(.down)))
        if whole >= 3600 { return StudioFormat.clock(seconds) }
        return String(format: "%d:%02d", whole / 60, whole % 60)
    }

    private func deleteDialogTitle(_ clip: Clip) -> String {
        var line = "Delete this clip from Studio PC and nas-vault?"
        if clip.offload.isActive {
            let target = model.studio?.settings.offloadTarget ?? "—"
            line += " It’s still being copied to \(target)."
        }
        return line
    }

    private func copyFilePath(_ clip: Clip) {
        let joined = "\(clip.folder)/\(clip.file)"
        if joined.contains(":\\") || clip.folder.contains(":") || clip.file.contains(":") {
            model.toast("That path stays on Studio PC.")
            return
        }
        UIPasteboard.general.string = joined
        model.toast("Copied file path.")
    }

    private func share(_ clip: Clip) {
        guard let remote = model.http("/files/clip/\(clip.id)") else { return }
        busy = true
        URLSession.shared.downloadTask(with: remote) { url, _, _ in
            Task { @MainActor in
                busy = false
                guard let url = url else {
                    model.toast("Studio PC didn’t send the file.")
                    return
                }
                let dest = FileManager.default.temporaryDirectory.appendingPathComponent(clip.file)
                try? FileManager.default.removeItem(at: dest)
                try? FileManager.default.copyItem(at: url, to: dest)
                shareItem = ShareItem(url: dest)
            }
        }.resume()
    }

    private func saveToPhotos(_ clip: Clip) {
        PHPhotoLibrary.requestAuthorization(for: .addOnly) { status in
            Task { @MainActor in
                guard status == .authorized || status == .limited else {
                    model.toast("Photos access is off.")
                    return
                }
                guard let remote = model.http("/files/clip/\(clip.id)") else { return }
                URLSession.shared.downloadTask(with: remote) { url, _, _ in
                    guard let url = url else {
                        Task { @MainActor in model.toast("Studio PC didn’t send the file.") }
                        return
                    }
                    PHPhotoLibrary.shared().performChanges {
                        PHAssetChangeRequest.creationRequestForAssetFromVideo(atFileURL: url)
                    } completionHandler: { ok, _ in
                        Task { @MainActor in
                            model.toast(ok ? "Saved to Photos." : "Photos couldn’t take that clip.")
                        }
                    }
                }.resume()
            }
        }
    }
}

private struct TrimRangeBar: View {
    @Binding var start: Double
    @Binding var end: Double
    var total: Double

    var body: some View {
        GeometryReader { geo in
            let width = max(1, geo.size.width - 24)
            let startFrac = CGFloat(min(1.0, max(0.0, start / total)))
            let endFrac = CGFloat(min(1.0, max(0.0, end / total)))
            let lo = min(startFrac, endFrac)
            let hi = max(startFrac, endFrac)

            ZStack(alignment: .leading) {
                Capsule()
                    .fill(Theme.ink.opacity(0.10))
                    .frame(height: 8)
                    .padding(.horizontal, 12)

                Capsule()
                    .fill(LinearGradient(colors: [Theme.violet, Theme.gold], startPoint: .leading, endPoint: .trailing))
                    .frame(width: max(8, width * (hi - lo)), height: 8)
                    .offset(x: 12 + width * lo)

                Circle()
                    .fill(Theme.violetPale)
                    .frame(width: 24, height: 24)
                    .overlay(Circle().stroke(Theme.inkDark, lineWidth: 2))
                    .offset(x: width * startFrac)
                    .gesture(
                        DragGesture(minimumDistance: 0).onChanged { value in
                            let frac = min(1.0, max(0.0, Double((value.location.x - 12) / width)))
                            start = min(end - 0.1, frac * total)
                        }
                    )

                Circle()
                    .fill(Theme.gold)
                    .frame(width: 24, height: 24)
                    .overlay(Circle().stroke(Theme.inkDark, lineWidth: 2))
                    .offset(x: width * endFrac)
                    .gesture(
                        DragGesture(minimumDistance: 0).onChanged { value in
                            let frac = min(1.0, max(0.0, Double((value.location.x - 12) / width)))
                            end = max(start + 0.1, frac * total)
                        }
                    )
            }
            .frame(maxHeight: .infinity)
        }
    }
}

private struct ShareItem: Identifiable {
    var url: URL
    var id: String { return url.absoluteString }
}

private struct ShareSheet: UIViewControllerRepresentable {
    var url: URL

    func makeUIViewController(context: Context) -> UIActivityViewController {
        return UIActivityViewController(activityItems: [url], applicationActivities: nil)
    }

    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
