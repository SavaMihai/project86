import Foundation
import SwiftUI
import AVFoundation

struct MachineFrame: Sendable {
    var text = Data(repeating: 0, count: 4000)
    var pixels = Data()
    var width = 0
    var height = 0
    var instructions: UInt64 = 0
    var registers = ""
    var status = "Ready"
    var diagnostic = ""
    var storageError: String?
    var accessibilityText: String {
        let bytes = [UInt8](text)
        return stride(from: 0, to: min(bytes.count,4000), by: 160).map { row in
            String(bytes: stride(from: row, to: min(row+160,bytes.count), by: 2).map { bytes[$0] >= 32 && bytes[$0] < 127 ? bytes[$0] : 32 }, encoding: .ascii) ?? ""
        }.joined(separator: "\n")
    }
}

/// The serial queue is the sole owner of the C machine, including all reads.
final class EmulationWorker: @unchecked Sendable {
    private let queue = DispatchQueue(label: "dev.project86.machine", qos: .userInitiated)
    private let machine: OpaquePointer
    private var timer: DispatchSourceTimer?
    private var running = true
    private var diskURL: URL?
    private var audioEngine: AVAudioEngine?
    private var audioPlayer: AVAudioPlayerNode?
    private var soundEnabled = false
    private var pendingPaste: [UInt8] = []
    private var mouseInput = MouseInput()
    private var clockRemainder: UInt64 = 0
    private static let framesPerSecond: UInt64 = 60
    private var queuedAudio = 0
    private var audioGeneration = 0
    private var storageError: String?
    private var lastCheckpoint = Date()
    private var onFrame: ((MachineFrame) -> Void)?

    func setFrameHandler(_ handler: @escaping (MachineFrame) -> Void) {
        queue.async { [weak self] in self?.onFrame = handler }
    }

    init() {
        guard let machine = p86_create() else { fatalError("Cannot allocate emulator") }
        self.machine = machine
        p86_set_cpu286(machine, 1)
        p86_set_cpu_speed(machine, 8)
        queue.async { [weak self] in
            guard let self else { return }
            p86_load_demo(self.machine)
            let timer = DispatchSource.makeTimerSource(queue: self.queue)
            timer.schedule(deadline: .now(), repeating: .nanoseconds(16_666_667))
            timer.setEventHandler { [weak self] in self?.tick() }
            self.timer = timer
            timer.resume()
        }
    }

    deinit {
        timer?.cancel()
        audioPlayer?.stop()
        audioEngine?.stop()
        p86_destroy(machine)
    }

    func setRunning(_ enabled: Bool) {
        queue.async { [weak self] in
            guard let self else { return }
            self.running = enabled
            if !enabled {
                self.mouseInput.reset(); p86_mouse(self.machine, 0, 0, 0)
                self.checkpoint(); self.audioPlayer?.stop(); self.queuedAudio = 0; self.audioGeneration += 1
            }
            else if self.soundEnabled { self.audioPlayer?.play() }
            self.publish()
        }
    }

    func flushSynchronously() { queue.sync { checkpoint(); publish() } }

    private func checkpoint() {
        if p86_flush_disks(machine) == 0 {
            storageError = "The disk could not be saved. Keep this window open and free disk space, then pause again to retry."
            running = false
        } else { storageError = nil }
        lastCheckpoint = Date()
    }

    func demo() {
        queue.async { [weak self] in
            guard let self else { return }
            p86_load_demo(self.machine); self.mouseInput.reset(); self.diskURL = nil; self.running = true; self.publish()
        }
    }

    func reboot() {
        queue.async { [weak self] in
            guard let self else { return }
            if self.diskURL != nil { _ = p86_boot(self.machine) } else { p86_load_demo(self.machine) }
            self.mouseInput.reset()
            self.running = true; self.publish()
        }
    }

