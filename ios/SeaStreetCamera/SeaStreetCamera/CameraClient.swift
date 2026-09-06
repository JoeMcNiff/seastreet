import AVFoundation
import AudioToolbox
import Combine
import UIKit
import WebRTC

final class CameraClient: NSObject, ObservableObject {
    @Published private(set) var status = "Ready"
    @Published private(set) var started = false
    @Published private(set) var connected = false
    @Published private(set) var showingAlert = false
    @Published var criminalProfile: CriminalProfile?
    @Published var licenseResult: LicenseLookup?
    @Published private(set) var videoTrack: RTCVideoTrack?

    private let factory: RTCPeerConnectionFactory
    private var capturer: RTCCameraVideoCapturer?
    private var licenseScanner: LicenseScanner?
    private var peer: RTCPeerConnection?
    private var alerts: RTCDataChannel?
    private var pendingLicense: String?
    private var serverURL: URL?
    private var running = false
    private var offerSent = false
    private var connecting = false
    private var reconnect: DispatchWorkItem?
    private lazy var warrantSound: SystemSoundID = {
        guard let url = Bundle.main.url(
            forResource: "WarrantAlert", withExtension: "wav"
        ) else { return 1025 }
        var sound: SystemSoundID = 0
        AudioServicesCreateSystemSoundID(url as CFURL, &sound)
        return sound
    }()

    override init() {
        RTCPeerConnectionFactory.initialize()
        factory = RTCPeerConnectionFactory(
            encoderFactory: RTCDefaultVideoEncoderFactory(),
            decoderFactory: RTCDefaultVideoDecoderFactory()
        )
        super.init()
    }

    func start(_ address: String) {
        guard let url = Self.serverURL(address) else {
            status = "Enter a valid laptop hostname or URL"
            return
        }
        serverURL = url
        running = true
        started = true
        status = "Starting camera…"
        UIApplication.shared.isIdleTimerDisabled = true
        requestCamera()
    }

    func stop() {
        running = false
        reconnect?.cancel()
        let oldPeer = peer
        peer = nil
        oldPeer?.close()
        capturer?.stopCapture()
        licenseScanner = nil
        pendingLicense = nil
        UIApplication.shared.isIdleTimerDisabled = false
        connected = false
    }

    private func requestCamera() {
        AVCaptureDevice.requestAccess(for: .video) { [weak self] allowed in
            guard let self else { return }
            guard allowed else {
                self.publish("Camera permission denied", started: false)
                return
            }
            self.startCapture()
        }
    }

    private func startCapture() {
        guard let device = RTCCameraVideoCapturer.captureDevices().first(where: {
            $0.position == .back
        }) else {
            publish("No rear camera found", started: false)
            return
        }
        let formats = RTCCameraVideoCapturer.supportedFormats(for: device)
        guard let format = Self.bestFormat(formats) else {
            publish("No supported camera format", started: false)
            return
        }

        do {
            try device.lockForConfiguration()
            if device.isFocusModeSupported(.continuousAutoFocus) {
                device.focusMode = .continuousAutoFocus
            }
            if device.isExposureModeSupported(.continuousAutoExposure) {
                device.exposureMode = .continuousAutoExposure
            }
            device.unlockForConfiguration()
        } catch {
            publish("Camera configuration failed: \(error.localizedDescription)")
        }

        let source = factory.videoSource()
        let track = factory.videoTrack(with: source, trackId: "camera")
        let capturer = RTCCameraVideoCapturer(delegate: source)
        self.capturer = capturer
        publishTrack(track)
        capturer.startCapture(with: device, format: format, fps: 30) {
            [weak self] error in
            guard let self else { return }
            if let error {
                self.publish("Camera failed: \(error.localizedDescription)", started: false)
            } else {
                let scanner = LicenseScanner { [weak self] value in
                    self?.queueLicense(value)
                }
                if scanner.install(on: capturer.captureSession) {
                    self.licenseScanner = scanner
                }
                self.connect(track)
            }
        }
    }

