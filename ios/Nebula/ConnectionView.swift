import SwiftUI
import UIKit

struct ConnectionView: View {
    @EnvironmentObject private var model: AppModel
    var done: (() -> Void)?
    var embedded = false

    var body: some View {
        if embedded {
            form
        } else {
            NavigationStack {
                form
                    .background(Theme.ground)
                    .toolbar {
                        if done != nil {
                            ToolbarItem(placement: .topBarTrailing) {
                                Button("Done") { done?() }
                                    .foregroundStyle(Theme.ink)
                            }
                        }
                    }
            }
        }
    }

    private var form: some View {
        ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text(embedded ? "This phone" : "Pair with your PC")
                        .font(.system(size: embedded ? 22 : 34, weight: .bold))
                        .foregroundStyle(Theme.ink)
                    Text("Type the address and token from Studio PC. They stay in this phone’s keychain and are not part of the app.")
                        .font(.system(size: 16))
                        .foregroundStyle(Theme.ink2)
                    field("Address", text: $model.hostField, secure: false)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    field("Port", text: $model.portField, secure: false, keyboard: .numberPad)
                    field("Token", text: $model.tokenField, secure: true)
                    if model.hasSavedToken {
                        Text("A token is already saved on this phone. Leave Token blank to keep it.")
                            .font(.system(size: 13))
                            .foregroundStyle(Theme.ink3)
                    }
                    if let notice = model.notice {
                        Text(notice)
                            .font(.system(size: 14))
                            .foregroundStyle(Theme.coral)
                    }
                    Button(action: model.connectFromFields) {
                        Text("Connect")
                            .font(.system(size: 17, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                            .frame(maxWidth: .infinity, minHeight: 56)
                            .background(
                                RoundedRectangle(cornerRadius: 28, style: .continuous)
                                    .fill(Theme.violet.opacity(0.20))
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: 28, style: .continuous)
                                    .stroke(Theme.violet.opacity(0.55), lineWidth: 1)
                            )
                    }
                    .buttonStyle(PressScaleStyle())
                    if model.hasSavedToken {
                        Button(role: .destructive, action: model.unpair) {
                            Text("Unpair")
                                .frame(maxWidth: .infinity, minHeight: 44)
                        }
                    }
                }
                .padding(20)
            }
            .scrollDismissesKeyboard(.interactively)
    }

    private func field(
        _ title: String,
        text: Binding<String>,
        secure: Bool,
        keyboard: UIKeyboardType = .default
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title.uppercased())
                .font(.system(size: 11, weight: .semibold))
                .tracking(1.6)
                .foregroundStyle(Theme.ink3)
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
            .font(.system(size: 16))
            .foregroundStyle(Theme.ink)
            .padding(.horizontal, 14)
            .frame(minHeight: 50)
            .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(Theme.card))
        }
    }
}
