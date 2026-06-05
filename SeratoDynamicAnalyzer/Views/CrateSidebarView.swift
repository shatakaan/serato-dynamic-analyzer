import SwiftUI

// MARK: - CrateSidebarView
// Sidebar showing the nested Serato crate hierarchy via OutlineGroup inside a List(selection:).
// Selection changes trigger LibraryViewModel.selectCrate via onChange.
// Loading state: ProgressView centered (replaces tree content entirely).

struct CrateSidebarView: View {
    @ObservedObject var viewModel: LibraryViewModel

    var body: some View {
        Group {
            if viewModel.isLoadingCrates {
                VStack {
                    Spacer()
                    ProgressView()
                        .tint(Color.kdPrimary)
                    Spacer()
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color.kdSurface)
            } else if viewModel.crateTree.isEmpty && !viewModel.seratoLibraryExists {
                // No Serato library — empty state shown inline in sidebar
                VStack(spacing: 8) {
                    Spacer()
                    Text("Could not read Serato library.")
                        .font(.kdBody)
                        .foregroundStyle(Color.kdSecondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 12)
                    Spacer()
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color.kdSurface)
            } else {
                crateList
            }
        }
    }

    private var crateList: some View {
        List(selection: $viewModel.selectedCrateID) {
            OutlineGroup(viewModel.crateTree,
                         id: \.id,
                         children: \.children) { crate in
                Label(crate.name,
                      systemImage: crate.id == viewModel.selectedCrateID ? "folder.fill" : "folder")
                    .font(.kdBody)
                    .foregroundStyle(crate.isSelectable ? Color.kdOnSurface : Color.kdMuted)
                    .tag(crate.id)
            }
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)
        .background(Color.kdSurface)
        .onChange(of: viewModel.selectedCrateID) { id in
            if let id, let crate = viewModel.crateTree.flattenedFind(id: id) {
                viewModel.selectCrate(crate)
            }
        }
    }
}
