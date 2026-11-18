import AVKit
import Photos
import SwiftUI

struct ClipDetailView: View {
    var id: String
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    @Environment(\.dismiss) private var dismiss
    @State private var player: AVPlayer?
    @State private var position: Double = 0
    @State private var playing = false
    @State private var full = false
    @State private var confirmDelete = false
    @State private var showTrim = false
    @State private var trimIn = 0.0
    @State private var trimOut = 1.0
    @State private var shareItem: ShareItem?
    @State private var busy = false

    private var clip: Clip? { model.studio?.clips.first { $0.id == id } }

    var body: some View {
        Group {
            if let clip {
                detail(clip)
            } else {
                Text("That clip is no longer on Studio PC.")
                    .foregroundStyle(Theme.ink2)
                    .padding(24)
            }
        }
        .background(Theme.ground.ignoresSafeArea())
        .toolbar(.hidden, for: .navigationBar)
        .onAppear { model.playback = true }
        .onDisappear {
            player?.pause()
            model.playback = false
            model.trimming = false
        }
    }

    private func detail(_ clip: Clip) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                stage(clip)
                VStack(alignment: .leading, spacing: 14) {
                    Text("\(clip.game.name) · \(clip.label)")
                        .font(.system(size: 28, weight: .bold))
                        .foregroundStyle(Theme.ink)
                    Text(meta(clip))
                        .font(.system(size: 14))
                        .foregroundStyle(Theme.ink2)
                    scrubber(clip)
                    facts(clip)
                    actions(clip)
                }
                .padding(.horizontal, 16)
                .offset(y: -48)
            }
            .padding(.bottom, 80)
        }
        .confirmationDialog(deleteTitle(clip), isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Delete", role: .destructive) { model.deleteClip(clip.id) }
            Button("Cancel", role: .cancel) {}
        }
        .sheet(isPresented: $showTrim) {
            trimSheet(clip)
        }
        .sheet(item: $shareItem) { item in
            ShareSheet(url: item.url)
        }
        .fullScreenCover(isPresented: $full) {
            if let player {
                VideoPlayer(player: player).ignoresSafeArea()
                    .onTapGesture(count: 2) { full = false }
            }
        }
    }

    private func stage(_ clip: Clip) -> some View {
        ZStack {
            ClipStill(reference: clip.thumbnailURL, seed: stillSeed(clip.id))
            LinearGradient(
                colors: [
                    Color(red: 7 / 255, green: 6 / 255, blue: 14 / 255).opacity(0.45),
                    .clear,
                    .clear,
                    Theme.ground
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            if playing, let player {
                VideoPlayer(player: player)
            } else if model.link == .offline || model.http("/files/clip/\(clip.id)") == nil {
                VStack(spacing: 8) {
                    Image(systemName: "play.slash").font(.system(size: 28, weight: .light))
                    Text(model.link == .offline ? "Playback is off while Studio PC is offline." : "Studio PC hasn’t sent this file yet.")
                        .font(.system(size: 14))
                        .multilineTextAlignment(.center)
                }
                .foregroundStyle(Theme.ink2)
                .padding(24)
            }
            HStack {
                round("chevron.left") { dismiss() }
                Spacer()
                Menu {
                    Button("Copy file name") { copyName(clip) }
                    Button("Open on PC") { model.toast("Open on PC is set on Studio PC.") }
                    Button("Rename label") { model.toast("Rename is set on Studio PC.") }
                } label: {
                    roundLabel("ellipsis")
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 54)
            .frame(maxHeight: .infinity, alignment: .top)
            Button {
                toggle(clip)
            } label: {
                GlassCircle(system: playing ? "pause.fill" : "play.fill", size: 68)
            }
            .buttonStyle(PressScaleStyle())
            .disabled(model.link == .offline)
            .opacity(model.link == .offline ? 0.45 : 1)
        }
        .frame(height: 360)
        .onTapGesture(count: 2) { full = true }
    }

    private func scrubber(_ clip: Clip) -> some View {
        let total = clip.duration ?? 0
        return VStack(spacing: 8) {
            GeometryReader { geo in
                let width = geo.size.width
                ZStack(alignment: .leading) {
                    Capsule().fill(Theme.ink.opacity(0.10)).frame(height: 6)
                    Capsule()
                        .fill(LinearGradient(colors: [Theme.violet, Theme.violetLight], startPoint: .leading, endPoint: .trailing))
                        .frame(width: max(6, width * CGFloat(position / max(total, 0.1))), height: 6)
                    if total > 0 {
                        ForEach(Array(clip.highlights.enumerated()), id: \.offset) { _, mark in
                            RoundedRectangle(cornerRadius: 2, style: .continuous)
                                .fill(Theme.amber)
                                .frame(width: 4, height: 18)
                                .offset(x: width * CGFloat(mark.at / total) - 2)
                                .accessibilityLabel(mark.label ?? "Highlight")
                                .onTapGesture {
                                    position = mark.at
                                    player?.seek(to: CMTime(seconds: mark.at, preferredTimescale: 600))
                                }
                        }
                    }
                    Circle()
                        .fill(Theme.ink)
                        .frame(width: 20, height: 20)
                        .offset(x: width * CGFloat(position / max(total, 0.1)) - 10)
                }
                .frame(height: 30)
                .gesture(DragGesture(minimumDistance: 0).onChanged { value in
                    guard total > 0, !clip.writing, model.link != .offline else { return }
                    position = min(total, max(0, total * value.location.x / width))
                }.onEnded { _ in
                    player?.seek(to: CMTime(seconds: position, preferredTimescale: 600))
                })
            }
            .frame(height: 30)
            HStack {
                Text(StudioFormat.clock(position)).foregroundStyle(Theme.ink2)
                Spacer()
                Text("\(clip.highlights.count) highlights").foregroundStyle(tone.tertiary)
                Spacer()
                Text(clip.duration == nil ? "—" : StudioFormat.clock(total)).foregroundStyle(Theme.ink2)
            }
            .font(.system(size: 12))
        }
    }

    private func facts(_ clip: Clip) -> some View {
        ReadingSurface {
            VStack(spacing: 0) {
                fact("Quality", clip.resolution.isEmpty ? "—" : "\(clip.resolution) · \(clip.fps) fps · \(clip.encoder)")
                fact("Size", StudioFormat.bytes(clip.bytes))
                fact("Stored", stored(clip))
                fact("Folder", clip.folder)
            }
            .padding(.horizontal, 14)
        }
    }

    private func fact(_ title: String, _ value: String) -> some View {
        HStack {
            Text(title).foregroundStyle(Theme.ink)
            Spacer()
            Text(value).foregroundStyle(tone.tertiary).lineLimit(1).truncationMode(.middle)
        }
        .font(.system(size: 16))
        .frame(minHeight: 50)
    }

    private func actions(_ clip: Clip) -> some View {
        let blocked = clip.writing || clip.offload.isActive
        return VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 12) {
                action("square.and.arrow.up", "Share") { share(clip) }
                action("arrow.down.to.line", "Save") { save(clip) }
                action("scissors", "Trim") {
                    trimOut = clip.duration ?? 1
                    model.trimming = true
                    showTrim = true
                }
                .disabled(blocked)
                .opacity(blocked ? 0.45 : 1)
                action("trash", "Delete", coral: true) { confirmDelete = true }
            }
            if blocked {
                Text(clip.writing ? "Trim waits until the clip has finished writing." : "Trim waits until the copy to NAS has finished.")
                    .font(.system(size: 13))
                    .foregroundStyle(tone.tertiary)
            }
        }
    }

    private func action(_ system: String, _ title: String, coral: Bool = false, go: @escaping () -> Void) -> some View {
        Button(action: go) {
            VStack(spacing: 6) {
                Image(systemName: system)
                    .font(.system(size: 18, weight: .light))
                    .frame(width: 56, height: 56)
                    .background(Circle().fill(coral ? Theme.coral.opacity(0.16) : Theme.ink.opacity(0.06)))
                    .overlay(Circle().stroke(coral ? Theme.coral.opacity(0.5) : Color.white.opacity(0.08), lineWidth: 1))
                Text(title).font(.system(size: 12, weight: .semibold))
            }
            .foregroundStyle(coral ? Theme.coralText : Theme.ink)
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(PressScaleStyle())
        .disabled(model.link == .offline || busy)
        .opacity(model.link == .offline ? 0.45 : 1)
    }

    private func trimSheet(_ clip: Clip) -> some View {
        let total = max(clip.duration ?? 1, 0.1)
        return NavigationStack {
            VStack(alignment: .leading, spacing: 16) {
                Text("Drag the two points, then save the selection as a new clip. The original stays.")
                    .font(.system(size: 15))
                    .foregroundStyle(Theme.ink2)
                Text("In \(StudioFormat.clock(trimIn))")
                Slider(value: $trimIn, in: 0 ... total)
                Text("Out \(StudioFormat.clock(trimOut))")
                Slider(value: $trimOut, in: 0 ... total)
                PrimaryPill(title: "Save as new clip", system: "checkmark") {
                    let start = min(trimIn, trimOut)
                    let end = max(trimIn, trimOut)
                    model.trimClip(clip.id, start: start, end: end)
                    showTrim = false
                    model.trimming = false
                }
                Spacer()
            }
            .padding(20)
            .background(Theme.ground)
            .navigationTitle("Trim")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") {
                        showTrim = false
                        model.trimming = false
                    }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    private func round(_ system: String, action: @escaping () -> Void) -> some View {
        Button(action: action) { roundLabel(system) }.buttonStyle(.plain).accessibilityLabel("Back")
    }

    private func roundLabel(_ system: String) -> some View {
        Image(systemName: system)
            .font(.system(size: 16, weight: .semibold))
            .foregroundStyle(Theme.ink)
            .frame(width: 40, height: 40)
            .background(.ultraThinMaterial, in: Circle())
    }

    private func toggle(_ clip: Clip) {
        guard model.link != .offline, let url = model.http("/files/clip/\(clip.id)") else { return }
        if player == nil { player = AVPlayer(url: url) }
        if playing {
            player?.pause()
            playing = false
        } else {
            player?.play()
            playing = true
        }
    }

    private func meta(_ clip: Clip) -> String {
        let when = clip.createdAt.map { StudioFormat.dayAndTime($0, now: Date()) } ?? "—"
        let length = clip.duration.map { StudioFormat.clock($0) } ?? "—"
        return "\(when) · \(length) · \(clip.label)"
    }

    private func stored(_ clip: Clip) -> String {
        let target = model.studio?.settings.offloadTarget ?? "NAS"
        switch clip.offload {
        case let .moving(progress, _):
            return "Offloading \(Int(progress * 100))%"
        case .queued:
            return "Queued"
        case .done:
            return clip.locations.contains("pc") ? "\(target) + Studio PC" : target
        case .failed(let reason):
            return reason
        case .none:
            if clip.locations.contains("nas") {
                return clip.locations.contains("pc") ? "\(target) + Studio PC" : target
            }
            return "Studio PC"
        }
    }

    private func deleteTitle(_ clip: Clip) -> String {
        var line = "Delete this clip from Studio PC and nas-vault?"
        if clip.offload.isActive {
            line += " It’s still being copied to nas-vault."
        }
        return line
    }

    private func copyName(_ clip: Clip) {
        let joined = "\(clip.folder)/\(clip.file)"
        if joined.contains(":\\") || clip.folder.contains(":") || clip.file.contains(":") {
            model.toast("That path stays on Studio PC.")
            return
        }
        UIPasteboard.general.string = joined
        model.toast("Copied the file name.")
    }

    private func share(_ clip: Clip) {
        guard let remote = model.http("/files/clip/\(clip.id)") else { return }
        busy = true
        URLSession.shared.downloadTask(with: remote) { url, _, _ in
            Task { @MainActor in
                busy = false
                guard let url else {
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

    private func save(_ clip: Clip) {
        PHPhotoLibrary.requestAuthorization(for: .addOnly) { status in
            Task { @MainActor in
                guard status == .authorized || status == .limited else {
                    model.toast("Photos access is off.")
                    return
                }
                guard let remote = model.http("/files/clip/\(clip.id)") else { return }
                URLSession.shared.downloadTask(with: remote) { url, _, _ in
                    guard let url else {
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

private struct ShareItem: Identifiable {
    var url: URL
    var id: String { url.absoluteString }
}

private struct ShareSheet: UIViewControllerRepresentable {
    var url: URL

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: [url], applicationActivities: nil)
    }

    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
