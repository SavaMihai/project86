import Foundation

@main struct MouseInputTests {
    static func main() {
        var input = MouseInput()
        for _ in 0..<1_000 { precondition(input.add(dx: 0.25, dy: -0.125, buttons: 0).isEmpty) }
        precondition(input.flush() == MousePacket(dx: 250, dy: -125, buttons: 0))
        precondition(input.flush() == nil)
        precondition(input.add(dx: 0.5, dy: 0, buttons: 0).isEmpty)
        precondition(input.flush() == nil)
        precondition(input.add(dx: 0.5, dy: 0, buttons: 0).isEmpty)
        precondition(input.flush() == MousePacket(dx: 1, dy: 0, buttons: 0))
        // Movement before a click is delivered with the previous button state;
        // down/up in the same tick must remain distinct packets.
        _ = input.add(dx: 5, dy: 3, buttons: 0)
        precondition(input.add(dx: 2, dy: 0, buttons: 1) == [
            MousePacket(dx: 5, dy: 3, buttons: 0), MousePacket(dx: 2, dy: 0, buttons: 1)])
        precondition(input.add(dx: 0, dy: 0, buttons: 0) == [MousePacket(dx: 0, dy: 0, buttons: 0)])
        precondition(input.flush() == nil)
        _ = input.add(dx: -0.75, dy: 0, buttons: 0)
        input.reset()
        _ = input.add(dx: -0.5, dy: 0, buttons: 0)
        precondition(input.flush() == nil)
        _ = input.add(dx: -0.5, dy: 0, buttons: 0)
        precondition(input.flush() == MousePacket(dx: -1, dy: 0, buttons: 0))
        _ = input.add(dx: .infinity, dy: .nan, buttons: 0)
        precondition(input.flush() == nil)
        _ = input.add(dx: Double(Int32.max) * 2, dy: Double(Int32.min) * 2, buttons: 0)
        precondition(input.flush() == MousePacket(dx: Int32.max, dy: Int32.min, buttons: 0))
        print("Mouse input tests passed: fractional movement, coalescing, button order, reset and bounds")
    }
}
