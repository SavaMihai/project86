import SwiftUI
import MetalKit
import CoreText
#if os(macOS)
import AppKit
#else
import UIKit
#endif

/// The display font comes from the host OS. No PC ROM or emulator font is copied.
final class TextRasterizer {
    private let width = 8, height = 16
    private var glyphs = [[UInt8]]()
    private let colors: [UInt32] = [0x000000,0xaa0000,0x00aa00,0xaaaa00,0x0000aa,0xaa00aa,0x0055aa,0xaaaaaa,
                                    0x555555,0xff5555,0x55ff55,0xffff55,0x5555ff,0xff55ff,0x55ffff,0xffffff]
    init() {
        let font = CTFontCreateWithName("Menlo" as CFString, 13, nil)
        let encoding = CFStringConvertEncodingToNSStringEncoding(CFStringEncoding(CFStringEncodings.dosLatinUS.rawValue))
        for value in 0..<256 {
            var pixels = [UInt8](repeating: 0, count: width*height)
            pixels.withUnsafeMutableBytes { data in
                guard let context = CGContext(data: data.baseAddress, width: width, height: height, bitsPerComponent: 8,
                                              bytesPerRow: width, space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGImageAlphaInfo.none.rawValue) else { return }
                context.setFillColor(gray: 0, alpha: 1); context.fill(CGRect(x: 0, y: 0, width: width, height: height))
                let string = value < 32 ? " " : String(bytes: [UInt8(value)], encoding: String.Encoding(rawValue: encoding)) ?? "?"
                let attrs: [NSAttributedString.Key: Any] = [.init(kCTFontAttributeName as String): font,
                    .init(kCTForegroundColorAttributeName as String): CGColor(gray: 1, alpha: 1)]
                let line = CTLineCreateWithAttributedString(NSAttributedString(string: string, attributes: attrs))
                context.textPosition = CGPoint(x: 0, y: 3); CTLineDraw(line, context)
            }
            glyphs.append(pixels)
        }
    }

    func render(_ text: Data) -> Data {
        var pixels = [UInt32](repeating: 0xff000000, count: 640*400)
        let cells = [UInt8](text)
        guard cells.count >= 4000 else { return pixels.withUnsafeBytes { Data($0) } }
        for cell in 0..<2000 {
            let glyph = glyphs[Int(cells[cell*2])], attr = cells[cell*2+1]
            let foreground = colors[Int(attr&15)], background = colors[Int((attr>>4)&7)]
            for y in 0..<height { for x in 0..<width {
                let intensity = UInt32(glyph[y*width+x])
                var pixel: UInt32 = 0xff000000
                for shift in stride(from: 0, through: 16, by: 8) {
                    let f = (foreground>>shift)&255, b = (background>>shift)&255
                    pixel |= ((f*intensity+b*(255-intensity))/255)<<shift
                }
                pixels[(cell/80*height+y)*640+(cell%80*width+x)] = pixel
            }}
        }
        return pixels.withUnsafeBytes { Data($0) }
    }
}

final class MetalRenderer: NSObject, MTKViewDelegate {
    private let device: MTLDevice
    private let commandQueue: MTLCommandQueue
    private let pipeline: MTLRenderPipelineState
    private var texture: MTLTexture?
    private let rasterizer = TextRasterizer()
    private var previousText = Data(), previousPixels = Data()
    private var frame = MachineFrame()
    init?(view: MTKView) {
        guard let device = MTLCreateSystemDefaultDevice(), let commands = device.makeCommandQueue() else { return nil }
        self.device = device; self.commandQueue = commands
        let source = """
        #include <metal_stdlib>
        using namespace metal;
        struct V { float4 position [[position]]; float2 uv; };
        vertex V screen_vertex(uint id [[vertex_id]], constant float2 &scale [[buffer(0)]]) {
            float2 positions[4] = {float2(-1,-1),float2(1,-1),float2(-1,1),float2(1,1)};
            float2 uvs[4] = {float2(0,1),float2(1,1),float2(0,0),float2(1,0)};
            V v; v.position=float4(positions[id]*scale,0,1);v.uv=uvs[id];return v;
        }
        fragment float4 screen_fragment(V v [[stage_in]], texture2d<float> image [[texture(0)]]) {
            constexpr sampler nearestSampler(coord::normalized, address::clamp_to_edge, filter::nearest);
            return image.sample(nearestSampler,v.uv);
        }
        """
        do {
            let library = try device.makeLibrary(source: source, options: nil)
            let descriptor = MTLRenderPipelineDescriptor()
            descriptor.vertexFunction = library.makeFunction(name: "screen_vertex")
            descriptor.fragmentFunction = library.makeFunction(name: "screen_fragment")
            descriptor.colorAttachments[0].pixelFormat = .bgra8Unorm
            self.pipeline = try device.makeRenderPipelineState(descriptor: descriptor)
        } catch { NSLog("Project86 Metal: %@", error.localizedDescription); return nil }
        super.init()
        view.device = device; view.colorPixelFormat = .bgra8Unorm
        view.clearColor = MTLClearColorMake(0.025,0.03,0.04,1)
        view.isPaused = true; view.enableSetNeedsDisplay = false; view.delegate = self
    }

