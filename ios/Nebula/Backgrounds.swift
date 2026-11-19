import CoreGraphics
import Foundation
import SwiftUI
import UIKit

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
                canvas(20.0)
            }
        }
        .accessibilityHidden(true)
        .allowsHitTesting(false)
        .ignoresSafeArea()
    }

    private func canvas(_ time: TimeInterval) -> some View {
        Canvas(rendersAsynchronously: true) { context, size in
            BackgroundDraw.paint(context, size: size, kind: kind, seed: seed, time: time)
        }
        .background(Theme.ground)
    }
}

/// Cropped live tile used in Settings > Appearance (3g) so bottom-anchored planets
/// and centre-anchored orbits/fields frame their focal art inside a 150pt tile.
struct BackgroundTilePreview: View {
    var kind: BackgroundKind
    var seed: Int
    var time: TimeInterval

    var body: some View {
        GeometryReader { geo in
            let tileW = max(1, geo.size.width)
            let tileH = max(1, geo.size.height)
            let virtualH = tileW * (Theme.Size.canvasHeight / Theme.Size.canvasWidth)
            let cropFraction: CGFloat = cropStartFraction(for: kind)
            let maxOffset = max(0, virtualH - tileH)
            let yOffset = -min(maxOffset, virtualH * cropFraction)

            Canvas { context, size in
                BackgroundDraw.paint(context, size: size, kind: kind, seed: seed, time: time)
            }
            .frame(width: tileW, height: virtualH)
            .offset(y: yOffset)
            .frame(width: tileW, height: tileH, alignment: .top)
            .clipped()
            .background(Theme.ground)
        }
        .accessibilityHidden(true)
        .allowsHitTesting(false)
    }

    private func cropStartFraction(for kind: BackgroundKind) -> CGFloat {
        switch kind {
        case .earth, .proc, .moon, .galaxy, .saturn:
            return 0.54
        case .solar:
            return 0.14
        case .ring:
            return 0.18
        case .dots:
            return 0.27
        case .dither:
            return 0.34
        }
    }
}

// MARK: - nm-space.js Renderer Port (§10)

enum BackgroundDraw {
    private static let baseW: Double = 402.0
    private static let baseH: Double = 874.0
    private static let tau: Double = .pi * 2.0

    private struct Star {
        var x: Double
        var y: Double
        var size: Double
        var phase: Double
        var rate: Double
    }

    private static let stars: [Star] = {
        var s: Int64 = 11
        func rnd() -> Double {
            s = (s * 16807) % 2147483647
            return Double(s) / 2147483647.0
        }
        var items: [Star] = []
        items.reserveCapacity(190)
        for _ in 0 ..< 190 {
            let x = rnd()
            let y = rnd()
            let u1 = rnd()
            let u2 = rnd()
            let sz = 0.35 + u1 * u2 * 1.5
            let ph = rnd() * (.pi * 2.0)
            let rt = 0.3 + rnd()
            items.append(Star(x: x, y: y, size: sz, phase: ph, rate: rt))
        }
        return items
    }()

    static func paint(_ context: GraphicsContext, size: CGSize, kind: BackgroundKind, seed: Int, time: TimeInterval) {
        guard size.width > 1, size.height > 1 else { return }
        let scale = Double(size.width) / baseW
        let logicalH = Double(size.height) / scale

        switch kind {
        case .earth:
            drawEarth(context, size: size, scale: scale, logicalH: logicalH, time: time)
        case .proc:
            drawProc(context, size: size, scale: scale, logicalH: logicalH, seed: seed, time: time)
        case .moon:
            drawMoon(context, size: size, scale: scale, logicalH: logicalH, time: time)
        case .solar:
            drawSolar(context, size: size, scale: scale, logicalH: logicalH, time: time)
        case .dots:
            drawDots(context, size: size, scale: scale, logicalH: logicalH, time: time)
        case .ring:
            drawRing(context, size: size, scale: scale, logicalH: logicalH, time: time)
        case .galaxy:
            drawGalaxy(context, size: size, scale: scale, logicalH: logicalH, time: time)
        case .saturn:
            drawSaturn(context, size: size, scale: scale, logicalH: logicalH, time: time)
        case .dither:
            drawDither(context, size: size, scale: scale, logicalH: logicalH, time: time)
        }
    }

    // MARK: - Shared Space Backdrop

    private static func drawSpace(_ context: GraphicsContext, size: CGSize, scale: Double, time: TimeInterval, bandY: Double = 0.38) {
        context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(Theme.ground))

        let cx = size.width * 0.55
        let cy = size.height * CGFloat(bandY)
        let maxR = size.height * 0.75

        var bandCtx = context
        bandCtx.translateBy(x: cx, y: cy)
        bandCtx.rotate(by: .radians(-0.9 + sin(time * 0.02) * 0.03))
        bandCtx.scaleBy(x: 1.0, y: 0.2)

        let bandRect = CGRect(x: -maxR, y: -maxR, width: maxR * 2, height: maxR * 2)
        bandCtx.fill(
            Path(ellipseIn: bandRect),
            with: .radialGradient(
                Gradient(stops: [
                    .init(color: Theme.SpacePalette.bandInner.opacity(0.34), location: 0.0),
                    .init(color: Theme.SpacePalette.bandMid.opacity(0.16), location: 0.3),
                    .init(color: Theme.magenta.opacity(0.05), location: 0.6),
                    .init(color: Theme.clear, location: 1.0),
                ]),
                center: .zero,
                startRadius: 0,
                endRadius: maxR
            )
        )

        let warmR = size.height * 0.30
        let warmCenter = CGPoint(x: -30 * scale, y: 10 * scale)
        bandCtx.fill(
            Path(ellipseIn: CGRect(x: warmCenter.x - warmR, y: warmCenter.y - warmR, width: warmR * 2, height: warmR * 2)),
            with: .radialGradient(
                Gradient(colors: [Theme.SpacePalette.bandWarmCore.opacity(0.10), Theme.clear]),
                center: warmCenter,
                startRadius: 0,
                endRadius: warmR
            )
        )

