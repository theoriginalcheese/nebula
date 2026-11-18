import SwiftUI

struct PressScaleStyle: ButtonStyle {
    @Environment(\.tone) private var tone

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(tone.reduceMotion ? .easeOut(duration: 0.15) : .easeOut(duration: 0.15), value: configuration.isPressed)
    }
}

struct GlassCircle: View {
    var system: String
    var size: CGFloat = 48
    var tint: Color = Theme.ink

    var body: some View {
        Group {
            if !system.isEmpty {
                Image(systemName: system)
                    .font(.system(size: size * 0.38, weight: .light))
                    .foregroundStyle(tint)
            }
        }
            .frame(width: size, height: size)
            .background {
                if toneOpaque {
                    Circle().fill(Theme.card)
                } else {
                    Circle().fill(.ultraThinMaterial)
                    Circle().fill(Color(red: 30 / 255, green: 26 / 255, blue: 48 / 255).opacity(0.30))
                }
            }
            .overlay(Circle().stroke(Color.white.opacity(0.14), lineWidth: 1))
    }

    @Environment(\.tone) private var tone
    private var toneOpaque: Bool { tone.reduceTransparency }
}

struct Tray<Content: View>: View {
    var radius: CGFloat = 34
    @ViewBuilder var content: () -> Content

    var body: some View {
        content()
            .clipShape(RoundedRectangle(cornerRadius: radius - 6, style: .continuous))
            .padding(6)
            .background(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .fill(Theme.ink.opacity(0.04))
            )
            .overlay(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .stroke(Theme.ink.opacity(0.09), lineWidth: 1)
            )
    }
}

struct ReadingSurface<Content: View>: View {
    var radius: CGFloat = 24
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    @ViewBuilder var content: () -> Content

    var body: some View {
        content()
            .background(background)
            .clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .stroke(Theme.ink.opacity(tone.hairline), lineWidth: 1)
            )
    }

    @ViewBuilder private var background: some View {
        if tone.reduceTransparency || model.prefs.surfaces == .solid {
            Theme.card
        } else if model.prefs.surfaces == .lively {
            ZStack {
                LinearGradient(colors: [Theme.livelyTop, Theme.livelyBottom], startPoint: .topLeading, endPoint: .bottomTrailing)
                RadialGradient(colors: [Theme.violet.opacity(0.30), .clear], center: .topLeading, startRadius: 0, endRadius: 180)
                RadialGradient(colors: [Theme.magenta.opacity(0.18), .clear], center: .bottomTrailing, startRadius: 0, endRadius: 160)
            }
        } else {
            ZStack {
                Theme.card.opacity(0.92)
                LinearGradient(
                    colors: [Theme.violetLight.opacity(0.16), .clear],
                    startPoint: .topLeading,
                    endPoint: UnitPoint(x: 0.7, y: 0.46)
                )
            }
        }
    }
}

struct NebulaSegments: View {
    var options: [(id: String, title: String)]
    var selection: String
    var onSelect: (String) -> Void
    @Environment(\.tone) private var tone

    var body: some View {
        HStack(spacing: 0) {
            ForEach(options, id: \.id) { option in
                Button {
                    withAnimation(tone.motion) { onSelect(option.id) }
                } label: {
                    Text(option.title)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(selection == option.id ? Theme.ink : tone.tertiary)
                        .frame(maxWidth: .infinity, minHeight: 32)
                        .background {
                            if selection == option.id {
                                RoundedRectangle(cornerRadius: 10, style: .continuous)
                                    .fill(Theme.violet.opacity(0.24))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                                            .stroke(Theme.violetLight.opacity(0.35), lineWidth: 1)
                                    )
                                    .padding(2)
                            }
                        }
                }
                .buttonStyle(.plain)
            }
        }
        .frame(minHeight: 36)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color(red: 10 / 255, green: 8 / 255, blue: 18 / 255).opacity(0.55))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Theme.ink.opacity(tone.hairline), lineWidth: 1)
        )
    }
}

