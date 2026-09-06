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

struct LicenseLookup: Decodable, Identifiable {
    let type: String
    let status: String
    let message: String
    let name: String?
    let number: String?
    let state: String?
    let expirationDate: String?
    let mismatches: [String]

    var id: String { "\(status)-\(state ?? "")-\(number ?? "")" }
    var shouldAlert: Bool {
        ["license_expired", "license_mismatch", "license_not_found", "invalid_barcode"]
            .contains(status)
    }

    enum CodingKeys: String, CodingKey {
        case type, status, message, name, number, state, mismatches
        case expirationDate = "expiration_date"
    }
}
