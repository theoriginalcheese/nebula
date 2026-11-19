import SwiftUI
import UIKit

struct ConnectionView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    var done: (() -> Void)?
    var embedded = false

    var body: some View {
        if embedded {
            form
        } else {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Space.sectionGap) {
                    HStack {
                        ZStack {
                            Circle()
                                .fill(Theme.violet.opacity(0.16))
                                .overlay(Circle().stroke(Theme.violet.opacity(0.32), lineWidth: Theme.Stroke.hairline))
                            NebulaMark(size: 28)
                        }
                        .frame(width: Theme.Size.settingsPCBadge, height: Theme.Size.settingsPCBadge)

                        Spacer()

                        if let done = done {
                            Button(action: done) {
                                Text("Done")
                                    .font(Theme.TypeScale.controlSemibold)
                                    .foregroundStyle(Theme.violetLight)
                                    .frame(minWidth: Theme.Size.minHitTarget, minHeight: Theme.Size.minHitTarget)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, Theme.Space.headerInset)

                    form
                }
                .padding(.horizontal, Theme.Space.screenMargin)
                .padding(.top, 24)
                .padding(.bottom, 40)
            }
            .scrollDismissesKeyboard(.interactively)
        }
    }

    private var form: some View {
        VStack(alignment: .leading, spacing: Theme.Space.sectionGap) {
            VStack(alignment: .leading, spacing: 6) {
                Text(embedded ? "Pair another PC" : "Pair with your PC")
                    .font(embedded ? Theme.TypeScale.cardTitleLarge : Theme.TypeScale.largeTitle)
                    .tracking(embedded ? 0 : Theme.TypeScale.largeTitleTracking)
                    .foregroundStyle(Theme.ink)
                Text("Type the address and token from Studio PC. They stay in this phone’s keychain and are not part of the app.")
                    .font(Theme.TypeScale.body)
                    .foregroundStyle(Theme.ink2)
            }
            .padding(.horizontal, embedded ? 0 : Theme.Space.headerInset)

            Tray(role: .tile) {
                ReadingSurface(radius: Theme.Radius.tileCard) {
                    VStack(alignment: .leading, spacing: 0) {
                        fieldRow("Address", text: $model.hostField, secure: false)
                        GroupDivider()
                        fieldRow("Port", text: $model.portField, secure: false, keyboard: .numberPad)
                        GroupDivider()
                        fieldRow("Token", text: $model.tokenField, secure: true)
                    }
                    .padding(.horizontal, 16)
                }
            }

            if model.hasSavedToken {
                Text("A token is already saved on this phone. Leave Token blank to keep it.")
                    .font(Theme.TypeScale.subtitle)
                    .foregroundStyle(tone.tertiary)
                    .padding(.horizontal, Theme.Space.headerInset)
            }

            if let notice = model.notice {
                Text(notice)
                    .font(Theme.TypeScale.rowValue)
                    .foregroundStyle(Theme.coralText)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(
                        RoundedRectangle(cornerRadius: Theme.Radius.field, style: .continuous)
                            .fill(Theme.coral.opacity(0.14))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: Theme.Radius.field, style: .continuous)
                            .stroke(Theme.coral.opacity(0.38), lineWidth: Theme.Stroke.hairline)
                    )
            }

            PrimaryPill(title: "Connect", system: "arrow.right") {
                model.connectFromFields()
            }

            if model.hasSavedToken && !embedded {
                Button(action: model.unpair) {
                    Text("Unpair")
                        .font(Theme.TypeScale.rowTitle)
                        .foregroundStyle(Theme.coralSoft)
                        .frame(maxWidth: .infinity, minHeight: Theme.Size.ghostHeight)
                        .background(
                            RoundedRectangle(cornerRadius: Theme.Radius.ghostPill, style: .continuous)
                                .fill(Theme.coral.opacity(0.12))
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: Theme.Radius.ghostPill, style: .continuous)
                                .stroke(Theme.coral.opacity(0.35), lineWidth: Theme.Stroke.hairline)
                        )
                }
                .buttonStyle(PressScaleStyle())
            }
        }
    }

    private func fieldRow(
        _ title: String,
        text: Binding<String>,
        secure: Bool,
        keyboard: UIKeyboardType = .default
    ) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Eyebrow(text: title)
            Group {
                if secure {
                    SecureField("", text: text)
                } else {
                    TextField("", text: text)
                        .keyboardType(keyboard)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
            }
            .font(Theme.TypeScale.rowLabel)
            .foregroundStyle(Theme.ink)
            .frame(minHeight: 32)
        }
        .padding(.vertical, 10)
    }
}
