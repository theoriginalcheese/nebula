import SwiftUI

/// The Nebula mark (orbit + four-point star). Compiled into the app and the
/// lock-screen widget, so both draw one mark rather than a copy each.
struct NebulaMark: View {
    var size: CGFloat = 26

    var body: some View {
        Canvas { context, canvasSize in
            let w = canvasSize.width
            let h = canvasSize.height
            let cx = w * 0.5
            let cy = h * 0.5
            let scale = min(w, h) / 64.0

            var orbitContext = context
            orbitContext.translateBy(x: cx, y: cy)
            orbitContext.rotate(by: .degrees(-22))
            let rx = 25.0 * scale
            let ry = 15.0 * scale
            let orbit = Path(ellipseIn: CGRect(x: -rx, y: -ry, width: rx * 2, height: ry * 2))
            orbitContext.stroke(orbit, with: .color(Theme.violetLight), lineWidth: 3.8 * scale)

            var star = Path()
            let outer = 19.0 * scale
            let inner = 4.6 * scale
            star.move(to: CGPoint(x: cx + outer, y: cy))
            star.addLine(to: CGPoint(x: cx + inner, y: cy + inner))
            star.addLine(to: CGPoint(x: cx, y: cy + outer))
            star.addLine(to: CGPoint(x: cx - inner, y: cy + inner))
            star.addLine(to: CGPoint(x: cx - outer, y: cy))
            star.addLine(to: CGPoint(x: cx - inner, y: cy - inner))
            star.addLine(to: CGPoint(x: cx, y: cy - outer))
            star.addLine(to: CGPoint(x: cx + inner, y: cy - inner))
            star.closeSubpath()
            context.fill(star, with: .color(Theme.ink))
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}
