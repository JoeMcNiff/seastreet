import SwiftUI
import WebRTC

struct CameraPreview: UIViewRepresentable {
    let track: RTCVideoTrack?

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    func makeUIView(context: Context) -> RTCMTLVideoView {
        let view = RTCMTLVideoView()
        view.backgroundColor = .black
        view.videoContentMode = .scaleAspectFill
        context.coordinator.view = view
        return view
    }

    func updateUIView(_ view: RTCMTLVideoView, context: Context) {
        guard context.coordinator.track !== track else { return }
        context.coordinator.track?.remove(view)
        track?.add(view)
        context.coordinator.track = track
    }

    static func dismantleUIView(_ view: RTCMTLVideoView, coordinator: Coordinator) {
        coordinator.track?.remove(view)
    }

    final class Coordinator {
        weak var view: RTCMTLVideoView?
        var track: RTCVideoTrack?
    }
}
