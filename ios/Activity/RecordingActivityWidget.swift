import ActivityKit
import SwiftUI
import WidgetKit

struct RecordingActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: RecordingActivity.self) { context in
            lock(context)
                .activityBackgroundTint(Color(red: 42 / 255, green: 36 / 255, blue: 66 / 255))
                .widgetURL(URL(string: "nebula://now"))
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Text(context.state.game)
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(Color(red: 245 / 255, green: 243 / 255, blue: 255 / 255))
                }
                DynamicIslandExpandedRegion(.trailing) {
                    clock(context.state)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    HStack {
                        Text(context.state.state == "bufferOnly" ? "BUFFER" : "REC")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(Color(red: 255 / 255, green: 232 / 255, blue: 188 / 255))
                        Spacer()
                        Link(destination: URL(string: "nebula://now/pause")!) {
                            Text(context.state.state == "paused" ? "Resume" : "Pause")
                        }
                        Link(destination: URL(string: "nebula://now/stop")!) {
                            Text("Stop")
                        }
                    }
                }
            } compactLeading: {
                Circle().fill(Color(red: 139 / 255, green: 124 / 255, blue: 246 / 255)).frame(width: 12, height: 12)
            } compactTrailing: {
                clock(context.state).font(.system(size: 12, weight: .medium))
            } minimal: {
                Circle().fill(Color(red: 255 / 255, green: 232 / 255, blue: 188 / 255)).frame(width: 8, height: 8)
            }
        }
    }

    private func lock(_ context: ActivityViewContext<RecordingActivity>) -> some View {
        HStack(spacing: 12) {
            Circle().fill(Color(red: 139 / 255, green: 124 / 255, blue: 246 / 255)).frame(width: 28, height: 28)
            VStack(alignment: .leading, spacing: 2) {
                Text("Nebula is recording")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Color(red: 245 / 255, green: 243 / 255, blue: 255 / 255))
                Text("\(context.state.game) · \(context.state.output)")
                    .font(.system(size: 12))
                    .foregroundStyle(Color(red: 201 / 255, green: 196 / 255, blue: 230 / 255))
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 4) {
                Text(context.state.state == "bufferOnly" ? "BUFFER" : "REC")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Color(red: 255 / 255, green: 232 / 255, blue: 188 / 255))
                clock(context.state)
                    .font(.system(size: 28, weight: .medium))
            }
        }
        .padding(14)
    }

    @ViewBuilder private func clock(_ state: RecordingActivity.ContentState) -> some View {
        if let frozen = state.frozen {
            Text(frozen)
                .monospacedDigit()
                .foregroundStyle(Color(red: 201 / 255, green: 196 / 255, blue: 230 / 255))
        } else {
            Text(timerInterval: state.clockStart ... Date.distantFuture, countsDown: false)
                .monospacedDigit()
                .foregroundStyle(Color(red: 255 / 255, green: 232 / 255, blue: 188 / 255))
        }
    }
}

@main
struct NebulaActivityBundle: WidgetBundle {
    var body: some Widget {
        RecordingActivityWidget()
    }
}
