import Foundation
import AppKit

// MARK: - AnalysisViewModel

@MainActor
class AnalysisViewModel: ObservableObject {
    @Published var trackURL: URL?
    @Published var progress: Double = 0.0
    @Published var statusText: String = "Drop a track to analyze"
    @Published var result: AnalysisResult?
    @Published var errorMessage: String?
    @Published var isRunning: Bool = false
    @Published var isDryRun: Bool = false
    @Published var workerReady: Bool = false
    @Published var showSeratoAlert: Bool = false

    private let bridge = PythonBridge()

    // MARK: Worker startup (call from .task{} in Scene or ContentView)

    func startWorker() async {
        do {
            try await bridge.startWorker()
            let ready = await bridge.waitForReady(timeout: 30)
            workerReady = ready
            if !ready {
                errorMessage = "Analysis engine failed to start within 30 seconds"
            }
        } catch {
            errorMessage = "Failed to launch Python worker: \(error)"
        }
    }

    // MARK: Serato check (ANAL-04)

    func isSeratoRunning() -> Bool {
        NSWorkspace.shared.runningApplications
            .contains { $0.bundleIdentifier == "com.serato.seratodj" }
    }

    // MARK: Start analysis

    func startAnalysis() {
        guard let url = trackURL else { return }
        guard !isRunning else { return }

        // ANAL-04: block write if Serato is open (unless dry run)
        if !isDryRun && isSeratoRunning() {
            showSeratoAlert = true
            return
        }

        isRunning = true
        progress = 0.0
        result = nil
        errorMessage = nil

        // Normalize dropped URL — Finder may give file reference URLs (Pitfall 5)
        let resolvedURL = url.standardizedFileURL

        Task { @MainActor in
            let stream = await bridge.analyzeStream(
                filePath: resolvedURL.path,
                bpmMin: 60,
                bpmMax: 200,
                dryRun: isDryRun
            )
            for await event in stream {
                switch event {
                case .ready:
                    break
                case .progress(_, let pct):
                    self.progress = Double(pct) / 100.0
                    self.statusText = "Analyzing… \(pct)%"
                case .result(let r):
                    self.result = r
                    self.isRunning = false
                    self.statusText = "Done"
                case .error(_, let msg):
                    self.errorMessage = msg
                    self.isRunning = false
                    self.statusText = "Error"
                }
            }
        }
    }
}
