import SwiftUI

struct GamesView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.tone) private var tone
    @State private var exe = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let note = model.undoNote {
                HStack {
                    Text(note).font(.system(size: 14, weight: .semibold)).foregroundStyle(Theme.ink)
                    Spacer()
                    Button("Undo") { model.undoClassify() }
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(Theme.violetLight)
                }
                .padding(12)
                .background(.ultraThinMaterial, in: Capsule())
            }
            pending
            games
            nonGames
        }
        .sheet(isPresented: $model.addGame) {
            NavigationStack {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Type the exe name from Studio PC. Nebula hasn’t sent a list of running processes.")
                        .font(.system(size: 15))
                        .foregroundStyle(Theme.ink2)
                    TextField("game.exe", text: $exe)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .padding(12)
                        .background(Theme.card, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    PrimaryPill(title: "Add as a game", system: "plus") {
                        let name = exe.trimmingCharacters(in: .whitespacesAndNewlines)
                        guard !name.isEmpty else { return }
                        model.reclassify(exe: name, isGame: true)
                        exe = ""
                        model.addGame = false
                    }
                    Spacer()
                }
                .padding(20)
                .background(Theme.ground)
                .navigationTitle("Add a game")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Cancel") { model.addGame = false }
                    }
                }
            }
            .presentationDetents([.medium])
        }
    }

    private var pending: some View {
        let rows = model.studio?.pending ?? []
        return VStack(spacing: 10) {
            ForEach(rows.prefix(3)) { item in
                pendingCard(item)
            }
            if rows.count > 3 {
                Text("+\(rows.count - 3) more")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(tone.tertiary)
            }
        }
    }

    private func pendingCard(_ item: PendingApp) -> some View {
        Tray(radius: 32) {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .center, spacing: 12) {
                    Text("?")
                        .font(.system(size: 19, weight: .semibold))
                        .foregroundStyle(Theme.violetLight)
                        .frame(width: 40, height: 40)
                        .background(Circle().fill(Theme.violet.opacity(0.18)))
                        .overlay(Circle().stroke(Theme.violet.opacity(0.3), lineWidth: 1))
                    VStack(alignment: .leading, spacing: 2) {
                        Eyebrow(text: "New app on Studio PC", color: Theme.violetLight)
                        Text("Is this a game?")
                            .font(.system(size: 19, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                        Text(item.exe)
                            .font(.system(size: 12, design: .monospaced))
                            .foregroundStyle(Theme.ink2)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }
                HStack(spacing: 8) {
                    Button("It’s a game") { model.classify(item, isGame: true, capture: "default") }
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                        .frame(maxWidth: .infinity, minHeight: 46)
                        .background(Capsule().fill(Theme.violet.opacity(0.20)))
                        .overlay(Capsule().stroke(Theme.violet.opacity(0.5), lineWidth: 1))
                    Button("Not a game") { model.classify(item, isGame: false, capture: "default") }
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(Theme.ink2)
                        .frame(maxWidth: .infinity, minHeight: 46)
                        .overlay(Capsule().stroke(Theme.ink.opacity(0.14), lineWidth: 1))
                }
                .buttonStyle(PressScaleStyle())
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                LinearGradient(colors: [Theme.violet.opacity(0.22), Color(red: 16 / 255, green: 13 / 255, blue: 28 / 255).opacity(0.6)], startPoint: .topLeading, endPoint: .bottom)
            )
        }
    }

    private var games: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Games · capture")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                Spacer()
                Text("Steam auto-classifies")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(tone.tertiary)
            }
            VStack(spacing: 0) {
                ForEach(model.studio?.games ?? []) { game in
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(game.name).font(.system(size: 16, weight: .semibold)).foregroundStyle(Theme.ink)
                            Spacer()
                            Text(game.sourceLabel)
                                .font(.system(size: 13))
                                .foregroundStyle(game.source == "prompt" ? Theme.violetLight : tone.tertiary)
                        }
                        NebulaSegments(
                            options: [("default", "Default"), ("record", "Record"), ("buffer", "Buffer"), ("both", "Both")],
                            selection: game.capture
                        ) { model.setCapture(game, $0) }
                    }
                    .padding(.vertical, 10)
                    .swipeActions {
                        Button("Not a game") { model.reclassify(exe: game.name, isGame: false) }
                            .tint(Theme.coral)
                    }
                    Divider().overlay(Theme.ink.opacity(tone.hairline))
                }
            }
        }
    }

    private var nonGames: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Not games · never recorded")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(Theme.ink)
            if (model.studio?.nonGames ?? []).isEmpty {
                Text("Nothing is filed here.")
                    .font(.system(size: 14))
                    .foregroundStyle(tone.tertiary)
            } else {
                FlowChips(items: model.studio?.nonGames ?? []) { item in
                    model.reclassify(exe: item.exe, isGame: true)
                }
            }
        }
    }
}

