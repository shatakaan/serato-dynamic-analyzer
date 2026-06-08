import SwiftUI
import UniformTypeIdentifiers
import AppKit

// NOTE: AppTab enum is declared in LibraryViewModel.swift — do NOT redeclare here.

struct ContentView: View {
    @StateObject private var batchViewModel = BatchViewModel()
    @StateObject private var libraryViewModel = LibraryViewModel()
    @State private var selectedTab: AppTab = .library

    var body: some View {
        VStack(spacing: 0) {
            AppHeaderView()
            TabView(selection: $selectedTab) {
                LibraryView(libraryViewModel: libraryViewModel,
                            batchViewModel: batchViewModel,
                            selectedTab: $selectedTab)
                    .tabItem { Label("Library", systemImage: "book.fill") }
                    .tag(AppTab.library)

                VStack(spacing: 0) {
                    BatchHeaderView(viewModel: batchViewModel)
                    BatchQueueView(viewModel: batchViewModel)
                }
                .tabItem { Label("Queue", systemImage: "list.bullet") }
                .tag(AppTab.queue)
            }
        }
        .background(Color.kdBg)
        .frame(minWidth: 700, idealWidth: 820, minHeight: 480)
        .alert("Serato DJ Pro is Running", isPresented: $batchViewModel.showSeratoAlert) {
            Button("Cancel", role: .cancel) { }
            Button("Continue Anyway", role: .destructive) {
                batchViewModel.skipSeratoCheck = true
                batchViewModel.startBatch()
            }
        } message: {
            Text("Writing to a track loaded in Serato may cause file corruption. Close Serato before analyzing, or eject the track from the deck.")
        }
        .task { await batchViewModel.startInitialWorker() }
        .task { libraryViewModel.loadCrateTree() }
    }
}