        let w = Double(size.width)
        let h = Double(size.height)
        for star in stars {
            let drift = (star.x * w + time * star.rate * 1.4 * scale).truncatingRemainder(dividingBy: w)
            let px = drift < 0 ? drift + w : drift
            let py = star.y * h
            let tw = 0.5 + 0.5 * sin(time * (0.5 + star.rate) + star.phase)
            let alpha = 0.2 + 0.65 * tw
            let r = star.size * 0.75 * scale
            let starColor = star.size > 1.4 ? Theme.SpacePalette.starWarm : Theme.SpacePalette.starCool
            context.fill(
                Path(ellipseIn: CGRect(x: px - r, y: py - r, width: r * 2, height: r * 2)),
                with: .color(starColor.opacity(alpha))
            )
            if star.size > 1.55 {
                let glintColor = Theme.SpacePalette.starCool.opacity(alpha * 0.25)
                let span = 4.0 * scale
                let thick = max(0.5, 0.5 * scale)
                context.fill(Path(CGRect(x: px - span, y: py - thick * 0.5, width: span * 2, height: thick)), with: .color(glintColor))
                context.fill(Path(CGRect(x: px - thick * 0.5, y: py - span, width: thick, height: span * 2)), with: .color(glintColor))
            }
        }
    }

    private static func drawGlow(_ context: GraphicsContext, cx: Double, cy: Double, radius: Double, color: Color, alpha: Double) {
        let rect = CGRect(x: cx - radius, y: cy - radius, width: radius * 2, height: radius * 2)
        context.fill(
            Path(ellipseIn: rect),
            with: .radialGradient(
                Gradient(stops: [
                    .init(color: color.opacity(alpha), location: 0.0),
                    .init(color: color.opacity(alpha * 0.35), location: 0.5),
                    .init(color: Theme.clear, location: 1.0),
                ]),
                center: CGPoint(x: cx, y: cy),
                startRadius: 0,
                endRadius: radius
            )
        )
    }

    // MARK: - Planets (Earth, Random, Moonrise with Spec §13 Fallbacks)

    private static func drawEarth(_ context: GraphicsContext, size: CGSize, scale: Double, logicalH: Double, time: TimeInterval) {
        let light = SphereEngine.norm(0.62, 0.5, -0.18)
        if let dayTex = SphereEngine.bundleTexture(named: "earth_atmos_2048") ?? SphereEngine.bundleTexture(named: "earth_day") {
            let nightTex = SphereEngine.bundleTexture(named: "earth_lights_2048")
            let cloudTex = SphereEngine.bundleTexture(named: "earth_clouds_1024")
            drawPlanetScene(
                context,
                size: size,
                scale: scale,
                logicalH: logicalH,
                time: time,
                cacheKey: "earth-nasa",
                geom: .big,
                tex: dayTex,
                night: nightTex,
                clouds: cloudTex,
                light: light,
                rot: time / 240.0,
                atm: Theme.SpacePalette.earthAtm,
                atmK: 1.0,
                amb: 0.02,
                spec: nightTex != nil,
                rim: Theme.SpacePalette.earthRim
            )
        } else {
            // Spec §13 & nm-space.js line 311: Missing NASA Earth texture falls back to Random planet seed 3
            let fallback = SphereEngine.proceduralPlanet(seed: 3)
            drawPlanetScene(
                context,
                size: size,
                scale: scale,
                logicalH: logicalH,
                time: time,
                cacheKey: "earth-fallback-3",
                geom: .big,
                tex: fallback.tex,
                night: nil,
                clouds: nil,
                light: light,
                rot: time / 240.0,
                atm: Theme.SpacePalette.earthAtm,
                atmK: 1.0,
                amb: 0.015,
                spec: false,
                rim: Theme.SpacePalette.earthRim
            )
        }
    }

    private static func drawProc(_ context: GraphicsContext, size: CGSize, scale: Double, logicalH: Double, seed: Int, time: TimeInterval) {
        let planet = SphereEngine.proceduralPlanet(seed: seed)
        let light = SphereEngine.norm(-0.45, 0.55, 0.5)
        drawPlanetScene(
            context,
            size: size,
            scale: scale,
            logicalH: logicalH,
            time: time,
            cacheKey: "proc-\(seed)",
            geom: .big,
            tex: planet.tex,
            night: nil,
            clouds: nil,
            light: light,
            rot: time / 180.0,
            atm: planet.atm,
            atmK: 1.2,
            amb: 0.03,
            spec: false,
            rim: Theme.SpacePalette.procRim
        )
    }

    private static func drawMoon(_ context: GraphicsContext, size: CGSize, scale: Double, logicalH: Double, time: TimeInterval) {
        if let moonTex = SphereEngine.bundleTexture(named: "moon_1024") ?? SphereEngine.bundleTexture(named: "moon") {
            let light = SphereEngine.norm(0.78, 0.5, 0.05)
            drawPlanetScene(
                context,
                size: size,
                scale: scale,
                logicalH: logicalH,
                time: time,
                cacheKey: "moon-nasa",
                geom: .moon,
                tex: moonTex,
                night: nil,
                clouds: nil,
                light: light,
                rot: time / 300.0,
                atm: Theme.SpacePalette.moonAtm,
                atmK: 0.4,
                amb: 0.01,
                spec: false,
                rim: Theme.SpacePalette.moonRim
            )
        } else {
            // Spec §13 & nm-space.js line 317: Missing NASA Moonrise texture falls back to space backdrop only
            drawSpace(context, size: size, scale: scale, time: time)
        }
    }

    private static func drawPlanetScene(
        _ context: GraphicsContext,
        size: CGSize,
        scale: Double,
        logicalH: Double,
        time: TimeInterval,
        cacheKey: String,
        geom: SphereGeomKind,
        tex: EquirectTexture,
        night: EquirectTexture?,
        clouds: EquirectTexture?,
        light: (Double, Double, Double),
        rot: Double,
        atm: Theme.RGB,
        atmK: Double,
        amb: Double,
        spec: Bool,
        rim: Theme.RGB
    ) {
        drawSpace(context, size: size, scale: scale, time: time)

        let radius = geom.radius * scale
        let cap = geom.cap * scale
        let cx = Double(size.width) * 0.5
        let cy = Double(size.height) + radius - cap
        let breathe = 0.86 + 0.14 * sin(time * 0.4)

        let haloOuter = radius * 1.32
        context.fill(
            Path(ellipseIn: CGRect(x: cx - haloOuter, y: cy - haloOuter, width: haloOuter * 2, height: haloOuter * 2)),
            with: .radialGradient(
                Gradient(stops: [
                    .init(color: atm.color.opacity(0.32 * breathe), location: 0.74),
                    .init(color: atm.color.opacity(0.10 * breathe), location: 0.84),
                    .init(color: Theme.clear, location: 1.0),
                ]),
                center: CGPoint(x: cx, y: cy),
                startRadius: 0,
                endRadius: haloOuter
            )
        )

        let ang = atan2(light.1, light.0)
        let lx = cx + radius * cos(ang)
        let ly = cy - radius * sin(ang)
        var screenCtx = context
        screenCtx.blendMode = .screen
        drawGlow(screenCtx, cx: lx, cy: ly, radius: Double(size.width) * 0.70, color: rim.color, alpha: 0.40 * breathe)
        drawGlow(screenCtx, cx: lx, cy: ly, radius: Double(size.width) * 0.22, color: Theme.SpacePalette.rimWarm, alpha: 0.35 * breathe)

        if let cgImage = SphereEngine.renderSphere(
            key: cacheKey,
            geomKind: geom,
            tex: tex,
            night: night,
            clouds: clouds,
            light: light,
            rot: rot,
            atm: atm,
            atmK: atmK,
            amb: amb,
            spec: spec
        ) {
            let capHeight = 256.0 * scale
            let destRect = CGRect(
                x: 0,
                y: Double(size.height) - capHeight,
                width: Double(size.width),
                height: capHeight
            )
            context.draw(Image(decorative: cgImage, scale: 1.0), in: destRect)
        }

        var rimArc = Path()
        rimArc.addArc(
            center: CGPoint(x: cx, y: cy),
            radius: radius,
            startAngle: .radians(.pi * 1.04),
            endAngle: .radians(.pi * 1.96),
            clockwise: false
        )
        context.stroke(
            rimArc,
            with: .linearGradient(
                Gradient(stops: [
                    .init(color: Theme.SpacePalette.rimCool.opacity(0.0), location: 0.0),
                    .init(color: Theme.SpacePalette.rimWarm.opacity(0.95), location: 0.5),
                    .init(color: Theme.SpacePalette.rimCool.opacity(0.0), location: 1.0),
                ]),
                startPoint: CGPoint(x: lx - Double(size.width) * 0.6, y: ly),
                endPoint: CGPoint(x: lx + Double(size.width) * 0.6, y: ly)
            ),
            lineWidth: max(1.0, 1.2 * scale)
        )
    }

    // MARK: - Solar Live (J2000 Mean Orbital Elements, §10)

    private struct SolarDef {
        var name: String
        var au: Double
        var l0: Double
        var rate: Double
        var radius: Double
        var colorIndex: Int
    }

    private static let solarPlanets: [SolarDef] = [
        SolarDef(name: "Mercury", au: 0.387, l0: 252.25, rate: 4.09233, radius: 2.2, colorIndex: 0),
        SolarDef(name: "Venus", au: 0.723, l0: 181.98, rate: 1.60213, radius: 3.4, colorIndex: 1),
        SolarDef(name: "Earth", au: 1.000, l0: 100.46, rate: 0.98561, radius: 3.6, colorIndex: 2),
        SolarDef(name: "Mars", au: 1.524, l0: 355.45, rate: 0.52403, radius: 2.8, colorIndex: 3),
        SolarDef(name: "Jupiter", au: 5.203, l0: 34.40, rate: 0.08309, radius: 7.5, colorIndex: 4),
        SolarDef(name: "Saturn", au: 9.537, l0: 49.94, rate: 0.03346, radius: 6.4, colorIndex: 5),
        SolarDef(name: "Uranus", au: 19.190, l0: 313.23, rate: 0.01173, radius: 4.6, colorIndex: 6),
        SolarDef(name: "Neptune", au: 30.070, l0: 304.88, rate: 0.00598, radius: 4.4, colorIndex: 7),
    ]

    private static let solarStampFormatter: DateFormatter = {
        let df = DateFormatter()
        df.locale = Locale(identifier: "en_GB")
        df.dateFormat = "d MMM yyyy"
        return df
    }()

    private static func drawSolar(_ context: GraphicsContext, size: CGSize, scale: Double, logicalH: Double, time: TimeInterval) {
        drawSpace(context, size: size, scale: scale, time: time, bandY: 0.22)

        // J2000 epoch: 2000-01-01 12:00 UTC (946728000 Unix timestamp), recomputed once per minute
        let nowFlooredMinute = floor(Date().timeIntervalSince1970 / 60.0) * 60.0
        let daysSinceJ2000 = (nowFlooredMinute - 946_728_000.0) / 86_400.0
        let cx = Double(size.width) * 0.5
        let cy = 330.0 * scale
        let tilt = 0.34
        let yaw = time * 0.012

        func orbitRadius(_ au: Double) -> Double {
            return (26.0 + 58.0 * sqrt(au)) * scale
        }

        for (idx, planet) in solarPlanets.enumerated() {
            let r = orbitRadius(planet.au)
            let rect = CGRect(x: cx - r, y: cy - r * tilt, width: r * 2, height: r * tilt * 2)
            let isEarth = idx == 2
            context.stroke(
                Path(ellipseIn: rect),
                with: .color(Theme.violetLight.opacity(isEarth ? 0.42 : 0.13)),
                lineWidth: isEarth ? 1.0 : 0.7
            )
        }

        struct PositionedPlanet {
            var def: SolarDef
            var x: Double
            var y: Double
            var z: Double
        }

        let positioned: [PositionedPlanet] = solarPlanets.map { p in
            let meanDeg = (p.l0 + p.rate * daysSinceJ2000).truncatingRemainder(dividingBy: 360.0)
            let angle = meanDeg * .pi / 180.0 + yaw
            let r = orbitRadius(p.au)
            return PositionedPlanet(
                def: p,
                x: cx + r * cos(angle),
                y: cy + r * sin(angle) * tilt,
                z: sin(angle)
            )
        }

        func drawSun() {
            var screenCtx = context
            screenCtx.blendMode = .screen
            drawGlow(screenCtx, cx: cx, cy: cy, radius: 150.0 * scale, color: Theme.SpacePalette.sunGlow, alpha: 0.35)
            drawGlow(screenCtx, cx: cx, cy: cy, radius: 46.0 * scale, color: Theme.SpacePalette.starWarm, alpha: 0.90)

            let sunR = 13.0 * scale
            let sunRect = CGRect(x: cx - sunR, y: cy - sunR, width: sunR * 2, height: sunR * 2)
            context.fill(
                Path(ellipseIn: sunRect),
                with: .radialGradient(
                    Gradient(stops: [
                        .init(color: Theme.SpacePalette.sunCore, location: 0.0),
                        .init(color: Theme.SpacePalette.sunMid, location: 0.6),
                        .init(color: Theme.SpacePalette.sunEdge, location: 1.0),
                    ]),
                    center: CGPoint(x: cx - 3 * scale, y: cy - 3 * scale),
                    startRadius: 1,
                    endRadius: 14 * scale
                )
            )
        }

        func drawBody(_ item: PositionedPlanet) {
            let s = item.def.radius * scale
            let baseRGB = Theme.SpacePalette.solarBodies[item.def.colorIndex]
            let litRGB = Theme.RGB(r: min(255, baseRGB.r + 40), g: min(255, baseRGB.g + 40), b: min(255, baseRGB.b + 40))
            let midRGB = Theme.RGB(r: baseRGB.r * 0.7, g: baseRGB.g * 0.7, b: baseRGB.b * 0.7)
            let ang = atan2(cy - item.y, cx - item.x)

            if item.def.name == "Saturn" {
                var ringCtx = context
                ringCtx.translateBy(x: item.x, y: item.y)
                ringCtx.rotate(by: .radians(-0.3))
                var backArc = Path()
                backArc.addArc(center: .zero, radius: s * 2.1, startAngle: .radians(.pi), endAngle: .radians(tau), clockwise: false)
                ringCtx.scaleBy(x: 1.0, y: 0.33)
                ringCtx.stroke(backArc, with: .color(Theme.SpacePalette.saturnRing.opacity(0.55)), lineWidth: 1.2)
            }

            let bodyRect = CGRect(x: item.x - s, y: item.y - s, width: s * 2, height: s * 2)
            context.fill(
                Path(ellipseIn: bodyRect),
                with: .radialGradient(
                    Gradient(stops: [
                        .init(color: litRGB.color, location: 0.0),
                        .init(color: midRGB.color, location: 0.55),
                        .init(color: Theme.segmentTrackBase, location: 1.0),
                    ]),
                    center: CGPoint(x: item.x + cos(ang) * s * 0.5, y: item.y + sin(ang) * s * 0.5),
                    startRadius: s * 0.1,
                    endRadius: s
                )
            )

            if item.def.name == "Saturn" {
                var ringCtx = context
                ringCtx.translateBy(x: item.x, y: item.y)
                ringCtx.rotate(by: .radians(-0.3))
                var frontArc = Path()
                frontArc.addArc(center: .zero, radius: s * 2.1, startAngle: .zero, endAngle: .radians(.pi), clockwise: false)
                ringCtx.scaleBy(x: 1.0, y: 0.33)
                ringCtx.stroke(frontArc, with: .color(Theme.SpacePalette.saturnRing.opacity(0.70)), lineWidth: 1.2)
            }

            let isEarth = item.def.name == "Earth"
            if isEarth {
                let pulse = 0.5 + 0.4 * sin(time * 2.0)
                let ringR = s + (5.0 + 2.0 * sin(time * 2.0)) * scale
                let pulseRect = CGRect(x: item.x - ringR, y: item.y - ringR, width: ringR * 2, height: ringR * 2)
                context.stroke(Path(ellipseIn: pulseRect), with: .color(Theme.gold.opacity(pulse)), lineWidth: 1.0)
            }

            let labelString = isEarth ? "EARTH · YOU" : item.def.name.uppercased()
            let text = Text(labelString)
                .font(Theme.TypeScale.solarLabel)
                .tracking(1.5)
                .foregroundColor(isEarth ? Theme.gold.opacity(0.95) : Theme.ink2.opacity(0.60))
            context.draw(text, at: CGPoint(x: item.x + s + 6.0 * scale, y: item.y), anchor: .leading)
        }

        for body in positioned.filter({ $0.z < 0 }).sorted(by: { $0.z < $1.z }) {
            drawBody(body)
        }
        drawSun()
        for body in positioned.filter({ $0.z >= 0 }).sorted(by: { $0.z < $1.z }) {
            drawBody(body)
        }

        let stampText = "LIVE · " + solarStampFormatter.string(from: Date()).uppercased()
        let stamp = Text(stampText)
            .font(Theme.TypeScale.solarStamp)
            .tracking(2.0)
            .foregroundColor(Theme.ink2.opacity(0.55))
        context.draw(stamp, at: CGPoint(x: 20.0 * scale, y: Double(size.height) - 74.0 * scale), anchor: .leading)
    }

    // MARK: - Dot Bloom (8pt grid on Theme.inkDark, §10)

    private struct BloomCore {
        var bx: Double
        var by: Double
        var r: Double
        var ax: Double
        var ay: Double
        var px: Double
        var py: Double
        var ph: Double
        var rp: Double
        var ra: Double
        var w: Double
    }

    private static let bloomCores: [BloomCore] = [
        BloomCore(bx: 300, by: 230, r: 130, ax: 46, ay: 70, px: 21, py: 27, ph: 0.0, rp: 9, ra: 0.25, w: 1.0),
        BloomCore(bx: 100, by: 480, r: 120, ax: -54, ay: 80, px: 25, py: 19, ph: 2.4, rp: 11, ra: 0.30, w: 1.0),
        BloomCore(bx: 290, by: 720, r: 140, ax: 50, ay: 56, px: 29, py: 23, ph: 1.0, rp: 13, ra: 0.30, w: 1.0),
        BloomCore(bx: 200, by: 420, r: 70, ax: 130, ay: 230, px: 17, py: 23, ph: 3.0, rp: 7, ra: 0.35, w: 0.85),
    ]

    private static func drawDots(_ context: GraphicsContext, size: CGSize, scale: Double, logicalH: Double, time: TimeInterval) {
        context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(Theme.inkDark))

        let activeCores = bloomCores.map { c -> (x: Double, y: Double, r: Double, w: Double) in
            let x = c.bx + sin(tau * time / c.px + c.ph) * c.ax
            let y = c.by + sin(tau * time / c.py + c.ph + 1.6) * c.ay
            let rad = c.r * (1.0 + sin(tau * time / c.rp + c.ph) * c.ra)
            return (x, y, rad, c.w)
        }

        let waveProgress = (time.truncatingRemainder(dividingBy: 7.0)) / 7.0
        let waveRadius = waveProgress * 760.0
        let waveAlpha = 1.0 - waveProgress

        var gy = 4.0
        while gy < logicalH {
            var gx = 4.0
            while gx < baseW {
                var v = 0.0
                for c in activeCores {
                    let dx = abs(gx - c.x)
                    let dy = abs(gy - c.y)
                    let d = cbrt(dx * dx * dx + dy * dy * dy)
                    let q = 1.0 - d / c.r
                    if q > 0 {
                        v += c.w * q * q * (3.0 - 2.0 * q)
                    }
                }
                let dw = hypot(gx - 201.0, gy - 300.0) - waveRadius
                v += exp(-(dw * dw) / 900.0) * 0.38 * waveAlpha

                let e = min(1.0, max(0.0, v))
                var rgb = e < 0.55
                    ? Theme.RGB.lerp(Theme.SpacePalette.dotViolet, Theme.SpacePalette.dotMagenta, e / 0.55)
                    : Theme.RGB.lerp(Theme.SpacePalette.dotMagenta, Theme.SpacePalette.dotInk, (e - 0.55) / 0.45)
                if v > 1.1 {
                    rgb = Theme.RGB.lerp(rgb, Theme.SpacePalette.dotAmber, min(0.7, (v - 1.1) * 1.4))
                }

                let dotR = (0.75 + 2.75 * e) * scale
                let cx = gx * scale
                let cy = gy * scale
                let alpha = 0.12 + 0.88 * e
                context.fill(
                    Path(ellipseIn: CGRect(x: cx - dotR, y: cy - dotR, width: dotR * 2, height: dotR * 2)),
                    with: .color(rgb.color.opacity(alpha))
                )
                gx += 8.0
            }
            gy += 8.0
        }
    }

    // MARK: - Pixel Orbit, Galaxy, Ringed, Dither (§10)

    private static func rh(_ a: Int, _ b: Int) -> Double {
        var h = Int32(truncatingIfNeeded: (a &* 73_856_093) ^ (b &* 19_349_663))
        h = (h ^ (h >> 13)) &* 1_274_126_177
        let u = UInt32(bitPattern: h ^ (h >> 16))
        return Double(u) / 4_294_967_295.0
    }

    private static func posMod(_ a: Double, _ n: Double) -> Double {
        let r = a.truncatingRemainder(dividingBy: n)
        return r < 0 ? r + n : r
    }

    private static let ringPalette: [Color] = [Theme.violet, Theme.violetLight, Theme.magenta, Theme.amber]
    private static let ringZones: [(Int, Int)] = [(0, 1), (1, 2), (2, 3), (0, 2), (3, 0), (1, 2)]

    private static func drawRing(_ context: GraphicsContext, size: CGSize, scale: Double, logicalH: Double, time: TimeInterval) {
        drawSpace(context, size: size, scale: scale, time: time, bandY: 0.62)
        drawGlow(context, cx: 250.0 * scale, cy: 330.0 * scale, radius: 260.0 * scale, color: Theme.violet, alpha: 0.16)

        let cell = 4.0
        let radAxis = 20.0 * .pi / 180.0
        let cosA = cos(radAxis)
        let sinA = sin(radAxis)
        let cols = Int(baseW / cell)

        func evalRing(isOuter: Bool, x: Double, y: Double) -> (Color, Double)? {
            let rRing = isOuter ? 236.0 : 170.0
            let rows = isOuter ? 9 : 6
            let rate = isOuter ? 14.0 : -7.0
            let dim = isOuter ? 1.0 : 0.8

            let dx = x - 250.0
            let dy = y - 330.0
            let px = dx * cosA - dy * sinA
            let py = (dx * sinA + dy * cosA) / 0.36
            let d = hypot(px, py)
            let band = Double(rows) * cell
            let inner = rRing - band * 0.5
            guard d >= inner, d < inner + band else { return nil }

            let row = Int(floor((d - inner) / cell))
            let raw = atan2(py, px) * 180.0 / .pi
            let ang = raw - rate * time
            let col: Color
            var al = 1.0

            if !isOuter {
                let n = max(1, Int((rRing * (40.0 * .pi / 180.0) / cell).rounded()))
                let u = posMod(ang, 40.0) / 40.0
                let jm = Int(floor(u * Double(n)))
                let zone = min(ringZones.count - 1, Int(floor(u * Double(ringZones.count))))
                let h1 = rh((jm / 3) * 7 + (row / 2) + 11, row + 3)
                let h2 = rh(jm + 5, row * 17 + 1)
                if ((row == 0 || row == rows - 1) && h2 < 0.32) || h2 < 0.10 { return nil }
                let pair = ringZones[zone]
                col = ringPalette[h1 < 0.62 ? pair.0 : pair.1]
            } else {
                let u = posMod(ang, 120.0) / 120.0
                guard u >= 0.3 else { return nil }
                let p = (u - 0.3) / 0.7
                let h2 = rh(Int(floor(posMod(ang, 360.0) / 2.4)), row + 5)
                guard h2 <= p * 1.15 + 0.05 else { return nil }
                if p > 0.92 {
                    col = h2 < 0.3 ? Theme.amber : Theme.ink
                } else if p > 0.7 {
                    col = Theme.violetLight
                } else if p > 0.4 {
                    col = Theme.violet
                } else {
                    col = Theme.magenta
                }
                al = 0.3 + 0.7 * p
            }

            al *= 0.35 + 0.65 * (sin(atan2(py, px)) * 0.5 + 0.5)
            return (col, al * dim)
        }

        for j in 40 ..< 160 {
            let y = Double(j) * cell + 2.0
            guard y < logicalH else { break }
            for i in 0 ..< cols {
                let x = Double(i) * cell + 2.0
                if let hit = evalRing(isOuter: true, x: x, y: y) ?? evalRing(isOuter: false, x: x, y: y) {
                    let rect = CGRect(
                        x: (Double(i) * cell + 0.4) * scale,
                        y: (Double(j) * cell + 0.4) * scale,
                        width: (cell - 0.8) * scale,
                        height: (cell - 0.8) * scale
                    )
                    context.fill(Path(rect), with: .color(hit.0.opacity(hit.1)))
                }
            }
        }
    }

    private static func drawGalaxy(_ context: GraphicsContext, size: CGSize, scale: Double, logicalH: Double, time: TimeInterval) {
        drawSpace(context, size: size, scale: scale, time: time, bandY: 0.30)

        let cell = 4.0
        let cx = 210.0
        let cy = logicalH - 174.0 // Bottom-anchored (700 on 874 canvas)
        drawGlow(context, cx: cx * scale, cy: cy * scale, radius: 260.0 * scale, color: Theme.violet, alpha: 0.20)

        let ax = -24.0 * .pi / 180.0
        let ca = cos(ax)
        let sa = sin(ax)
        let sy = 0.42
        let startRow = max(0, Int((cy - 160.0) / cell))
        let endRow = Int(ceil(logicalH / cell))
        let cols = Int(baseW / cell)

        for j in startRow ..< endRow {
            for i in 0 ..< cols {
                let dx = Double(i) * cell + 2.0 - cx
                let dy = Double(j) * cell + 2.0 - cy
                let px = dx * ca - dy * sa
                let py = (dx * sa + dy * ca) / sy
                let r = hypot(px, py)
                guard r <= 300.0 else { continue }
                let th = atan2(py, px)
                let arm = cos(2.0 * (th - log(r + 8.0) * 2.4 + time * 0.05))
                let core = exp(-r / 34.0)
                let v = max(0.0, arm) * exp(-r / 150.0) * 1.2 + core * 1.3
                let h = rh(i, j)
                guard v >= 0.06, h >= 0.12 else { continue }

                let col: Color
                if core > 0.5 {
                    col = h < 0.4 ? Theme.gold : Theme.ink
                } else if v > 0.7 {
                    col = Theme.violetLight
                } else if r > 150.0 {
                    col = Theme.magenta
                } else {
                    col = Theme.violet
                }

                let tStep = min(1.0, max(0.0, (v - 0.06) / (0.70 - 0.06)))
                let smooth = tStep * tStep * (3.0 - 2.0 * tStep)
                let alpha = smooth * (0.5 + 0.5 * (sin(th) * 0.5 + 0.5)) * (0.75 + 0.25 * h)
                let rect = CGRect(
                    x: (Double(i) * cell + 0.4) * scale,
                    y: (Double(j) * cell + 0.4) * scale,
                    width: (cell - 0.8) * scale,
                    height: (cell - 0.8) * scale
                )
                context.fill(Path(rect), with: .color(col.opacity(alpha)))
            }
        }
    }

    private static func drawSaturn(_ context: GraphicsContext, size: CGSize, scale: Double, logicalH: Double, time: TimeInterval) {
        drawSpace(context, size: size, scale: scale, time: time, bandY: 0.30)

        let cell = 4.0
        let cx = 250.0
        let cy = logicalH - 162.0 // Bottom-anchored (712 on 874 canvas)
        let pr = 92.0
        drawGlow(context, cx: cx * scale, cy: cy * scale, radius: 260.0 * scale, color: Theme.violet, alpha: 0.16)

        let ax = -18.0 * .pi / 180.0
        let ca = cos(ax)
        let sa = sin(ax)
        let sy = 0.30
        let bands = Theme.SpacePalette.saturnBands
        let startRow = max(0, Int((cy - 152.0) / cell))
        let endRow = Int(ceil(logicalH / cell))
        let cols = Int(baseW / cell)

        func ringCell(i: Int, j: Int, front: Bool) -> (Color, Double)? {
            let dx = Double(i) * cell + 2.0 - cx
            let dy = Double(j) * cell + 2.0 - cy
            let px = dx * ca - dy * sa
            let pyRaw = dx * sa + dy * ca
            if front ? (pyRaw < 0) : (pyRaw >= 0) { return nil }
            let py = pyRaw / sy
            let r = hypot(px, py)
            if r < 124.0 || r > 214.0 || (r > 168.0 && r < 177.0) { return nil }
            let ang = atan2(py, px) * 180.0 / .pi - time * 9.0
            let seg = Int(floor(posMod(ang, 360.0) / 3.0))
            let h = rh(seg, Int(floor(r / 4.0)))
            guard h >= 0.18 else { return nil }
            let col: Color = r < 168.0
                ? (h > 0.85 ? Theme.amber : Theme.violetLight)
                : (h > 0.80 ? Theme.magenta : Theme.violet)
            let alpha = (r < 168.0 ? 0.85 : 0.55) * (front ? 1.0 : 0.6)
            return (col, alpha)
        }

        for pass in 0 ..< 3 {
            for j in startRow ..< endRow {
                for i in 0 ..< cols {
                    let rect = CGRect(
                        x: (Double(i) * cell + 0.4) * scale,
                        y: (Double(j) * cell + 0.4) * scale,
                        width: (cell - 0.8) * scale,
                        height: (cell - 0.8) * scale
                    )
                    if pass == 1 {
                        let dx = Double(i) * cell + 2.0 - cx
                        let dy = Double(j) * cell + 2.0 - cy
                        let d = hypot(dx, dy)
                        guard d <= pr else { continue }
                        let lat = dy * ca - dx * sa
                        let bandIdxRaw = Int(floor((lat / pr + 1.0) * 6.0 + 0.6 * sin((dx * ca + dy * sa) / 18.0 + time * 0.5 + lat / 9.0)))
                        let bandIdx = ((bandIdxRaw % bands.count) + bands.count) % bands.count
                        let shade = max(0.15, min(1.0, 0.35 + (-dx / pr) * 0.5 + (1.0 - d / pr) * 0.5))
                        context.fill(Path(rect), with: .color(bands[bandIdx].opacity(shade)))
                    } else if let hit = ringCell(i: i, j: j, front: pass == 2) {
                        context.fill(Path(rect), with: .color(hit.0.opacity(hit.1)))
                    }
                }
            }
        }
    }

    private static let bayer4x4: [Double] = [
        0, 8, 2, 10,
        12, 4, 14, 6,
        3, 11, 1, 9,
        15, 7, 13, 5,
    ]

    private static func drawDither(_ context: GraphicsContext, size: CGSize, scale: Double, logicalH: Double, time: TimeInterval) {
        context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(Theme.ditherGround))

        let cell = 6.0
        let palette = Theme.SpacePalette.ditherSteps
        let z = time * 0.05
        let rows = Int(ceil(logicalH / cell))
        let cols = Int(ceil(baseW / cell))

        for j in 0 ..< rows {
            for i in 0 ..< cols {
                let x = Double(i) * (cell / 4.0) / 26.0
                let y = Double(j) * (cell / 4.0) / 26.0
                let wx = SphereEngine.fbm(x: x + z, y: y, z: z, seed: 3, octaves: 2)
                let v = SphereEngine.fbm(x: x + wx * 1.6, y: y - z * 1.4, z: z * 0.7, seed: 9, octaves: 3)
                let e = (v - 0.38) * 2.6 - (Double(j) / Double(max(1, rows))) * 0.35 + (1.0 - abs(Double(i) / Double(max(1, cols)) - 0.62) * 1.4) * 0.25
                guard e > 0 else { continue }
                let lv = e * Double(palette.count - 1)
                let k = Int(floor(lv))
                let frac = lv - Double(k)
                let threshold = bayer4x4[(j & 3) * 4 + (i & 3)] / 16.0
                let idx = min(palette.count - 1, max(0, k + (frac > threshold ? 1 : 0)))
                guard idx > 0 else { continue }

                let rect = CGRect(
                    x: (Double(i) * cell + 0.4) * scale,
                    y: (Double(j) * cell + 0.4) * scale,
                    width: (cell - 0.8) * scale,
                    height: (cell - 0.8) * scale
                )
                context.fill(Path(rect), with: .color(palette[idx]))
            }
        }
    }
}

