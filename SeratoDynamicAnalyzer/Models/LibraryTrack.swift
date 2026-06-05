import Foundation

// MARK: - BeatgridSource

/// Indicates the origin of the beatgrid tag in a Serato library track.
enum BeatgridSource: String {
    case none   = "none"    // no GEOB:Serato BeatGrid tag present
    case serato = "serato"  // tagged by Serato DJ (version byte 0x01 0x00)
    case tool   = "tool"    // tagged by this tool (version byte 0x01 0x01, D-07)
}

// MARK: - LibraryTrack

/// A track record read from a Serato crate.
/// Struct (not class) — rebuilt whole on each crate selection; no per-field @Published needed.
struct LibraryTrack: Identifiable {
    let id = UUID()
    let url: URL
    let filename: String
    let beatgridSource: BeatgridSource
    let durationSec: Double?    // nil for M4A/AAC (Phase 5 will add M4A duration support)

    init(json: [String: Any]) {
        let path = json["path"] as? String ?? ""
        url = URL(fileURLWithPath: path)
        filename = json["filename"] as? String ?? url.lastPathComponent
        let src = json["beatgrid_source"] as? String ?? "none"
        beatgridSource = BeatgridSource(rawValue: src) ?? .none
        durationSec = json["duration_sec"] as? Double
    }
}
