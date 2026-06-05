import SwiftUI

// MARK: - LibraryView
// HSplitView: CrateSidebarView (left, 180-320pt) + track table + toolbar (right).
// When ~/Music/_Serato_/ is absent: shows LibraryEmptyStateView in the right panel (D-06).
// D-03: HSplitView (macOS 13+); NavigationSplitView is prohibited.

struct LibraryView: View {
    @ObservedObject var libraryViewModel: LibraryViewModel
    @ObservedObject var batchViewModel: BatchViewModel
    @Binding var selectedTab: AppTab

    var body: some View {
        HSplitView {
            CrateSidebarView(viewModel: libraryViewModel)
                .frame(minWidth: 180, idealWidth: 220, maxWidth: 320)

            rightPanel
                .frame(minWidth: 400)
        }
        .background(Color.kdBg)
    }

    // MARK: - Right panel

    @ViewBuilder
    private var rightPanel: some View {
        if !libraryViewModel.seratoLibraryExists {
            LibraryEmptyStateView()
        } else {
            VStack(spacing: 0) {
                LibraryTrackTableView(viewModel: libraryViewModel)
                LibraryToolbarView(viewModel: libraryViewModel,
                                   batchViewModel: batchViewModel,
                                   selectedTab: $selectedTab)
            }
        }
    }
}
