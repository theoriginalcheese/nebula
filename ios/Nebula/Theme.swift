import SwiftUI

enum Theme {
    // MARK: - Core Contract Colours (§6.1)
    static let ground = Color(red: 6.0 / 255.0, green: 5.0 / 255.0, blue: 12.0 / 255.0)       // #06050C
    static let ink = Color(red: 245.0 / 255.0, green: 243.0 / 255.0, blue: 255.0 / 255.0)     // #F5F3FF
    static let ink2 = Color(red: 201.0 / 255.0, green: 196.0 / 255.0, blue: 230.0 / 255.0)    // #C9C4E6
    static let ink3 = Color(red: 154.0 / 255.0, green: 147.0 / 255.0, blue: 196.0 / 255.0)    // #9A93C4
    static let violet = Color(red: 139.0 / 255.0, green: 124.0 / 255.0, blue: 246.0 / 255.0)  // #8B7CF6
    static let violetLight = Color(red: 185.0 / 255.0, green: 174.0 / 255.0, blue: 249.0 / 255.0) // #B9AEF9
    static let violetPale = Color(red: 196.0 / 255.0, green: 184.0 / 255.0, blue: 255.0 / 255.0)  // #C4B8FF
    static let gold = Color(red: 255.0 / 255.0, green: 232.0 / 255.0, blue: 188.0 / 255.0)    // #FFE8BC
    static let amber = Color(red: 233.0 / 255.0, green: 184.0 / 255.0, blue: 114.0 / 255.0)   // #E9B872
    static let teal = Color(red: 62.0 / 255.0, green: 190.0 / 255.0, blue: 176.0 / 255.0)     // #3EBEB0
    static let coral = Color(red: 255.0 / 255.0, green: 92.0 / 255.0, blue: 122.0 / 255.0)    // #FF5C7A
    static let magenta = Color(red: 212.0 / 255.0, green: 113.0 / 255.0, blue: 224.0 / 255.0)  // #D471E0
    static let card = Color(red: 28.0 / 255.0, green: 23.0 / 255.0, blue: 48.0 / 255.0)       // #1C1730
    static let lock = Color(red: 42.0 / 255.0, green: 36.0 / 255.0, blue: 66.0 / 255.0)       // #2A2442
    static let inkDark = Color(red: 16.0 / 255.0, green: 13.0 / 255.0, blue: 28.0 / 255.0)    // #100D1C

    // MARK: - Extended Contract Tints (§6.1–§6.2, Mockups 2f–3h)
    static let inkSoft = Color(red: 227.0 / 255.0, green: 223.0 / 255.0, blue: 245.0 / 255.0)     // #E3DFF5
    static let inkMuted = Color(red: 115.0 / 255.0, green: 107.0 / 255.0, blue: 164.0 / 255.0)    // #736BA4
    static let amberDeep = Color(red: 224.0 / 255.0, green: 168.0 / 255.0, blue: 92.0 / 255.0)    // #E0A85C
    static let amberPale = Color(red: 242.0 / 255.0, green: 210.0 / 255.0, blue: 164.0 / 255.0)   // #F2D2A4
    static let tealPale = Color(red: 159.0 / 255.0, green: 227.0 / 255.0, blue: 214.0 / 255.0)    // #9FE3D6
    static let coralText = Color(red: 255.0 / 255.0, green: 194.0 / 255.0, blue: 206.0 / 255.0)   // #FFC2CE
    static let coralSoft = Color(red: 255.0 / 255.0, green: 143.0 / 255.0, blue: 163.0 / 255.0)   // #FF8FA3
    static let magentaLight = Color(red: 231.0 / 255.0, green: 169.0 / 255.0, blue: 238.0 / 255.0) // #E7A9EE

