import AppKit
import SwiftUI

@main struct CPUSpeedControlTests {
    @MainActor static func main() {
        let application = NSApplication.shared
        application.setActivationPolicy(.prohibited)
        var selected = 8
        let view = NSHostingView(rootView: CPUSpeedControl(selection: Binding(get: { selected }, set: { selected = $0 })))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 260, height: 44),
                              styleMask: .borderless, backing: .buffered, defer: false)
        window.contentView = view
        view.frame = NSRect(x: 0, y: 0, width: 260, height: 44)
        view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.1))
        func findControl(_ parent: NSView) -> NSSegmentedControl? {
            if let control = parent as? NSSegmentedControl { return control }
            return parent.subviews.lazy.compactMap { findControl($0) }.first
        }
        guard let control = findControl(view) else { fatalError("Native CPU selector not created") }
        precondition(control.segmentCount == 4 && control.selectedSegment == 2)
        for index in [0, 1, 3, 2] {
            control.selectedSegment = index
            precondition(control.sendAction(control.action, to: control.target))
            RunLoop.main.run(until: Date().addingTimeInterval(0.05))
            precondition(selected == [1, 4, 8, 16][index], "Native action chose the wrong CPU multiplier")
        }
        print("Native CPU selector passed: four segments, default 8x, all action-to-binding mappings")
        window.orderOut(nil)
    }
}
