import SwiftUI
import UniformTypeIdentifiers

@main struct Project86App: App {
    @StateObject private var model = EmulatorModel()
    @Environment(\.scenePhase) private var scenePhase
    var body: some Scene {
        WindowGroup {
            ComputerView(model: model)
                .onChange(of: scenePhase) { _, phase in
                    if phase != .active { model.worker.setRunning(false); model.worker.flushSynchronously() }
                    else if !model.paused { model.worker.setRunning(true) }
                }
                #if os(macOS)
                .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in model.worker.flushSynchronously() }
                #endif
        }
        #if os(macOS)
        .defaultSize(width: 1000, height: 740)
        #endif
    }
}

struct ComputerView: View {
    @ObservedObject var model: EmulatorModel
    @State private var importing = false
    @State private var importingHardDisk = false
    @State private var diagnostics = false
    @State private var keyboard = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Image(systemName: "desktopcomputer").font(.title2)
                VStack(alignment: .leading, spacing: 3) {
                    Text("Project86").font(.headline)
                    Text(model.diskName).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                MachineStatusView(display: model.display, paused: model.paused)
            }.padding(16)
            Divider()
            MachineScreenView(display: model.display, worker: model.worker, keyboardRequested: keyboard)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            Divider()
            HStack(spacing: 16) {
                Button { importingHardDisk = false; importing = true } label: { Label("Open floppy", systemImage: "externaldrive") }
                Button { model.togglePause() } label: { Image(systemName: model.paused ? "play.fill" : "pause.fill") }.help("Pause or resume")
                Button { model.toggleSound() } label: { Image(systemName: model.sound ? "speaker.wave.2" : "speaker.slash") }.help("PC speaker, AdLib and Sound Blaster")
                #if os(iOS)
                Button { keyboard.toggle() } label: { Image(systemName: "keyboard") }
                #endif
                Spacer()
                CPUSpeedControl(selection: Binding(get: { model.cpuSpeed }, set: { model.setCPUSpeed($0) }))
                Menu {
                    Button("Boot rebuilt MS-DOS (new floppy)") { model.bootBundledDOS() }
                    Button("Open previous boot floppy") { model.openPreviousFloppy() }
                        .disabled(UserDefaults.standard.string(forKey: "previousWorkingDisk") == nil)
                    Button("Attach hard disk and reboot…") { importingHardDisk = true; importing = true }
                    Button("Reboot computer") { model.reboot() }
                    Button("Reopen saved disk") { model.reopenDisk() }
                    Button("CPU demonstration") { model.demo() }
                    Toggle("Show diagnostics", isOn: $diagnostics)
                } label: { Image(systemName: "ellipsis.circle") }
            }.buttonStyle(.borderless).padding(16)
            if diagnostics {
                MachineDiagnosticsView(display: model.display)
            }
        }
        .background(Color.primary.opacity(0.025))
        #if os(macOS)
        .frame(minWidth: 720, minHeight: 520)
        #endif
        .fileImporter(isPresented: $importing, allowedContentTypes: [.data], allowsMultipleSelection: false) { result in
            switch result { case .success(let urls): if let url = urls.first { model.importDisk(url, hard: importingHardDisk) }
            case .failure(let error): model.error = error.localizedDescription }
        }
        .alert("Project86", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) {
            Button("OK") { model.error = nil }
        } message: { Text(model.error ?? "") }
    }
}

// Observe frames at the leaf views, not at the window/control-menu level.
private struct MachineScreenView: View {
    @ObservedObject var display: MachineDisplayState
    let worker: EmulationWorker
    let keyboardRequested: Bool

    var body: some View {
        EmulatorDisplay(frame: display.frame, worker: worker, keyboardRequested: keyboardRequested)
            .accessibilityLabel("DOS computer display. Click to type.")
    }
}

private struct MachineStatusView: View {
    @ObservedObject var display: MachineDisplayState
    let paused: Bool

    var body: some View {
        Label(display.frame.status, systemImage: paused ? "pause.circle" : "circle.fill")
            .font(.caption).foregroundStyle(display.frame.status == "Stopped" ? .red : .secondary)
    }
}

private struct MachineDiagnosticsView: View {
    @ObservedObject var display: MachineDisplayState

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(display.frame.registers)
            Text("\(display.frame.instructions.formatted()) instructions · ARM-native interpreter · no JIT")
            if !display.frame.diagnostic.isEmpty { Text(display.frame.diagnostic).foregroundStyle(.orange) }
        }.font(.system(.caption, design: .monospaced))
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding([.horizontal,.bottom],16)
    }
}
