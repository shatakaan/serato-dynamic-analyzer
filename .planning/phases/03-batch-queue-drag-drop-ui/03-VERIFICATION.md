---
phase: 03-batch-queue-drag-drop-ui
verified: 2026-06-04T00:00:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Drop individual MP3/AIFF/WAV files onto the window"
    expected: "Each file appears immediately as a Pending row with status pill"
    why_human: "Drag-and-drop gesture from Finder cannot be tested programmatically"
  - test: "Drop a folder containing audio files"
    expected: "All MP3/AIFF/WAV files recursively discovered and added as Pending rows; non-audio files ignored"
    why_human: "File system enumeration triggered by drop gesture requires human to exercise"
  - test: "Click 'Analyze All', wait for completion"
    expected: "Row pills transition Pending → Analyzing → Done/Failed; header counter 'X / N TRACKS' updates live; up to 4 parallel workers active"
    why_human: "Requires bundled Python backend; runtime parallel worker behavior not statically verifiable"
  - test: "Click a Done row to expand it"
    expected: "Accordion opens showing BPM range, marker count, analysis duration, and 'Show Backup in Finder' link if backup exists"
    why_human: "UI-03 accordion expansion requires running app with real analysis result data"
  - test: "Click a Failed row to expand it"
    expected: "Accordion shows specific, human-readable Python error message in red (not just 'failed')"
    why_human: "UI-02 error message population requires runtime execution of failing analysis"
  - test: "Click BPM override icon on a Pending row, change Min to 80, click Done"
    expected: "Icon turns accent-colored; popover re-opens showing persisted value 80; Reset clears back to global default"
    why_human: "Popover state persistence requires interactive testing"
  - test: "Click X on a Pending row"
    expected: "Row disappears immediately from queue"
    why_human: "Cancel interaction requires running app"
  - test: "Click X on an Analyzing row"
    expected: "Row transitions to Failed with 'Cancelled by user'; other tracks continue"
    why_human: "Requires running Python worker that can be interrupted"
---

# Phase 3: Batch Queue + Drag & Drop UI Verification Report

