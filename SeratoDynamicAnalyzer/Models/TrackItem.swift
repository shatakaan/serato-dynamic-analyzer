import Foundation

// MARK: - TrackStatus

enum TrackStatus: String {
    case pending   = "Pending"
    case analyzing = "Analyzing"
    case done      = "Done"
    case failed    = "Failed"
}

// MARK: - TrackItem
// Must be a class (not struct) so that individual row updates are scoped to the
// affected row view rather than triggering full-array diffing. (RESEARCH.md Pitfall 5)
// @Observable is intentionally NOT used — requires macOS 14+; project targets 13.0.

@MainActor
class TrackItem: ObservableObject, Identifiable {
    let id = UUID()
    let url: URL
    var filename: String { url.lastPathComponent }

    @Published var status: TrackStatus = .pending
    @Published var progress: Double = 0.0
    @Published var result: AnalysisResult? = nil
    @Published var errorMessage: String? = nil
    @Published var analysisDuration: TimeInterval? = nil
    @Published var isExpanded: Bool = false
    @Published var bpmMinOverride: Int? = nil
    @Published var bpmMaxOverride: Int? = nil

    init(url: URL) {
        self.url = url
    }
}