    private func connect(_ track: RTCVideoTrack? = nil) {
        guard running, !connecting, let serverURL,
              let track = track ?? videoTrack else { return }
        connecting = true
        offerSent = false
        reconnect?.cancel()
        let oldPeer = peer
        peer = nil
        alerts = nil
        oldPeer?.close()

        let configuration = RTCConfiguration()
        configuration.iceServers = []
        configuration.sdpSemantics = .unifiedPlan
        let constraints = RTCMediaConstraints(
            mandatoryConstraints: nil,
            optionalConstraints: ["DtlsSrtpKeyAgreement": "true"]
        )
        guard let peer = factory.peerConnection(
            with: configuration, constraints: constraints, delegate: self
        ) else {
            connecting = false
            scheduleReconnect("Could not create WebRTC connection")
            return
        }
        self.peer = peer

        if let sender = peer.add(track, streamIds: ["camera-stream"]) {
            let parameters = sender.parameters
            if let encoding = parameters.encodings.first {
                encoding.maxBitrateBps = 8_000_000
                encoding.maxFramerate = 30
                sender.parameters = parameters
            }
        }

        let channelConfiguration = RTCDataChannelConfiguration()
        channelConfiguration.isOrdered = true
        alerts = peer.dataChannel(
            forLabel: "alerts", configuration: channelConfiguration
        )
        alerts?.delegate = self

        publish("Connecting to \(serverURL.host ?? "laptop")…")
        peer.offer(for: RTCMediaConstraints(
            mandatoryConstraints: ["OfferToReceiveAudio": "false"],
            optionalConstraints: nil
        )) { [weak self, weak peer] description, error in
            guard let self, let peer, peer === self.peer else { return }
            guard let description else {
                self.connecting = false
                self.scheduleReconnect(error?.localizedDescription ?? "Could not create offer")
                return
            }
            peer.setLocalDescription(description) { error in
                if let error {
                    self.connecting = false
                    self.scheduleReconnect(error.localizedDescription)
                }
            }
        }
    }

    private func sendOffer(_ peer: RTCPeerConnection) {
        guard running, peer === self.peer, !offerSent,
              let description = peer.localDescription, let serverURL else {
            return
        }
        offerSent = true
        var request = URLRequest(url: serverURL.appendingPathComponent("offer"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: [
            "type": "offer", "sdp": description.sdp,
        ])
        URLSession.shared.dataTask(with: request) { [weak self, weak peer] data, response, error in
            guard let self, let peer, peer === self.peer else { return }
            guard error == nil,
                  let response = response as? HTTPURLResponse,
                  (200..<300).contains(response.statusCode),
                  let data,
                  let object = try? JSONSerialization.jsonObject(with: data) as? [String: String],
                  let sdp = object["sdp"] else {
                self.connecting = false
                self.scheduleReconnect(error?.localizedDescription ?? "Laptop did not accept connection")
                return
            }
            peer.setRemoteDescription(
                RTCSessionDescription(type: .answer, sdp: sdp)
            ) { error in
                self.connecting = false
                if let error {
                    self.scheduleReconnect(error.localizedDescription)
                }
            }
        }.resume()
    }

    private func scheduleReconnect(_ message: String) {
        guard running else { return }
        publish(message, connected: false)
        reconnect?.cancel()
        let work = DispatchWorkItem { [weak self] in self?.connect() }
        reconnect = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 2, execute: work)
    }

