import Foundation
import AppKit

// MARK: - BatchViewModel
// Root state owner for the batch queue (Phase 3).
// @MainActor ensures all @Published mutations happen on the main thread.
// ObservableObject (NOT @Observable) — @Observable requires macOS 14+; target is 13.0.

@MainActor
class BatchViewModel: ObservableObject {
    @Published var tracks: [TrackItem] = []
    @Published var globalBpmMin: Int = 60
    @Published var globalBpmMax: Int = 200
    @Published var isDryRun: Bool = false
    @Published var workerReadyCount: Int = 0
    @Published var showSeratoAlert: Bool = false
    @Published var isScanning: Bool = false

    /// Set to true before calling startBatch() from the Serato alert "Continue Anyway"
    /// button so the Serato-running check is skipped on that second call (T-02-04-04).
    var skipSeratoCheck: Bool = false

    /// Dynamic pool of PythonBridge workers; grows from 0 to max 4.
    private var workers: [PythonBridge] = []
    /// Slot index → active TrackItem currently being analyzed on that worker.
    private var assignments: [Int: TrackItem] = [:]
    /// Deduplication set — silently ignores re-dropped URLs.
    private var queuedURLs: Set<URL> = []

    // MARK: - Computed Properties

    @Published var completedCount: Int = 0

    var totalCount: Int { tracks.count }

    var isAnalyzing: Bool {
        tracks.contains { $0.status == .analyzing }
    }

    var canStartBatch: Bool {
        !tracks.isEmpty && tracks.contains { $0.status == .pending }
    }

    // MARK: - Worker Startup

    /// Called once from ContentView .task{} to warm up the first Python worker.
    func startInitialWorker() async {
        let bridge = PythonBridge()
        workers.append(bridge)
        await startWorkerSlot(bridge: bridge, slotIndex: 0)
    }

    /// Start a single worker slot: launch the Python process and wait for the ready signal.
    func startWorkerSlot(bridge: PythonBridge, slotIndex: Int) async {
        do {
            try await bridge.startWorker()
            let ready = await bridge.waitForReady(timeout: 30)
            if ready {
                workerReadyCount += 1
                dispatchNextPendingTracks()  // slot is now ready — assign pending tracks
            } else {
                fputs("[BatchViewModel] Worker slot \(slotIndex) failed to become ready within 30s\n", stderr)
            }
        } catch {
            fputs("[BatchViewModel] Worker slot \(slotIndex) failed to start: \(error)\n", stderr)
        }
    }

    // MARK: - Serato Check (ANAL-04)

    func isSeratoRunning() -> Bool {
        NSWorkspace.shared.runningApplications
            .contains { $0.bundleIdentifier == "com.serato.seratodj" }
    }

    // MARK: - Batch Control

    /// Called by "Analyze All" button. Checks Serato once for the whole batch.
    func startBatch() {
        guard canStartBatch else { return }
        // ANAL-04: single Serato check for the entire batch (not per-track — RESEARCH.md Pitfall 6)
        if !isDryRun && !skipSeratoCheck && isSeratoRunning() {
            showSeratoAlert = true
            return
        }
        skipSeratoCheck = false
        dispatchNextPendingTracks()
    }

    /// Synchronous (non-async) — no await inside this method. This prevents actor
    /// reentrancy double-dispatch when multiple Tasks call back into @MainActor
    /// simultaneously. (RESEARCH.md Pitfall 4)
    func dispatchNextPendingTracks() {
        let pendingTracks = tracks.filter { $0.status == .pending }
        guard !pendingTracks.isEmpty else { return }

        // Dynamically grow pool up to 4 based on pending depth.
        let desiredWorkers = min(max(1, pendingTracks.count), 4)
        if workers.count < desiredWorkers {
            for _ in workers.count..<desiredWorkers {
                let bridge = PythonBridge()
                let slotIndex = workers.count
                workers.append(bridge)
                Task { await self.startWorkerSlot(bridge: bridge, slotIndex: slotIndex) }
            }
        }

        // Assign pending tracks to idle worker slots.
        // Only assign to slots that are confirmed ready (index < workerReadyCount).
        // Newly-appended bridges are started asynchronously via startWorkerSlot();
        // they call dispatchNextPendingTracks() again once ready, preventing the
        // double-startWorker() race (CR-01).
        for (slotIndex, bridge) in workers.enumerated() {
            guard slotIndex < workerReadyCount else { continue }  // slot not yet ready
            guard assignments[slotIndex] == nil else { continue }  // slot busy
            guard let next = tracks.first(where: { $0.status == .pending }) else { break }
            next.status = .analyzing
            assignments[slotIndex] = next
            let startTime = Date()
            Task {
                let stream = await bridge.analyzeStream(
                    filePath: next.url.path,
                    bpmMin: next.bpmMinOverride ?? self.globalBpmMin,
                    bpmMax: next.bpmMaxOverride ?? self.globalBpmMax,
                    dryRun: self.isDryRun
                )
                for await event in stream {
                    await self.handleWorkerEvent(event, trackItem: next,
                                                 slotIndex: slotIndex, startTime: startTime)
                }
            }
        }
    }

