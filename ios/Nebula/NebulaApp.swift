import SwiftUI

@main
struct NebulaApp: App {
    @StateObject private var model = AppModel()
    @Environment(\.scenePhase) private var scene

    var body: some Scene {
        WindowGroup {
            ToneReader { _ in
                RootView()
            }
            .environmentObject(model)
            .preferredColorScheme(.dark)
            .onOpenURL { model.open($0) }
            .onChange(of: scene) { _, phase in
                model.setActive(phase == .active)
            }
        }
    }
}

struct RootView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        Group {
            if model.link == .unpaired {
                ZStack {
                    BackgroundView(kind: model.prefs.background, seed: model.prefs.planetSeed, live: false)
                    ConnectionView(done: nil)
                }
            } else {
                ShellView()
            }
        }
        .background(Theme.ground.ignoresSafeArea())
    }
}
