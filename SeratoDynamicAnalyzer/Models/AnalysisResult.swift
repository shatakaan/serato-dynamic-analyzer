import Foundation

// MARK: - WorkerEvent

enum WorkerEvent {
    case ready
    case progress(file: String, pct: Int)
    case result(AnalysisResult)
    case error(file: String, message: String)
}

// MARK: - AnalysisResult

struct AnalysisResult {
    let file: String
    let bpmMin: Double
    let bpmMax: Double
    let markerCount: Int
    let durationSec: Double
    let backupPath: String?
    let isDryRun: Bool

    init(json: [String: Any]) {
        file = json["file"] as? String ?? ""
        bpmMin = json["bpm_min"] as? Double ?? 0
        bpmMax = json["bpm_max"] as? Double ?? 0
        markerCount = json["marker_count"] as? Int ?? 0
        durationSec = json["duration_sec"] as? Double ?? 0
        backupPath = json["backup_path"] as? String
        isDryRun = json["dry_run"] as? Bool ?? false
    }
}
