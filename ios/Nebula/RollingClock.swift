import SwiftUI

struct RollingClock: View {
    var seconds: TimeInterval
    var paused: Bool
    var size: CGFloat = 42
    @Environment(\.tone) private var tone

    var body: some View {
        let text = StudioFormat.clock(seconds)
        HStack(spacing: 0) {
            ForEach(Array(text.enumerated()), id: \.offset) { _, character in
                if let digit = Int(String(character)) {
                    DigitColumn(digit: digit, size: size, color: paused ? tone.tertiary : Theme.gold, animate: !tone.reduceMotion && !paused)
                } else {
                    Text(String(character))
                        .font(.system(size: size, weight: .medium).monospacedDigit())
                        .foregroundStyle(paused ? tone.tertiary : Theme.gold)
                        .frame(height: size + 4)
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(paused ? "Paused, \(StudioFormat.spoken(seconds))" : "Recording, \(StudioFormat.spoken(seconds))")
    }
}

private struct DigitColumn: View {
    var digit: Int
    var size: CGFloat
    var color: Color
    var animate: Bool

    var body: some View {
        let line = size + 4
        VStack(spacing: 0) {
            ForEach(0 ..< 10, id: \.self) { value in
                Text("\(value)")
                    .font(.system(size: size, weight: .medium).monospacedDigit())
                    .foregroundStyle(color)
                    .frame(height: line)
            }
        }
        .offset(y: -CGFloat(digit) * line)
        .frame(width: size * 0.62, height: line, alignment: .top)
        .clipped()
        .animation(animate ? Theme.spring : .easeOut(duration: 0.15), value: digit)
    }
}
