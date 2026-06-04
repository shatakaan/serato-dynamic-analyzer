import SwiftUI
import AppKit

// MARK: - TrackDetailView
// Accordion detail content rendered inside DisclosureGroup for Done and Failed rows.
// @ObservedObject ensures this view re-renders when item.result or item.errorMessage changes
// without triggering full-list diffing (class reference semantics — RESEARCH.md Pitfall 5).

struct TrackDetailView: View {
    @ObservedObject var item: TrackItem

    var body: some View {
        switch item.status {
        case .done:
            doneContent
        case .failed:
            failedContent
        default:
            EmptyView()
        }
    }

    // MARK: - Done expanded content

    @ViewBuilder
    private var doneContent: some View {
        HStack(alignment: .top, spacing: 16) {
            // Left: analysis metrics
            VStack(alignment: .leading, spacing: 4) {
                if let result = item.result {
                    Text("BPM range: \(String(format: "%.1f", result.bpmMin))–\(String(format: "%.1f", result.bpmMax))")
                        .font(.caption)
                    Text("Markers: \(result.markerCount)")
                        .font(.caption)
                    Text("Duration: \(String(format: "%.1f", result.durationSec))s")
                        .font(.caption)
                    if let duration = item.analysisDuration {
                        Text("Analysis time: \(String(format: "%.1f", duration))s")
                            .font(.caption)
                    }
                }
            }

            Spacer()

            // Right: backup link and dry run badge
            VStack(alignment: .trailing, spacing: 4) {
                if let backupPath = item.result?.backupPath {
                    Button("Show Backup in Finder") {
                        NSWorkspace.shared.activateFileViewerSelecting(
                            [URL(fileURLWithPath: backupPath)]
                        )
                    }
                    .buttonStyle(.link)
                    .font(.caption)
                }
                if item.result?.isDryRun == true {
                    Text("DRY RUN — no changes written")
                        .font(.caption)
                        .foregroundColor(.orange)
                        .bold()
                }
            }
        }
        .padding(16)
        .background(Color(nsColor: .controlBackgroundColor))
        .cornerRadius(6)
    }

    // MARK: - Failed expanded content

    @ViewBuilder
    private var failedContent: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Error:")
                .font(.caption)
                .bold()
            if let msg = item.errorMessage {
                Text(msg)
                    .font(.caption)
                    .foregroundColor(.red)
            }
            Text("File: \(item.filename)")
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .padding(16)
        .background(Color(nsColor: .controlBackgroundColor))
        .cornerRadius(6)
    }
}
