import Foundation

// MARK: - SeratoCrate

/// A node in the Serato crate tree.
/// children is Optional — nil means a leaf node (no disclosure triangle in OutlineGroup).
/// A non-nil but empty children array would still show a disclosure triangle; use nil to suppress.
/// (RESEARCH.md Pitfall 6 — OutlineGroup leaf detection)
struct SeratoCrate: Identifiable {
    let id = UUID()
    let name: String
    let cratePath: String?         // nil for implied parent nodes (folder without own .crate file)
    var children: [SeratoCrate]?   // nil = leaf (no disclosure triangle); non-nil = parent

    var isSelectable: Bool { cratePath != nil }

    init(json: [String: Any]) {
        name = json["name"] as? String ?? ""
        // crate_path is nil when the JSON value is null or absent (implied parent)
        if let path = json["crate_path"] as? String {
            cratePath = path
        } else {
            cratePath = nil
        }
        // children is nil when the JSON value is null/absent (leaf node)
        if let rawChildren = json["children"] as? [[String: Any]] {
            children = rawChildren.map { SeratoCrate(json: $0) }
        } else {
            children = nil
        }
    }
}

// MARK: - Array<SeratoCrate> depth-first search

extension Array where Element == SeratoCrate {
    /// Depth-first search for a crate with the given id.
    /// Used by Plan 03's sidebar onChange to resolve the selected crate.
    func flattenedFind(id: UUID) -> SeratoCrate? {
        for crate in self {
            if crate.id == id { return crate }
            if let found = crate.children?.flattenedFind(id: id) {
                return found
            }
        }
        return nil
    }
}
