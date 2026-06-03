import SwiftUI
import UniformTypeIdentifiers
import AppKit

struct ContentView: View {
    @StateObject private var viewModel = AnalysisViewModel()
    @State private var isTargeted: Bool = false
    @State private var showFilePicker: Bool = false

    var body: some View {
        VStack(spacing: 20) {
            // Drop Zone (D-05: primary affordance, center)
            dropZone
            // File picker button (secondary)
            Button("Choose Track…") { showFilePicker = true }
                .disabled(viewModel.isRunning)
            // Analyze button + Dry Run toggle (D-07)
            HStack {
                Button("Analyze") { viewModel.startAnalysis() }
                    .disabled(!viewModel.workerReady || viewModel.isRunning
                              || viewModel.trackURL == nil)
                Toggle("Dry Run", isOn: $viewModel.isDryRun)
                    .disabled(viewModel.isRunning)
            }
            // Worker warmup hint — shown while Python is loading libraries
            if !viewModel.workerReady && !viewModel.isRunning {
                Text("Starting analysis engine…")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            // Progress view (D-06)
            if viewModel.isRunning {
                VStack {
                    ProgressView(value: viewModel.progress)
                    Text(viewModel.statusText).font(.caption)
                }
            }
            // Result card (D-08)
            if let result = viewModel.result {
                resultCard(result)
            }
            // Error display
            if let error = viewModel.errorMessage {
                Text(error)
                    .foregroundColor(.red)
                    .font(.caption)
                    .multilineTextAlignment(.center)
            }
        }
        .padding(24)
        .frame(minWidth: 480, minHeight: 360)
        // Drop zone handler — T-02-04-01: standardizedFileURL applied immediately
        .onDrop(of: [UTType.fileURL], isTargeted: $isTargeted) { providers in
            guard let provider = providers.first else { return false }
            _ = provider.loadObject(ofClass: URL.self) { url, _ in
                guard let url = url else { return }
                DispatchQueue.main.async {
                    viewModel.trackURL = url.standardizedFileURL
                }
            }
            return true
        }
        // File picker (secondary track selection)
        .fileImporter(
            isPresented: $showFilePicker,
            allowedContentTypes: [
                UTType.mp3,
                UTType(filenameExtension: "aiff") ?? UTType.audio,
                UTType(filenameExtension: "wav")  ?? UTType.audio,
            ],
            allowsMultipleSelection: false
        ) { result in
            if case .success(let urls) = result, let url = urls.first {
                viewModel.trackURL = url.standardizedFileURL
            }
        }
        // ANAL-04: Serato-running blocking alert (D-07)
        // T-02-04-04: "Continue Anyway" sets skipSeratoCheck so the second
        // startAnalysis() call skips the Serato check and proceeds to write.
        .alert("Serato DJ Pro is Running", isPresented: $viewModel.showSeratoAlert) {
            Button("Cancel", role: .cancel) { }
            Button("Continue Anyway", role: .destructive) {
                viewModel.skipSeratoCheck = true
                viewModel.startAnalysis()
            }
        } message: {
            Text("Writing to a track loaded in Serato may cause file corruption. Close Serato before analyzing, or eject the track from the deck.")
        }
        // Start Python worker after first render (RISK-06: prevents blocking first frame)
        .task { await viewModel.startWorker() }
    }

    // MARK: - Drop Zone subview

    var dropZone: some View {
        RoundedRectangle(cornerRadius: 12)
            .strokeBorder(
                isTargeted ? Color.accentColor : Color.secondary,
                lineWidth: isTargeted ? 3 : 1
            )
            .frame(height: 160)
            .overlay(
                VStack(spacing: 8) {
                    Image(systemName: "music.note")
                        .font(.system(size: 40))
                        .foregroundColor(.secondary)
                    if let url = viewModel.trackURL {
                        Text(url.lastPathComponent).font(.headline)
                    } else {
                        Text("Drop Audio File Here")
                            .foregroundColor(.secondary)
                    }
                }
            )
    }

    // MARK: - Result card (D-08, SAFE-01, SAFE-02)

    @ViewBuilder
    func resultCard(_ result: AnalysisResult) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(URL(fileURLWithPath: result.file).lastPathComponent)
                .font(.headline)
            Text("BPM: \(String(format: "%.1f", result.bpmMin)) – \(String(format: "%.1f", result.bpmMax))")
            Text("Markers: \(result.markerCount)  ·  Duration: \(String(format: "%.1f", result.durationSec))s")
            // SAFE-02: dry run badge
            if result.isDryRun {
                Text("DRY RUN — no changes written")
                    .foregroundColor(.orange)
                    .bold()
            }
            // SAFE-01: backup path as clickable Finder-reveal link
            if let backupPath = result.backupPath {
                Button("Backup: \(URL(fileURLWithPath: backupPath).lastPathComponent)") {
                    NSWorkspace.shared.activateFileViewerSelecting(
                        [URL(fileURLWithPath: backupPath)]
                    )
                }
                .buttonStyle(.link)
                .font(.caption)
            }
        }
        .padding(12)
        .background(Color(nsColor: .controlBackgroundColor))
        .cornerRadius(8)
    }
}