    // MARK: - Surface & Glass Bases (§6.2, §6.4)
    static let glassHeroBase = inkDark                                                             // rgb(16,13,28)
    static let glassBarBase = Color(red: 30.0 / 255.0, green: 26.0 / 255.0, blue: 48.0 / 255.0)    // rgb(30,26,48)
    static let glassReadingBase = Color(red: 22.0 / 255.0, green: 18.0 / 255.0, blue: 40.0 / 255.0) // rgb(22,18,40)
    static let glassSheetBase = Color(red: 22.0 / 255.0, green: 18.0 / 255.0, blue: 38.0 / 255.0)  // rgb(22,18,38)
    static let segmentTrackBase = Color(red: 10.0 / 255.0, green: 8.0 / 255.0, blue: 18.0 / 255.0) // rgb(10,8,18)
    static let scrimBase = Color(red: 7.0 / 255.0, green: 6.0 / 255.0, blue: 14.0 / 255.0)         // rgb(7,6,14)
    static let modalBackdrop = Color(red: 5.0 / 255.0, green: 4.0 / 255.0, blue: 10.0 / 255.0)     // rgb(5,4,10)
    static let livelyTop = Color(red: 36.0 / 255.0, green: 28.0 / 255.0, blue: 68.0 / 255.0)       // #241C44
    static let livelyBottom = Color(red: 23.0 / 255.0, green: 18.0 / 255.0, blue: 44.0 / 255.0)    // #17122C
    static let ditherGround = Color(red: 11.0 / 255.0, green: 9.0 / 255.0, blue: 22.0 / 255.0)     // #0B0916
    static let specular = Color(red: 1.0, green: 1.0, blue: 1.0)
    static let shadow = Color(red: 0.0, green: 0.0, blue: 0.0)
    static let clear = Color.clear

    /// Per-background reading glass alpha table (§6.2: raise toward .60 when background exceeds L* 35).
    static func readingGlassAlpha(for backgroundRaw: String) -> Double {
        switch backgroundRaw {
        case "dots", "dither":
            return 0.56
        case "proc", "solar":
            return 0.50
        case "ring", "saturn":
            return 0.46
        default:
            return 0.42
        }
    }

    // MARK: - Concentric Radii (§6.2, §6.4)
    enum Radius {
        static let heroTray: CGFloat = 34
        static let heroCard: CGFloat = 28
        static let featuredTray: CGFloat = 32
        static let featuredCard: CGFloat = 26
        static let tileTray: CGFloat = 30
        static let tileCard: CGFloat = 24

        static let group: CGFloat = 24
        static let settingsGroup: CGFloat = 22
        static let sheetCard: CGFloat = 38
        static let appearanceTile: CGFloat = 20
        static let banner: CGFloat = 18
        static let field: CGFloat = 14
        static let peerIcon: CGFloat = 10
        static let settingsIcon: CGFloat = 9
        static let clipThumb: CGFloat = 8
        static let highlightStrip: CGFloat = 6
        static let stopGlyph: CGFloat = 3
        static let track: CGFloat = 3
        static let bar: CGFloat = 2
        static let pauseBar: CGFloat = 1.6
        static let playhead: CGFloat = 1

        static let tabBar: CGFloat = 31
        static let primaryPill: CGFloat = 28
        static let ghostPill: CGFloat = 26
        static let actionPill: CGFloat = 23
        static let searchBar: CGFloat = 22
        static let segmentTrack: CGFloat = 18
        static let segmentThumb: CGFloat = 16
        static let segmentCompactTrack: CGFloat = 16
        static let segmentCompactThumb: CGFloat = 14
        static let stepperTrack: CGFloat = 17
        static let stepperButton: CGFloat = 15
    }

    // MARK: - Spacing & Sizing (§6.3, §6.4, §9)
    enum Space {
        static let trayPad: CGFloat = 6
        static let screenMargin: CGFloat = 14
        static let headerInset: CGFloat = 6      // 14 + 6 = 20 pt content edge
        static let sheetMargin: CGFloat = 20
        static let sectionGap: CGFloat = 14
        static let bentoGap: CGFloat = 12
        static let gridGap: CGFloat = 10
        static let chipGap: CGFloat = 8
        static let tagGap: CGFloat = 6
        static let segmentPad: CGFloat = 2

        static let tabBarSideInset: CGFloat = 21
        static let tabBarBottomInset: CGFloat = 28
        static let tabBarInnerPad: CGFloat = 6
        static let contentBottomInset: CGFloat = 110
    }

    enum Size {
        static let canvasWidth: CGFloat = 402
        static let canvasHeight: CGFloat = 874
        static let targetWidth: CGFloat = 390
        static let targetHeight: CGFloat = 844

        static let tabBarHeight: CGFloat = 62
        static let tabIcon: CGFloat = 24
        static let minHitTarget: CGFloat = 44