// MARK: - 3D Sphere Noise & Equirectangular Lighting Engine

private enum SphereGeomKind {
    case big  // R 560, cap 236, tilt 1.15
    case moon // R 420, cap 250, tilt 1.0

    var radius: Double {
        switch self {
        case .big: return 560.0
        case .moon: return 420.0
        }
    }

    var cap: Double {
        switch self {
        case .big: return 236.0
        case .moon: return 250.0
        }
    }

    var tilt: Double {
        switch self {
        case .big: return 1.15
        case .moon: return 1.00
        }
    }
}

private struct EquirectTexture {
    var width: Int
    var height: Int
    var pixels: [UInt8] // RGBA
}

private struct ProceduralPlanet {
    var tex: EquirectTexture
    var atm: Theme.RGB
}

private enum SphereEngine {
    private static let bufW = 201
    private static let bufH = 128
    private static let topLogical = 874.0 - 256.0 // 618

    private struct PrecomputedGeom {
        var indices: [Int]
        var nx: [Double]
        var ny: [Double]
        var nz: [Double]
        var lf: [Double]
        var vr: [Double]
        var aa: [Double]
    }

    private static let lock = NSLock()
    private static var proceduralCache: [Int: ProceduralPlanet] = [:]
    private static var bundleCache: [String: EquirectTexture?] = [:]
    private static var renderedCache: [String: (quantRot: Int, image: CGImage)] = [:]

