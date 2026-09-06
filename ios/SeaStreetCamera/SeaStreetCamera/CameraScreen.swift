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

            if let license = camera.licenseResult {
                VStack {
                    HStack(spacing: 12) {
                        Circle()
                            .fill(license.shouldAlert ? Color.red : Color.green)
                            .frame(width: 10, height: 10)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(license.message)
                                .font(.caption.weight(.black))
                            if let name = license.name {
                                Text(name.uppercased())
                                    .font(.caption2.weight(.bold))
                            }
                            Text([license.state, license.number].compactMap { $0 }.joined(separator: "  "))
                                .font(.system(size: 10, weight: .medium, design: .monospaced))
                        }
                        Spacer()
                        Button(action: camera.dismissLicense) {
                            Image(systemName: "xmark")
                                .font(.caption.weight(.bold))
                        }
                    }
                    .foregroundStyle(.black)
                    .padding(13)
                    .background(Color(white: 0.97))
                    .overlay(Rectangle().stroke(brandBlue, lineWidth: 2))
                    .shadow(color: .black.opacity(0.4), radius: 10)
                    Spacer()
                }
                .padding(.horizontal, 12)
                .padding(.top, 62)
                .transition(.move(edge: .top).combined(with: .opacity))
                .zIndex(3)
            }

            if let profile = camera.criminalProfile {
                VStack {
                    Spacer()
                    CriminalProfileCard(profile: profile) {
                        camera.criminalProfile = nil
                    }
                }
                .padding(12)
                .transition(.move(edge: .bottom).combined(with: .opacity))
                .zIndex(2)
            }
        }
        .animation(.easeInOut(duration: 0.2), value: camera.showingAlert)
        .animation(.easeInOut(duration: 0.2), value: camera.licenseResult?.id)
        .animation(.easeInOut(duration: 0.25), value: camera.criminalProfile?.id)
        .onDisappear { camera.stop() }
    }
}
