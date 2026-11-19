import SwiftUI

// MARK: - 1. The One Tray ("Machined Bezel", §6.2)

enum TrayRole {
    case hero     // 34 outer -> 28 inner
    case featured // 32 outer -> 26 inner
    case tile     // 30 outer -> 24 inner

    var outerRadius: CGFloat {
        switch self {
        case .hero:
            return Theme.Radius.heroTray
        case .featured:
            return Theme.Radius.featuredTray
        case .tile:
            return Theme.Radius.tileTray
        }
    }

    var innerRadius: CGFloat {
        return outerRadius - Theme.Space.trayPad
    }
}

enum TrayTint {
    case standard
    case violet
}

struct Tray<Content: View>: View {
    var role: TrayRole = .hero
    var tint: TrayTint = .standard
    @Environment(\.tone) private var tone
    @ViewBuilder var content: () -> Content

    var body: some View {
        let outer = role.outerRadius
        let inner = role.innerRadius
        content()
            .clipShape(RoundedRectangle(cornerRadius: inner, style: .continuous))
            .padding(Theme.Space.trayPad)
            .background(
                RoundedRectangle(cornerRadius: outer, style: .continuous)
                    .fill(fillColor)
            )
            .overlay(
                RoundedRectangle(cornerRadius: outer, style: .continuous)
                    .stroke(strokeColor, lineWidth: Theme.Stroke.hairline)
            )
    }

    private var fillColor: Color {
        switch tint {
        case .standard:
            return Theme.ink.opacity(Theme.Opacity.trayFill)
        case .violet:
            return Theme.violet.opacity(0.08)
        }
    }

    private var strokeColor: Color {
        switch tint {
        case .standard:
            return Theme.ink.opacity(tone.hairline)
        case .violet:
            return Theme.violet.opacity(0.28)
        }
    }
}

// MARK: - 2. The One Glass Reading Surface (glass / lively / solid, §6.2)

enum SurfaceKind {
    case reading // Follows PhonePrefs.surfaces (glass / lively / solid) + per-background contrast table
    case hero    // Live hero glass: rgba(16,13,28,.50) + ultraThinMaterial (or inkDark when reduceTransparency)
    case prompt  // Violet radial glow over live glass (3c pending card)
    case sheet   // Modal sheet glass: rgba(22,18,38,.72) + ultraThinMaterial
    case bar     // Floating pill / search / banner glass: rgba(30,26,48,.30-.34) + ultraThinMaterial
}

struct ReadingSurface<Content: View>: View {
    var radius: CGFloat = Theme.Radius.tileCard
    var kind: SurfaceKind = .reading
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    @ViewBuilder var content: () -> Content

    var body: some View {
        content()
            .background(surfaceFill)
            .clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .stroke(borderColor, lineWidth: Theme.Stroke.hairline)
            )
    }

    private var borderColor: Color {
        switch kind {
        case .hero, .prompt, .sheet:
            return Theme.specular.opacity(tone.increaseContrast ? Theme.Opacity.highContrastHairline : 0.12)
        case .bar:
            return Theme.specular.opacity(tone.hairline)
        case .reading:
            return Theme.ink.opacity(tone.hairline)
        }
    }

    @ViewBuilder private var surfaceFill: some View {
        switch kind {
        case .hero:
            if tone.reduceTransparency {
                Theme.inkDark
            } else {
                ZStack {
                    Rectangle().fill(.ultraThinMaterial)
                    Theme.glassHeroBase.opacity(Theme.Opacity.heroGlassFill)
                    LinearGradient(
                        colors: [Theme.specular.opacity(0.12), Theme.clear],
                        startPoint: .top,
                        endPoint: UnitPoint(x: 0.5, y: 0.35)
                    )
                }
            }
        case .prompt:
            if tone.reduceTransparency {
                Theme.card
            } else {
                ZStack {
                    Rectangle().fill(.ultraThinMaterial)
                    Theme.glassHeroBase.opacity(0.60)
                    RadialGradient(
                        colors: [Theme.violet.opacity(0.22), Theme.clear],
                        center: .topLeading,
                        startRadius: 0,
                        endRadius: 220
                    )
                }
            }
        case .sheet:
            if tone.reduceTransparency {
                Theme.card
            } else {
                ZStack {
                    Rectangle().fill(.ultraThinMaterial)
                    Theme.glassSheetBase.opacity(Theme.Opacity.sheetGlassFill)
                }
            }
        case .bar:
            if tone.reduceTransparency {
                Theme.card
            } else {
                ZStack {
                    Rectangle().fill(.ultraThinMaterial)
                    Theme.glassBarBase.opacity(Theme.Opacity.searchGlassFill)
                }
            }
        case .reading:
            if tone.reduceTransparency || model.prefs.surfaces == .solid {
                Theme.card
            } else if model.prefs.surfaces == .lively {
                ZStack {
                    LinearGradient(
                        colors: [Theme.livelyTop, Theme.livelyBottom],
                        startPoint: UnitPoint(x: 0.15, y: 0.0),
                        endPoint: UnitPoint(x: 0.85, y: 1.0)
                    )
                    RadialGradient(
                        colors: [Theme.violet.opacity(0.30), Theme.clear],
                        center: .topLeading,
                        startRadius: 0,
                        endRadius: 190
                    )
                    RadialGradient(
                        colors: [Theme.magenta.opacity(0.18), Theme.clear],
                        center: .bottomTrailing,
                        startRadius: 0,
                        endRadius: 170
                    )
                }
            } else {
                let alpha = Theme.readingGlassAlpha(for: model.prefs.background.rawValue)
                ZStack {
                    Rectangle().fill(.ultraThinMaterial)
                    Theme.glassReadingBase.opacity(alpha)
                    LinearGradient(
                        colors: [Theme.violetLight.opacity(Theme.Opacity.specularMedium), Theme.clear],
                        startPoint: .topLeading,
                        endPoint: UnitPoint(x: 0.65, y: 0.46)
                    )
                }
            }
        }
    }
}