        static let chromeButton: CGFloat = 42
        static let transportButton: CGFloat = 48
        static let clipActionCircle: CGFloat = 56
        static let stagePlayButton: CGFloat = 68

        static let primaryHeight: CGFloat = 56
        static let primaryTrailingCircle: CGFloat = 44
        static let ghostHeight: CGFloat = 52
        static let compactPillHeight: CGFloat = 46
        static let compactTrailingCircle: CGFloat = 38
        static let searchHeight: CGFloat = 44

        static let segmentHeight: CGFloat = 36
        static let segmentCompactHeight: CGFloat = 32
        static let stepperHeight: CGFloat = 34
        static let stepperButton: CGFloat = 30
        static let filterChipHeight: CGFloat = 34
        static let rerollPillHeight: CGFloat = 32
        static let tagChipHeight: CGFloat = 28
        static let statusChipHeight: CGFloat = 26
        static let badgeChipHeight: CGFloat = 24
        static let metaPillHeight: CGFloat = 22

        static let settingsRowHeight: CGFloat = 50
        static let folderRowHeight: CGFloat = 54
        static let peerRowHeight: CGFloat = 58
        static let stepperRowHeight: CGFloat = 60
        static let factRowHeight: CGFloat = 46
        static let sheetFactRowHeight: CGFloat = 44

        static let storageRing: CGFloat = 52
        static let hostAvatar: CGFloat = 76
        static let settingsPCBadge: CGFloat = 48
        static let pendingBadge: CGFloat = 40
        static let sheetBadge: CGFloat = 56
        static let peerIconBox: CGFloat = 34
        static let settingsIconBox: CGFloat = 30
        static let checkBadge: CGFloat = 22

        static let clockBento: CGFloat = 42
        static let clockGame: CGFloat = 46
        static let clockClips: CGFloat = 38

        static let clipStackCardHeight: CGFloat = 180
        static let clipStackContainerHeight: CGFloat = 228
        static let latestClipHeight: CGFloat = 176
        static let gameCoverHeight: CGFloat = 118
        static let appearanceTileHeight: CGFloat = 150
        static let clipStageHeight: CGFloat = 360
        static let sparklineHeight: CGFloat = 28
    }

    // MARK: - Opacity & Stroke Tokens (§6.2, §9.1)
    enum Opacity {
        static let trayFill: Double = 0.04
        static let hairline: Double = 0.09
        static let highContrastHairline: Double = 0.20

        static let heroGlassFill: Double = 0.50
        static let barGlassFill: Double = 0.30
        static let searchGlassFill: Double = 0.34
        static let actionGlassFill: Double = 0.40
        static let chipGlassFill: Double = 0.55
        static let sheetGlassFill: Double = 0.72
        static let segmentTrackFill: Double = 0.55

        static let specularStrong: Double = 0.26
        static let specularMedium: Double = 0.16
        static let specularSubtle: Double = 0.08
        static let innerHairline: Double = 0.07

        static let primaryFill: Double = 0.20
        static let primaryRing: Double = 0.55
        static let primaryBadgeFill: Double = 0.30
        static let segmentSelectedFill: Double = 0.24
        static let segmentSelectedRing: Double = 0.35

        static let connectingDim: Double = 0.70
        static let disabled: Double = 0.45

        static let stackFront: Double = 1.00
        static let stackMiddle: Double = 0.72
        static let stackBack: Double = 0.45
    }

    enum ClipStack {
        static let frontScale: CGFloat = 1.00
        static let middleScale: CGFloat = 0.92
        static let backScale: CGFloat = 0.84

        static let frontOffset: CGFloat = 48
        static let middleOffset: CGFloat = 22
        static let backOffset: CGFloat = 0
    }

    enum Stroke {
        static let divider: CGFloat = 0.5
        static let hairline: CGFloat = 1.0
        static let sparkline: CGFloat = 1.5
        static let selectedTile: CGFloat = 2.0
        static let storageRing: CGFloat = 4.0
    }

    // MARK: - Type Scale (§6.3, SF Pro + SF Mono)
    enum TypeScale {
        static let largeTitle = Font.system(size: 34, weight: .bold)
        static let largeTitleTracking: CGFloat = -0.34

