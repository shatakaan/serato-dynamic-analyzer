import SwiftUI

// MARK: - LibraryToolbarView
// 44pt bar pinned at the bottom of the right panel.
// Contains the selected-count label and the "ANALYZE SELECTED" CTA button.
// Button state: enabled (kdPrimary fill) ↔ disabled (kdOutline fill) based on selection.

struct LibraryToolbarView: View {
    @ObservedObject var viewModel: LibraryViewModel
    @ObservedObject var batchViewModel: BatchViewModel
    @Binding var selectedTab: AppTab

    var body: some View {
        HStack(spacing: 0) {
            Spacer()

            // Selected count label — hidden when selection is empty
            if !viewModel.selectedTrackIDs.isEmpty {
                Text("\(viewModel.selectedTrackIDs.count) selected")
                    .font(.kdLabel)
                    .foregroundStyle(Color.kdMuted)
                    .padding(.trailing, 12)
            }

            // ANALYZE SELECTED button
            Button {
                viewModel.analyzeSelected(batchViewModel: batchViewModel,
                                          selectedTab: $selectedTab)
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "arrow.right.circle.fill")
                        .font(.system(size: 12, weight: .bold))
                    Text("ANALYZE SELECTED")
                        .font(.kdLabel)
                }
                .foregroundStyle(
                    viewModel.selectedTrackIDs.isEmpty ? Color.kdMuted : Color.kdBg
                )
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(
                    viewModel.selectedTrackIDs.isEmpty ? Color.kdOutline : Color.kdPrimary
                )
                .cornerRadius(6)
            }
            .buttonStyle(.plain)
            .disabled(viewModel.selectedTrackIDs.isEmpty)
            .animation(.easeInOut(duration: 0.15), value: viewModel.selectedTrackIDs.isEmpty)
        }
        .padding(.horizontal, 20)
        .frame(height: 44)
        .background(Color.kdBg)
        .overlay(alignment: .top) {
            Rectangle()
                .fill(Color.kdOutline)
                .frame(height: 1)
        }
    }
}
