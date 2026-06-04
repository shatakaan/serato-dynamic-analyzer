import SwiftUI
import UniformTypeIdentifiers
import AppKit

struct ContentView: View {
    @StateObject private var viewModel = BatchViewModel()

    var body: some View {
        VStack(spacing: 0) {
            AppHeaderView()
            BatchHeaderView(viewModel: viewModel)
            BatchQueueView(viewModel: viewModel)
        }
        .background(Color.kdBg)
        .frame(minWidth: 700, idealWidth: 820, minHeight: 480)
        .alert("Serato DJ Pro is Running", isPresented: $viewModel.showSeratoAlert) {
            Button("Cancel", role: .cancel) { }
            Button("Continue Anyway", role: .destructive) {
                viewModel.skipSeratoCheck = true
                viewModel.startBatch()
            }
        } message: {
            Text("Writing to a track loaded in Serato may cause file corruption. Close Serato before analyzing, or eject the track from the deck.")
        }
        .task { await viewModel.startInitialWorker() }
    }
}
