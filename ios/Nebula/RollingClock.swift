import SwiftUI

struct RollingClock: View {
    var seconds: TimeInterval
    var paused: Bool
    var size: CGFloat = Theme.Size.clockBento
    @Environment(\.tone) private var tone

    var body: some View {
        let text = StudioFormat.clock(seconds)
        let color = paused ? Theme.ink2 : Theme.gold
        let shouldRoll = !tone.isStill && !paused

        HStack(spacing: 0) {
            ForEach(Array(text.enumerated()), id: \.offset) { _, character in
                if let digit = Int(String(character)) {
                    DigitColumn(
                        digit: digit,
                        size: size,
                        color: color,
                        animate: shouldRoll
                    )
                } else {
                    Text(String(character))
                        .font(Theme.TypeScale.heroClock(size))
                        .tracking(Theme.TypeScale.heroClockTracking(size))
                        .foregroundStyle(color)
                        .frame(height: lineHeight)
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(spokenLabel)
    }

    private var lineHeight: CGFloat {
        return (size * 1.10).rounded()
    }

    /// Spec §12: VoiceOver updates at most every 10 s while ticking.
    private var spokenLabel: String {
        let quantized: TimeInterval
        if paused || seconds < 10 {
            quantized = seconds
        } else {
            quantized = floor(seconds / 10.0) * 10.0
        }
        if paused {
            return "Paused, \(StudioFormat.spoken(quantized))"
        }
        return "Recording, \(StudioFormat.spoken(quantized))"
    }
}

private struct DigitColumn: View {
    var digit: Int
    var size: CGFloat
    var color: Color
    var animate: Bool

    var body: some View {
        let line = (size * 1.10).rounded()
        VStack(spacing: 0) {
            ForEach(0 ..< 10, id: \.self) { value in
                Text("\(value)")
                    .font(Theme.TypeScale.heroClock(size))
                    .tracking(Theme.TypeScale.heroClockTracking(size))
                    .foregroundStyle(color)
                    .frame(height: line)
            }
        }
        .offset(y: -CGFloat(digit) * line)
        .frame(width: (size * 0.60).rounded(), height: line, alignment: .top)
        .clipped()
        .animation(animate ? Theme.clockSpring : Theme.clockStillFade, value: digit)
    }
}
