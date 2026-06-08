import SwiftUI

// MARK: - AppTab

/// Navigation tabs for the main ContentView TabView.
/// Defined here (Plan 02) so LibraryViewModel.analyzeSelected can switch tabs.
/// Plan 03's ContentView reuses this declaration — do NOT redeclare it there.
enum AppTab: Hashable {
    case library
    case queue
}

// MARK: - LibraryViewModel

/// State owner for the Serato crate tree and track list.
/// Owns a DEDICATED PythonBridge instance — never shared with BatchViewModel's worker pool
/// (RESEARCH Pitfall 4 / T-04-IPC: shared stdout would interleave JSON-Lines events).
///
/// @MainActor ensures all @Published mutations happen on the main thread.
/// ObservableObject (NOT @Observable) — @Observable requires macOS 14+; target is 13.0.
@MainActor
class LibraryViewModel: ObservableObject {

    // MARK: Published state

    @Published var crateTree: [SeratoCrate] = []
    @Published var selectedCrateID: UUID? = nil
    @Published var trackList: [LibraryTrack] = []
    @Published var selectedTrackIDs: Set<UUID> = []
    @Published var isLoadingTracks: Bool = false
    @Published var isLoadingCrates: Bool = false

    // MARK: Private

    /// Dedicated bridge — the library worker is separate from BatchViewModel's pool.
    private let libraryBridge = PythonBridge()
    private var isWorkerReady = false

    // MARK: Serato library detection

    var seratoLibraryPath: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Music/_Serato_")
    }

    var seratoLibraryExists: Bool {
        FileManager.default.fileExists(atPath: seratoLibraryPath.path)
    }

    // MARK: Worker lifecycle

    /// Start the dedicated library Python worker.
    /// Mirrors BatchViewModel.startWorkerSlot but with no slot index.
    func startLibraryWorker() async {
        do {
            try await libraryBridge.startWorker()
            isWorkerReady = await libraryBridge.waitForReady(timeout: 30)
            if !isWorkerReady {
                fputs("[LibraryViewModel] Library worker failed to become ready within 30s\n", stderr)
            }
        } catch {
            fputs("[LibraryViewModel] Library worker failed to start: \(error)\n", stderr)
        }
    }

    // MARK: Data loading

    /// Load the full Serato crate tree from the Python library backend.
    /// listCrates() handles worker start + single-session read (CR-03).
    func loadCrateTree() {
        Task {
            isLoadingCrates = true
            let tree = await libraryBridge.listCrates()
            crateTree = tree
            isLoadingCrates = false
        }
    }

    /// Select a crate and load its tracks.
    /// Guards on cratePath != nil — non-selectable implied parent nodes never issue list_tracks
    /// (T-04-NULLPATH: prevents DoS from clicking on folder-only nodes).
    func selectCrate(_ crate: SeratoCrate) {
        guard let path = crate.cratePath else { return }
        selectedCrateID = crate.id
        // Clear previous track list and selection immediately (UI-SPEC interaction contract)
        trackList = []
        selectedTrackIDs = []
        Task {
            isLoadingTracks = true
            let list = await libraryBridge.listTracks(crate: path)
            trackList = list
            isLoadingTracks = false
        }
    }

    // MARK: Queue integration

    /// Add all selected tracks to the batch queue and switch to the Queue tab.
    func analyzeSelected(batchViewModel: BatchViewModel, selectedTab: Binding<AppTab>) {
        for id in selectedTrackIDs {
            if let track = trackList.first(where: { $0.id == id }) {
                batchViewModel.addLibraryTrack(url: track.url)
            }
        }
        selectedTrackIDs = []
        selectedTab.wrappedValue = .queue
    }
}