// MARK: - 3. The One Primary Pill (§6.4, Button-in-Button)

enum PillTone {
    case violet    // Primary action: violet tint .20 + .55 ring, 44pt trailing circle
    case coralTint // Start recording: coral tint .12 + .42 ring, coralText, tinted trailing circle (never solid coral!)
}

struct PrimaryPill: View {
    var title: String
    var system: String
    var toneStyle: PillTone = .violet
    var compact: Bool = false
    var action: () -> Void

    var body: some View {
        let height = compact ? Theme.Size.compactPillHeight : Theme.Size.primaryHeight
        let circleSize = compact ? Theme.Size.compactTrailingCircle : Theme.Size.primaryTrailingCircle
        let radius = height / 2.0

        Button(action: action) {
            HStack(spacing: Theme.Space.bentoGap) {
                Text(title)
                    .font(compact ? Theme.TypeScale.rowTitle : Theme.TypeScale.cardTitle)
                    .foregroundStyle(labelColor)
                    .lineLimit(1)
                Spacer(minLength: 4)
                ZStack {
                    Circle()
                        .fill(badgeFill)
                        .overlay(Circle().stroke(badgeRing, lineWidth: Theme.Stroke.hairline))
                    if toneStyle == .coralTint {
                        // The design's glyph: a 12pt dark dot on a solid coral circle.
                        Circle()
                            .fill(Theme.inkDark)
                            .frame(width: 12, height: 12)
                    } else {
                        Image(systemName: system)
                            .font(Theme.TypeScale.icon(compact ? 14 : 16, weight: .semibold))
                            .foregroundStyle(iconColor)
                    }
                }
                .frame(width: circleSize, height: circleSize)
            }
            .padding(.leading, compact ? 20 : 22)
            .padding(.trailing, compact ? 4 : 6)
            .frame(maxWidth: .infinity, minHeight: height)
            .background(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .fill(pillFill)
            )
            .overlay(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .stroke(pillRing, lineWidth: Theme.Stroke.hairline)
            )
            .contentShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
        }
        .buttonStyle(PressScaleStyle())
    }

    private var labelColor: Color {
        switch toneStyle {
        case .violet:
            return Theme.ink
        case .coralTint:
            return Theme.coralText
        }
    }

    private var iconColor: Color {
        switch toneStyle {
        case .violet:
            return Theme.ink
        case .coralTint:
            return Theme.coral
        }
    }

    private var pillFill: Color {
        switch toneStyle {
        case .violet:
            return Theme.violet.opacity(Theme.Opacity.primaryFill)
        case .coralTint:
            return Theme.coral.opacity(0.12)
        }
    }

    private var pillRing: Color {
        switch toneStyle {
        case .violet:
            return Theme.violet.opacity(Theme.Opacity.primaryRing)
        case .coralTint:
            return Theme.coral.opacity(0.42)
        }
    }

