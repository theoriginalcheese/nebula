import ActivityKit
import Foundation

struct RecordingActivity: ActivityAttributes {
    struct ContentState: Codable, Hashable {
        var state: String
        var game: String
        var output: String
        var clockStart: Date
        var frozen: String?
    }

    var name: String
}
