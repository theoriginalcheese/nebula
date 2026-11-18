import Foundation

enum BackgroundKind: String, Codable, CaseIterable, Identifiable {
    case earth, proc, moon, solar, dots, ring, galaxy, saturn, dither

    var id: String { rawValue }

    var title: String {
        switch self {
        case .earth: "Earth"
        case .proc: "Random"
        case .moon: "Moonrise"
        case .solar: "Solar live"
        case .dots: "Dot bloom"
        case .ring: "Pixel orbit"
        case .galaxy: "Galaxy"
        case .saturn: "Ringed"
        case .dither: "Dither"
        }
    }
}

enum SurfaceStyle: String, Codable, CaseIterable, Identifiable {
    case glass, lively, solid
    var id: String { rawValue }
    var title: String { rawValue.prefix(1).uppercased() + rawValue.dropFirst() }
}

enum NowLayout: String, Codable, CaseIterable, Identifiable {
    case bento, game, clips
    var id: String { rawValue }
    var title: String {
        switch self {
        case .bento: "Bento"
        case .game: "Game-aware"
        case .clips: "Clips-led"
        }
    }
}

struct PhonePrefs: Codable, Equatable {
    var background: BackgroundKind = .earth
    var planetSeed: Int = 7
    var motion: String = "live"
    var surfaces: SurfaceStyle = .glass
    var nowLayout: NowLayout = .bento

    var still: Bool { motion == "still" }

    static func load(_ url: URL) -> PhonePrefs {
        guard let data = try? Data(contentsOf: url),
              let prefs = try? JSONDecoder().decode(PhonePrefs.self, from: data)
        else {
            return PhonePrefs()
        }
        return prefs
    }

    func save(_ url: URL) {
        guard let data = try? JSONEncoder().encode(self) else { return }
        try? data.write(to: url, options: .atomic)
    }
}

enum PlanetName {
    static func make(_ seed: Int) -> String {
        var rng = SplitMix(seed: UInt64(bitPattern: Int64(seed)))
        let lead = ["va", "ke", "or", "lu", "sa", "ni", "xe", "tu"]
        let tail = ["ri", "on", "el", "ar", "os", "ix", "un", "ae"]
        let suffix = ["prime", "ii", "vale", "reach", "dune"]
        let word = lead[rng.int(lead.count)] + tail[rng.int(tail.count)]
        return word.prefix(1).uppercased() + word.dropFirst() + " " + suffix[rng.int(suffix.count)]
    }
}

struct SplitMix {
    var state: UInt64

    init(seed: UInt64) {
        state = seed == 0 ? 0xA5A5_5A5A_1234_5678 : seed
    }

    mutating func next() -> UInt64 {
        state &+= 0x9E37_79B9_7F4A_7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
        z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
        return z ^ (z >> 31)
    }

    mutating func unit() -> Double {
        Double(next() % 10_000) / 10_000
    }

    mutating func int(_ count: Int) -> Int {
        guard count > 0 else { return 0 }
        return Int(next() % UInt64(count))
    }
}