private struct FlowChips: View {
    var items: [NonGame]
    var mark: (NonGame) -> Void

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 110), spacing: 8)], alignment: .leading, spacing: 8) {
            ForEach(items) { item in
                Text(item.displayName)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                    .padding(.horizontal, 12)
                    .frame(minHeight: 36)
                    .background(Capsule().fill(Theme.card))
                    .contextMenu {
                        Button("Mark as game") { mark(item) }
                    }
            }
        }
    }
}

struct ClassifySheet: View {
    var item: PendingApp
    @EnvironmentObject private var model: AppModel
    @State private var capture: String = "record"

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Capsule().fill(Theme.ink3).frame(width: 36, height: 5).frame(maxWidth: .infinity)
                Text("?")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundStyle(Theme.violetLight)
                    .frame(width: 56, height: 56)
                    .background(Circle().fill(Theme.violet.opacity(0.2)))
                if let seen = item.seenAt {
                    TimelineView(.periodic(from: .now, by: 1)) { context in
                        Eyebrow(text: "New app on Studio PC · \(StudioFormat.relative(seen, now: context.date))", color: Theme.violetLight)
                    }
                }
                Text("Is this a game?")
                    .font(.system(size: 30, weight: .bold))
                    .foregroundStyle(Theme.ink)
                ReadingSurface {
                    VStack(spacing: 0) {
                        row("Process", item.exe)
                        row("Window", item.fullscreen ? "Fullscreen · \(item.width) × \(item.height)" : "Windowed")
                        row("Steam", item.inSteam ? "In library" : "Not in library")
                    }
                    .padding(.horizontal, 14)
                }
                Eyebrow(text: "If it’s a game")
                NebulaSegments(
                    options: [("record", "Record"), ("buffer", "Buffer"), ("both", "Both")],
                    selection: capture
                ) { capture = $0 }
                PrimaryPill(title: "It’s a game — \(verb)", system: "checkmark") {
                    model.classify(item, isGame: true, capture: capture)
                    model.classifyID = nil
                }
                Button("Not a game") {
                    model.classify(item, isGame: false, capture: "default")
                    model.classifyID = nil
                }
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(Theme.ink2)
                .frame(maxWidth: .infinity, minHeight: 44)
                Text("Asked once, remembered forever. Change any call in Games.")
                    .font(.system(size: 13))
                    .foregroundStyle(Theme.ink3)
            }
            .padding(20)
        }
        .background(Theme.ground)
        .onAppear { capture = model.studio?.settings.launchCapture ?? "record" }
    }

    private var verb: String {
        switch capture {
        case "buffer": "buffer it"
        case "both": "record + buffer"
        default: "record it"
        }
    }

    private func row(_ title: String, _ value: String) -> some View {
        HStack {
            Text(title).foregroundStyle(Theme.ink)
            Spacer()
            Text(value)
                .font(.system(size: 13, design: title == "Process" ? .monospaced : .default))
                .foregroundStyle(title == "Steam" && !item.inSteam ? Theme.amber : Theme.ink2)
                .lineLimit(1)
                .truncationMode(.middle)
        }
        .frame(minHeight: 48)
    }
}
