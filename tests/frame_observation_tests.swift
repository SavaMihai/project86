import Foundation
import Combine

@main struct FrameObservationTests {
    @MainActor static func main() {
        precondition(CommandLine.arguments.contains("--demo"), "Use --demo so the test never opens managed disks")
        let model = EmulatorModel()
        var controlUpdates = 0, displayUpdates = 0
        let controls = model.objectWillChange.sink { controlUpdates += 1 }
        let display = model.display.objectWillChange.sink { displayUpdates += 1 }

        for index in 0..<120 {
            var frame = MachineFrame()
            frame.instructions = UInt64(index)
            frame.status = index.isMultiple(of: 2) ? "Running" : "Ready for input"
            model.display.frame = frame
        }
        precondition(displayUpdates == 120, "Screen views must still receive every frame")
        precondition(controlUpdates == 0, "Frame updates must not invalidate the control menu")
        precondition(model.frame.instructions == 119)

        model.paused = true
        precondition(controlUpdates == 1, "Control changes must still refresh the UI")
        model.diskName = "Private observation test"
        precondition(controlUpdates == 2)
        model.worker.setRunning(false)
        withExtendedLifetime((controls, display)) {}
        print("Frame observation passed: 120 display updates, zero control invalidations; controls still publish")
    }
}
