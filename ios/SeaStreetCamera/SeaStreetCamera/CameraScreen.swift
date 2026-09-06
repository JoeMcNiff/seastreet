import SwiftUI

private let brandBlue = Color(red: 0, green: 74 / 255, blue: 138 / 255)

struct CameraScreen: View {
    @StateObject private var camera = CameraClient()
    @AppStorage("serverAddress") private var serverAddress =
        "Josephs-MacBook-Air-481.local"

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VStack(spacing: 18) {
                Text("ROBIN INTELLIGENCE")
                    .font(.headline.weight(.bold))
                    .foregroundStyle(.white)
                    .tracking(1.4)

                ZStack {
                    CameraPreview(track: camera.videoTrack)
                    if camera.videoTrack == nil {
                        Image(systemName: "video")
                            .font(.system(size: 42))
                            .foregroundStyle(brandBlue)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(.black)
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(brandBlue, lineWidth: 2)
                )

                if !camera.started {
                    TextField("Laptop hostname or URL", text: $serverAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                        .padding(13)
                        .foregroundStyle(.white)
                        .background(Color.white.opacity(0.1))
                        .clipShape(RoundedRectangle(cornerRadius: 7))

                    Button("Start Camera") {
                        camera.start(serverAddress)
                    }
                    .fontWeight(.bold)
                    .foregroundStyle(.white)
                    .padding(.horizontal, 24)
                    .padding(.vertical, 14)
                    .background(brandBlue)
                    .clipShape(RoundedRectangle(cornerRadius: 7))
                }

                HStack(spacing: 8) {
                    Circle()
                        .fill(camera.connected ? Color.green : brandBlue)
                        .frame(width: 9, height: 9)
                    Text(camera.status)
                        .foregroundStyle(.white)
                }
                .font(.callout)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .padding(20)

            if camera.showingAlert {
                VStack {
                    Text("RECORD ALERT")
                        .font(.headline.weight(.bold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 22)
                        .padding(.vertical, 13)
                        .background(brandBlue)
                        .clipShape(Capsule())
                        .padding(.top, 12)
                    Spacer()
                }
                .transition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.2), value: camera.showingAlert)
        .onDisappear { camera.stop() }
    }
}