    private static let bigGeom = buildGeom(.big)
    private static let moonGeom = buildGeom(.moon)

    static func norm(_ x: Double, _ y: Double, _ z: Double) -> (Double, Double, Double) {
        let len = max(1e-9, sqrt(x * x + y * y + z * z))
        return (x / len, y / len, z / len)
    }

    static func h3(_ i: Int, _ j: Int, _ k: Int, _ s: Int) -> Double {
        var h = Int32(truncatingIfNeeded: i &* 374_761_393 &+ j &* 668_265_263 &+ k &* 2_147_483_647 &+ s &* 1_274_126_177)
        h = (h ^ (h >> 13)) &* 1_274_126_177
        let u = UInt32(bitPattern: h ^ (h >> 16))
        return Double(u) / 4_294_967_295.0
    }

    static func valueNoise(_ x: Double, _ y: Double, _ z: Double, _ s: Int) -> Double {
        let i = Int(floor(x))
        let j = Int(floor(y))
        let k = Int(floor(z))
        let fx = x - Double(i)
        let fy = y - Double(j)
        let fz = z - Double(k)
        let u = fx * fx * (3.0 - 2.0 * fx)
        let v = fy * fy * (3.0 - 2.0 * fy)
        let w = fz * fz * (3.0 - 2.0 * fz)

        let a = h3(i, j, k, s)
        let b = h3(i + 1, j, k, s)
        let c = h3(i, j + 1, k, s)
        let d = h3(i + 1, j + 1, k, s)
        let e = h3(i, j, k + 1, s)
        let f = h3(i + 1, j, k + 1, s)
        let g = h3(i, j + 1, k + 1, s)
        let hh = h3(i + 1, j + 1, k + 1, s)

        let x1 = a + (b - a) * u
        let x2 = c + (d - c) * u
        let x3 = e + (f - e) * u
        let x4 = g + (hh - g) * u
        let y1 = x1 + (x2 - x1) * v
        let y2 = x3 + (x4 - x3) * v
        return y1 + (y2 - y1) * w
    }