    func importDisk(_ source: URL, hard: Bool = false, completion: @escaping (Result<String, Error>) -> Void) {
        queue.async { [weak self] in
            guard let self else { return }
            let scoped = source.startAccessingSecurityScopedResource()
            defer { if scoped { source.stopAccessingSecurityScopedResource() } }
            do {
                let manager = FileManager.default
                let root = try manager.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
                    .appendingPathComponent("Project86/Disks", isDirectory: true)
                let directory = root.appendingPathComponent(UUID().uuidString, isDirectory: true)
                try manager.createDirectory(at: directory, withIntermediateDirectories: true)
                let original = directory.appendingPathComponent("original.ima")
                let working = directory.appendingPathComponent("working.ima")
                try manager.copyItem(at: source, to: original)
                try manager.copyItem(at: original, to: working)
                // A fresh bundled floppy still uses the user's saved C: disk.
                if !hard, let saved = UserDefaults.standard.string(forKey: "workingHardDisk") {
                    guard p86_attach_hard_disk(self.machine, saved, 1) != 0 else {
                        throw NSError(domain: "Project86", code: 4, userInfo: [NSLocalizedDescriptionKey: self.snapshot().diagnostic])
                    }
                }
                let attached = hard ? p86_attach_hard_disk(self.machine, working.path, 1) : p86_attach_floppy(self.machine, working.path, 1)
                guard attached != 0, p86_boot(self.machine) != 0 else {
                    throw NSError(domain: "Project86", code: 1, userInfo: [NSLocalizedDescriptionKey: self.snapshot().diagnostic])
                }
                if !hard { self.diskURL = working }
                self.mouseInput.reset()
                self.running = true
                if !hard, let previous = UserDefaults.standard.string(forKey: "workingDisk") {
                    UserDefaults.standard.set(previous, forKey: "previousWorkingDisk")
                }
                UserDefaults.standard.set(working.path, forKey: hard ? "workingHardDisk" : "workingDisk")
                self.publish()
                completion(.success(source.lastPathComponent))
            } catch { completion(.failure(error)) }
        }
    }

    func reopenDisk(completion: @escaping (Result<String, Error>) -> Void) {
        queue.async { [weak self] in
            guard let self else { return }
            guard let path = UserDefaults.standard.string(forKey: "workingDisk") else {
                completion(.failure(NSError(domain: "Project86", code: 2, userInfo: [NSLocalizedDescriptionKey: "Import a boot floppy first."]))); return
            }
            if let hard = UserDefaults.standard.string(forKey: "workingHardDisk") {
                guard p86_attach_hard_disk(self.machine, hard, 1) != 0 else {
                    completion(.failure(NSError(domain: "Project86", code: 4, userInfo: [NSLocalizedDescriptionKey: self.snapshot().diagnostic]))); return
                }
            }
            guard p86_attach_floppy(self.machine, path, 1) != 0, p86_boot(self.machine) != 0 else {
                completion(.failure(NSError(domain: "Project86", code: 3, userInfo: [NSLocalizedDescriptionKey: self.snapshot().diagnostic]))); return
            }
            self.mouseInput.reset()
            self.diskURL = URL(fileURLWithPath: path); self.running = true; self.publish(); completion(.success("Saved working disk"))
        }
    }

    func paste(_ text: String) {
        queue.async { [weak self] in self?.pendingPaste += text.utf8.filter { $0 < 128 }.map { $0 == 10 ? 13 : $0 } }
    }

    func key(_ ascii: UInt8, scan: UInt8 = 0, pressed: Bool = true) {
        queue.async { [weak self] in
            guard let self else { return }
            p86_key(self.machine, ascii, scan, pressed ? 1 : 0)
        }
    }

    func mouse(dx: Double, dy: Double, buttons: UInt8) {
        queue.async { [weak self] in
            guard let self else { return }
            guard self.running else { return }
            for packet in self.mouseInput.add(dx: dx, dy: dy, buttons: buttons) {
                p86_mouse(self.machine, packet.dx, packet.dy, packet.buttons)
            }
        }
    }