    private var badgeFill: Color {
        switch toneStyle {
        case .violet:
            return Theme.violet.opacity(Theme.Opacity.primaryBadgeFill)
        case .coralTint:
            return Theme.coral
        }
    }

    private var badgeRing: Color {
        switch toneStyle {
        case .violet:
            return Theme.violetLight.opacity(0.32)
        case .coralTint:
            return Theme.clear
        }
    }
}

// MARK: - 4. The One Segmented Control (§6.4, §7.1 Sliding Selection)

struct NebulaSegments: View {
    var options: [(id: String, title: String)]
    var selection: String
    var compact: Bool = false
    var onSelect: (String) -> Void

    @Environment(\.tone) private var tone
    @Namespace private var slideNamespace

    var body: some View {
        let trackHeight = compact ? Theme.Size.segmentCompactHeight : Theme.Size.segmentHeight
        let trackRadius = compact ? Theme.Radius.segmentCompactTrack : Theme.Radius.segmentTrack
        let thumbRadius = compact ? Theme.Radius.segmentCompactThumb : Theme.Radius.segmentThumb

        HStack(spacing: Theme.Space.segmentPad) {
            ForEach(options, id: \.id) { option in
                let isSelected = selection == option.id
                Button {
                    withAnimation(tone.motion) {
                        onSelect(option.id)
                    }
                } label: {
                    Text(option.title)
                        .font(compact ? Theme.TypeScale.segmentCompact : Theme.TypeScale.segment)
                        .foregroundStyle(isSelected ? Theme.ink : tone.tertiary)
                        .lineLimit(1)
                        .frame(maxWidth: .infinity)
                        .frame(height: trackHeight - Theme.Space.segmentPad * 2)
                        .background {
                            if isSelected {
                                RoundedRectangle(cornerRadius: thumbRadius, style: .continuous)
                                    .fill(Theme.violet.opacity(Theme.Opacity.segmentSelectedFill))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: thumbRadius, style: .continuous)
                                            .stroke(Theme.violetLight.opacity(Theme.Opacity.segmentSelectedRing), lineWidth: Theme.Stroke.hairline)
                                    )
                                    .matchedGeometryEffect(id: "segmentThumb", in: slideNamespace)
                            }
                        }
                        .frame(minHeight: Theme.Size.minHitTarget)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(isSelected ? .isSelected : [])
            }
        }
        .padding(.horizontal, Theme.Space.segmentPad)
        .frame(height: trackHeight)
        .background(
            RoundedRectangle(cornerRadius: trackRadius, style: .continuous)
                .fill(tone.reduceTransparency ? Theme.inkDark : Theme.segmentTrackBase.opacity(Theme.Opacity.segmentTrackFill))
        )
        .overlay(
            RoundedRectangle(cornerRadius: trackRadius, style: .continuous)
                .stroke(Theme.ink.opacity(tone.hairline), lineWidth: Theme.Stroke.hairline)
        )
        .frame(minHeight: Theme.Size.minHitTarget)
    }
}

// MARK: - 5. The One Eyebrow (§6.3, §11)

struct Eyebrow: View {
    var text: String
    var color: Color? = nil
    @Environment(\.tone) private var tone

    var body: some View {
        Text(text.uppercased())
            .font(Theme.TypeScale.eyebrow)
            .tracking(Theme.TypeScale.eyebrowTracking)
            .foregroundStyle(color ?? tone.tertiary)
            .lineLimit(1)
    }
}

// MARK: - Supporting Contract Micro-Primitives

struct PressScaleStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0)
            .animation(Theme.pressAnimation, value: configuration.isPressed)
    }
}

struct GroupDivider: View {
    @Environment(\.tone) private var tone

    var body: some View {
        Rectangle()
            .fill(Theme.ink.opacity(tone.hairline))
            .frame(height: Theme.Stroke.divider)
    }
}

struct GlassCircle: View {
    var system: String
    var size: CGFloat = Theme.Size.transportButton
    var tint: Color = Theme.ink
    var coralTint: Bool = false
    @Environment(\.tone) private var tone