    // MARK: - Worker Event Handling

    func handleWorkerEvent(_ event: WorkerEvent, trackItem: TrackItem,
                           slotIndex: Int, startTime: Date) async {
        switch event {
        case .ready:
            break
        case .progress(_, let pct):
            trackItem.progress = Double(pct) / 100.0
        case .result(let r):
            trackItem.result = r
            trackItem.analysisDuration = Date().timeIntervalSince(startTime)
            trackItem.status = .done
            completedCount += 1
            assignments[slotIndex] = nil
            dispatchNextPendingTracks()
        case .error(_, let msg):
            trackItem.errorMessage = msg
            trackItem.analysisDuration = Date().timeIntervalSince(startTime)
            trackItem.status = .failed
            completedCount += 1
            assignments[slotIndex] = nil
            dispatchNextPendingTracks()
        }
    }

    // MARK: - Queue Management

    /// Entry point for files/folders dropped onto the window.
    func addDroppedURL(_ url: URL) async {
        var isDir: ObjCBool = false
        FileManager.default.fileExists(atPath: url.path, isDirectory: &isDir)

        if isDir.boolValue {
            isScanning = true
            let urls = await scanFolder(url)
            appendUniqueURLs(urls)
            isScanning = false
        } else {
            let ext = url.pathExtension.lowercased()
            guard ["mp3", "aiff", "aif", "wav", "m4a", "mp4"].contains(ext) else { return }
            appendUniqueURL(url)
        }
    }

    /// Recursively enumerate a folder for supported audio files.
    /// Runs on a background Task to avoid blocking the main thread.
    private func scanFolder(_ url: URL) async -> [URL] {
        return await Task.detached(priority: .userInitiated) {
            var results: [URL] = []
            guard let enumerator = FileManager.default.enumerator(
                at: url,
                includingPropertiesForKeys: [.isRegularFileKey],
                options: [.skipsHiddenFiles, .skipsPackageDescendants]
            ) else { return results }
            for case let fileURL as URL in enumerator {
                let ext = fileURL.pathExtension.lowercased()
                if ["mp3", "aiff", "aif", "wav", "m4a", "mp4"].contains(ext) {
                    results.append(fileURL.standardizedFileURL)
                }
            }
            return results
        }.value
    }

    private func appendUniqueURL(_ url: URL) {
        let standardized = url.standardizedFileURL
        guard !queuedURLs.contains(standardized) else { return }
        queuedURLs.insert(standardized)
        tracks.append(TrackItem(url: standardized))
    }

    private func appendUniqueURLs(_ urls: [URL]) {
        for url in urls {
            appendUniqueURL(url)
        }
    }

    // MARK: - Library Integration (Plan 04-02)

    /// Called by LibraryViewModel.analyzeSelected() — same dedup as addDroppedURL.
    func addLibraryTrack(url: URL) {
        appendUniqueURL(url)
    }

    // MARK: - Per-Track Cancel (D-11)

    func cancelTrack(_ item: TrackItem) {
        if item.status == .pending {
            tracks.removeAll { $0.id == item.id }
            queuedURLs.remove(item.url.standardizedFileURL)
        } else if item.status == .analyzing {
            if let slotIndex = assignments.first(where: { $0.value.id == item.id })?.key {
                let worker = workers[slotIndex]
                Task { await worker.terminate() }
                item.errorMessage = "Cancelled by user"
                item.status = .failed
                completedCount += 1
                assignments[slotIndex] = nil
                dispatchNextPendingTracks()
            }
        }
    }
}
