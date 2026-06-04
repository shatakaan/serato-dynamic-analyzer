import SwiftUI
import UniformTypeIdentifiers
import AppKit

struct ContentView: View {
    @StateObject private var viewModel = BatchViewModel()

    var body: some View {
        VStack(spacing: 0) {
            BatchHeaderView(viewModel: viewModel)
            BatchQueueView(viewModel: viewModel)
        }
        .frame(minWidth: 640, minHeight: 480)
        // ANAL-04: Serato-running blocking alert (D-07)
        // T-02-04-04: "Continue Anyway" sets skipSeratoCheck so the second
        // startBatch() call skips the Serato check and proceeds to write.
        .alert("Serato DJ Pro is Running", isPresented: $viewModel.showSeratoAlert) {
            Button("Cancel", role: .cancel) { }
            Button("Continue Anyway", role: .destructive) {
                viewModel.skipSeratoCheck = true
                viewModel.startBatch()
            }
        } message: {
            Text("Writing to a track loaded in Serato may cause file corruption. Close Serato before analyzing, or eject the track from the deck.")
        }
        // Start initial Python worker after first render (RISK-06: prevents blocking first frame)
        .task { await viewModel.startInitialWorker() }
    }
}