    var body: some View {
        ZStack {
            if coralTint {
                Circle().fill(Theme.coral.opacity(0.14))
            } else if tone.reduceTransparency {
                Circle().fill(Theme.card)
            } else {
                Circle().fill(.ultraThinMaterial)
                Circle().fill(Theme.glassBarBase.opacity(Theme.Opacity.barGlassFill))
            }
            if !system.isEmpty {
                Image(systemName: system)
                    .font(Theme.TypeScale.icon(size * 0.38, weight: .light))
                    .foregroundStyle(coralTint ? Theme.coralSoft : tint)
            }
        }
        .frame(width: size, height: size)
        .overlay(
            Circle().stroke(
                coralTint ? Theme.coral.opacity(0.35) : Theme.specular.opacity(0.16),
                lineWidth: Theme.Stroke.hairline
            )
        )
        .frame(minWidth: Theme.Size.minHitTarget, minHeight: Theme.Size.minHitTarget)
        .contentShape(Circle())
    }
}

enum StatusChipStyle {
    case rec
    case paused
    case buffer
    case idle
    case latest
    case writing
}

struct StatusChip: View {
    var style: StatusChipStyle
    var customTitle: String? = nil

    var body: some View {
        HStack(spacing: 7) {
            Circle()
                .strokeBorder(dotColor, lineWidth: isHollow ? 1.5 : 0)
                .background(Circle().fill(isHollow ? Theme.clear : dotColor))
                .frame(width: 7, height: 7)
            Eyebrow(text: customTitle ?? defaultTitle, color: labelColor)
        }
        .padding(.horizontal, 11)
        .frame(height: chipHeight)
        .background(Capsule().fill(backgroundFill))
        .overlay(Capsule().stroke(borderStroke, lineWidth: Theme.Stroke.divider))
    }

    private var chipHeight: CGFloat {
        switch style {
        case .latest, .writing:
            return Theme.Size.badgeChipHeight
        default:
            return Theme.Size.statusChipHeight
        }
    }

    private var isHollow: Bool {
        switch style {
        case .paused:
            return true
        default:
            return false
        }
    }

    private var defaultTitle: String {
        switch style {
        case .rec:
            return "REC"
        case .paused:
            return "PAUSED"
        case .buffer:
            return "BUFFER"
        case .idle:
            return "IDLE"
        case .latest:
            return "LATEST"
        case .writing:
            return "WRITING"
        }
    }

    private var dotColor: Color {
        switch style {
        case .rec, .latest:
            return Theme.gold
        case .paused:
            return Theme.ink2
        case .buffer, .writing:
            return Theme.violetLight
        case .idle:
            return Theme.ink3
        }
    }

    private var labelColor: Color {
        switch style {
        case .rec, .latest:
            return Theme.gold
        case .paused, .idle:
            return Theme.ink2
        case .buffer, .writing:
            return Theme.violetPale
        }
    }

    private var backgroundFill: Color {
        switch style {
        case .rec:
            return Theme.gold.opacity(0.10)
        case .paused, .idle:
            return Theme.ink.opacity(0.08)
        case .buffer:
            return Theme.violet.opacity(0.16)
        case .latest, .writing:
            return Theme.glassHeroBase.opacity(Theme.Opacity.chipGlassFill)
        }
    }

    private var borderStroke: Color {
        switch style {
        case .rec, .latest:
            return Theme.gold.opacity(0.32)
        case .paused, .idle:
            return Theme.ink.opacity(0.18)
        case .buffer, .writing:
            return Theme.violetLight.opacity(0.38)
        }
    }
}

struct FlowLayout: Layout {
    var spacing: CGFloat = Theme.Space.tagGap
    var lineSpacing: CGFloat = Theme.Space.tagGap

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? Theme.Size.targetWidth
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        var usedWidth: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > 0 && x + size.width > maxWidth {
                x = 0
                y += rowHeight + lineSpacing
                rowHeight = 0
            }
            usedWidth = max(usedWidth, x + size.width)
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
        }
        return CGSize(width: min(maxWidth, max(usedWidth, 0)), height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX
        var y = bounds.minY
        var rowHeight: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > bounds.minX && x + size.width > bounds.maxX {
                x = bounds.minX
                y += rowHeight + lineSpacing
                rowHeight = 0
            }
            subview.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
        }
    }
}

struct ToastBanner: View {
    var text: String
    @Environment(\.tone) private var tone

    var body: some View {
        Text(text)
            .font(Theme.TypeScale.controlSemibold)
            .foregroundStyle(Theme.ink)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background {
                if tone.reduceTransparency {
                    Capsule().fill(Theme.card)
                } else {
                    Capsule().fill(.ultraThinMaterial)
                    Capsule().fill(Theme.glassHeroBase.opacity(Theme.Opacity.heroGlassFill))
                }
            }
            .overlay(Capsule().stroke(Theme.specular.opacity(0.14), lineWidth: Theme.Stroke.hairline))
            .padding(.horizontal, 24)
    }
}

