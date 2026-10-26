import Foundation

struct MousePacket: Equatable {
    let dx: Int32
    let dy: Int32
    let buttons: UInt8
}

/// Owned by the emulation queue. Retain subpixel input and combine motion into
/// one update per tick, while delivering button transitions in their original order.
struct MouseInput {
    private var x = 0.0, y = 0.0
    private var buttons: UInt8 = 0

    mutating func add(dx: Double, dy: Double, buttons: UInt8) -> [MousePacket] {
        var packets: [MousePacket] = []
        if buttons != self.buttons {
            if let packet = flush() { packets.append(packet) }
            self.buttons = buttons
            accumulate(dx: dx, dy: dy)
            packets.append(take())
        } else { accumulate(dx: dx, dy: dy) }
        return packets
    }

    mutating func flush() -> MousePacket? {
        guard abs(x) >= 1 || abs(y) >= 1 else { return nil }
        return take()
    }

    mutating func reset() { self = MouseInput() }

    private mutating func accumulate(dx: Double, dy: Double) {
        if dx.isFinite { x = min(Double(Int32.max), max(Double(Int32.min), x + dx)) }
        if dy.isFinite { y = min(Double(Int32.max), max(Double(Int32.min), y + dy)) }
    }

    private mutating func take() -> MousePacket {
        let dx = Int32(x), dy = Int32(y)
        x -= Double(dx); y -= Double(dy)
        return MousePacket(dx: dx, dy: dy, buttons: buttons)
    }
}
