---
phase: "04-serato-library-browser"
plan: "02"
subsystem: "swift-data-layer"
tags: ["swift", "library-browser", "serato-crate", "ipc", "viewmodel", "observable-object"]
dependency_graph:
  requires:
    - "python/library.py (build_crate_tree, list_crates, list_tracks) — from Plan 04-01"
    - "cmd:list_crates IPC event (type:crates) — from Plan 04-01"
    - "cmd:list_tracks IPC event (type:tracks) — from Plan 04-01"
  provides:
    - "struct SeratoCrate: Identifiable with Optional children + flattenedFind(id:)"
    - "enum BeatgridSource + struct LibraryTrack: Identifiable"
    - "enum LibraryEvent (crates/tracks/error)"
    - "PythonBridge.listCrates() async -> [SeratoCrate]"
    - "PythonBridge.listTracks(crate:) async -> [LibraryTrack]"
    - "PythonBridge.parseLibraryEvent(_:) nonisolated"
    - "enum AppTab: Hashable (library/queue)"
    - "@MainActor class LibraryViewModel: ObservableObject with dedicated libraryBridge"
    - "BatchViewModel.addLibraryTrack(url:)"
  affects:
    - "SeratoDynamicAnalyzer/PythonBridge.swift (library methods added)"
    - "SeratoDynamicAnalyzer/ViewModels/BatchViewModel.swift (addLibraryTrack added)"
    - "SeratoDynamicAnalyzer.xcodeproj/project.pbxproj (3 new source files registered)"
tech_stack:
  added: []
  patterns:
    - "struct (not class) for value-type models rebuilt whole per load (SeratoCrate, LibraryTrack)"
    - "Optional children: [SeratoCrate]? for OutlineGroup leaf detection (nil=leaf, no disclosure triangle)"
    - "Dedicated PythonBridge per ViewModel — library commands never share the analysis worker pool"
    - "fputs(stderr) for all diagnostics — stdout reserved for Python JSON-Lines"
    - "AppTab enum defined at plan 02 scope so plan 03 ContentView can reuse without redeclaring"
key_files:
  created:
    - "SeratoDynamicAnalyzer/Models/SeratoCrate.swift"
    - "SeratoDynamicAnalyzer/Models/LibraryTrack.swift"
    - "SeratoDynamicAnalyzer/ViewModels/LibraryViewModel.swift"
  modified:
    - "SeratoDynamicAnalyzer/PythonBridge.swift"
    - "SeratoDynamicAnalyzer/ViewModels/BatchViewModel.swift"
    - "SeratoDynamicAnalyzer.xcodeproj/project.pbxproj"
decisions:
  - "AppTab enum defined in LibraryViewModel.swift (Plan 02) rather than ContentView.swift (Plan 03) to avoid forward-dependency; Plan 03 reuses this declaration"
  - "listCrates/listTracks are actor-isolated (not nonisolated) to allow direct stdinPipe/stdoutPipe access without actor isolation hops"
  - "addLibraryTrack calls private appendUniqueURL directly — no access-level change needed since it is in the same class scope"
metrics:
  duration: "~15 min"
  completed_date: "2026-06-05"
  tasks_completed: 3
  files_created: 3
  files_modified: 3
---

# Phase 04 Plan 02: Swift Data Layer (SeratoCrate + LibraryTrack models, PythonBridge IPC extension, LibraryViewModel) Summary

**One-liner:** Swift data layer consuming Plan 01's IPC contract — SeratoCrate/LibraryTrack models, PythonBridge listCrates/listTracks with LibraryEvent parser, dedicated LibraryViewModel, and BatchViewModel.addLibraryTrack queue integration.

---

## What Was Built

### SeratoDynamicAnalyzer/Models/SeratoCrate.swift (new)

- `struct SeratoCrate: Identifiable` with `let id = UUID()`, `let name: String`, `let cratePath: String?` (nil for implied parent nodes), `var children: [SeratoCrate]?` (nil for leaf nodes — suppresses OutlineGroup disclosure triangle per RESEARCH Pitfall 6), `var isSelectable: Bool { cratePath != nil }`
- `init(json: [String: Any])`: reads name, crate_path (nil when JSON value absent/null), recursively maps children array into `[SeratoCrate]?` (nil when absent/null)
- `extension Array where Element == SeratoCrate { func flattenedFind(id: UUID) -> SeratoCrate? }`: depth-first search helper for Plan 03's sidebar `onChange`

