import AVFoundation

final class LicenseScanner: NSObject, AVCaptureMetadataOutputObjectsDelegate {
    private let output = AVCaptureMetadataOutput()
    private let queue = DispatchQueue(label: "com.robin.camera.license")
    private let onScan: (String) -> Void
    private var lastValue: String?
    private var lastSent = Date.distantPast

    init(onScan: @escaping (String) -> Void) {
        self.onScan = onScan
    }

    func install(on session: AVCaptureSession) -> Bool {
        session.beginConfiguration()
        defer { session.commitConfiguration() }
        guard session.canAddOutput(output) else { return false }
        session.addOutput(output)
        guard output.availableMetadataObjectTypes.contains(.pdf417) else {
            session.removeOutput(output)
            return false
        }
        output.setMetadataObjectsDelegate(self, queue: queue)
        output.metadataObjectTypes = [.pdf417]
        return true
    }

    func metadataOutput(
        _ output: AVCaptureMetadataOutput,
        didOutput metadataObjects: [AVMetadataObject],
        from connection: AVCaptureConnection
    ) {
        guard let value = metadataObjects.compactMap({ object in
            (object as? AVMetadataMachineReadableCodeObject)?.stringValue
        }).first, !value.isEmpty else { return }

        let now = Date()
        guard value != lastValue || now.timeIntervalSince(lastSent) >= 8 else { return }
        lastValue = value
        lastSent = now
        onScan(value)
    }
}
