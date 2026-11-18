import SwiftUI

struct BackgroundView: View {
    var kind: BackgroundKind
    var seed: Int
    var live: Bool

    var body: some View {
        Group {
            if live {
                TimelineView(.periodic(from: .now, by: 1.0 / 20.0)) { context in
                    canvas(context.date.timeIntervalSinceReferenceDate)
                }
            } else {
                canvas(20)
            }
        }
        .accessibilityHidden(true)
        .allowsHitTesting(false)
        .ignoresSafeArea()
    }

    private func canvas(_ time: TimeInterval) -> some View {
        Canvas { context, size in
            BackgroundDraw.paint(context, size: size, kind: kind, seed: seed, time: time)
        }
        .background(Theme.ground)
    }
}

enum BackgroundDraw {
    static func paint(_ context: GraphicsContext, size: CGSize, kind: BackgroundKind, seed: Int, time: TimeInterval) {
        let scale = size.width / 402
        space(context, size: size, time: time, scale: scale)
        switch kind {
        case .earth:
            sphere(context, size: size, scale: scale, time: time, radius: 560, cap: 236, night: true, seed: 11)
        case .proc:
            sphere(context, size: size, scale: scale, time: time, radius: 520, cap: 250, night: false, seed: seed)
        case .moon:
            sphere(context, size: size, scale: scale, time: time, radius: 420, cap: 250, night: false, seed: 2, moon: true)
        case .solar:
            solar(context, size: size, scale: scale, time: time)
        case .dots:
            dots(context, size: size, scale: scale, time: time)
        case .ring:
            orbits(context, size: size, scale: scale, time: time)
        case .galaxy:
            galaxy(context, size: size, scale: scale, time: time)
        case .saturn:
            ringed(context, size: size, scale: scale, time: time)
        case .dither:
            dither(context, size: size, scale: scale, time: time)
        }
    }