**Phase Goal:** A user can drop any number of audio files or folders onto the app, monitor per-track analysis status in real time, and see clear success or failure details for every track in the batch
**Verified:** 2026-06-04
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Dragging individual MP3/AIFF/WAV files onto the app window adds them to the queue immediately | VERIFIED | `BatchQueueView.onDrop` calls `provider.loadObject(ofClass: URL.self)` synchronously for every provider; resolved URL passed to `viewModel.addDroppedURL(_:)` which validates extension whitelist `["mp3","aiff","aif","wav"]` before calling `appendUniqueURL` |
| 2 | Dragging a folder recursively discovers all supported audio files and adds them to the queue | VERIFIED | `addDroppedURL` detects `isDirectory`; calls `scanFolder` (Task.detached with `FileManager.enumerator` using `.skipsHiddenFiles, .skipsPackageDescendants`); `url.standardizedFileURL` applied to every result |
| 3 | Up to 4 tracks analyzed in parallel; every track shows one of four statuses | VERIFIED | `dispatchNextPendingTracks()` (synchronous, no `await`) caps pool at `min(max(1, pendingTracks.count), 4)`; `TrackStatus` enum has exactly four raw-value cases: Pending/Analyzing/Done/Failed; `TrackRowView` switches on all four; `StatusPillView` renders each |
| 4 | Batch header displays "X of N tracks complete" and updates live as tracks finish | VERIFIED | `BatchHeaderView` renders `"\(viewModel.completedCount) / \(viewModel.totalCount) TRACKS"` with `KdProgressBar` animated on `.completedCount`; `completedCount` incremented in `.result`, `.error`, and cancel paths of `BatchViewModel` |
| 5 | Failed tracks show specific error message; user can expand per-track log showing BPM, marker count, duration | VERIFIED | `TrackDetailView.failedContent` renders `item.errorMessage` in `.foregroundColor(.red)`; `.doneContent` renders BPM range, marker count, duration, analysis time; `TrackRowView` wraps `.done`/`.failed` in `DisclosureGroup(isExpanded: $item.isExpanded)` with `TrackDetailView` as disclosure content |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `SeratoDynamicAnalyzer/Models/TrackItem.swift` | Per-track model: TrackStatus enum, TrackItem class, @Published properties | VERIFIED | `@MainActor class TrackItem: ObservableObject, Identifiable`; all 8 @Published properties present; class (not struct); no @Observable |
| `SeratoDynamicAnalyzer/ViewModels/BatchViewModel.swift` | Queue owner: tracks array, worker pool, dispatchNextPendingTracks(), startBatch(), addDroppedURL() | VERIFIED | `@MainActor class BatchViewModel: ObservableObject`; dynamic `[PythonBridge]` pool; synchronous `dispatchNextPendingTracks()`; all required methods present |
| `SeratoDynamicAnalyzer/Views/BatchHeaderView.swift` | Sticky header: progress counter, linear ProgressView, BPM Steppers, Dry Run toggle, Analyze All CTA | VERIFIED | `struct BatchHeaderView: View`; counter + animated KdProgressBar; KdStepper pair; KdToggle; Analyze All button wired to `viewModel.startBatch()` |
| `SeratoDynamicAnalyzer/Views/BatchQueueView.swift` | Primary content: List of TrackRowView, onDrop handler, folder scan, drop strip, NSOpenPanel | VERIFIED | `struct BatchQueueView: View`; List/ForEach; `onDrop(of: [UTType.fileURL])`; `DropStripView`; `NSOpenPanel` with `canChooseDirectories = true` |
| `SeratoDynamicAnalyzer/Views/TrackRowView.swift` | Per-row view: StatusPillView, filename, progress, BPM/markers, error summary; DisclosureGroup; BPM popover | VERIFIED | `struct TrackRowView: View`; `@ObservedObject var item: TrackItem`; `DisclosureGroup(isExpanded: $item.isExpanded)`; `slider.horizontal.3` popover; `xmark.circle.fill` cancel; no @Observable |
| `SeratoDynamicAnalyzer/Views/TrackDetailView.swift` | Accordion detail content for Done (BPM/markers/duration/backup) and Failed (error message) rows | VERIFIED | `struct TrackDetailView: View`; `@ObservedObject var item: TrackItem`; done/failed cases with `Color(nsColor: .controlBackgroundColor)` card backgrounds; `NSWorkspace.shared.activateFileViewerSelecting`; `"DRY RUN — no changes written"` |
| `SeratoDynamicAnalyzer/ContentView.swift` | App root: BatchViewModel @StateObject, BatchHeaderView + BatchQueueView composition | VERIFIED | `@StateObject private var viewModel = BatchViewModel()`; `BatchHeaderView(viewModel:) + BatchQueueView(viewModel:)`; `.frame(minWidth: 700, ...)`; `.task { await viewModel.startInitialWorker() }`; Serato alert wired to `startBatch()` |
| `SeratoDynamicAnalyzer/AnalysisViewModel.swift` | DELETED | VERIFIED | File does not exist on disk; no references in any `.swift` file |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| BatchQueueView.swift | BatchViewModel.swift | `addDroppedURL(_:)` called from `onDrop` | WIRED | Line 64: `await viewModel.addDroppedURL(resolved)` inside `loadObject` callback |
| BatchViewModel.swift | PythonBridge.swift | `bridge.analyzeStream()` in `dispatchNextPendingTracks()` | WIRED | Line 115: `let stream = await bridge.analyzeStream(filePath: next.url.path, bpmMin:, bpmMax:, dryRun:)` |
| TrackRowView.swift | TrackItem.swift | `@ObservedObject var item: TrackItem` | WIRED | Line 10: `@ObservedObject var item: TrackItem`; binding via `$item.isExpanded` at line 27 |
| TrackRowView.swift | TrackDetailView.swift | `TrackDetailView(item: item)` inside DisclosureGroup | WIRED | Line 28: `TrackDetailView(item: item)` |
| TrackDetailView.swift | TrackItem.swift | `item.result.backupPath` for Finder reveal | WIRED | Line 48: `if let backupPath = item.result?.backupPath` → `NSWorkspace.shared.activateFileViewerSelecting` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| BatchHeaderView | `viewModel.completedCount` | `BatchViewModel.handleWorkerEvent` increments on `.result` / `.error` / cancel | Yes — incremented in 3 code paths (lines 142, 149, 219) | FLOWING |
| TrackRowView | `item.status` | `BatchViewModel.dispatchNextPendingTracks` sets `.analyzing`; `handleWorkerEvent` sets `.done`/`.failed` | Yes | FLOWING |
| TrackDetailView | `item.result` (bpmMin, bpmMax, markerCount, durationSec, backupPath) | `BatchViewModel.handleWorkerEvent` case `.result(let r)` sets `trackItem.result = r` | Yes — populated from PythonBridge stream event | FLOWING |
| TrackDetailView | `item.errorMessage` | `BatchViewModel.handleWorkerEvent` case `.error(_, let msg)` sets `trackItem.errorMessage = msg` | Yes — populated from stream | FLOWING |

