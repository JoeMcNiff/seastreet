import Foundation
import UIKit

struct CriminalProfile: Decodable, Identifiable {
    let type: String
    let name: String
    let similarity: Double
    let record: CriminalRecord
    let photo: String?

    var id: String { "\(record.id ?? 0)-\(name)" }

    var image: UIImage? {
        guard let photo, let data = Data(base64Encoded: photo) else { return nil }
        return UIImage(data: data)
    }
}

struct CriminalRecord: Decodable {
    let id: Int64?
    let recordStatus: String?
    let wantedLevel: Int?
    let arrestCount: Int?
    let activeWarrant: Bool?
    let convictionCount: Int?
    let primaryOffense: String?
    let warrantNumber: String?
    let lastArrestDate: String?
    let warrantIssueDate: String?

    enum CodingKeys: String, CodingKey {
        case id
        case recordStatus = "record_status"
        case wantedLevel = "wanted_level"
        case arrestCount = "arrest_count"
        case activeWarrant = "active_warrant"
        case convictionCount = "conviction_count"
        case primaryOffense = "primary_offense"
        case warrantNumber = "warrant_number"
        case lastArrestDate = "last_arrest_date"
        case warrantIssueDate = "warrant_issue_date"
    }
}