    private static func space(_ context: GraphicsContext, size: CGSize, time: TimeInterval, scale: CGFloat) {
        context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(Theme.ground))
        let band = Path(CGRect(x: -size.width, y: size.height * 0.35, width: size.width * 3, height: size.height * 0.22))
        var bandContext = context
        bandContext.rotate(by: .radians(-0.9))
        bandContext.fill(band, with: .linearGradient(
            Gradient(colors: [Theme.violet.opacity(0.34), Theme.magenta.opacity(0.05), .clear]),
            startPoint: CGPoint(x: 0, y: size.height * 0.4),
            endPoint: CGPoint(x: size.width, y: size.height * 0.55)
        ))
        var rng = SplitMix(seed: 11)
        for index in 0 ..< 190 {
            let speed = 0.3 + rng.unit()
            let baseX = rng.unit() * Double(size.width)
            let y = rng.unit() * Double(size.height)
            let drift = (time * speed * Double(scale) * 8).truncatingRemainder(dividingBy: Double(size.width))
            let x = (baseX + drift).truncatingRemainder(dividingBy: Double(size.width))
            let twinkle = 0.35 + 0.65 * abs(sin(time * 1.7 + Double(index)))
            let radius = (index % 17 == 0 ? 1.6 : 0.8) * scale
            let rect = CGRect(x: x, y: y, width: radius * 2, height: radius * 2)
            context.fill(Path(ellipseIn: rect), with: .color(Theme.ink.opacity(twinkle)))
        }
    }

    private static func sphere(
        _ context: GraphicsContext,
        size: CGSize,
        scale: CGFloat,
        time: TimeInterval,
        radius: CGFloat,
        cap: CGFloat,
        night: Bool,
        seed: Int,
        moon: Bool = false
    ) {
        let r = radius * scale
        let shown = cap * scale
        let center = CGPoint(x: size.width * 0.55, y: size.height + r - shown)
        let rect = CGRect(x: center.x - r, y: center.y - r, width: r * 2, height: r * 2)
        var disc = context
        disc.clip(to: Path(ellipseIn: rect))
        if moon {
            disc.fill(Path(ellipseIn: rect), with: .linearGradient(
                Gradient(colors: [Color(white: 0.72), Color(white: 0.18)]),
                startPoint: CGPoint(x: rect.maxX, y: rect.minY),
                endPoint: CGPoint(x: rect.minX, y: rect.maxY)
            ))
        } else if night {
            disc.fill(Path(ellipseIn: rect), with: .color(Color(red: 0.04, green: 0.07, blue: 0.14)))
            var lights = SplitMix(seed: UInt64(seed + 19))
            for _ in 0 ..< 90 {
                let px = rect.minX + lights.unit() * rect.width
                let py = rect.minY + lights.unit() * rect.height
                let dx = px - center.x
                let dy = py - center.y
                guard dx * dx + dy * dy < Double(r * r) * 0.8 else { continue }
                let dot = CGRect(x: px, y: py, width: 2.2 * scale, height: 2.2 * scale)
                disc.fill(Path(ellipseIn: dot), with: .color(Color(red: 1, green: 0.8, blue: 0.55).opacity(0.85)))
            }
        } else {
            var rng = SplitMix(seed: UInt64(bitPattern: Int64(seed)))
            let hue = rng.unit()
            let top = Color(hue: hue, saturation: 0.45, brightness: 0.55)
            let bottom = Color(hue: (hue + 0.08).truncatingRemainder(dividingBy: 1), saturation: 0.55, brightness: 0.18)
            disc.fill(Path(ellipseIn: rect), with: .linearGradient(
                Gradient(colors: [top, bottom]),
                startPoint: CGPoint(x: rect.midX, y: rect.minY),
                endPoint: CGPoint(x: rect.midX, y: rect.maxY)
            ))
        }
        let spin = time / 240
        let terminator = CGRect(x: center.x - r * 0.15 + CGFloat(sin(spin)) * 12, y: center.y - r, width: r * 1.4, height: r * 2)
        disc.fill(Path(ellipseIn: terminator), with: .color(Color(red: 0.45, green: 0.55, blue: 0.85).opacity(night ? 0.18 : 0.12)))
        context.stroke(Path(ellipseIn: rect.insetBy(dx: -3 * scale, dy: -3 * scale)), with: .color(Color(red: 0.43, green: 0.55, blue: 1).opacity(0.35)), lineWidth: 8 * scale)
    }

    private static func solar(_ context: GraphicsContext, size: CGSize, scale: CGFloat, time: TimeInterval) {
        let sun = CGPoint(x: size.width * 0.5, y: size.height * 0.72)
        let sunRect = CGRect(x: sun.x - 18 * scale, y: sun.y - 10 * scale, width: 36 * scale, height: 20 * scale)
        context.fill(Path(ellipseIn: sunRect), with: .color(Theme.gold))
        let planets: [(Double, Color, String?)] = [
            (0.4, Theme.amber, nil),
            (0.7, Theme.teal, nil),
            (1.0, Theme.gold, "EARTH · YOU"),
            (1.4, Theme.violetLight, nil),
            (1.9, Theme.coralText, nil),
        ]
        for (index, planet) in planets.enumerated() {
            let a = (26 + 58 * planet.0.squareRoot()) * Double(scale)
            let angle = time * 0.012 + Double(index)
            let x = sun.x + CGFloat(cos(angle) * a)
            let y = sun.y + CGFloat(sin(angle) * a * 0.34)
            let rect = CGRect(x: x - 5 * scale, y: y - 5 * scale, width: 10 * scale, height: 10 * scale)
            context.stroke(Path(ellipseIn: CGRect(x: sun.x - a, y: sun.y - a * 0.34, width: a * 2, height: a * 0.68)), with: .color(Theme.ink.opacity(0.15)), lineWidth: 1)
            context.fill(Path(ellipseIn: rect), with: .color(planet.1))
            if let label = planet.2 {
                context.draw(Text(label).font(.system(size: 10, weight: .semibold)).foregroundColor(Theme.gold), at: CGPoint(x: x, y: y - 16 * scale))
            }
        }
        let stamp = Text("LIVE").font(.system(size: 11, weight: .semibold)).foregroundColor(Theme.ink2)
        context.draw(stamp, at: CGPoint(x: 54 * scale, y: size.height - 48 * scale))
    }

    private static func dots(_ context: GraphicsContext, size: CGSize, scale: CGFloat, time: TimeInterval) {
        let step = 8 * scale
        var y = CGFloat(0)
        while y < size.height {
            var x = CGFloat(0)
            while x < size.width {
                let field = bloom(x / scale, y / scale, time: time)
                let radius = (0.75 + 2.75 * field) * scale
                let color = field > 1.1 ? Theme.amber : (field > 0.6 ? Theme.magenta : Theme.violet)
                let rect = CGRect(x: x, y: y, width: radius, height: radius)
                context.fill(Path(ellipseIn: rect), with: .color(color.opacity(0.35 + min(field, 1) * 0.65)))
                x += step
            }
            y += step
        }
    }

    private static func bloom(_ x: CGFloat, _ y: CGFloat, time: TimeInterval) -> Double {
        let cores: [(Double, Double, Double)] = [(17, 80, 220), (23, 260, 360), (29, 140, 640), (19, 300, 180)]
        var sum = 0.0
        for (index, core) in cores.enumerated() {
            let cx = core.1 + sin(time / core.0) * 70
            let cy = core.2 + cos(time / core.0 + Double(index)) * 90
            let dx = (Double(x) - cx) / 90
            let dy = (Double(y) - cy) / 90
            let superellipse = abs(dx * dx * dx) + abs(dy * dy * dy)
            sum += exp(-superellipse * 2.2)
        }
        return sum
    }

    private static func orbits(_ context: GraphicsContext, size: CGSize, scale: CGFloat, time: TimeInterval) {
        let center = CGPoint(x: 250 * scale, y: min(size.height * 0.72, 330 * scale + size.height * 0.35))
        ring(context, center: center, radius: 236 * scale, rows: 9, speed: 14, time: time, scale: scale, squash: 0.36)
        ring(context, center: center, radius: 170 * scale, rows: 6, speed: -7, time: time, scale: scale, squash: 0.36)
    }

    private static func ring(_ context: GraphicsContext, center: CGPoint, radius: CGFloat, rows: Int, speed: Double, time: TimeInterval, scale: CGFloat, squash: CGFloat) {
        let cell = 4 * scale
        for row in 0 ..< rows {
            let r = radius - CGFloat(row) * cell * 1.4
            let count = max(12, Int(r / (cell * 0.8)))
            for step in 0 ..< count {
                let angle = (Double(step) / Double(count)) * .pi * 2 + time * speed * .pi / 180
                let x = center.x + CGFloat(cos(angle)) * r
                let y = center.y + CGFloat(sin(angle)) * r * squash
                let shade = 0.35 + 0.65 * (sin(angle) * 0.5 + 0.5)
                let rect = CGRect(x: x, y: y, width: cell, height: cell)
                context.fill(Path(rect), with: .color(Theme.violetLight.opacity(shade)))
            }
        }
    }

    private static func galaxy(_ context: GraphicsContext, size: CGSize, scale: CGFloat, time: TimeInterval) {
        let center = CGPoint(x: size.width * 0.52, y: size.height - 80 * scale)
        for arm in 0 ..< 2 {
            for step in 0 ..< 180 {
                let t = Double(step) / 180
                let angle = t * 5.2 + Double(arm) * .pi + time * 0.05
                let distance = (20 + t * 210) * Double(scale)
                let x = center.x + CGFloat(cos(angle) * distance)
                let y = center.y + CGFloat(sin(angle) * distance * 0.42)
                let rect = CGRect(x: x, y: y, width: 3 * scale, height: 3 * scale)
                let color = t < 0.15 ? Theme.gold : Theme.violetLight
                context.fill(Path(rect), with: .color(color.opacity(1 - t * 0.7)))
            }
        }
    }

    private static func ringed(_ context: GraphicsContext, size: CGSize, scale: CGFloat, time: TimeInterval) {
        let center = CGPoint(x: size.width * 0.5, y: size.height - 70 * scale)
        let ring = CGRect(x: center.x - 214 * scale, y: center.y - 40 * scale, width: 428 * scale, height: 80 * scale)
        context.stroke(Path(ellipseIn: ring), with: .color(Theme.violetLight.opacity(0.7)), lineWidth: 10 * scale)
        let planet = CGRect(x: center.x - 92 * scale, y: center.y - 70 * scale, width: 184 * scale, height: 140 * scale)
        context.fill(Path(ellipseIn: planet), with: .linearGradient(
            Gradient(colors: [Theme.violet, Theme.gold.opacity(0.8), Theme.magenta]),
            startPoint: CGPoint(x: planet.minX, y: planet.minY + CGFloat(sin(time * 0.2)) * 8),
            endPoint: CGPoint(x: planet.maxX, y: planet.maxY)
        ))
        context.stroke(Path(ellipseIn: ring), with: .color(Theme.ink.opacity(0.25)), lineWidth: 4 * scale)
    }

    private static func dither(_ context: GraphicsContext, size: CGSize, scale: CGFloat, time: TimeInterval) {
        let cell = 8 * scale
        let palette: [Color] = [Theme.ground, Theme.inkDark, Theme.card, Theme.violet.opacity(0.7), Theme.magenta.opacity(0.55), Theme.ink2]
        var y = CGFloat(0)
        var row = 0
        while y < size.height {
            var x = CGFloat(0)
            var column = 0
            while x < size.width {
                let warp = sin((Double(x) / 80) + time * 0.05) + cos((Double(y) / 90) - time * 0.04)
                let step = min(palette.count - 1, max(0, Int((warp + 2) / 4 * Double(palette.count))))
                let bayer = ((row & 1) << 1) | (column & 1)
                let color = palette[min(palette.count - 1, step + (bayer == 3 ? 1 : 0))]
                context.fill(Path(CGRect(x: x, y: y, width: cell, height: cell)), with: .color(color))
                x += cell
                column += 1
            }
            y += cell
            row += 1
        }
    }
}
