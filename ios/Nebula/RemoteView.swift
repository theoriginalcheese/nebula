import SwiftUI
import UIKit

struct RemoteView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.tone) private var tone
    @Environment(\.openURL) private var openURL

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Space.bentoGap) {
            hostTray
            tilesRow
            peersSection
        }
    }

    // MARK: - Host Tray (3e: 34/28 Hero Tray + PrimaryPill)

    private var hostTray: some View {
        let online = model.link == .online
        return Tray(role: .hero) {
            ReadingSurface(radius: Theme.Radius.heroCard, kind: .hero) {
                VStack(alignment: .leading, spacing: 18) {
                    HStack(spacing: 16) {
                        HostEmblem()
                            .frame(width: Theme.Size.hostAvatar, height: Theme.Size.hostAvatar)
                            .clipShape(Circle())
                            .overlay(
                                Circle()
                                    .stroke(Theme.ink.opacity(0.16), lineWidth: Theme.Stroke.hairline)
                            )
                            .shadow(color: Theme.violet.opacity(0.25), radius: 15)

                        VStack(alignment: .leading, spacing: 4) {
                            Text("Studio PC")
                                .font(Theme.TypeScale.cardTitleLarge)
                                .foregroundStyle(Theme.ink)

                            HStack(spacing: 6) {
                                Circle()
                                    .fill(online ? Theme.teal : tone.tertiary)
                                    .frame(width: 7, height: 7)
                                Text(hostStatusLabel)
                                    .font(Theme.TypeScale.subtitle)
                                    .foregroundStyle(online ? Theme.teal : tone.tertiary)
                            }

                            Text(model.streaming ? "Streaming to iPhone" : "Moonlight not running")
                                .font(Theme.TypeScale.subtitle)
                                .foregroundStyle(Theme.ink2)
                        }
                    }

                    // Always try moonlight://. canOpenURL is only a hint (it
                    // reads LSApplicationQueriesSchemes from the signed plist),
                    // so a false there must never send the user to the store.
                    PrimaryPill(title: "Stream to this phone", system: "play.fill") {
                        model.stream {
                            openMoonlight()
                        }
                    }
                }
                .padding(20)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    // MARK: - Stream & Controller Bento Tiles (3e: 30/24 Tile Trays)

    private var tilesRow: some View {
        Group {
            if typeSize >= .accessibility1 {
                VStack(spacing: Theme.Space.bentoGap) {
                    infoTile(eyebrow: "Stream", value: panelValue, detail: panelDetail)
                    infoTile(eyebrow: "Controller", value: "On screen", detail: "Or pair a pad")
                }
            } else {
                HStack(alignment: .top, spacing: Theme.Space.bentoGap) {
                    infoTile(eyebrow: "Stream", value: panelValue, detail: panelDetail)
                    infoTile(eyebrow: "Controller", value: "On screen", detail: "Or pair a pad")
                }
            }
        }
    }

    private func infoTile(eyebrow: String, value: String, detail: String) -> some View {
        Tray(role: .tile) {
            ReadingSurface(radius: Theme.Radius.tileCard) {
                VStack(alignment: .leading, spacing: 6) {
                    Eyebrow(text: eyebrow)
                    Text(value)
                        .font(Theme.TypeScale.cardTitle)
                        .foregroundStyle(Theme.ink)
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                    Text(detail)
                        .font(Theme.TypeScale.caption)
                        .foregroundStyle(tone.tertiary)
                        .lineLimit(1)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    // MARK: - Tailscale Peers Group (3e: Labels Only, Zero IPs / Ping)

    private var peersSection: some View {
        let peers = model.studio?.peers ?? []
        return VStack(alignment: .leading, spacing: Theme.Space.chipGap) {
            HStack(alignment: .firstTextBaseline) {
                Eyebrow(text: "Tailscale peers", color: Theme.ink2)
                Spacer()
                Text(peers.isEmpty ? "—" : "\(peers.count) \(peers.count == 1 ? "device" : "devices")")
                    .font(Theme.TypeScale.caption)
                    .foregroundStyle(tone.tertiary)
            }
            .padding(.horizontal, Theme.Space.headerInset)
            .padding(.top, 4)

            ReadingSurface(radius: Theme.Radius.group) {
                if peers.isEmpty {
                    Text("No Tailscale peers reported.")
                        .font(Theme.TypeScale.rowValue)
                        .foregroundStyle(tone.tertiary)
                        .padding(16)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    VStack(spacing: 0) {
                        ForEach(Array(peers.enumerated()), id: \.element.id) { index, peer in
                            if index > 0 {
                                GroupDivider()
                            }
                            HStack(spacing: Theme.Space.bentoGap) {
                                ZStack {
                                    RoundedRectangle(cornerRadius: Theme.Radius.peerIcon, style: .continuous)
                                        .fill(Theme.ink.opacity(0.06))
                                    Image(systemName: peerIcon(for: peer))
                                        .font(Theme.TypeScale.icon(16, weight: .light))
                                        .foregroundStyle(Theme.ink2)
                                }
                                .frame(width: Theme.Size.peerIconBox, height: Theme.Size.peerIconBox)

                                VStack(alignment: .leading, spacing: 1) {
                                    Text(peer.name)
                                        .font(Theme.TypeScale.rowLabel)
                                        .foregroundStyle(Theme.ink)
                                        .lineLimit(1)
                                    Text(peer.online ? "Online" : "Offline")
                                        .font(Theme.TypeScale.caption)
                                        .foregroundStyle(peer.online ? Theme.teal : tone.tertiary)
                                }

                                Spacer()

                                Circle()
                                    .fill(peer.online ? Theme.teal : Theme.inkMuted)
                                    .frame(width: 8, height: 8)
                            }
                            .frame(minHeight: Theme.Size.peerRowHeight)
                        }
                    }
                    .padding(.horizontal, 16)
                }
            }
        }
    }

    private func peerIcon(for peer: Peer) -> String {
        let lower = peer.name.lowercased()
        if lower.contains("laptop") || lower.contains("book") {
            return "laptopcomputer"
        }
        if lower.contains("phone") || lower.contains("iphone") {
            return "iphone"
        }
        return "desktopcomputer"
    }

    private var hostStatusLabel: String {
        if model.link != .online { return "Offline" }
        if model.studio?.settings.tailscale == true { return "Online on Tailscale" }
        return "Online"
    }

    private func openMoonlight() {
        guard let url = URL(string: "moonlight://") else { return }
        openURL(url) { accepted in
            if !accepted {
                model.toast("Couldn’t open Moonlight on this phone.")
            }
        }
    }

    // MARK: - This phone's real panel

    private var phoneScreen: UIScreen? {
        for scene in UIApplication.shared.connectedScenes {
            if let windowScene = scene as? UIWindowScene {
                return windowScene.screen
            }
        }
        return nil
    }

    /// Native pixels, long edge first: what this panel really is, or an em dash.
    private var panelValue: String {
        guard let screen = phoneScreen else { return "—" }
        let pixels = screen.nativeBounds
        let longEdge = Int(max(pixels.width, pixels.height).rounded())
        let shortEdge = Int(min(pixels.width, pixels.height).rounded())
        if longEdge <= 0 || shortEdge <= 0 { return "—" }
        return "\(longEdge)×\(shortEdge)"
    }

    private var panelDetail: String {
        guard let screen = phoneScreen else { return "This phone" }
        let rate = screen.maximumFramesPerSecond
        if rate <= 0 { return "This phone" }
        return "\(rate) Hz · this phone"
    }
}