func stillSeed(_ text: String) -> Int {
    return text.utf8.reduce(7) { ($0 &* 33) &+ Int($1) }
}

/// Abstract Nebula surface used when the PC has not supplied a thumbnail URL.
/// Never invents or bundles a photo of the user's footage.
struct ProceduralClipBackdrop: View {
    var seed: Int

    var body: some View {
        Canvas { context, size in
            var rng = SplitMix(seed: UInt64(bitPattern: Int64(seed)))
            let base = GraphicsContext.Shading.linearGradient(
                Gradient(colors: [Theme.inkDark, Theme.card, Theme.ground]),
                startPoint: .zero,
                endPoint: CGPoint(x: size.width, y: size.height)
            )
            context.fill(Path(CGRect(origin: .zero, size: size)), with: base)

            let cx1 = size.width * CGFloat(0.2 + rng.unit() * 0.6)
            let cy1 = size.height * CGFloat(0.15 + rng.unit() * 0.45)
            let r1 = max(size.width, size.height) * 0.55
            context.fill(
                Path(ellipseIn: CGRect(x: cx1 - r1, y: cy1 - r1 * 0.65, width: r1 * 2, height: r1 * 1.3)),
                with: .radialGradient(
                    Gradient(colors: [Theme.violet.opacity(0.28), Theme.clear]),
                    center: CGPoint(x: cx1, y: cy1),
                    startRadius: 0,
                    endRadius: r1
                )
            )

            let cx2 = size.width * CGFloat(0.25 + rng.unit() * 0.6)
            let cy2 = size.height * CGFloat(0.35 + rng.unit() * 0.45)
            let r2 = max(size.width, size.height) * 0.42
            context.fill(
                Path(ellipseIn: CGRect(x: cx2 - r2, y: cy2 - r2 * 0.65, width: r2 * 2, height: r2 * 1.3)),
                with: .radialGradient(
                    Gradient(colors: [Theme.magenta.opacity(0.18), Theme.clear]),
                    center: CGPoint(x: cx2, y: cy2),
                    startRadius: 0,
                    endRadius: r2
                )
            )
        }
        .accessibilityHidden(true)
    }
}

struct ClipStill: View {
    var reference: String?
    var seed: Int
    @EnvironmentObject private var model: AppModel

    var body: some View {
        GeometryReader { geo in
            ZStack {
                ProceduralClipBackdrop(seed: seed)
                if let url = resolved {
                    AsyncImage(url: url) { phase in
                        if case let .success(image) = phase {
                            image
                                .resizable()
                                .scaledToFill()
                                .frame(width: geo.size.width, height: geo.size.height)
                                .clipped()
                        }
                    }
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .clipped()
        }
        .allowsHitTesting(false)
    }

    private var resolved: URL? {
        guard let reference = reference, !reference.isEmpty else { return nil }
        if reference.hasPrefix("/") { return model.http(reference) }
        return URL(string: reference)
    }
}

struct HostEmblem: View {
    var body: some View {
        Canvas { context, size in
            context.fill(
                Path(CGRect(origin: .zero, size: size)),
                with: .linearGradient(
                    Gradient(colors: [Theme.livelyTop, Theme.inkDark, Theme.ground]),
                    startPoint: .zero,
                    endPoint: CGPoint(x: size.width, y: size.height)
                )
            )
            var rng = SplitMix(seed: 42)
            let count = 14
            let step = size.width / CGFloat(count)
            for idx in 0 ..< count {
                let h = size.height * CGFloat(0.18 + rng.unit() * 0.42)
                let rect = CGRect(x: CGFloat(idx) * step + 1, y: size.height - h, width: max(2, step - 1.5), height: h)
                let barColor = idx % 3 == 0 ? Theme.violetLight.opacity(0.32) : Theme.violet.opacity(0.22)
                context.fill(Path(rect), with: .color(barColor))
            }
            context.fill(
                Path(CGRect(origin: .zero, size: size)),
                with: .radialGradient(
                    Gradient(colors: [Theme.violetLight.opacity(0.20), Theme.scrimBase.opacity(0.45)]),
                    center: CGPoint(x: size.width * 0.35, y: size.height * 0.30),
                    startRadius: 0,
                    endRadius: size.width * 0.65
                )
            )
        }
        .overlay {
            NebulaMark(size: 30)
        }
        .accessibilityHidden(true)
    }
}
