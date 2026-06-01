# Architecture: Serato Dynamic Analyzer

**Domain:** Native macOS DJ tool — Swift frontend + embedded Python analysis subprocess
**Researched:** 2026-06-01
**Overall confidence:** HIGH (Swift concurrency, Process API, Serato formats are well-documented)

---

## Component Map

```
┌─────────────────────────────────────────────────────────────────┐
│  SwiftUI Layer (Main Thread / @MainActor)                       │
│                                                                 │
│  LibraryView          QueueView           TrackDetailView       │
│  (crate browser)      (batch progress)    (single track)        │
└──────────────┬──────────────┬─────────────────────┬────────────┘
               │              │                     │
               ▼              ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  ViewModel / State Layer (@Observable, macOS 14+)               │
│                                                                 │
│  LibraryViewModel     AnalysisQueueViewModel                    │
│  - crate tree         - per-track status: pending/running/      │
│  - track list           done/failed                             │
│  - drag & drop        - progress 0.0-1.0 per track              │
│                       - error messages                          │
└──────────────┬──────────────┬──────────────────────────────────┘
               │              │
               ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Service Layer (actors / structured concurrency)                │
│                                                                 │
│  SeratoLibraryReader       AnalysisOrchestrator                 │
│  - parse database.V2       - owns the TaskGroup                 │
│  - parse .crate files      - limits concurrency (2-4 workers)   │
│  - resolve file paths      - per-track error isolation          │
│                            - cancellation support               │
└──────────────┬──────────────┬──────────────────────────────────┘
               │              │
               ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Infrastructure Layer                                           │
│                                                                 │
│  PythonBridge                       SeratoTagWriter             │
│  - locates bundled python binary    (Swift — reads/writes GEOB  │
│  - launches Process per track       tags via file handle if     │
│  - reads JSONL from stdout          needed for verification;    │
│  - terminates on cancel/timeout     actual writing is in Python)│
│  - reports crashes vs. errors                                   │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Python Subprocess (bundled, per-track process)                 │
│                                                                 │
│  analyze.py                                                     │
│  - loads audio via librosa                                      │
│  - runs beat tracking (librosa.beat.beat_track)                 │
│  - converts beats to Serato non-terminal + terminal markers     │
│  - writes GEOB tag via mutagen                                  │
│  - emits JSONL progress to stdout (line-flushed)                │
│  - exits 0 on success, non-zero on failure                      │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| SwiftUI Views | Display state, handle user interaction, drag & drop | ViewModels only |
| LibraryViewModel | Crate tree state, track selection, file drop handling | SeratoLibraryReader, AnalysisQueueViewModel |
| AnalysisQueueViewModel | Per-track status, progress, errors, start/cancel | AnalysisOrchestrator |
| SeratoLibraryReader | Parse Serato binary files, return track models | File system only |
| AnalysisOrchestrator | Concurrency control, TaskGroup management | PythonBridge (one per track) |
| PythonBridge | Spawn/kill Python, stream stdout, parse JSONL | OS Process API |
| analyze.py | Audio analysis + GEOB tag writing | File system, librosa, mutagen |

---

## Data Flow

### Track Analysis (Single Track)

```
User selects track
        │
        ▼
AnalysisQueueViewModel.enqueue(trackURL)
        │
        ▼
AnalysisOrchestrator.analyze(track)
        │  TaskGroup child task
        ▼
PythonBridge.run(trackURL)
 - Process(launchPath: bundled_python)
 - args: ["-u", "analyze.py", trackPath]
 - stdout pipe → FileHandle.readabilityHandler → AsyncStream<String>
        │
        │  For each stdout line:
        ▼
parse JSONL line:
  {"type":"progress","value":0.42}       → update track.progress
  {"type":"result","bpm":123.4}          → store result
  {"type":"error","message":"..."}       → record error, exit cleanly
        │
        │  On Process termination:
        ▼
terminationStatus == 0? → success → update track.status = .done
terminationStatus != 0? → failure → update track.status = .failed(reason)
        │
        ▼
AnalysisQueueViewModel publishes update (@MainActor)
        │
        ▼
SwiftUI re-renders progress row
```

### Serato Library Loading

```
App launch / Library tab selected
        │
        ▼
