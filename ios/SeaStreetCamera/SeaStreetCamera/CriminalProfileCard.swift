import SwiftUI

struct CriminalProfileCard: View {
    let profile: CriminalProfile
    let dismiss: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("ROBIN INTELLIGENCE")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(Color(red: 0, green: 74 / 255, blue: 138 / 255))
                    Text("LIKELY CRIMINAL PROFILE")
                        .font(.headline.weight(.black))
                }
                Spacer()
                Button(action: dismiss) {
                    Image(systemName: "xmark")
                        .font(.caption.weight(.bold))
                        .padding(8)
                        .background(Color.black.opacity(0.08), in: Circle())
                }
                .foregroundStyle(.black)
            }

            Divider().overlay(Color.black)

            HStack(alignment: .top, spacing: 14) {
                Group {
                    if let image = profile.image {
                        Image(uiImage: image)
                            .resizable()
                            .scaledToFill()
                    } else {
                        Image(systemName: "person.crop.rectangle")
                            .resizable()
                            .scaledToFit()
                            .padding(20)
                            .foregroundStyle(.gray)
                    }
                }
                .frame(width: 92, height: 112)
                .background(Color.black.opacity(0.06))
                .clipped()
                .overlay(Rectangle().stroke(.black, lineWidth: 1))

                VStack(alignment: .leading, spacing: 6) {
                    Text(profile.name.uppercased())
                        .font(.title3.weight(.black))
                        .lineLimit(1)
                    field(
                        "IDENTITY MATCH",
                        value: String(format: "%.0f%%", profile.similarity * 100)
                    )
                    field("RECORD ID", value: profile.record.id.map(String.init))
                    field("STATUS", value: profile.record.recordStatus)
                    field(
                        "PRIMARY OFFENSE",
                        value: profile.record.primaryOffense,
                        warning: true
                    )
                    field(
                        "ACTIVE WARRANT",
                        value: profile.record.activeWarrant == true ? "YES" : "NO",
                        warning: profile.record.activeWarrant == true
                    )
                }
            }

            Divider()

            HStack {
                field("WANTED LEVEL", value: profile.record.wantedLevel.map(String.init))
                Spacer()
                field("ARRESTS", value: profile.record.arrestCount.map(String.init))
                Spacer()
                field("CONVICTIONS", value: profile.record.convictionCount.map(String.init))
            }

            HStack {
                field("WARRANT", value: profile.record.warrantNumber)
                Spacer()
                field("WARRANT ISSUED", value: profile.record.warrantIssueDate)
                Spacer()
                field("LAST ARREST", value: profile.record.lastArrestDate)
            }
        }
        .foregroundStyle(.black)
        .padding(16)
        .frame(maxWidth: 620)
        .background(Color(white: 0.97))
        .overlay(Rectangle().stroke(.black, lineWidth: 1))
        .shadow(color: .black.opacity(0.45), radius: 16, y: -4)
    }

    private func field(_ label: String, value: String?, warning: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(label)
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(.gray)
            Text((value.flatMap { $0.isEmpty ? nil : $0 } ?? "—").uppercased())
                .font(.system(size: 12, weight: .semibold, design: .monospaced))
                .foregroundStyle(warning ? .red : .black)
                .lineLimit(1)
        }
    }
}
