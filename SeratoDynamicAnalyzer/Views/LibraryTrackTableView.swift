import SwiftUI

// MARK: - LibraryTrackTableView
// Track list for the selected crate — column header + List(selection:) with LibraryTrackRow.
// Handles loading state, no-crate-selected state, and populated track list.

struct LibraryTrackTableView: View {
    @ObservedObject var viewModel: LibraryViewModel

    var body: some View {
        VStack(spacing: 0) {
            // Pinned column header row
            columnHeaders

            // Divider below headers
            Rectangle()
                .fill(Color.kdOutline)
                .frame(height: 1)

            // Content: loading spinner | no-crate message | track list
            trackContent
        }
    }

    // MARK: - Column headers

    private var columnHeaders: some View {
        HStack(spacing: 0) {
            // Spacer aligned with the beatgrid dot column (28pt)
            Spacer().frame(width: 32)

            Text("FILENAME")
                .font(.kdLabel)
                .foregroundStyle(Color.kdMuted)
                .frame(maxWidth: .infinity, alignment: .leading)

            Text("DURATION")
                .font(.kdLabel)
                .foregroundStyle(Color.kdMuted)
                .frame(width: 56, alignment: .trailing)

            Text("BPM")
                .font(.kdLabel)
                .foregroundStyle(Color.kdMuted)
                .frame(width: 72, alignment: .trailing)
                .padding(.trailing, 8)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 8)
        .background(Color.kdSurface)
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(Color.kdOutline)
                .frame(height: 1)
        }
    }

    // MARK: - Track content

    @ViewBuilder
    private var trackContent: some View {
        if viewModel.isLoadingTracks {
            loadingView
        } else if viewModel.selectedCrateID == nil {
            noCrateView
        } else {
            trackList
        }
    }

    private var loadingView: some View {
        VStack(spacing: 12) {
            Spacer()
            ProgressView()
                .tint(Color.kdPrimary)
            Text("Loading tracks...")
                .font(.kdBody)
                .foregroundStyle(Color.kdMuted)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.kdBg)
    }

    private var noCrateView: some View {
        VStack {
            Spacer()
            Text("Select a crate to view tracks")
                .font(.kdBody)
                .foregroundStyle(Color.kdMuted)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.kdBg)
    }

    private var trackList: some View {
        List(viewModel.trackList, id: \.id, selection: $viewModel.selectedTrackIDs) { track in
            LibraryTrackRow(track: track)
                .tag(track.id)
                .listRowBackground(Color.kdBg)
                .listRowInsets(EdgeInsets())
                .listRowSeparatorTint(Color.kdOutline.opacity(0.5))
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .background(Color.kdBg)
    }
}
