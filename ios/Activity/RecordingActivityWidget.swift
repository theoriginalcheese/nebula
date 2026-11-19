import ActivityKit
import SwiftUI
import WidgetKit

struct RecordingActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: RecordingActivity.self) { context in
            lockCard(context)
                .activityBackgroundTint(Theme.lock)
                .widgetURL(URL(string: "nebula://now"))
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Text(context.state.game)
                        .font(Theme.TypeScale.controlSemibold)
                        .foregroundStyle(Theme.ink)
                        .lineLimit(1)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    clockText(context.state)
                        .font(Theme.TypeScale.cardTitle)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    HStack(spacing: Theme.Space.bentoGap) {
                        HStack(spacing: 5) {
                            Circle()
                                .fill(context.state.state == "paused" ? Theme.ink2 : Theme.gold)
                                .frame(width: 6, height: 6)
                            Text(chipTitle(context.state.state))
                                .font(Theme.TypeScale.eyebrow)
                                .tracking(Theme.TypeScale.eyebrowTracking)
                                .foregroundStyle(context.state.state == "paused" ? Theme.ink2 : Theme.gold)
                        }
                        Text(context.state.output.isEmpty ? "—" : context.state.output)
                            .font(Theme.TypeScale.caption)
                            .foregroundStyle(Theme.ink2)
                            .lineLimit(1)
                        Spacer()
                        Link(destination: URL(string: "nebula://now/pause")!) {
                            Text(context.state.state == "paused" ? "Resume" : "Pause")
                                .font(Theme.TypeScale.captionSemibold)
                                .foregroundStyle(Theme.ink)
                                .padding(.horizontal, 12)
                                .frame(height: 28)
                                .background(Capsule().fill(Theme.ink.opacity(0.12)))
                        }
                        Link(destination: URL(string: "nebula://now/stop")!) {
                            Text("Stop")
                                .font(Theme.TypeScale.captionSemibold)
                                .foregroundStyle(Theme.coralText)
                                .padding(.horizontal, 12)
                                .frame(height: 28)
                                .background(Capsule().fill(Theme.coral.opacity(0.20)))
                                .overlay(Capsule().stroke(Theme.coral.opacity(0.45), lineWidth: Theme.Stroke.hairline))
                        }
                    }
                }
            } compactLeading: {
                Circle()
                    .fill(Theme.violet)
                    .frame(width: 10, height: 10)
            } compactTrailing: {
                clockText(context.state)
                    .font(Theme.TypeScale.captionTabular)
            } minimal: {
                Circle()
                    .fill(Theme.gold)
                    .frame(width: 8, height: 8)
            }
        }
    }

    /// Spec §9.11: solid card, Nebula mark, "Nebula is recording", REC chip,
    /// the clock at 58, game · output, Pause and Stop. Pause and Stop are
    /// `nebula://` links: they open the app, which then sends the command.
    /// A button that acts without opening Nebula needs an App Intent run by
    /// the app process, which this extension does not set up, so these are
    /// deliberately not presented as background actions.
    private func lockCard(_ context: ActivityViewContext<RecordingActivity>) -> some View {
        let paused = context.state.state == "paused"
        return VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: Theme.Space.bentoGap) {
                NebulaMark(size: 26)
                Text("Nebula is recording")
                    .font(Theme.TypeScale.segment)
                    .foregroundStyle(Theme.ink)
                    .lineLimit(1)
                Spacer(minLength: 6)
                HStack(spacing: 5) {
                    Circle()
                        .fill(paused ? Theme.ink2 : Theme.gold)
                        .frame(width: 6, height: 6)
                    Text(chipTitle(context.state.state))
                        .font(Theme.TypeScale.eyebrow)
                        .tracking(Theme.TypeScale.eyebrowTracking)
                        .foregroundStyle(paused ? Theme.ink2 : Theme.gold)
                }
            }

            // 58 pt is the design size; it scales down only if a long
            // h:mm:ss would not fit the card width.
            clockText(context.state)
                .font(Theme.TypeScale.lockClock)
                .lineLimit(1)
                .minimumScaleFactor(0.5)
                .frame(maxWidth: .infinity, alignment: .leading)

            HStack(spacing: Theme.Space.bentoGap) {
                Text("\(context.state.game) · \(context.state.output.isEmpty ? "—" : context.state.output)")
                    .font(Theme.TypeScale.caption)
                    .foregroundStyle(Theme.ink2)
                    .lineLimit(1)
                Spacer(minLength: 6)
                Link(destination: URL(string: "nebula://now/pause")!) {
                    Text(paused ? "Resume" : "Pause")
                        .font(Theme.TypeScale.captionSemibold)
                        .foregroundStyle(Theme.ink)
                        .padding(.horizontal, 12)
                        .frame(height: 28)
                        .background(Capsule().fill(Theme.ink.opacity(0.12)))
                }
                Link(destination: URL(string: "nebula://now/stop")!) {
                    Text("Stop")
                        .font(Theme.TypeScale.captionSemibold)
                        .foregroundStyle(Theme.coralText)
                        .padding(.horizontal, 12)
                        .frame(height: 28)
                        .background(Capsule().fill(Theme.coral.opacity(0.20)))
                        .overlay(Capsule().stroke(Theme.coral.opacity(0.45), lineWidth: Theme.Stroke.hairline))
                }
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }

    private func chipTitle(_ state: String) -> String {
        switch state {
        case "paused":
            return "PAUSED"
        case "bufferOnly":
            return "BUFFER"
        default:
            return "REC"
        }
    }

    @ViewBuilder private func clockText(_ state: RecordingActivity.ContentState) -> some View {
        if let frozen = state.frozen {
            Text(frozen)
                .monospacedDigit()
                .foregroundStyle(Theme.ink2)
        } else {
            Text(timerInterval: state.clockStart ... Date.distantFuture, countsDown: false)
                .monospacedDigit()
                .foregroundStyle(Theme.gold)
        }
    }
}

@main
struct NebulaActivityBundle: WidgetBundle {
    var body: some Widget {
        RecordingActivityWidget()
    }
}