### Behavioral Spot-Checks

Step 7b: SKIPPED — this phase produces Swift/macOS native UI code requiring a running app and Python backend. No standalone runnable entry points can be tested without the full Xcode build and macOS process environment.

### Probe Execution

Step 7c: SKIPPED — no `scripts/*/tests/probe-*.sh` files present; phase produces SwiftUI code, not a CLI/pipeline.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| INPUT-01 | 03-01-PLAN | User kann einzelne Tracks per Drag & Drop in die App ziehen | SATISFIED | `BatchQueueView.onDrop` with `UTType.fileURL` provider loop; `addDroppedURL` validates extension and appends `TrackItem` |
| INPUT-02 | 03-01-PLAN | User kann Ordner per Drag & Drop hinzufügen — alle unterstützten Dateien werden gefunden | SATISFIED | `addDroppedURL` isDirectory branch → `scanFolder` with `FileManager.enumerator` recursion; `.skipsPackageDescendants` applied |
| BATCH-01 | 03-01-PLAN | User kann mehrere Tracks gleichzeitig analysieren (2–4 parallel) | SATISFIED | `dispatchNextPendingTracks()` grows pool to `min(max(1, pendingTracks.count), 4)`; separate `Task` spawned per slot calling `bridge.analyzeStream()` |
| BATCH-02 | 03-01-PLAN | User sieht Gesamtfortschritt der Batch-Verarbeitung (X von N Tracks fertig) | SATISFIED | `BatchHeaderView` displays `completedCount / totalCount TRACKS` with animated `KdProgressBar`; `@Published var completedCount` incremented in result, error, and cancel paths |
| UI-01 | 03-01-PLAN | App zeigt pro Track einen Status: Pending / Analyzing / Done / Failed | SATISFIED | `TrackStatus` enum (four raw-value cases); `TrackRowView` switch on all four; `statusIcon` and `bpmColumn` render distinct content per state |
| UI-02 | 03-02-PLAN | Bei fehlgeschlagenen Tracks zeigt die App eine spezifische, lesbare Fehlermeldung | SATISFIED | `TrackDetailView.failedContent` renders `item.errorMessage` (populated from JSON "msg" field via `BatchViewModel.handleWorkerEvent`) in `.foregroundColor(.red)`; `DisclosureGroup` in `TrackRowView` exposes this on tap |
| UI-03 | 03-02-PLAN | User kann ein Analyse-Log pro Track einsehen (erkannte BPM, Marker-Anzahl, Analysedauer) | SATISFIED | `TrackDetailView.doneContent` renders BPM range, Markers, Duration, Analysis time from `item.result` and `item.analysisDuration`; "Show Backup in Finder" link conditionally shown |

All 7 requirements satisfied in code. Runtime verification deferred to human smoke test.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| BatchQueueView.swift | 168 | Comment: `// Left edge indicator placeholder` | Info | Describes an intentional 3px spacer `Rectangle().fill(.clear).frame(width: 3)` that aligns with the status edge in rows — implementation is complete, comment is descriptive only. Not a stub. |

No TBD/FIXME/XXX debt markers. No @Observable macro. No .id() on ForEach children. No empty return stubs.

**Minor deviations (not blockers):**