        static let sheetTitle = Font.system(size: 30, weight: .bold)
        static let gameHeroTitle = Font.system(size: 30, weight: .semibold)
        static let detailTitle = Font.system(size: 28, weight: .bold)
        static let detailTitleTracking: CGFloat = -0.56

        static let statMetric = Font.system(size: 28, weight: .medium).monospacedDigit()
        static let lockClock = Font.system(size: 28, weight: .medium).monospacedDigit()

        static func heroClock(_ size: CGFloat) -> Font {
            return Font.system(size: size, weight: .medium).monospacedDigit()
        }

        static func heroClockTracking(_ size: CGFloat) -> CGFloat {
            return -size * 0.025
        }

        static let sheetBadgeGlyph = Font.system(size: 26, weight: .semibold)
        static let cardTitleLarge = Font.system(size: 22, weight: .semibold)
        static let bufferLine = Font.system(size: 20, weight: .medium)
        static let sectionHeading = Font.system(size: 20, weight: .semibold)
        static let promptTitle = Font.system(size: 19, weight: .semibold)
        static let featuredTitle = Font.system(size: 18, weight: .semibold)
        static let stepperSymbol = Font.system(size: 18, weight: .regular)

        static let cardTitle = Font.system(size: 17, weight: .semibold)
        static let searchField = Font.system(size: 17, weight: .regular)
        static let navInlineAction = Font.system(size: 17, weight: .regular)

        static let rowTitle = Font.system(size: 16, weight: .semibold)
        static let rowLabel = Font.system(size: 16, weight: .regular)

        static let controlSemibold = Font.system(size: 15, weight: .semibold)
        static let factMedium = Font.system(size: 15, weight: .medium)
        static let factMediumTabular = Font.system(size: 15, weight: .medium).monospacedDigit()
        static let body = Font.system(size: 15, weight: .regular)

        static let filterChip = Font.system(size: 14, weight: .semibold)
        static let rowValue = Font.system(size: 14, weight: .regular)

        static let segment = Font.system(size: 13, weight: .semibold)
        static let ringPercent = Font.system(size: 13, weight: .semibold).monospacedDigit()
        static let subtitle = Font.system(size: 13, weight: .regular)
        static let monoFolder = Font.system(size: 13, weight: .regular, design: .monospaced)

        static let segmentCompact = Font.system(size: 12, weight: .semibold)
        static let captionSemibold = Font.system(size: 12, weight: .semibold)
        static let captionTabular = Font.system(size: 12, weight: .semibold).monospacedDigit()
        static let captionMedium = Font.system(size: 12, weight: .medium)
        static let caption = Font.system(size: 12, weight: .regular)
        static let captionRegularTabular = Font.system(size: 12, weight: .regular).monospacedDigit()
        static let mono = Font.system(size: 12, weight: .regular, design: .monospaced)

        static let eyebrow = Font.system(size: 11, weight: .semibold)
        static let eyebrowTracking: CGFloat = 1.76 // 0.16em at 11pt

        static let tabLabel = Font.system(size: 10, weight: .semibold)
        static let solarStamp = Font.system(size: 10, weight: .semibold)
        static let solarLabel = Font.system(size: 9, weight: .semibold)

        static func icon(_ size: CGFloat, weight: Font.Weight = .light) -> Font {
            return Font.system(size: size, weight: weight)
        }
    }

    // MARK: - Motion (§7.1–§7.3)
    static let spring = Animation.spring(response: 0.45, dampingFraction: 0.86)
    static let clockSpring = Animation.spring(response: 0.55, dampingFraction: 0.86)
    static let pressAnimation = Animation.easeOut(duration: 0.15)
    static let stillFade = Animation.easeOut(duration: 0.20)
    static let clockStillFade = Animation.easeOut(duration: 0.15)

    static func fade(_ reduceMotion: Bool) -> Animation {
        return reduceMotion ? stillFade : spring
    }

    // MARK: - Space Engine & Procedural Art Palettes (§10, nm-space.js)
    struct RGB: Sendable {
        var r: Double
        var g: Double
        var b: Double

        var color: Color {
            return Color(red: r / 255.0, green: g / 255.0, blue: b / 255.0)
        }