struct PrimaryPill: View {
    var title: String
    var system: String
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                Text(title)
                    .font(.system(size: 17, weight: .semibold))
                Spacer()
                Image(systemName: system)
                    .font(.system(size: 18, weight: .light))
                    .frame(width: 44, height: 44)
                    .background(Circle().fill(Theme.violet.opacity(0.18)))
                    .overlay(Circle().stroke(Theme.violet.opacity(0.55), lineWidth: 1))
            }
            .foregroundStyle(Theme.ink)
            .padding(.leading, 18)
            .padding(.trailing, 6)
            .frame(maxWidth: .infinity, minHeight: 56)
            .background(
                RoundedRectangle(cornerRadius: 28, style: .continuous)
                    .fill(Theme.violet.opacity(0.20))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 28, style: .continuous)
                    .stroke(Theme.violet.opacity(0.55), lineWidth: 1)
            )
        }
        .buttonStyle(PressScaleStyle())
    }
}

struct Eyebrow: View {
    var text: String
    var color: Color = Theme.ink3

    var body: some View {
        Text(text.uppercased())
            .font(.system(size: 11, weight: .semibold))
            .tracking(1.6)
            .foregroundStyle(color)
    }
}

struct ToastBanner: View {
    var text: String

    var body: some View {
        Text(text)
            .font(.system(size: 15, weight: .semibold))
            .foregroundStyle(Theme.ink)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(.ultraThinMaterial, in: Capsule())
            .overlay(Capsule().stroke(Color.white.opacity(0.12), lineWidth: 1))
            .padding(.horizontal, 24)
    }
}

func stillSeed(_ text: String) -> Int {
    text.utf8.reduce(7) { ($0 &* 33) &+ Int($1) }
}

struct NightStill: View {
    var seed: Int

    var body: some View {
        Canvas { context, size in
            let sky = GraphicsContext.Shading.linearGradient(
                Gradient(colors: [
                    Color(red: 0.04, green: 0.03, blue: 0.09),
                    Color(red: 0.16, green: 0.07, blue: 0.22),
                    Color(red: 0.03, green: 0.04, blue: 0.08)
                ]),
                startPoint: .zero,
                endPoint: CGPoint(x: size.width * 0.2, y: size.height)
            )
            context.fill(Path(CGRect(origin: .zero, size: size)), with: sky)
            var rng = SplitMix(seed: UInt64(bitPattern: Int64(seed)))
            let glow = Color(red: 0.83, green: 0.44, blue: 0.88)
            context.fill(
                Path(ellipseIn: CGRect(x: size.width * 0.35, y: size.height * 0.42, width: size.width * 0.7, height: 80)),
                with: .color(glow.opacity(0.28))
            )
            let columns = 8
            let width = size.width / CGFloat(columns)
            for column in 0..<columns {
                let height = size.height * CGFloat(0.28 + rng.unit() * 0.48)
                let rect = CGRect(x: CGFloat(column) * width, y: size.height - height, width: width - 1, height: height)
                context.fill(Path(rect), with: .color(Color(white: 0.04 + rng.unit() * 0.07)))
                var y = rect.minY + 8
                while y < size.height - 10 {
                    let lit = rng.unit()
                    if lit > 0.45 {
                        let pane = CGRect(x: rect.minX + 4, y: y, width: 3, height: 4)
                        let neon = lit > 0.82 ? Theme.gold : (lit > 0.68 ? Theme.coral : Theme.violetLight)
                        context.fill(Path(pane), with: .color(neon.opacity(0.85)))
                    }
                    y += 9
                }
            }
        }
        .accessibilityHidden(true)
    }
}

struct ClipStill: View {
    var reference: String?
    var seed: Int
    @EnvironmentObject private var model: AppModel

    var body: some View {
        ZStack {
            NightStill(seed: seed)
            if let url = resolved {
                AsyncImage(url: url) { phase in
                    if case let .success(image) = phase {
                        image.resizable().scaledToFill()
                    }
                }
            }
        }
        .clipped()
        .allowsHitTesting(false)
    }

    private var resolved: URL? {
        guard let reference, !reference.isEmpty else { return nil }
        if reference.hasPrefix("/") { return model.http(reference) }
        return URL(string: reference)
    }
}
