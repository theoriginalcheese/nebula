import SwiftUI

enum Theme {
    static let ground = Color(red: 6 / 255, green: 5 / 255, blue: 12 / 255)
    static let ink = Color(red: 245 / 255, green: 243 / 255, blue: 255 / 255)
    static let ink2 = Color(red: 201 / 255, green: 196 / 255, blue: 230 / 255)
    static let ink3 = Color(red: 154 / 255, green: 147 / 255, blue: 196 / 255)
    static let violet = Color(red: 139 / 255, green: 124 / 255, blue: 246 / 255)
    static let violetLight = Color(red: 185 / 255, green: 174 / 255, blue: 249 / 255)
    static let violetPale = Color(red: 196 / 255, green: 184 / 255, blue: 255 / 255)
    static let gold = Color(red: 255 / 255, green: 232 / 255, blue: 188 / 255)
    static let amber = Color(red: 233 / 255, green: 184 / 255, blue: 114 / 255)
    static let teal = Color(red: 62 / 255, green: 190 / 255, blue: 176 / 255)
    static let tealPale = Color(red: 159 / 255, green: 227 / 255, blue: 214 / 255)
    static let coral = Color(red: 255 / 255, green: 92 / 255, blue: 122 / 255)
    static let coralText = Color(red: 255 / 255, green: 194 / 255, blue: 206 / 255)
    static let magenta = Color(red: 212 / 255, green: 113 / 255, blue: 224 / 255)
    static let card = Color(red: 28 / 255, green: 23 / 255, blue: 48 / 255)
    static let inkDark = Color(red: 16 / 255, green: 13 / 255, blue: 28 / 255)
    static let lock = Color(red: 42 / 255, green: 36 / 255, blue: 66 / 255)
    static let livelyTop = Color(red: 36 / 255, green: 28 / 255, blue: 68 / 255)
    static let livelyBottom = Color(red: 23 / 255, green: 18 / 255, blue: 44 / 255)
    static let spring = Animation.spring(response: 0.45, dampingFraction: 0.86)

    static func fade(_ reduceMotion: Bool) -> Animation {
        reduceMotion ? .easeOut(duration: 0.2) : spring
    }
}

struct Tone {
    var reduceTransparency: Bool
    var increaseContrast: Bool
    var reduceMotion: Bool

    var tertiary: Color { increaseContrast ? Theme.ink2 : Theme.ink3 }
    var hairline: Double { increaseContrast ? 0.2 : 0.09 }
    var motion: Animation { Theme.fade(reduceMotion) }
}

private struct ToneKey: EnvironmentKey {
    static let defaultValue = Tone(reduceTransparency: false, increaseContrast: false, reduceMotion: false)
}

extension EnvironmentValues {
    var tone: Tone {
        get { self[ToneKey.self] }
        set { self[ToneKey.self] = newValue }
    }
}

struct ToneReader<Content: View>: View {
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @ViewBuilder var content: (Tone) -> Content

    var body: some View {
        let tone = Tone(
            reduceTransparency: reduceTransparency,
            increaseContrast: contrast == .increased,
            reduceMotion: reduceMotion
        )
        content(tone)
            .environment(\.tone, tone)
    }
}
