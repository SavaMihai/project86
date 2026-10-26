import AppKit
import MetalKit
import Foundation

@main struct RenderPreview {
    static func main() throws {
        guard CommandLine.arguments.count == 3, let machine = p86_create() else { fatalError("Usage: render-preview DOS.IMA OUTPUT.PNG") }
        defer { p86_destroy(machine) }
        guard p86_attach_floppy(machine, CommandLine.arguments[1], 0) != 0, p86_boot(machine) != 0 else { fatalError("Boot image failed") }
        let input = Array("\r\rver\recho NATIVE MAC DISPLAY\r".utf8)
        var index = 0, idle = 0
        for _ in 0..<10000 {
            let status = p86_run(machine, 10000)
            if status == P86_FAULT { fatalError("Guest execution fault") }
            if status == P86_WAITING_KEY {
                if index < input.count { p86_key(machine, input[index], input[index] == 13 ? 0x1c : 0, 1); index += 1; idle = 0 }
                else { idle += 1; if idle > 100 { break } }
            }
        }
        var text = Data(count: 4000)
        text.withUnsafeMutableBytes { _ = p86_copy_text(machine, $0.bindMemory(to: UInt8.self).baseAddress, 4000) }
        let pixels = TextRasterizer().render(text)
        let provider = CGDataProvider(data: pixels as CFData)!
        let image = CGImage(width: 640, height: 400, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: 2560,
                            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue),
                            provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent)!
        let bitmap = NSBitmapImageRep(cgImage: image)
        try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[2]))
        let view = MTKView(frame: CGRect(x:0,y:0,width:640,height:400))
        guard MetalRenderer(view: view) != nil else { fatalError("Metal pipeline did not compile") }
        print("Native CoreText display rendered; Metal shader pipeline compiled successfully.")
    }
}