    static func fbm(x: Double, y: Double, z: Double, seed: Int, octaves: Int) -> Double {
        var amp = 0.5
        var total = 0.0
        var normSum = 0.0
        var px = x
        var py = y
        var pz = z
        for idx in 0 ..< octaves {
            total += amp * valueNoise(px, py, pz, seed + idx * 17)
            normSum += amp
            px *= 2.03
            py *= 2.03
            pz *= 2.03
            amp *= 0.5
        }
        return total / max(1e-9, normSum)
    }

    private static func smoothstep(_ a: Double, _ b: Double, _ v: Double) -> Double {
        let t = min(1.0, max(0.0, (v - a) / (b - a)))
        return t * t * (3.0 - 2.0 * t)
    }

    private static func ramp(_ palette: [Theme.RGB], _ value: Double) -> Theme.RGB {
        let clamped = min(0.9999, max(0.0, value)) * Double(palette.count - 1)
        let idx = Int(clamped)
        return Theme.RGB.lerp(palette[idx], palette[min(palette.count - 1, idx + 1)], clamped - Double(idx))
    }

    static func bundleTexture(named name: String) -> EquirectTexture? {
        lock.lock()
        if let cached = bundleCache[name] {
            lock.unlock()
            return cached
        }
        lock.unlock()

        guard let image = UIImage(named: name), let cg = image.cgImage else {
            lock.lock()
            bundleCache[name] = .some(nil)
            lock.unlock()
            return nil
        }

        let w = 512
        let h = 256
        var pixels = [UInt8](repeating: 0, count: w * h * 4)
        let colorSpace = CGColorSpaceCreateDeviceRGB()
        if let ctx = CGContext(
            data: &pixels,
            width: w,
            height: h,
            bitsPerComponent: 8,
            bytesPerRow: w * 4,
            space: colorSpace,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) {
            ctx.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
        }
        let tex = EquirectTexture(width: w, height: h, pixels: pixels)
        lock.lock()
        bundleCache[name] = .some(tex)
        lock.unlock()
        return tex
    }