        static func lerp(_ a: RGB, _ b: RGB, _ t: Double) -> RGB {
            let clamped = min(1.0, max(0.0, t))
            return RGB(
                r: a.r + (b.r - a.r) * clamped,
                g: a.g + (b.g - a.g) * clamped,
                b: a.b + (b.b - a.b) * clamped
            )
        }
    }

    enum SpacePalette {
        static let bandInner = Color(red: 150.0 / 255.0, green: 130.0 / 255.0, blue: 255.0 / 255.0)
        static let bandMid = Color(red: 120.0 / 255.0, green: 96.0 / 255.0, blue: 230.0 / 255.0)
        static let bandWarmCore = Color(red: 255.0 / 255.0, green: 232.0 / 255.0, blue: 200.0 / 255.0)
        static let starWarm = Color(red: 255.0 / 255.0, green: 236.0 / 255.0, blue: 206.0 / 255.0)
        static let starCool = Color(red: 228.0 / 255.0, green: 224.0 / 255.0, blue: 255.0 / 255.0)

        static let earthAtm = RGB(r: 110, g: 140, b: 255)
        static let earthRim = RGB(r: 255, g: 206, b: 150)
        static let earthCityLight = RGB(r: 255, g: 205, b: 140)
        static let procRim = RGB(r: 200, g: 184, b: 255)
        static let procGasAtm = RGB(r: 140, g: 124, b: 246)
        static let procRockAtm = RGB(r: 150, g: 140, b: 220)
        static let moonAtm = RGB(r: 60, g: 50, b: 110)
        static let moonRim = RGB(r: 255, g: 226, b: 180)
        static let rimWarm = Color(red: 255.0 / 255.0, green: 244.0 / 255.0, blue: 226.0 / 255.0)
        static let rimCool = Color(red: 160.0 / 255.0, green: 140.0 / 255.0, blue: 255.0 / 255.0)

        static let sunCore = Color(red: 255.0 / 255.0, green: 248.0 / 255.0, blue: 234.0 / 255.0) // #FFF8EA
        static let sunMid = Color(red: 255.0 / 255.0, green: 217.0 / 255.0, blue: 160.0 / 255.0)  // #FFD9A0
        static let sunEdge = Color(red: 240.0 / 255.0, green: 168.0 / 255.0, blue: 96.0 / 255.0)  // #F0A860
        static let sunGlow = Color(red: 255.0 / 255.0, green: 190.0 / 255.0, blue: 120.0 / 255.0)
        static let saturnRing = Color(red: 233.0 / 255.0, green: 210.0 / 255.0, blue: 160.0 / 255.0)

        static let solarBodies: [RGB] = [
            RGB(r: 184, g: 176, b: 170), // Mercury
            RGB(r: 236, g: 214, b: 170), // Venus
            RGB(r: 110, g: 160, b: 255), // Earth
            RGB(r: 226, g: 120, b: 80),  // Mars
            RGB(r: 222, g: 190, b: 150), // Jupiter
            RGB(r: 233, g: 210, b: 160), // Saturn
            RGB(r: 160, g: 220, b: 230), // Uranus
            RGB(r: 110, g: 140, b: 240), // Neptune
        ]

        static let gasPalettes: [[RGB]] = [
            [RGB(r: 30, g: 22, b: 56), RGB(r: 75, g: 58, b: 143), RGB(r: 139, g: 124, b: 246), RGB(r: 201, g: 184, b: 255), RGB(r: 242, g: 210, b: 164), RGB(r: 154, g: 111, b: 192), RGB(r: 46, g: 36, b: 88)],
            [RGB(r: 20, g: 34, b: 58), RGB(r: 47, g: 94, b: 150), RGB(r: 127, g: 178, b: 216), RGB(r: 227, g: 230, b: 224), RGB(r: 200, g: 168, b: 130), RGB(r: 58, g: 76, b: 122), RGB(r: 23, g: 34, b: 56)],
            [RGB(r: 42, g: 20, b: 38), RGB(r: 122, g: 58, b: 94), RGB(r: 212, g: 113, b: 224), RGB(r: 242, g: 194, b: 160), RGB(r: 255, g: 232, b: 208), RGB(r: 160, g: 80, b: 110), RGB(r: 42, g: 20, b: 38)],
            [RGB(r: 15, g: 36, b: 38), RGB(r: 33, g: 112, b: 110), RGB(r: 127, g: 211, b: 196), RGB(r: 230, g: 240, b: 224), RGB(r: 185, g: 174, b: 249), RGB(r: 58, g: 79, b: 134), RGB(r: 18, g: 28, b: 48)],
            [RGB(r: 43, g: 28, b: 16), RGB(r: 122, g: 78, b: 42), RGB(r: 201, g: 149, b: 96), RGB(r: 240, g: 217, b: 176), RGB(r: 233, g: 184, b: 114), RGB(r: 140, g: 90, b: 58), RGB(r: 36, g: 22, b: 14)],
        ]

