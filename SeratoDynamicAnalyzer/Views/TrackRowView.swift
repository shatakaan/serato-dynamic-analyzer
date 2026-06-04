import SwiftUI
import AppKit

// MARK: - TrackRowView
// Kinetic Dark library row: 3px colored left edge, beatgrid icon, filename/path,
// mono BPM result, cancel button. Done and Failed rows wrap in a DisclosureGroup
// showing TrackDetailView. Uses @ObservedObject so only the affected row re-renders.

struct TrackRowView: View {
    @ObservedObject var item: TrackItem
    @ObservedObject var viewModel: BatchViewModel
    @State private var isHovered = false
    @State private var showBpmPopover: Bool = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var trackDisplayName: String {
        item.url.deletingPathExtension().lastPathComponent
    }

    private var trackSubtitle: String {
        item.url.deletingLastPathComponent().lastPathComponent
    }

    var body: some View {
        switch item.status {
        case .done, .failed:
            DisclosureGroup(isExpanded: $item.isExpanded) {
                TrackDetailView(item: item)
                    .padding(.leading, 3)
                    .padding(.bottom, 4)
            } label: {
                rowContent
            }
        case .pending, .analyzing:
            rowContent
        }
    }

    // MARK: - Row content (shared label for DisclosureGroup and plain rows)

    private var rowContent: some View {
        HStack(spacing: 0) {
            // 3px status edge
            Rectangle()
                .fill(Color.kdStatusEdge(item.status))
                .frame(width: 3)
                .animation(.easeInOut(duration: 0.2), value: item.status)

            // Beatgrid / status icon
            statusIcon
                .frame(width: 36, alignment: .center)

            // Track name + folder
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 4) {
                    Text(trackDisplayName)
                        .font(.kdBody)
                        .fontWeight(.semibold)
                        .foregroundStyle(Color.kdOnSurface)
                        .lineLimit(1)
                        .truncationMode(.middle)

                    // BPM override icon — Pending rows only
                    if item.status == .pending {
                        bpmOverrideButton
                    }
                }
                Text(trackSubtitle)
                    .font(.system(size: 11))
                    .foregroundStyle(Color.kdMuted)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.leading, 4)

            // Inline progress bar while analyzing
            if item.status == .analyzing && item.progress > 0 {
                ProgressView(value: item.progress)
                    .progressViewStyle(.linear)
                    .tint(Color.kdPrimary)
                    .frame(width: 60)
                    .padding(.trailing, 8)
            }

            // BPM result / state indicator
            bpmColumn
                .frame(width: 88, alignment: .trailing)
                .padding(.trailing, 8)