    static func proceduralPlanet(seed: Int) -> ProceduralPlanet {
        lock.lock()
        if let cached = proceduralCache[seed] {
            lock.unlock()
            return cached
        }
        lock.unlock()

        var s = Int64(seed) * 9301 + 49297
        if s <= 0 { s = 49297 }
        func rnd() -> Double {
            s = (s * 16807) % 2147483647
            return Double(s) / 2147483647.0
        }
        for _ in 0 ..< 4 { _ = rnd() }

        let isGas = rnd() < 0.6
        let gasList = Theme.SpacePalette.gasPalettes
        let rockList = Theme.SpacePalette.rockPalettes
        let palette: [Theme.RGB] = isGas
            ? gasList[min(gasList.count - 1, Int(rnd() * Double(gasList.count)))]
            : rockList[min(rockList.count - 1, Int(rnd() * Double(rockList.count)))]

        let w = 256
        let h = 128
        var pixels = [UInt8](repeating: 255, count: w * h * 4)
        let bands = 6.0 + rnd() * 10.0
        let warp = 1.2 + rnd() * 2.4
        let sd = Int(rnd() * 1000.0)
        let stormCount = isGas ? (1 + Int(rnd() * 3.0)) : 0
        var storms: [(la: Double, lo: Double, r: Double)] = []
        for _ in 0 ..< stormCount {
            storms.append(((rnd() - 0.5) * 1.6, rnd() * .pi * 2.0, 0.08 + rnd() * 0.16))
        }

        for j in 0 ..< h {
            let lat = (0.5 - (Double(j) + 0.5) / Double(h)) * .pi
            let cl = cos(lat)
            let sl = sin(lat)
            for i in 0 ..< w {
                let lon = (Double(i) + 0.5) / Double(w) * (.pi * 2.0)
                let px = cl * cos(lon)
                let py = sl
                let pz = cl * sin(lon)
                var col: Theme.RGB
                if isGas {
                    let n = fbm(x: px * 2.2, y: py * 6.0, z: pz * 2.2, seed: sd, octaves: 5)
                    let t2 = fbm(x: px * 7.0, y: py * 18.0, z: pz * 7.0, seed: sd + 3, octaves: 3)
                    var v = 0.5 + 0.5 * sin(lat * bands + (n - 0.5) * warp * 4.0) * 0.8 + (t2 - 0.5) * 0.35
                    for st in storms {
                        let dl = (lat - st.la) / st.r
                        let dn = atan2(sin(lon - st.lo), cos(lon - st.lo)) / (st.r * 2.2)
                        let dd = dl * dl + dn * dn
                        if dd < 1.0 {
                            v += (1.0 - dd) * (0.25 + 0.2 * sin(dd * 12.0))
                        }
                    }
                    col = ramp(palette, v)
                } else {
                    let n = fbm(x: px * 2.5, y: py * 2.5, z: pz * 2.5, seed: sd, octaves: 6)
                    let r2 = fbm(x: px * 9.0, y: py * 9.0, z: pz * 9.0, seed: sd + 5, octaves: 3)
                    let v = n * 1.1 - 0.05 + (r2 - 0.5) * 0.25
                    col = ramp(palette, v)
                    let ice = smoothstep(0.78, 0.90, abs(sl) + (n - 0.5) * 0.3)
                    if let tip = palette.last {
                        col = Theme.RGB.lerp(col, tip, ice * 0.9)
                    }
                }
                let k = (j * w + i) * 4
                pixels[k] = UInt8(min(255, max(0, Int(col.r))))
                pixels[k + 1] = UInt8(min(255, max(0, Int(col.g))))
                pixels[k + 2] = UInt8(min(255, max(0, Int(col.b))))
                pixels[k + 3] = 255
            }
        }

        let atm: Theme.RGB = isGas
            ? Theme.RGB.lerp(palette[min(2, palette.count - 1)], Theme.SpacePalette.procGasAtm, 0.5)
            : Theme.SpacePalette.procRockAtm

        let built = ProceduralPlanet(tex: EquirectTexture(width: w, height: h, pixels: pixels), atm: atm)
        lock.lock()
        proceduralCache[seed] = built
        lock.unlock()
        return built
    }

