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

    func captureOutput(_ output: AVCaptureOutput, didOutput sample: CMSampleBuffer, from connection: AVCaptureConnection) {
        count += 1
        guard count % 3 == 0, let buffer = CMSampleBufferGetImageBuffer(sample) else { return }
        var image = CIImage(cvImageBuffer: buffer)
        let scale = min(1, 960 / image.extent.width)
        image = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        if let jpeg = context.jpegRepresentation(
            of: image,
            colorSpace: colorSpace,
            options: [kCGImageDestinationLossyCompressionQuality as CIImageRepresentationOption: 0.75]
        ) {
            server.send(jpeg)
        }
    }
}

final class CameraView: NSView {
    let session = AVCaptureSession()
    let preview = AVCaptureVideoPreviewLayer()
    let frameOutput = FrameOutput()

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
                    Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in self?.connect() }
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

    @objc func connect() {
        guard session.inputs.isEmpty else { return }
        let devices = AVCaptureDevice.DiscoverySession(
            deviceTypes: [.continuityCamera, .external],
            mediaType: .video,
            position: .unspecified
        ).devices
        let phone = devices.first {
            $0.deviceType == .continuityCamera || $0.localizedName.lowercased().contains("iphone")
        }

        guard let phone = phone,
              let input = try? AVCaptureDeviceInput(device: phone),
              session.canAddInput(input) else {
            window?.title = "No iPhone camera found"
            return
        }

        session.beginConfiguration()
        session.sessionPreset = .high
        session.addInput(input)
        let output = AVCaptureVideoDataOutput()
        output.alwaysDiscardsLateVideoFrames = true
        output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA]
        output.setSampleBufferDelegate(frameOutput, queue: DispatchQueue(label: "camera.capture"))
        guard session.canAddOutput(output) else {
            session.commitConfiguration()
            window?.title = "Could not create video output"
            return
        }
        session.addOutput(output)
        session.commitConfiguration()
        preview.session = session
        window?.title = phone.localizedName
        DispatchQueue.global(qos: .userInitiated).async { self.session.startRunning() }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!

    func applicationDidFinishLaunching(_ notification: Notification) {
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 960, height: 640),
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

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.setActivationPolicy(.regular)
app.delegate = delegate
app.run()