1. `canStartBatch` omits `workerReadyCount > 0` condition (plan specified it). The on-demand worker spawn in `dispatchNextPendingTracks()` means "Analyze All" remains functional even when the initial worker hasn't warmed up yet — the pool grows as needed. Functional path unaffected.
2. BPM override popover "Reset to Global Default" button labeled "Reset" in code. Functionally equivalent — sets both overrides to `nil`.
3. ContentView `minWidth` is 700 (not 640 as plan specified) — a deliberate aesthetic upgrade with `idealWidth: 820`.
4. Worker warmup hint "Starting analysis engine…" from plan spec absent from BatchHeaderView. Not a user-facing regression — batch still works.

### Human Verification Required

All automated checks pass. The following behaviors require a running app for confirmation.

#### 1. Single File Drag & Drop (INPUT-01)

**Test:** Drop 3–5 MP3/AIFF/WAV files from Finder onto the app window.
**Expected:** Each file appears immediately as a row with a grey "Pending" status indicator. Non-audio files (e.g., `.txt`) are silently ignored.
**Why human:** Finder drag-and-drop gesture cannot be exercised programmatically.

#### 2. Folder Drop with Recursive Discovery (INPUT-02)

**Test:** Drop a folder containing a mix of audio files and non-audio files (including subdirectories).
**Expected:** All MP3/AIFF/WAV files recursively found and added as Pending rows. Subfolders inside `.app` bundles skipped. Duplicate drops silently ignored.
**Why human:** Requires real file system path resolution through drag-and-drop.

#### 3. Parallel Batch Analysis and Live Counter (BATCH-01, BATCH-02, UI-01)

**Test:** Drop 5+ files, click "Analyze All", observe.
**Expected:** Multiple rows transition to "Analyzing" simultaneously (up to 4). Header counter increments live. Each row shows exactly one of: Pending, Analyzing, Done, or Failed indicator.
**Why human:** Requires bundled Python worker process running; parallel execution visible only at runtime.

#### 4. Done Row Accordion Expansion (UI-03)

**Test:** After analysis completes, click a Done row.
**Expected:** Row expands showing BPM range (e.g., "120.0–122.5"), Markers count, Duration in seconds, Analysis time in seconds. If dry run was not active, "Show Backup in Finder" link is visible and opens Finder at the backup location.
**Why human:** Requires `item.result` populated by real analysis; DisclosureGroup animation and content verified visually.

#### 5. Failed Row Accordion Expansion (UI-02)

**Test:** Drop a zero-byte or corrupt audio file, click "Analyze All", wait for failure, click the Failed row.
**Expected:** Row expands showing a specific Python error message in red (e.g., "librosa.load failed: …"), not just a generic "Failed" label.
**Why human:** Requires runtime error from Python subprocess; error text populated dynamically.

#### 6. Per-Track BPM Override Popover

**Test:** Drop a file (Pending), click the `slider.horizontal.3` icon. Change Min to 80, click "Done". Re-open popover. Click "Reset".
**Expected:** After setting, icon turns accent-colored. Re-open shows persisted value 80. After Reset, icon returns to tertiary color and steppers default back to global values (60/200).
**Why human:** Popover state persistence and icon color change require interactive testing.

#### 7. Cancel Pending Row

**Test:** Drop several files (without clicking Analyze All), click the X on one Pending row.
**Expected:** Row disappears immediately from the queue. Other rows unaffected.
**Why human:** Cancel interaction requires running app; immediate removal verified visually.

#### 8. Cancel Analyzing Row

**Test:** Drop several files, click "Analyze All", immediately click X on a row showing "Analyzing".
**Expected:** That row transitions to Failed and expands showing "Cancelled by user". Analysis of remaining tracks continues uninterrupted.
**Why human:** Requires timing the cancel during active Python worker execution.

---

## Gaps Summary

No gaps blocking goal achievement. All 5 observable truths are verified in code. All 7 requirement IDs (INPUT-01, INPUT-02, BATCH-01, BATCH-02, UI-01, UI-02, UI-03) have complete implementations with verified data flows. BUILD SUCCEEDED. Four minor deviations from plan spec details are non-blocking.

Status is `human_needed` because the phase goal is an interactive UI workflow requiring a running app with Python backend to confirm the end-to-end user experience described by the roadmap success criteria.

---

_Verified: 2026-06-04_
_Verifier: Claude (gsd-verifier)_