    private static func buildGeom(_ kind: SphereGeomKind) -> PrecomputedGeom {
        let r = kind.radius
        let cx = 201.0
        let cy = 874.0 + r - kind.cap
        let ct = cos(kind.tilt)
        let st = sin(kind.tilt)
        let subScale = Double(bufW) / 402.0

        var indices: [Int] = []
        var nxArr: [Double] = []
        var nyArr: [Double] = []
        var nzArr: [Double] = []
        var lfArr: [Double] = []
        var vrArr: [Double] = []
        var aaArr: [Double] = []

        for by in 0 ..< bufH {
            for bx in 0 ..< bufW {
                let lx = (Double(bx) + 0.5) / subScale
                let ly = topLogical + (Double(by) + 0.5) / subScale
                let dx = (lx - cx) / r
                let dy = (ly - cy) / r
                let r2 = dx * dx + dy * dy
                if r2 >= 1.0 { continue }
                let nz = sqrt(1.0 - r2)
                let nx = dx
                let ny = -dy
                let ny2 = ny * ct - nz * st
                let nz2 = ny * st + nz * ct

                indices.append(by * bufW + bx)
                nxArr.append(nx)
                nyArr.append(ny)
                nzArr.append(nz)
                lfArr.append(atan2(nx, nz2) / (.pi * 2.0) + 0.5)
                vrArr.append(min(0.9999, max(0.0, 0.5 - asin(min(1.0, max(-1.0, ny2))) / .pi)))
                aaArr.append(min(1.0, max(0.0, (1.0 - sqrt(r2)) * r * subScale)))
            }
        }
        return PrecomputedGeom(indices: indices, nx: nxArr, ny: nyArr, nz: nzArr, lf: lfArr, vr: vrArr, aa: aaArr)
    }

