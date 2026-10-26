import SwiftUI
#if os(macOS)
import AppKit
#endif

struct CPUSpeedControl: View {
    @Binding var selection: Int

    var body: some View {
        HStack(spacing: 8) {
            Text("CPU").font(.caption).foregroundStyle(.secondary)
            #if os(macOS)
            NativeCPUSpeedSelector(selection: $selection)
                .frame(width: 200, height: 24)
            #else
            Picker("CPU speed", selection: $selection) {
                Text("1×").tag(1)
                Text("4×").tag(4)
                Text("8×").tag(8)
                Text("16×").tag(16)
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(width: 200)
            .accessibilityIdentifier("cpu-speed-selector")
            #endif
        }
        .help("CPU speed: 1× compatibility, 8× default")
    }
}

#if os(macOS)
private struct NativeCPUSpeedSelector: NSViewRepresentable {
    @Binding var selection: Int
    private static let speeds = [1, 4, 8, 16]

    final class Coordinator: NSObject {
        var selection: Binding<Int>
        init(selection: Binding<Int>) { self.selection = selection }

        @objc func choose(_ sender: NSSegmentedControl) {
            guard NativeCPUSpeedSelector.speeds.indices.contains(sender.selectedSegment) else { return }
            selection.wrappedValue = NativeCPUSpeedSelector.speeds[sender.selectedSegment]
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator(selection: $selection) }

    func makeNSView(context: Context) -> NSSegmentedControl {
        let control = NSSegmentedControl(labels: Self.speeds.map { "\($0)×" },
                                         trackingMode: .selectOne,
                                         target: context.coordinator,
                                         action: #selector(Coordinator.choose(_:)))
        control.segmentStyle = .rounded
        control.setAccessibilityLabel("CPU speed")
        control.setAccessibilityIdentifier("cpu-speed-selector")
        control.selectedSegment = Self.speeds.firstIndex(of: selection) ?? 2
        return control
    }

    func updateNSView(_ control: NSSegmentedControl, context: Context) {
        context.coordinator.selection = $selection
        control.selectedSegment = Self.speeds.firstIndex(of: selection) ?? 2
    }
}
#endif