            // Cancel / remove button
            cancelButton
                .frame(width: 32)
                .padding(.trailing, 8)
        }
        .frame(minHeight: 44)
        .background(rowBackground)
        .animation(.easeInOut(duration: 0.15), value: isHovered)
        .onHover { isHovered = $0 }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(trackDisplayName), \(item.status.rawValue)")
    }

    // MARK: - BPM override icon button

    private var bpmOverrideButton: some View {
        let hasOverride = item.bpmMinOverride != nil || item.bpmMaxOverride != nil
        return Button {
            showBpmPopover = true
        } label: {
            Image(systemName: "slider.horizontal.3")
                .font(.system(size: 11))
                .foregroundColor(hasOverride ? Color.accentColor : Color(nsColor: .tertiaryLabelColor))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("BPM override for \(trackDisplayName)")
        .popover(isPresented: $showBpmPopover) {
            bpmOverridePopover
        }
    }

    // MARK: - BPM override popover content

    private var bpmOverridePopover: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("BPM Override")
                .font(.headline)
            Text(trackDisplayName)
                .font(.caption)
                .foregroundStyle(Color(nsColor: .secondaryLabelColor))
                .lineLimit(1)
                .truncationMode(.middle)

            HStack(spacing: 4) {
                Text("Min:")
                    .font(.caption)
                Stepper(
                    "",
                    value: Binding(
                        get: { item.bpmMinOverride ?? viewModel.globalBpmMin },
                        set: { item.bpmMinOverride = $0 }
                    ),
                    in: 20...((item.bpmMaxOverride ?? viewModel.globalBpmMax) - 1)
                )
                .labelsHidden()
                Text("\(item.bpmMinOverride ?? viewModel.globalBpmMin)")
                    .font(.body.monospacedDigit())
                    .frame(minWidth: 36)
            }

            HStack(spacing: 4) {
                Text("Max:")
                    .font(.caption)
                Stepper(
                    "",
                    value: Binding(
                        get: { item.bpmMaxOverride ?? viewModel.globalBpmMax },
                        set: { item.bpmMaxOverride = $0 }
                    ),
                    in: ((item.bpmMinOverride ?? viewModel.globalBpmMin) + 1)...300
                )
                .labelsHidden()
                Text("\(item.bpmMaxOverride ?? viewModel.globalBpmMax)")
                    .font(.body.monospacedDigit())
                    .frame(minWidth: 36)
            }

            HStack {
                Button("Reset") {
                    item.bpmMinOverride = nil
                    item.bpmMaxOverride = nil
                }
                .buttonStyle(.borderless)
                .font(.caption)
                .foregroundStyle(Color(nsColor: .secondaryLabelColor))

                Spacer()

                Button("Done") { showBpmPopover = false }
                    .buttonStyle(.borderedProminent)
                    .font(.caption)
            }
        }
        .padding(16)
        .frame(minWidth: 200)
    }

    // MARK: - Sub-views

    @ViewBuilder
    private var statusIcon: some View {
        switch item.status {
        case .pending:
            Image(systemName: "square.grid.3x3")
                .font(.system(size: 13))
                .foregroundStyle(Color.kdMuted.opacity(0.5))
        case .analyzing:
            ProgressView()
                .scaleEffect(0.7)
                .tint(Color.kdPrimary)
        case .done:
            Image(systemName: "square.grid.3x3.fill")
                .font(.system(size: 13))
                .foregroundStyle(Color.kdTertiary)
        case .failed:
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 12))
                .foregroundStyle(Color.kdSecondary)
        }
    }

    @ViewBuilder
    private var bpmColumn: some View {
        switch item.status {
        case .pending:
            Text("—.—")
                .font(.kdMono)
                .foregroundStyle(Color.kdMuted.opacity(0.4))

        case .analyzing:
            Text("···")
                .font(.kdMono)
                .foregroundStyle(Color.kdPrimary)

        case .done:
            if let r = item.result {
                VStack(alignment: .trailing, spacing: 1) {
                    Text(String(format: "%.2f", (r.bpmMin + r.bpmMax) / 2))
                        .font(.kdMonoLg)
                        .foregroundStyle(Color.kdTertiary)
                    if abs(r.bpmMax - r.bpmMin) > 0.5 {
                        Text(String(format: "%.1f–%.1f", r.bpmMin, r.bpmMax))
                            .font(.system(size: 9, weight: .medium, design: .monospaced))
                            .foregroundStyle(Color.kdMuted)
                    }
                }
            }

        case .failed:
            Text("ERR")
                .font(.kdMono)
                .foregroundStyle(Color.kdSecondary)
        }
    }

    @ViewBuilder
    private var cancelButton: some View {
        if item.status == .pending || item.status == .analyzing {
            CancelButtonView(item: item, viewModel: viewModel)
        } else {
            Spacer().frame(width: 32)
        }
    }

    private var rowBackground: Color {
        isHovered ? Color.kdSurface.opacity(0.6) : Color.clear
    }
}

// MARK: - CancelButtonView

private struct CancelButtonView: View {
    var item: TrackItem
    @ObservedObject var viewModel: BatchViewModel
    @State private var isHovered = false

    var body: some View {
        Button {
            viewModel.cancelTrack(item)
        } label: {
            Image(systemName: "xmark.circle.fill")
                .font(.system(size: 15))
                .foregroundStyle(isHovered ? Color.kdSecondary : Color.kdMuted.opacity(0.4))
        }
        .buttonStyle(.plain)
        .frame(width: 32, height: 44)
        .onHover { isHovered = $0 }
        .animation(.easeInOut(duration: 0.1), value: isHovered)
        .accessibilityLabel(item.status == .pending
            ? "Remove \(item.url.lastPathComponent) from queue"
            : "Cancel analysis of \(item.url.lastPathComponent)")
    }
}