        static let rockPalettes: [[RGB]] = [
            [RGB(r: 18, g: 14, b: 24), RGB(r: 59, g: 47, b: 74), RGB(r: 110, g: 94, b: 126), RGB(r: 168, g: 152, b: 176), RGB(r: 226, g: 216, b: 232)],
            [RGB(r: 26, g: 16, b: 12), RGB(r: 90, g: 52, b: 34), RGB(r: 160, g: 96, b: 58), RGB(r: 216, g: 160, b: 112), RGB(r: 242, g: 220, b: 192)],
            [RGB(r: 12, g: 20, b: 24), RGB(r: 36, g: 64, b: 74), RGB(r: 78, g: 122, b: 132), RGB(r: 156, g: 196, b: 200), RGB(r: 234, g: 244, b: 242)],
            [RGB(r: 20, g: 12, b: 16), RGB(r: 74, g: 30, b: 38), RGB(r: 142, g: 58, b: 58), RGB(r: 217, g: 138, b: 90), RGB(r: 255, g: 217, b: 168)],
        ]

        static let saturnBands: [Color] = [
            Color(red: 46.0 / 255.0, green: 36.0 / 255.0, blue: 88.0 / 255.0),   // #2E2458
            Color(red: 75.0 / 255.0, green: 58.0 / 255.0, blue: 143.0 / 255.0),  // #4B3A8F
            Theme.violet,
            Theme.violetLight,
            Theme.amber,
            Theme.magenta,
            Theme.violet,
            Color(red: 75.0 / 255.0, green: 58.0 / 255.0, blue: 143.0 / 255.0),
        ]

        static let ditherSteps: [Color] = [
            Theme.inkDark,
            Color(red: 46.0 / 255.0, green: 36.0 / 255.0, blue: 88.0 / 255.0),   // #2E2458
            Color(red: 75.0 / 255.0, green: 58.0 / 255.0, blue: 143.0 / 255.0),  // #4B3A8F
            Theme.violet,
            Theme.magenta,
            Theme.amberPale,
        ]

        static let dotViolet = RGB(r: 139, g: 124, b: 246)
        static let dotMagenta = RGB(r: 212, g: 113, b: 224)
        static let dotInk = RGB(r: 245, g: 243, b: 255)
        static let dotAmber = RGB(r: 233, g: 184, b: 114)
    }
}

struct Tone {
    var reduceTransparency: Bool
    var increaseContrast: Bool
    var reduceMotion: Bool
    var stillPref: Bool = false

    var tertiary: Color {
        return increaseContrast ? Theme.ink2 : Theme.ink3
    }

    var hairline: Double {
        return increaseContrast ? Theme.Opacity.highContrastHairline : Theme.Opacity.hairline
    }

    var isStill: Bool {
        return reduceMotion || stillPref
    }

    var motion: Animation {
        return Theme.fade(isStill)
    }
}

private struct ToneKey: EnvironmentKey {
    static let defaultValue = Tone(reduceTransparency: false, increaseContrast: false, reduceMotion: false, stillPref: false)
}

extension EnvironmentValues {
    var tone: Tone {
        get { return self[ToneKey.self] }
        set { self[ToneKey.self] = newValue }
    }
}

struct ToneReader<Content: View>: View {
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var stillPref: Bool = false
    @ViewBuilder var content: (Tone) -> Content

    var body: some View {
        let tone = Tone(
            reduceTransparency: reduceTransparency,
            increaseContrast: contrast == .increased,
            reduceMotion: reduceMotion,
            stillPref: stillPref
        )
        content(tone)
            .environment(\.tone, tone)
    }
}