    func setCPUSpeed(_ multiplier: Int) {
        queue.async { [weak self] in
            guard let self else { return }
            p86_set_cpu_speed(self.machine, UInt32(clamping: multiplier))
        }
    }

    func sound(_ enabled: Bool) {
        queue.async { [weak self] in
            guard let self else { return }
            self.soundEnabled = enabled
            p86_enable_audio(self.machine, enabled ? 1 : 0)
            if !enabled { self.audioPlayer?.stop(); self.queuedAudio = 0; self.audioGeneration += 1; return }
            do {
                if self.audioEngine == nil {
                    #if os(iOS)
                    try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
                    try AVAudioSession.sharedInstance().setActive(true)
                    #endif
                    let engine = AVAudioEngine(), player = AVAudioPlayerNode()
                    engine.attach(player)
                    engine.connect(player, to: engine.mainMixerNode, format: AVAudioFormat(standardFormatWithSampleRate: 48000, channels: 1))
                    self.audioEngine = engine; self.audioPlayer = player
                }
                try self.audioEngine?.start(); self.audioPlayer?.play()
            } catch {
                self.soundEnabled = false
                var frame = self.snapshot(); frame.diagnostic = "Audio: \(error.localizedDescription)"; self.onFrame?(frame)
            }
        }
    }

    private func tick() {
        if running {
            // Bounded slices keep input and lifecycle operations responsive.
            if !pendingPaste.isEmpty {
                // Paste one character per slice to respect the DOS BIOS ring buffer.
                let head = UInt16(p86_read_memory(machine, 0x41a)) | UInt16(p86_read_memory(machine, 0x41b)) << 8
                let tail = UInt16(p86_read_memory(machine, 0x41c)) | UInt16(p86_read_memory(machine, 0x41d)) << 8
                let next = tail + 2 >= 0x3e ? 0x1e : tail + 2
                if next != head { let byte = pendingPaste.removeFirst(); p86_key(machine, byte, byte == 13 ? 0x1c : 0, 1) }
            }
            if let packet = mouseInput.flush() { p86_mouse(machine, packet.dx, packet.dy, packet.buttons) }
            // More CPU work per device tick, not a faster PIT/audio clock.
            clockRemainder += 4_772_728
            let budget = clockRemainder / Self.framesPerSecond
            clockRemainder %= Self.framesPerSecond
            _ = p86_run_cycles(machine, budget)
            if soundEnabled, queuedAudio < 3, let format = AVAudioFormat(standardFormatWithSampleRate: 48000, channels: 1),
               let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 800), let samples = buffer.floatChannelData?[0] {
                buffer.frameLength = 800; _ = p86_read_audio(machine, samples, 800)
                queuedAudio += 1
                let generation = audioGeneration
                audioPlayer?.scheduleBuffer(buffer, completionHandler: { [weak self] in
                    self?.queue.async { [weak self] in if let self, self.audioGeneration == generation { self.queuedAudio = max(0, self.queuedAudio - 1) } }
                })
            }
        }
        if Date().timeIntervalSince(lastCheckpoint) >= 5 { checkpoint() }
        publish()
    }

    private func snapshot() -> MachineFrame {
        var raw = P86Snapshot(); p86_get_snapshot(machine, &raw)
        var frame = MachineFrame()
        frame.text.withUnsafeMutableBytes { bytes in _ = p86_copy_text(machine, bytes.bindMemory(to: UInt8.self).baseAddress, bytes.count) }
        var width: UInt32 = 0, height: UInt32 = 0
        let count = p86_copy_pixels(machine, nil, 0, &width, &height)
        if count > 0 {
            frame.pixels = Data(count: count * 4)
            frame.pixels.withUnsafeMutableBytes { bytes in _ = p86_copy_pixels(machine, bytes.bindMemory(to: UInt32.self).baseAddress, count, &width, &height) }
            frame.width = Int(width); frame.height = Int(height)
        }
        frame.instructions = raw.instructions
        frame.storageError = storageError
        frame.status = storageError != nil ? "Disk save failed" : raw.status == P86_FAULT ? "Stopped" : !running ? "Paused" : raw.status == P86_WAITING_KEY ? "Ready for input" : "Running"
        frame.registers = String(format: "CS:IP %04X:%04X  AX %04X  BX %04X  CX %04X  DX %04X", Int(raw.cpu.cs), Int(raw.cpu.ip), Int(raw.cpu.ax), Int(raw.cpu.bx), Int(raw.cpu.cx), Int(raw.cpu.dx))
        frame.diagnostic = withUnsafeBytes(of: raw.message) { bytes in String(decoding: bytes.prefix { $0 != 0 }, as: UTF8.self) }
        return frame
    }

    private func publish() { onFrame?(snapshot()) }
}

