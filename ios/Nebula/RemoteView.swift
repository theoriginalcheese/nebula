import SwiftUI
import UIKit

struct RemoteView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    @Environment(\.openURL) private var openURL

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            host
            HStack(alignment: .top, spacing: 12) {
                infoTile("Stream", "1080p · 60", "Matches this screen")
                infoTile("Controller", "On screen", "Or pair a pad")
            }
            peers
        }
    }

    private var host: some View {
        Tray {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 14) {
                    NightCity()
                        .frame(width: 76, height: 76)
                        .clipShape(Circle())
                        .overlay(Circle().stroke(Theme.violet.opacity(0.7), lineWidth: 2))
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Studio PC")
                            .font(.system(size: 20, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                        Text(status)
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(model.link == .online ? Theme.teal : tone.tertiary)
                        Text(model.streaming ? "Streaming to iPhone" : "Moonlight not running")
                            .font(.system(size: 13))
                            .foregroundStyle(tone.tertiary)
                    }
                }
                if moonlightOnPhone {
                    PrimaryPill(title: "Stream to this phone", system: "play.fill") {
                        model.stream {
                            if let url = URL(string: "moonlight://") {
                                openURL(url)
                            }
                        }
                    }
                    .disabled(model.link != .online)
                    .opacity(model.link == .online ? 1 : 0.45)
                } else {
                    PrimaryPill(title: "Get Moonlight", system: "arrow.down") {
                        if let url = URL(string: "https://apps.apple.com/search?term=Moonlight%20Game%20Streaming") {
                            openURL(url)
                        }
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
                }
            }
        }
    }

    private var peers: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Eyebrow(text: "Tailscale peers", color: Theme.ink2)
                Spacer()
                Text("\((model.studio?.peers ?? []).count) devices")
                    .font(.system(size: 12))
                    .foregroundStyle(tone.tertiary)
            }
            VStack(spacing: 0) {
                ForEach(model.studio?.peers ?? []) { peer in
                    HStack(spacing: 12) {
                        Image(systemName: "desktopcomputer")
                            .font(.system(size: 16, weight: .light))
                            .foregroundStyle(Theme.ink)
                            .frame(width: 32)
                        Text(peer.name).font(.system(size: 16)).foregroundStyle(Theme.ink)
                        Spacer()
                        Text(peer.online ? "Online" : "Offline")
                            .font(.system(size: 14))
                            .foregroundStyle(peer.online ? Theme.teal : tone.tertiary)
                        Circle().fill(peer.online ? Theme.teal : Theme.ink3).frame(width: 8, height: 8)
                    }
                    .frame(minHeight: 58)
                    .padding(.horizontal, 12)
                }
            }
            .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Theme.card.opacity(0.55)))
            if (model.studio?.peers ?? []).isEmpty {
                Text("No peers reported.")
                    .foregroundStyle(tone.tertiary)
            }
        }
    }

    private func infoTile(_ title: String, _ value: String, _ detail: String) -> some View {
        Tray(radius: 30) {
            VStack(alignment: .leading, spacing: 6) {
                Eyebrow(text: title, color: tone.tertiary)
                Text(value).font(.system(size: 18, weight: .semibold)).foregroundStyle(Theme.ink)
                Text(detail).font(.system(size: 13)).foregroundStyle(tone.tertiary)
            }
            .padding(14)
            .frame(maxWidth: .infinity, minHeight: 110, alignment: .leading)
            .background(Theme.card.opacity(0.55))
        }
    }

    private var status: String {
        if model.link != .online { return "Offline" }
        if model.studio?.settings.tailscale == true { return "Online on Tailscale" }
        return "Online"
    }

    private var moonlightOnPhone: Bool {
        guard let url = URL(string: "moonlight://") else { return false }
        return UIApplication.shared.canOpenURL(url)
    }
}

private struct NightCity: View {
    var body: some View {
        Canvas { context, size in
            context.fill(Path(CGRect(origin: .zero, size: size)), with: .linearGradient(
                Gradient(colors: [Color(red: 0.08, green: 0.07, blue: 0.18), Color(red: 0.02, green: 0.02, blue: 0.05)]),
                startPoint: .zero,
                endPoint: CGPoint(x: size.width, y: size.height)
            ))
            var rng = SplitMix(seed: 42)
            for _ in 0 ..< 18 {
                let x = rng.unit() * size.width
                let h = 10 + rng.unit() * size.height * 0.45
                let rect = CGRect(x: x, y: size.height - h, width: 6, height: h)
                context.fill(Path(rect), with: .color(Theme.violet.opacity(0.8)))
            }
        }
        .accessibilityHidden(true)
    }
}