### SeratoDynamicAnalyzer/Models/LibraryTrack.swift (new)

- `enum BeatgridSource: String { case none="none"; case serato="serato"; case tool="tool" }` — maps the D-07 version byte distinction to a type-safe enum
- `struct LibraryTrack: Identifiable` with `id = UUID()`, `url: URL`, `filename: String`, `beatgridSource: BeatgridSource`, `durationSec: Double?` (nil for M4A; Phase 5 adds M4A duration)
- `init(json: [String: Any])` mirrors `AnalysisResult.init(json:)` pattern

### SeratoDynamicAnalyzer/PythonBridge.swift (extended)

- `enum LibraryEvent { case crates([SeratoCrate]); case tracks([LibraryTrack]); case error(String) }` — top-level, before the actor
- `func listCrates() async -> [SeratoCrate]`: actor-isolated; restarts worker if `!isWorkerRunning`; writes `{"cmd":"list_crates"}` to stdin; reads stdout until `.crates` terminal event
- `func listTracks(crate: String) async -> [LibraryTrack]`: same pattern for `{"cmd":"list_tracks","crate":"..."}`;  reads until `.tracks` terminal event
- `nonisolated func parseLibraryEvent(_ line: String) -> LibraryEvent?`: mirrors `parseEvent`; switches on `type` field — "crates"/"tracks"/"error"

### SeratoDynamicAnalyzer/ViewModels/LibraryViewModel.swift (new)

- `enum AppTab: Hashable { case library, queue }` — defined at file scope; Plan 03's ContentView reuses this without redeclaring
- `@MainActor class LibraryViewModel: ObservableObject` with `@Published crateTree`, `selectedCrateID`, `trackList`, `selectedTrackIDs`, `isLoadingTracks`, `isLoadingCrates`
- `private let libraryBridge = PythonBridge()` — dedicated instance, never shared (T-04-IPC isolation)
- `func startLibraryWorker() async`: starts bridge, waits for ready; logs via `fputs(stderr)` (T-04-STDOUT)
- `func loadCrateTree()`: Task-launched; auto-starts worker; populates crateTree
- `func selectCrate(_ crate: SeratoCrate)`: guards `cratePath != nil` (T-04-NULLPATH); clears trackList + selectedTrackIDs immediately; loads tracks async
- `var seratoLibraryPath: URL` / `var seratoLibraryExists: Bool` computed properties
- `func analyzeSelected(batchViewModel:selectedTab:)`: routes selected tracks to queue; switches to `.queue` tab

### SeratoDynamicAnalyzer/ViewModels/BatchViewModel.swift (extended)

- `func addLibraryTrack(url: URL) { appendUniqueURL(url) }` — public wrapper; calls existing dedup logic with same Set<URL> guard as drag-drop

### SeratoDynamicAnalyzer.xcodeproj/project.pbxproj (extended)

- 3 new source files registered: SeratoCrate.swift, LibraryTrack.swift, LibraryViewModel.swift
- PBXBuildFile + PBXFileReference + group membership + Sources build phase entries for each

---

## Deviations from Plan

None — plan executed exactly as written. All threat mitigations (T-04-IPC, T-04-STDOUT, T-04-NULLPATH) are implemented as specified.

---

## Known Stubs

None — all methods are fully implemented. `LibraryTrack.durationSec` may be `nil` for M4A tracks (intentional; Plan 01 documents this as Phase 5 work).

---

## Threat Flags

No new threat surface beyond the plan's threat model. All three STRIDE mitigations implemented:
- T-04-IPC: `private let libraryBridge = PythonBridge()` — dedicated instance confirmed
- T-04-STDOUT: all LibraryViewModel diagnostics use `fputs(..., stderr)`
- T-04-NULLPATH: `selectCrate` guards on `cratePath != nil` before issuing list_tracks

---

## Self-Check

### Files Exist

- SeratoDynamicAnalyzer/Models/SeratoCrate.swift: FOUND
- SeratoDynamicAnalyzer/Models/LibraryTrack.swift: FOUND
- SeratoDynamicAnalyzer/ViewModels/LibraryViewModel.swift: FOUND

### Commits Exist

- 21f3fad (Task 1: SeratoCrate + LibraryTrack models): FOUND
- 1d76677 (Task 2: PythonBridge library methods): FOUND
- e03e778 (Task 3: LibraryViewModel + addLibraryTrack): FOUND

### Build Status

- xcodebuild: BUILD SUCCEEDED
- Python suite: 64 passed

## Self-Check: PASSED