/// Only display/status/diagnostic views observe this high-frequency stream.
/// Publishing frames on the control model invalidates open SwiftUI menus.
@MainActor final class MachineDisplayState: ObservableObject {
    @Published var frame = MachineFrame()
}

@MainActor final class EmulatorModel: ObservableObject {
    let display = MachineDisplayState()
    var frame: MachineFrame { display.frame }
    @Published var diskName = "CPU demonstration"
    @Published var paused = false
    @Published var sound = false
    @Published private(set) var cpuSpeed: Int = {
        let saved = UserDefaults.standard.integer(forKey: "cpuSpeed")
        return [1, 4, 8, 16].contains(saved) ? saved : 8
    }()
    @Published var error: String?
    let worker = EmulationWorker()

    init() {
        worker.setCPUSpeed(cpuSpeed)
        worker.setFrameHandler { [weak self] frame in DispatchQueue.main.async {
            if let message = frame.storageError, self?.frame.storageError != message { self?.error = message }
            self?.display.frame = frame
        } }
        if !ProcessInfo.processInfo.arguments.contains("--demo") {
            if !ProcessInfo.processInfo.arguments.contains("--fresh-dos"), let path = UserDefaults.standard.string(forKey: "workingDisk"), FileManager.default.fileExists(atPath: path) { reopenDisk() }
            else { bootBundledDOS() }
        }
        let arguments = ProcessInfo.processInfo.arguments
        if let index = arguments.firstIndex(of: "--hard-disk"), arguments.indices.contains(index+1) {
            importDisk(URL(fileURLWithPath: arguments[index+1]), hard: true)
        }
    }

    func setCPUSpeed(_ multiplier: Int) {
        guard [1, 4, 8, 16].contains(multiplier) else { return }
        cpuSpeed = multiplier
        UserDefaults.standard.set(multiplier, forKey: "cpuSpeed")
        worker.setCPUSpeed(multiplier)
    }

    func importDisk(_ url: URL, hard: Bool = false) { worker.importDisk(url, hard: hard) { [weak self] result in self?.accept(result) } }
    func bootBundledDOS() {
        guard let url = Bundle.main.url(forResource: "project86", withExtension: "ima") else {
            error = "The rebuilt DOS boot image is missing. Rebuild the app with make mac or make ios."; return
        }
        importDisk(url)
    }
    func openPreviousFloppy() {
        guard let path = UserDefaults.standard.string(forKey: "previousWorkingDisk") else {
            error = "There is no previous boot floppy to reopen."; return
        }
        importDisk(URL(fileURLWithPath: path))
    }
    func reopenDisk() { worker.reopenDisk { [weak self] result in self?.accept(result) } }
    nonisolated private func accept(_ result: Result<String, Error>) {
        DispatchQueue.main.async { [weak self] in
            switch result { case .success(let name): self?.diskName = name; self?.paused = false
            case .failure(let error): self?.error = error.localizedDescription }
        }
    }
    func togglePause() { paused.toggle(); worker.setRunning(!paused) }
    func toggleSound() { sound.toggle(); worker.sound(sound) }
    func demo() { worker.demo(); diskName = "CPU demonstration"; paused = false }
    func reboot() { worker.reboot(); paused = false }
}
