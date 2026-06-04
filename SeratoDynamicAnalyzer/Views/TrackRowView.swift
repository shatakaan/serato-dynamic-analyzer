import SwiftUI
import AppKit

// MARK: - TrackRowView
// Per-row view in the batch queue list. Uses @ObservedObject on the TrackItem class
// so only the affected row re-renders when status/progress changes — not the full list.

struct TrackRowView: View {
    @ObservedObject var item: TrackItem
    @ObservedObject var viewModel: BatchViewModel

    var body: some View {
        HStack(alignment: .center, spacing: 8)  {
            // Status pill (fixed width to keep columns aligned)
            StatusPillView(status: item.status)
                .frame(width: 88)
                .accessibilityLabel("\(item.filename), status: \(item.status.rawValue)")

            // Filename (truncated in the middle for long paths)
            Text(item.filename)
                .font(.body)
                .lineLimit(1)
                .truncationMode(.middle)
                .frame(maxWidth: .infinity, alignment: .leading)

            // Status-dependent right column
            switch item.status {
            case .analyzing:
                ProgressView()
                    .scaleEffect(0.8)
                    .tint(.accentColor)
                    .frame(width: 80)
            case .done:
                if let result = item.result {
                    Text(String(format: "%.1f–%.1f", result.bpmMin, result.bpmMax))
                        .font(.caption)
                        .frame(width: 64)
                    Text("\(result.markerCount)")
                        .font(.caption)
                        .frame(width: 48)
                }
            case .failed:
                if let msg = item.errorMessage {
                    Text(msg)
                        .font(.caption)
                        .foregroundColor(.red)
                        .lineLimit(1)
                        .frame(maxWidth: 160)
                }
            case .pending:
                Spacer()
                    .frame(width: 0)
            }

            // Cancel / remove button (Pending and Analyzing rows only)
            if item.status == .pending || item.status == .analyzing {
                CancelButton(item: item, viewModel: viewModel)
            } else {
                Spacer()
                    .frame(width: 32)
            }
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 16)
        .frame(minHeight: 44)
    }
}

// MARK: - StatusPillView

private struct StatusPillView: View {
    var status: TrackStatus

    var body: some View {
        HStack(spacing: 4) {
            // Leading icon / spinner
            switch status {
            case .pending:
                Image(systemName: "clock")
                    .font(.caption)
            case .analyzing:
                ProgressView()
                    .scaleEffect(0.6)
            case .done:
                Image(systemName: "checkmark.circle.fill")
                    .font(.caption)
            case .failed:
                Image(systemName: "exclamationmark.circle.fill")
                    .font(.caption)
            }
            Text(status.rawValue)
                .font(.caption)
        }
        .padding(.vertical, 4)
        .padding(.horizontal, 8)
        .background(pillBackground(for: status))
        .foregroundColor(pillForeground(for: status))
        .cornerRadius(4)
    }

    private func pillBackground(for status: TrackStatus) -> Color {
        switch status {
        case .pending:   return Color(nsColor: .quaternaryLabelColor)
        case .analyzing: return Color.accentColor.opacity(0.15)
        case .done:      return Color.green.opacity(0.15)
        case .failed:    return Color.red.opacity(0.15)
        }
    }

    private func pillForeground(for status: TrackStatus) -> Color {
        switch status {
        case .pending:   return Color(nsColor: .secondaryLabelColor)
        case .analyzing: return Color.accentColor
        case .done:      return Color.green
        case .failed:    return Color.red
        }
    }
}

// MARK: - CancelButton

private struct CancelButton: View {
    var item: TrackItem
    @ObservedObject var viewModel: BatchViewModel
    @State private var isHovered: Bool = false

    var body: some View {
        Button {
            viewModel.cancelTrack(item)
        } label: {
            Image(systemName: "xmark.circle.fill")
                .font(.system(size: 16))
                .foregroundColor(isHovered
                    ? Color(nsColor: .secondaryLabelColor)
                    : Color(nsColor: .tertiaryLabelColor))
        }
        .buttonStyle(.plain)
        .frame(width: 32, height: 44)
        .onHover { hovering in isHovered = hovering }
        .accessibilityLabel(
            item.status == .pending
                ? "Remove \(item.filename) from queue"
                : "Cancel analysis of \(item.filename)"
        )
    }
}