    func update(_ frame: MachineFrame, view: MTKView) {
        self.frame = frame
        let graphic = !frame.pixels.isEmpty
        let width = graphic ? frame.width : 640, height = graphic ? frame.height : 400
        let changed = texture == nil || texture?.width != width || texture?.height != height ||
            (graphic ? frame.pixels != previousPixels : frame.text != previousText)
        if changed {
            let data = graphic ? frame.pixels : rasterizer.render(frame.text)
            if texture == nil || texture?.width != width || texture?.height != height {
                let descriptor = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: .rgba8Unorm, width: width, height: height, mipmapped: false)
                descriptor.usage = .shaderRead; descriptor.storageMode = .shared
                texture = device.makeTexture(descriptor: descriptor)
            }
            data.withUnsafeBytes { bytes in if let base = bytes.baseAddress {
                texture?.replace(region: MTLRegionMake2D(0,0,width,height), mipmapLevel: 0, withBytes: base, bytesPerRow: width*4)
            }}
            previousText = frame.text; previousPixels = frame.pixels
        }
        view.draw()
    }
    func mtkView(_ view: MTKView, drawableSizeWillChange size: CGSize) { view.draw() }
    func draw(in view: MTKView) {
        guard let texture, let descriptor = view.currentRenderPassDescriptor, let drawable = view.currentDrawable,
              let command = commandQueue.makeCommandBuffer(), let encoder = command.makeRenderCommandEncoder(descriptor: descriptor) else { return }
        let contentAspect: Float = frame.pixels.isEmpty ? 1.6 : 4.0/3.0
        let viewAspect = Float(max(view.drawableSize.width,1)/max(view.drawableSize.height,1))
        var scale = SIMD2<Float>(viewAspect>contentAspect ? contentAspect/viewAspect : 1,
                                 viewAspect<contentAspect ? viewAspect/contentAspect : 1)
        encoder.setRenderPipelineState(pipeline); encoder.setVertexBytes(&scale, length: MemoryLayout<SIMD2<Float>>.size, index: 0)
        encoder.setFragmentTexture(texture, index: 0); encoder.drawPrimitives(type: .triangleStrip, vertexStart: 0, vertexCount: 4)
        encoder.endEncoding(); command.present(drawable); command.commit()
    }
}

#if os(macOS)
final class InputMetalView: MTKView {
    weak var worker: EmulationWorker?
    private var tracking: NSTrackingArea?
    private var buttons: UInt8 = 0
    override var acceptsFirstResponder: Bool { true }
    override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); window?.makeFirstResponder(self); window?.acceptsMouseMovedEvents = true }
    override func updateTrackingAreas() {
        super.updateTrackingAreas(); if let tracking { removeTrackingArea(tracking) }
        tracking = NSTrackingArea(rect: bounds, options: [.mouseMoved,.activeInKeyWindow,.inVisibleRect], owner: self)
        if let tracking { addTrackingArea(tracking) }
    }
    private func scan(_ code: UInt16) -> UInt8 {
        let map: [UInt16:UInt8] = [0:0x1e,1:0x1f,2:0x20,3:0x21,4:0x23,5:0x22,6:0x2c,7:0x2d,8:0x2e,9:0x2f,11:0x30,
            12:0x10,13:0x11,14:0x12,15:0x13,16:0x15,17:0x14,18:2,19:3,20:4,21:5,22:7,23:6,24:13,25:10,26:8,27:12,28:9,29:11,
            30:0x1b,31:0x18,32:0x16,33:0x1a,34:0x17,35:0x19,36:0x1c,37:0x26,38:0x24,39:0x28,40:0x25,41:0x27,42:0x2b,43:0x33,44:0x35,45:0x31,46:0x32,47:0x34,48:0x0f,49:0x39,50:0x29,51:0x0e,53:1,
            122:0x3b,120:0x3c,99:0x3d,118:0x3e,96:0x3f,97:0x40,98:0x41,100:0x42,101:0x43,109:0x44,123:0x4b,124:0x4d,125:0x50,126:0x48,115:0x47,119:0x4f,116:0x49,121:0x51,117:0x53]
        return map[code] ?? 0
    }
    override func flagsChanged(with event: NSEvent) {
        let mapping: [UInt16:(UInt8,NSEvent.ModifierFlags)] = [56:(0x2a,.shift),60:(0x36,.shift),59:(0x1d,.control),62:(0x1d,.control),58:(0x38,.option),61:(0x38,.option)]
        if let (scan, flag) = mapping[event.keyCode] { worker?.key(0, scan: scan, pressed: event.modifierFlags.contains(flag)) }
    }
    @objc func paste(_ sender: Any?) { if let text = NSPasteboard.general.string(forType: .string) { worker?.paste(text) } }
    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        if event.modifierFlags.contains(.command), event.charactersIgnoringModifiers == "v" { paste(nil); return true }
        return super.performKeyEquivalent(with: event)
    }
    override func keyDown(with event: NSEvent) {
        if event.modifierFlags.contains(.command) { super.keyDown(with: event); return }
        var ascii = event.characters?.utf8.first ?? 0
        if event.keyCode == 36 { ascii = 13 }; if event.keyCode == 51 { ascii = 8 }
        if event.keyCode >= 115 || event.characters?.unicodeScalars.first?.value ?? 0 > 127 { ascii = 0 }
        worker?.key(ascii, scan: scan(event.keyCode))
    }
    override func keyUp(with event: NSEvent) { worker?.key(0, scan: scan(event.keyCode), pressed: false) }
    override func mouseDown(with event: NSEvent) { window?.makeFirstResponder(self); buttons |= 1; worker?.mouse(dx: 0, dy: 0, buttons: buttons) }
    override func mouseUp(with event: NSEvent) { buttons &= ~1; worker?.mouse(dx: 0, dy: 0, buttons: buttons) }
    override func rightMouseDown(with event: NSEvent) { buttons |= 2; worker?.mouse(dx: 0, dy: 0, buttons: buttons) }
    override func rightMouseUp(with event: NSEvent) { buttons &= ~2; worker?.mouse(dx: 0, dy: 0, buttons: buttons) }
    override func mouseMoved(with event: NSEvent) { worker?.mouse(dx: Double(event.deltaX), dy: Double(event.deltaY), buttons: buttons) }
    override func mouseDragged(with event: NSEvent) { mouseMoved(with: event) }
    override func rightMouseDragged(with event: NSEvent) { mouseMoved(with: event) }
}