    static func renderSphere(
        key: String,
        geomKind: SphereGeomKind,
        tex: EquirectTexture,
        night: EquirectTexture?,
        clouds: EquirectTexture?,
        light: (Double, Double, Double),
        rot: Double,
        atm: Theme.RGB,
        atmK: Double,
        amb: Double,
        spec: Bool
    ) -> CGImage? {
        let wrappedRot = rot - floor(rot)
        let quantRot = Int(wrappedRot * 720.0)

        lock.lock()
        if let hit = renderedCache[key], hit.quantRot == quantRot {
            lock.unlock()
            return hit.image
        }
        lock.unlock()

        let g = geomKind == .big ? bigGeom : moonGeom
        var out = [UInt8](repeating: 0, count: bufW * bufH * 4)
        let tw = tex.width
        let th = tex.height
        let td = tex.pixels
        let hv = norm(light.0, light.1, light.2 + 1.0)
        let city = Theme.SpacePalette.earthCityLight

        for p in 0 ..< g.indices.count {
            let k = g.indices[p] * 4
            let nx = g.nx[p]
            let ny = g.ny[p]
            let nz = g.nz[p]
            let dot = nx * light.0 + ny * light.1 + nz * light.2
            let diff = max(0.0, dot)
            let day = smoothstep(-0.10, 0.28, dot)

            var u = g.lf[p] + wrappedRot
            u -= floor(u)
            let tx = min(tw - 1, max(0, Int(u * Double(tw))))
            let ty = min(th - 1, max(0, Int(g.vr[p] * Double(th))))
            let ti = (ty * tw + tx) * 4

            var rr = Double(td[ti]) * (amb + 1.15 * diff)
            var gg = Double(td[ti + 1]) * (amb + 1.15 * diff)
            var bb = Double(td[ti + 2]) * (amb + 1.15 * diff)

            if let nightTex = night {
                let ntx = min(nightTex.width - 1, max(0, Int(u * Double(nightTex.width))))
                let nty = min(nightTex.height - 1, max(0, Int(g.vr[p] * Double(nightTex.height))))
                let ni = (nty * nightTex.width + ntx) * 4
                let nl = (Double(nightTex.pixels[ni]) / 255.0) * pow(1.0 - day, 2.0) * 1.6
                rr += city.r * nl
                gg += city.g * nl
                bb += city.b * nl
            }

            if let cloudTex = clouds {
                var u2 = g.lf[p] + wrappedRot * 1.25 + 0.1
                u2 -= floor(u2)
                let ctxX = min(cloudTex.width - 1, max(0, Int(u2 * Double(cloudTex.width))))
                let ctxY = min(cloudTex.height - 1, max(0, Int(g.vr[p] * Double(cloudTex.height))))
                let ci = (ctxY * cloudTex.width + ctxX) * 4
                let ca = (Double(cloudTex.pixels[ci]) / 255.0) * (Double(cloudTex.pixels[ci + 3]) / 255.0) * 0.9
                let cl = 245.0 * (0.02 + diff * 1.05)
                rr = rr * (1.0 - ca) + cl * ca
                gg = gg * (1.0 - ca) + cl * ca
                bb = bb * (1.0 - ca) + (cl + 8.0) * ca
            }

            let fresnel = pow(1.0 - nz, 2.6) * atmK
            let atmAmt = fresnel * (0.12 + 0.95 * day)
            rr += atm.r * atmAmt
            gg += atm.g * atmAmt
            bb += atm.b * atmAmt

            if spec {
                let specFactor = pow(max(0.0, nx * hv.0 + ny * hv.1 + nz * hv.2), 60.0) * (Int(td[ti + 2]) > Int(td[ti]) + 10 ? 0.9 : 0.1)
                rr += 255.0 * specFactor
                gg += 236.0 * specFactor
                bb += 210.0 * specFactor
            }

            let alpha = g.aa[p]
            out[k] = UInt8(min(255.0, max(0.0, rr * alpha)))
            out[k + 1] = UInt8(min(255.0, max(0.0, gg * alpha)))
            out[k + 2] = UInt8(min(255.0, max(0.0, bb * alpha)))
            out[k + 3] = UInt8(min(255.0, max(0.0, 255.0 * alpha)))
        }

        let colorSpace = CGColorSpaceCreateDeviceRGB()
        guard let provider = CGDataProvider(data: Data(out) as CFData),
              let cgImage = CGImage(
                  width: bufW,
                  height: bufH,
                  bitsPerComponent: 8,
                  bitsPerPixel: 32,
                  bytesPerRow: bufW * 4,
                  space: colorSpace,
                  bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue),
                  provider: provider,
                  decode: nil,
                  shouldInterpolate: true,
                  intent: .defaultIntent
              )
        else {
            return nil
        }

        lock.lock()
        if renderedCache.count > 16 {
            renderedCache.removeAll(keepingCapacity: true)
        }
        renderedCache[key] = (quantRot, cgImage)
        lock.unlock()
        return cgImage
    }
}
