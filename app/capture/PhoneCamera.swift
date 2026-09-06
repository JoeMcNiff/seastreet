import AppKit
import AVFoundation
import CoreImage
import ImageIO
import Network

final class FrameServer {
    private let queue = DispatchQueue(label: "camera.frames")
    private var listener: NWListener?
    private var client: NWConnection?
    private var sending = false

    init() {
        let settings = NWParameters.tcp
        settings.requiredLocalEndpoint = .hostPort(host: "127.0.0.1", port: 8765)
        listener = try? NWListener(using: settings)
        listener?.newConnectionHandler = { [weak self] connection in
            guard let self = self else { return }
            self.client?.cancel()
            self.client = connection
            connection.start(queue: self.queue)
        }
        listener?.start(queue: queue)
    }

    func send(_ jpeg: Data) {
        queue.async {
            guard let client = self.client, !self.sending else { return }
            var size = UInt32(jpeg.count).bigEndian
            var packet = Data(bytes: &size, count: 4)
            packet.append(jpeg)
            self.sending = true
            client.send(content: packet, completion: .contentProcessed { error in
                self.sending = false
                if error != nil {
                    client.cancel()
                    self.client = nil
                }
            })
        }
    }
}

final class FrameOutput: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    private let server = FrameServer()
    private let context = CIContext()
    private let colorSpace = CGColorSpaceCreateDeviceRGB()
    private var count = 0

    func captureOutput(
        _ output: AVCaptureOutput,
        didOutput sample: CMSampleBuffer,
        from connection: AVCaptureConnection
    ) {
        count += 1
        guard count % 2 == 0,
              let buffer = CMSampleBufferGetImageBuffer(sample) else { return }
        var image = CIImage(cvImageBuffer: buffer)
        let scale = min(1, 1920 / image.extent.width)
        image = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        if let jpeg = context.jpegRepresentation(
            of: image,
            colorSpace: colorSpace,
            options: [kCGImageDestinationLossyCompressionQuality as CIImageRepresentationOption: 0.9]
        ) {
            server.send(jpeg)
        }
    }
}

final class CameraView: NSView {
    private let session = AVCaptureSession()
    private let preview = AVCaptureVideoPreviewLayer()
    private let frameOutput = FrameOutput()

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer?.backgroundColor = NSColor.black.cgColor
        preview.videoGravity = .resizeAspect
        layer?.addSublayer(preview)

        AVCaptureDevice.requestAccess(for: .video) { allowed in
            DispatchQueue.main.async {
                if allowed {
                    self.connect()
                    Timer.scheduledTimer(withTimeInterval: 2, repeats: true) {
                        [weak self] _ in self?.connect()
                    }
                } else {
                    self.window?.title = "Camera permission denied"
                }
            }
        }
    }

    required init?(coder: NSCoder) { fatalError() }

    override func layout() {
        super.layout()
        preview.frame = bounds
    }

    @objc private func connect() {
        guard session.inputs.isEmpty else { return }
        let phones = AVCaptureDevice.DiscoverySession(
            deviceTypes: [.continuityCamera],
            mediaType: .video,
            position: .unspecified
        ).devices
        guard let phone = phones.first,
              let input = try? AVCaptureDeviceInput(device: phone),
              session.canAddInput(input) else {
            window?.title = "No iPhone camera found"
            return
        }

        session.addInput(input)
        let output = AVCaptureVideoDataOutput()
        output.alwaysDiscardsLateVideoFrames = true
        output.setSampleBufferDelegate(
            frameOutput, queue: DispatchQueue(label: "camera.capture")
        )
        if session.canAddOutput(output) { session.addOutput(output) }
        preview.session = session
        window?.title = phone.localizedName
        DispatchQueue.global(qos: .userInitiated).async {
            self.session.startRunning()
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var window: NSWindow!

    func applicationDidFinishLaunching(_ notification: Notification) {
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 720, height: 480),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Looking for iPhone…"
        window.contentView = CameraView(frame: window.contentView!.bounds)
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.setActivationPolicy(.regular)
app.delegate = delegate
app.run()