struct EmulatorDisplay: NSViewRepresentable {
    let frame: MachineFrame
    let worker: EmulationWorker
    var keyboardRequested: Bool
    final class Coordinator { var renderer: MetalRenderer? }
    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeNSView(context: Context) -> InputMetalView {
        let view = InputMetalView(); view.worker = worker; view.setAccessibilityIdentifier("dos-screen"); view.setAccessibilityElement(true); view.setAccessibilityRole(.textArea)
        context.coordinator.renderer = MetalRenderer(view: view); return view
    }
    func updateNSView(_ view: InputMetalView, context: Context) { view.setAccessibilityValue(frame.accessibilityText); context.coordinator.renderer?.update(frame, view: view) }
}
#else
final class InputMetalView: MTKView, UIKeyInput {
    weak var worker: EmulationWorker?
    var hasText: Bool { true }
    var keyboardAppearance: UIKeyboardAppearance = .dark
    var autocorrectionType: UITextAutocorrectionType = .no
    var autocapitalizationType: UITextAutocapitalizationType = .none
    override var canBecomeFirstResponder: Bool { true }
    private var lastPoint = CGPoint.zero
    func insertText(_ text: String) { worker?.paste(text) }
    func deleteBackward() { worker?.key(8, scan: 0x0e) }
    func configure() {
        let tap = UITapGestureRecognizer(target: self, action: #selector(tap(_:))); addGestureRecognizer(tap)
        let pan = UIPanGestureRecognizer(target: self, action: #selector(pan(_:))); addGestureRecognizer(pan)
        let right = UITapGestureRecognizer(target: self, action: #selector(rightTap(_:))); right.numberOfTouchesRequired = 2; addGestureRecognizer(right)
    }
    @objc private func tap(_ sender: UITapGestureRecognizer) { worker?.mouse(dx: 0, dy: 0, buttons: 1); worker?.mouse(dx: 0, dy: 0, buttons: 0) }
    @objc private func rightTap(_ sender: UITapGestureRecognizer) { worker?.mouse(dx: 0, dy: 0, buttons: 2); worker?.mouse(dx: 0, dy: 0, buttons: 0) }
    @objc private func pan(_ sender: UIPanGestureRecognizer) {
        let point = sender.translation(in: self)
        if sender.state == .began { lastPoint = point }
        worker?.mouse(dx: Double(point.x-lastPoint.x), dy: Double(point.y-lastPoint.y), buttons: 0); lastPoint = point
    }
}
struct EmulatorDisplay: UIViewRepresentable {
    let frame: MachineFrame
    let worker: EmulationWorker
    var keyboardRequested: Bool
    final class Coordinator { var renderer: MetalRenderer?; var previousKeyboard = false }
    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeUIView(context: Context) -> InputMetalView {
        let view = InputMetalView(); view.worker = worker; view.configure(); view.accessibilityIdentifier = "dos-screen"; view.isAccessibilityElement = true
        context.coordinator.renderer = MetalRenderer(view: view); return view
    }
    func updateUIView(_ view: InputMetalView, context: Context) {
        view.accessibilityValue = frame.accessibilityText
        context.coordinator.renderer?.update(frame, view: view)
        if context.coordinator.previousKeyboard != keyboardRequested {
            context.coordinator.previousKeyboard = keyboardRequested
            if keyboardRequested { view.becomeFirstResponder() } else { view.resignFirstResponder() }
        }
    }
}
#endif