SeratoLibraryReader.load()
 - discovers ~/Music/_Serato_/
 - reads database.V2 (binary, tag-length-value format)
   → builds track index: path → metadata
 - reads Subcrates/*.crate (binary TLV)
   → builds crate tree with track file paths
        │
        ▼
LibraryViewModel receives crate tree
        │
        ▼
SwiftUI renders crate sidebar + track list
```

---

## Concurrency Model

### Threading Diagram

```
Main Thread (@MainActor)
├── SwiftUI rendering
├── User input handling
└── ViewModel @Observable property writes

Swift Cooperative Thread Pool (background)
├── AnalysisOrchestrator actor
│   └── withThrowingTaskGroup: controlled concurrency (max N parallel)
│       ├── PythonBridge task 1 (awaiting stdout lines)
│       ├── PythonBridge task 2 (awaiting stdout lines)
│       └── PythonBridge task 3 (awaiting stdout lines)
└── SeratoLibraryReader actor (one-shot parsing)

OS Processes (external)
├── python3 analyze.py track1.mp3  (separate process)
├── python3 analyze.py track2.mp3  (separate process)
└── python3 analyze.py track3.mp3  (separate process)
```

### Concurrency Decisions

**Use `withThrowingTaskGroup` for batch processing.** This is the idiomatic Swift Concurrency pattern for parallel work with per-task error handling. Seed the group with N initial tasks and add new ones as slots free up to maintain a constant concurrency level.

**Concurrency limit: 2-4 parallel Python processes.** Each Python process loads librosa + numpy and decodes audio — this is CPU and memory intensive (~200-400 MB RAM per process). A semaphore-like pattern using task group slot counting keeps concurrency bounded. Start with 2 for safety; make it configurable.

**Controlled slot pattern:**
```swift
// Seed with maxConcurrency tasks
for track in tracks.prefix(maxConcurrency) {
    group.addTask { try await self.analyzeTrack(track) }
}
// As each finishes, add the next
for try await result in group {
    handle(result)
    if let next = remaining.next() {
        group.addTask { try await self.analyzeTrack(next) }
    }
}
```

**AnalysisOrchestrator as Swift `actor`.** Protects mutable state (queue, running set, results) from data races. All external calls cross the actor boundary via `await`.

**@Observable on ViewModels (requires macOS 14 / Ventura+ already targeted).** Use `@Observable` macro instead of `ObservableObject`/`@Published`. Only accessed properties trigger re-renders — critical for a list of 100+ tracks each with their own progress value. Update ViewModels on `@MainActor` using `await MainActor.run { ... }` from background tasks.

**AsyncStream for stdout.** Wrap `FileHandle.readabilityHandler` in an `AsyncStream<String>` that yields complete lines. Buffer partial data between handler calls (pipes are block-buffered by default; Python runs with `-u` flag for unbuffered stdout). The stream terminates when the process exits.

**Python `-u` flag is mandatory.** Without it, Python buffers stdout in 4KB or 8KB blocks when connected to a pipe, causing progress updates to arrive in bursts at the end rather than in real time. Launch the Python interpreter with `-u` as the first argument: `["/path/to/python3", "-u", "analyze.py", trackPath]`.

---

## Process Architecture (Python Subprocess)

### Lifecycle

```
PythonBridge.run(trackURL) called
        │
        ▼
Locate Python binary:
  Bundle.main.path(forResource: "python3", ofType: nil)
  → .app/Contents/Resources/python-runtime/bin/python3
        │
        ▼
Set environment:
  PYTHONPATH = .app/Contents/Resources/python-runtime/lib/...
  PYTHONUNBUFFERED = "1"  (belt-and-suspenders alongside -u flag)
        │
        ▼
Launch Process:
  process.executableURL = pythonURL
  process.arguments = ["-u", analyzeScriptPath, trackPath]
  process.standardOutput = stdoutPipe
  process.standardError = stderrPipe
  process.launch()
        │
        ├── stdout → AsyncStream<String> (JSONL lines)
        ├── stderr → captured for crash diagnostics
        │
        ▼
Await termination
  process.terminationStatus: Int32
  process.terminationReason: Process.TerminationReason
        │
        ├── .exit, status 0 → success
        ├── .exit, status != 0 → Python-reported failure
        └── .uncaughtSignal → crash (SIGSEGV, SIGKILL, etc.)
                              → include stderr in error report
```

### Crash Isolation

Each track runs in its own process. A crash (SIGSEGV from numpy, memory overflow, corrupt audio decoder) kills that process only. The Swift Task catches the termination, marks that track as `.failed`, and continues with the remaining queue. No shared state between Python processes.

**Timeout guard:** A track should never take more than 5 minutes (even a 60-minute live recording). If a track exceeds the timeout, call `process.terminate()` (SIGTERM) and mark it `.failed(reason: .timeout)`. Implement with Swift's `Task.sleep` racing against the process completion.

### Binary Location in Bundle

```
SeratoDynamicAnalyzer.app/
└── Contents/
    ├── MacOS/
    │   └── SeratoDynamicAnalyzer          (Swift binary)
    ├── Resources/
    │   ├── python-runtime/                (bundled CPython 3.12)
    │   │   ├── bin/
    │   │   │   └── python3
    │   │   └── lib/
    │   │       └── python3.12/
    │   │           └── site-packages/     (librosa, numpy, mutagen, ...)
    │   └── scripts/
    │       └── analyze.py                 (analysis + tag writing script)
    └── Info.plist
```

**Code signing requirement:** Every `.dylib` and binary inside `python-runtime/` must be individually signed before the outer app bundle is signed. Sign bottom-up (innermost binaries first). Python apps require the `com.apple.security.cs.allow-unsigned-executable-memory` entitlement because Python's JIT/eval loop writes to executable memory — this is required for notarization of apps with embedded Python.

---

## Serato Library Structure

### Directory Layout

```
~/Music/_Serato_/
├── database.V2          — binary track database (all library metadata)
├── Subcrates/
│   ├── House.crate      — binary crate file (flat crate)
│   ├── Techno.crate
│   └── House%%Deep.crate  — nested crate (%%  = path separator)
├── History/             — play history (not needed)
├── Smartcrates/         — smart crate definitions (not needed for v1)
└── BPMAnalysis/         — cached analysis data
```

### Binary Format (TLV — Tag Length Value)

Both `database.V2` and `.crate` files use the same envelope:

```
[4-byte ASCII tag][4-byte big-endian uint32 length][N bytes payload]
```

Tag prefix conventions (from Mixxx reverse engineering documentation):
- `o*` — nested record (payload is more TLV records)
- `t*` — UTF-16 BE text string
- `p*` — file path (UTF-16 BE, may be absolute or relative)
- `u*` — 32-bit big-endian integer
- `b*` — boolean (1 byte)

### Key Tags

**database.V2 (library index):**
- `vrsn` — file version header
- `otrk` — track record container
  - `ptrk` — file path (relative to music root, UTF-16 BE)
  - `tbpm` — BPM string
  - `tkey` — musical key
  - `tadd` — date added
  - `uadd` — date added (int)

**Crate files:**
- `vrsn` — version header
- `osrt` — sort order
- `otrk` — track reference
  - `ptrk` — file path reference matching database.V2 entries

### Reading Strategy for Swift

**Do not write a Swift binary parser.** The Python subprocess (or a separate one-shot Python invocation at app startup) can read the crate files and return JSON to Swift. Alternatively, parse in Swift using `Data` and `BinaryInteger` — the format is simple enough.

For v1, the pragmatic approach: write a small Python script (`read_library.py`) that parses `database.V2` and `Subcrates/*.crate`, outputs a single JSON document with the full crate tree and track list, then Swift reads that JSON. This script is a one-shot invocation (not a long-lived process), takes under a second for typical libraries (5000 tracks), and re-uses the existing Python runtime bundle.

**Reference implementations:**
- `jesseward/Serato-lib` — Python, documents the full TLV structure
- `mixxxdj/mixxx` Serato Database Format wiki — most complete binary spec
- `bvandrc/serato-tools` — Python, has crate reading + database parsing
- `sharst/seratopy` — minimal Python library for crate access

---

## Serato BeatGrid GEOB Tag Structure

**Source: Holzhaus/serato-tags (HIGH confidence, documented by reverse engineering + validated by Mixxx implementation)**

The tag is stored as an ID3v2 GEOB frame with description `"Serato BeatGrid"` in MP3. Equivalent storage in M4A/FLAC uses format-specific encapsulation.

```
Header:   2 bytes (0x01 0x00)
Markers:  variable count
Footer:   1 byte (0xFF)
```

**Non-terminal marker** (all markers except the last):
```
position:  4 bytes big-endian float   (seconds from start)
beats_till_next: 4 bytes big-endian uint32
```

**Terminal marker** (always the final marker):
```
position:  4 bytes big-endian float   (seconds from start)
bpm:       4 bytes big-endian float   (BPM at this point)
```

The Python `analyze.py` script handles all of this via `mutagen`. Swift does not need to know the binary format — it delegates writing entirely to Python. Swift only needs to verify success (exit code 0).

---

## Suggested Build Order

### Dependency Graph

```
1. Python analysis script (analyze.py)
        ↓ required by
2. PythonBridge (Swift Process wrapper)
        ↓ required by
3. AnalysisOrchestrator (concurrency + queue)
        ↓ required by
4. AnalysisQueueViewModel + Progress UI
        ↓ parallel track after step 1:
5. SeratoLibraryReader (Serato binary parsing)
        ↓ required by
6. LibraryViewModel + LibraryView (crate browser)
        ↓ both 4+6 required for:
7. End-to-end integration (select from library → analyze → write tag)
        ↓ polish:
8. Drag & Drop, error states, batch cancel, settings
```

### Phase Breakdown

**Phase 1 — Core Pipeline Proof of Concept (validate the central bet)**

Build `analyze.py` first. This is the highest-risk component: does librosa's beat tracking produce results Serato will accept? Verify it standalone before touching Swift.

Steps:
1. Port / adapt `bvandrc/serato-tools` dynamic analysis into a standalone `analyze.py`
2. Accept a file path as command-line argument
3. Emit JSONL progress to stdout (with `flush=True` on every print)
4. Write the GEOB tag using mutagen on success
5. Exit 0/1 appropriately
6. Test manually: run on 3 tracks, open in Serato, verify beatgrid is correct

**Do not proceed to Swift until Serato accepts the tags from this script.**

**Phase 2 — PythonBridge (Swift process wrapper)**

Build the Swift layer that launches `analyze.py` for a single hardcoded file path:
1. `PythonBridge` class/actor with `run(url: URL) async throws -> AnalysisResult`
2. Locate bundled Python binary via `Bundle.main`
3. Set up `Process` with stdout pipe
4. Wrap `readabilityHandler` in `AsyncStream<String>`
5. Parse JSONL lines into typed events
6. Handle exit codes and crash signals
7. Manual test: trigger from a button in a throwaway SwiftUI view

**Phase 3 — AnalysisOrchestrator + Queue ViewModel**

Add concurrency control and observable state:
1. `AnalysisOrchestrator` actor with `withThrowingTaskGroup` and slot-counting for concurrency limit
2. `AnalysisQueueViewModel` `@Observable` class with per-track `TrackAnalysisState` (pending/running/done/failed)
3. Progress UI: list of tracks with progress bars, status icons, error messages
4. Start/pause/cancel controls
5. Test with 10 tracks dropped onto the window

**Phase 4 — Serato Library Reader**

Read the existing Serato library (crates + tracks):
1. Python script `read_library.py` that parses `database.V2` and `Subcrates/*.crate`
2. Outputs JSON: `{ "crates": [...], "tracks": [...] }`
3. Swift: launch this script once at startup (or on "Reload Library"), parse JSON
4. `SeratoLibraryReader` actor wrapping this
5. `LibraryViewModel` with crate tree, track list
6. `LibraryView`: sidebar with crates, main area with track table
7. "Analyze Selected" button → hand tracks to AnalysisOrchestrator

**Phase 5 — Drag & Drop + Polish**

1. Drag & drop: accept `.mp3`, `.m4a`, `.flac`, `.mp4` URLs onto the queue
2. Error state details: expandable error messages, "Retry" per track
3. Settings: concurrency limit slider, output path options
4. Batch cancel
5. App icon, menu bar items

---

## Critical Path

The single most important unknown: **will Serato actually accept the beatgrid tags written by the Python script?**

Everything else (SwiftUI, process management, library reading) is standard macOS development with well-understood patterns. The beatgrid binary format requires byte-exact compliance — off-by-one in the marker count, wrong byte order, or missing footer byte makes the track unloadable in Serato.

**Validate this first, before writing any Swift code:**

```
analyze.py → test track → open in Serato → beatgrid correct? → proceed
                                          → broken?          → fix format
```

The second most important unknown: **Python bundle size and startup time.** Each track spawns a Python process. If startup time for librosa is 3-5 seconds per track, that's a terrible UX for batch jobs. Measure this early. Mitigation if slow: keep a persistent Python worker process and communicate via stdin/stdout (a lightweight RPC loop), rather than one process per track.

### Architectural Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Serato rejects tag byte layout | Medium | Critical | Test manually in Phase 1 before any Swift work |
| librosa startup time too slow per-process | Medium | High | Measure in Phase 1; pivot to persistent worker process if >2s |
| Code signing fails for bundled Python dylibs | Medium | High | Test signing pipeline early (Phase 2); sign bottom-up |
| numpy/librosa uses too much RAM (OOM with N parallel jobs) | Low | Medium | Limit concurrency to 2; test with Activity Monitor |
| Serato library binary format changed in newer Serato version | Low | Medium | Pin to documented format; graceful failure with clear message |
| M4A/AIFF GEOB equivalent tags differ from MP3 | Medium | Medium | Scope to MP3-first in Phase 1; add M4A via mutagen in Phase 3 |

---

## Anti-Patterns to Avoid

**Do not use PythonKit (embedding Python in-process).** PythonKit requires disabling Hardened Runtime and App Sandbox, breaks code signing for notarization, and causes crashes on Apple Silicon with numpy/librosa. The subprocess model is the correct architecture for distributing Python with a signed macOS app.

**Do not spawn one Process per progress update.** Python startup + librosa import costs ~1-2 seconds. The analysis script must run once per track end-to-end, streaming progress via stdout, not via repeated subprocess calls.

**Do not update SwiftUI state from background threads.** All `@Observable` property mutations must be on `@MainActor`. Use `await MainActor.run { }` when updating from inside a TaskGroup child task or an actor method.

**Do not use `DispatchQueue` or `OperationQueue` for new code.** The project targets macOS 13+. Use Swift Concurrency (async/await, actors, TaskGroup) throughout. This avoids the complexity of mixing two concurrency systems and prepares for Swift 6 strict concurrency checking.

**Do not write the Serato binary formats in Swift for v1.** The Python implementations (mutagen + bvandrc/serato-tools) are battle-tested and the reference for the byte format. Implement in Python first. A native Swift tag writer is a v2 optimisation if performance demands it.

---

## Sources

- [Holzhaus/serato-tags — BeatGrid format docs](https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_beatgrid.md)
- [Holzhaus/serato-tags — File formats](https://github.com/Holzhaus/serato-tags/blob/main/docs/fileformats.md)
- [bvandrc/serato-tools — Dynamic analysis reference](https://github.com/bvandrc/serato-tools)
- [Mixxx Wiki — Serato Database Format](https://github.com/mixxxdj/mixxx/wiki/Serato-Database-Format)
- [jesseward/Serato-lib — Crate format documentation](https://github.com/jesseward/Serato-lib)
- [jamf/Subprocess — Swift async process library](https://github.com/jamf/Subprocess)
- [swiftlang/swift-subprocess — Official Swift subprocess package](https://github.com/swiftlang/swift-subprocess)
- [Apple Developer — Process.terminationStatus](https://developer.apple.com/documentation/foundation/process/1415801-terminationstatus)
- [Apple Developer — FileHandle.readabilityHandler](https://developer.apple.com/documentation/foundation/filehandle/1412413-readabilityhandler)
- [SwiftLee — Task Groups in Swift](https://www.avanderlee.com/concurrency/task-groups-in-swift/)
- [Signing and notarizing Python macOS apps](https://haim.dev/posts/2020-08-08-python-macos-app)
- [Serato support — What is in the _Serato_ folder?](https://support.serato.com/hc/en-us/articles/204022904-What-is-in-the-Serato-folder)
- [librosa.beat.beat_track documentation](https://librosa.org/doc/main/generated/librosa.beat.beat_track.html)