    private func alert(_ profile: CriminalProfile) {
        DispatchQueue.main.async {
            self.playWarning()
            self.criminalProfile = profile
            self.showingAlert = true
            self.status = "Criminal record found"
            DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                self.showingAlert = false
            }
        }
    }

    func dismissLicense() {
        licenseResult = nil
    }

    private func queueLicense(_ value: String) {
        DispatchQueue.main.async {
            self.pendingLicense = value
            self.flushLicense()
        }
    }

    private func flushLicense() {
        guard alerts?.readyState == .open, let value = pendingLicense,
              let data = try? JSONSerialization.data(withJSONObject: [
                "type": "license_scan", "raw": value,
              ]) else { return }
        if alerts?.sendData(RTCDataBuffer(data: data, isBinary: false)) == true {
            pendingLicense = nil
        }
    }

    private func showLicense(_ result: LicenseLookup) {
        DispatchQueue.main.async {
            self.licenseResult = result
            if result.shouldAlert {
                self.playWarning()
            }
        }
    }

    private func playWarning() {
        AudioServicesPlaySystemSound(warrantSound)
        for index in 0..<4 {
            DispatchQueue.main.asyncAfter(deadline: .now() + Double(index) * 0.18) {
                UINotificationFeedbackGenerator().notificationOccurred(.warning)
            }
        }
    }

    private func publish(
        _ status: String, started: Bool? = nil, connected: Bool? = nil
    ) {
        DispatchQueue.main.async {
            self.status = status
            if let started { self.started = started }
            if let connected { self.connected = connected }
        }
    }

    private func publishTrack(_ track: RTCVideoTrack) {
        DispatchQueue.main.async { self.videoTrack = track }
    }

    private static func serverURL(_ address: String) -> URL? {
        let address = address.trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard !address.isEmpty else { return nil }
        if address.contains("://") {
            return URL(string: address)
        }
        return URL(string: "https://\(address):8443")
    }

    private static func bestFormat(
        _ formats: [AVCaptureDevice.Format]
    ) -> AVCaptureDevice.Format? {
        formats
            .filter { format in
                format.videoSupportedFrameRateRanges.contains { $0.maxFrameRate >= 30 }
            }
            .min { first, second in
                distance(first) < distance(second)
            }
    }

    private static func distance(_ format: AVCaptureDevice.Format) -> Int64 {
        let size = CMVideoFormatDescriptionGetDimensions(format.formatDescription)
        return abs(Int64(size.width) * Int64(size.height) - 1920 * 1080)
    }
}

extension CameraClient: RTCPeerConnectionDelegate {
    func peerConnection(
        _ peerConnection: RTCPeerConnection,
        didChange stateChanged: RTCSignalingState
    ) {}

    func peerConnection(
        _ peerConnection: RTCPeerConnection,
        didAdd stream: RTCMediaStream
    ) {}

    func peerConnection(
        _ peerConnection: RTCPeerConnection,
        didRemove stream: RTCMediaStream
    ) {}

    func peerConnectionShouldNegotiate(_ peerConnection: RTCPeerConnection) {}

    func peerConnection(
        _ peerConnection: RTCPeerConnection,
        didChange newState: RTCIceConnectionState
    ) {}

    func peerConnection(
        _ peerConnection: RTCPeerConnection,
        didChange newState: RTCIceGatheringState
    ) {
        if peerConnection === peer, newState == .complete {
            sendOffer(peerConnection)
        }
    }

    func peerConnection(
        _ peerConnection: RTCPeerConnection,
        didGenerate candidate: RTCIceCandidate
    ) {}

    func peerConnection(
        _ peerConnection: RTCPeerConnection,
        didRemove candidates: [RTCIceCandidate]
    ) {}

    func peerConnection(
        _ peerConnection: RTCPeerConnection,
        didOpen dataChannel: RTCDataChannel
    ) {}

    func peerConnection(
        _ peerConnection: RTCPeerConnection,
        didChange newState: RTCPeerConnectionState
    ) {
        guard peerConnection === peer else { return }
        switch newState {
        case .connected:
            connecting = false
            publish("Connected to Remote Server", connected: true)
        case .failed, .disconnected, .closed:
            connecting = false
            scheduleReconnect("Connection \(String(describing: newState))")
        default:
            break
        }
    }
}

extension CameraClient: RTCDataChannelDelegate {
    func dataChannelDidChangeState(_ dataChannel: RTCDataChannel) {
        DispatchQueue.main.async { self.flushLicense() }
    }

    func dataChannel(
        _ dataChannel: RTCDataChannel,
        didReceiveMessageWith buffer: RTCDataBuffer
    ) {
        if let profile = try? JSONDecoder().decode(
            CriminalProfile.self, from: buffer.data
        ), profile.type == "criminal_profile" {
            alert(profile)
        } else if let result = try? JSONDecoder().decode(
            LicenseLookup.self, from: buffer.data
        ), result.type == "license_result" {
            showLicense(result)
        }
    }
}
