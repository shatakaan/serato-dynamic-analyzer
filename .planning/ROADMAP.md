# Roadmap: Serato Dynamic Analyzer

**Project mode:** Vertical MVP (each phase delivers a working user-facing capability)
**Granularity:** Standard
**Coverage:** 22/22 v1 requirements mapped

---

## Phases

- [x] **Phase 1: Python Analysis Core** - Validate the central bet: analyze.py writes byte-exact GEOB tags that Serato accepts (completed 2026-06-02)
- [x] **Phase 2: PythonBridge + Swift Integration** - Launch analysis from Swift for a single track; sign and notarize the app bundle (completed 2026-06-02)
- [x] **Phase 3: Batch Queue + Drag & Drop UI** - Multi-track workflow: drop files, watch progress, read per-track results and errors (completed 2026-06-04)
- [ ] **Phase 4: Serato Library Browser** - Browse crates, inspect existing beatgrids, send library tracks to the analysis queue
- [ ] **Phase 5: Format Expansion + Distribution** - M4A and MP4 support via ffmpeg; signed and notarized DMG for GitHub Releases

---

## Phase Details

### Phase 1: Python Analysis Core

**Goal**: A standalone Python script correctly analyzes a track's dynamic tempo and writes a byte-exact Serato BeatGrid GEOB tag that Serato DJ Pro reads and displays without errors
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: ANAL-01, ANAL-02, ANAL-03, FMT-01, FMT-02, FMT-03, SAFE-03
**Success Criteria** (what must be TRUE):

  1. Running `analyze.py track.mp3` produces a GEOB tag that Serato DJ Pro displays as a correct, aligned beatgrid (verified manually on 3 real tracks: one MP3, one AIFF, one live recording with tempo variation)
  2. The script accepts `--bpm-min` and `--bpm-max` arguments (default 60-200) and uses them to constrain the tempo estimation
  3. The script leaves all other Serato GEOB tags (Cues, Loops, Waveform) in the file byte-for-byte unchanged after writing the BeatGrid tag
  4. A write interrupted mid-way leaves no corrupted file state: the script writes to a temp file and uses `os.replace()` atomically, so the original is intact or replaced entirely
  5. Python startup + librosa analysis time is measured and logged per track; if startup exceeds 2 seconds the phase notes confirm a persistent worker process is needed before Phase 2

**Plans**: 4 plans

**Wave 1**

- [x] 01-01-PLAN.md — GEOB encoding core: pack_beatgrid(), encode_markers(), per-format write functions, atomic write, TDD round-trip tests (10/10 tests passing)
- [x] 01-02-PLAN.md — Audio loading pipeline: load_audio() format dispatch (MP3 via imageio-ffmpeg pipe, AIFF/WAV via soundfile), TDD tests

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-03-PLAN.md — Beat detection: detect_beats() using librosa.beat.plp() + frame-level tempo, onset correction, TDD tests (12/12 tests passing; 29 total)
- [x] 01-04-PLAN.md — CLI integration: analyze_track() orchestrator, argparse entry point, JSONL output, startup timing, manual Serato gate

### Phase 2: PythonBridge + Swift Integration

**Goal**: A SwiftUI app window triggers analysis of a single hardcoded or user-selected track, streams live JSONL progress into the UI, and the signed DMG installs and notarizes cleanly on a fresh macOS machine
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: ANAL-04, SAFE-01, SAFE-02
**Success Criteria** (what must be TRUE):

  1. Clicking "Analyze" in the app launches the bundled Python process; stdout JSONL progress lines update a progress indicator in real time without freezing the UI
  2. If Serato DJ Pro is running when the user initiates a write, the app shows a blocking warning dialog before any file is touched
  3. Before every write, the app creates a visible `<filename>.serato-backup` file; the UI shows the backup path so the user knows where to restore from
  4. A "Dry Run" toggle causes the app to run the full analysis, show what BPM and marker count would be written, and not modify the audio file
  5. The notarized DMG installs and runs on a fresh macOS 13 Ventura machine with no developer tools or Python installed

**Plans**: 5 plans

**Wave 0** *(blocking prerequisite — must complete before Wave 1+)*

- [x] 02-01-PLAN.md — Prerequisites + TDD RED stubs: Install Xcode.app (human gate) + uv; write failing tests for worker mode, backup, dry run

**Wave 1** *(blocked on Wave 0)*

- [x] 02-02-PLAN.md — Python worker extensions GREEN: create_backup(), dry_run param, --worker stdin loop, ready signal; all tests pass (54 total)

**Wave 2** *(blocked on Wave 0)*

- [x] 02-03-PLAN.md — Xcode project + PythonBridge actor + AnalysisViewModel: project skeleton, entitlements, actor IPC bridge, ObservableObject ViewModel (BUILD SUCCEEDED, Swift 6.3.2)

**Wave 3** *(blocked on Wave 2)*

- [x] 02-04-PLAN.md — ContentView + Safety UX: drop zone, file picker, ProgressView, result card, Dry Run toggle, Serato-running alert; smoke test gate

**Wave 4** *(blocked on Wave 3)*

- [x] 02-05-PLAN.md — Makefile + build + ad-hoc signing + DMG + Phase 2 acceptance gate

### Phase 3: Batch Queue + Drag & Drop UI

**Goal**: A user can drop any number of audio files or folders onto the app, monitor per-track analysis status in real time, and see clear success or failure details for every track in the batch
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: INPUT-01, INPUT-02, BATCH-01, BATCH-02, UI-01, UI-02, UI-03
**Success Criteria** (what must be TRUE):

  1. Dragging individual MP3, AIFF, or WAV files onto the app window adds them to the analysis queue immediately
  2. Dragging a folder onto the app recursively discovers all supported audio files and adds them to the queue
  3. Up to 4 tracks are analyzed in parallel; every track in the queue shows one of four statuses: Pending, Analyzing, Done, or Failed
  4. A batch header displays "X of N tracks complete" and updates live as tracks finish
  5. Failed tracks show a specific, human-readable error message (not just "failed"), and the user can expand a per-track log showing detected BPM, marker count, and analysis duration

**Plans**: 2 plans

**Wave 1**

- [x] 03-01-PLAN.md — Core batch slice: TrackItem model, BatchViewModel with 1–4 worker pool, BatchHeaderView, BatchQueueView (drop handler + folder scan), TrackRowView (status pills), ContentView refactor, AnalysisViewModel deleted

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03-02-PLAN.md — Detail layer: TrackDetailView (accordion expansion for Done/Failed), DisclosureGroup wiring, per-track BPM override popover, cancel button; phase acceptance smoke test

### Phase 4: Serato Library Browser

**Goal**: A user can open their Serato library inside the app, browse crates, see which tracks already have a beatgrid, select tracks, and send them to the analysis queue without leaving the app
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: LIB-01, LIB-02, LIB-03
**Success Criteria** (what must be TRUE):

  1. The app reads `~/Music/_Serato_/` on launch and displays the full crate hierarchy (nested crates included) in a sidebar
  2. Selecting a crate shows its tracks in a table with filename, duration, and current BPM
  3. Each track in the library view shows a visual indicator: no beatgrid, beatgrid set by Serato's own analysis, or beatgrid set by this tool
  4. Selecting one or more tracks and clicking "Analyze Selected" adds them to the batch queue and begins analysis

**Plans**: 3 plans (3 waves)
**UI hint**: yes

Plans:
- [ ] 04-01-PLAN.md — Python backbone: library.py (crate tree, list_crates/list_tracks IPC, read_beatgrid_source), 0x01 0x01 version byte, test_library.py
- [ ] 04-02-PLAN.md — Swift data layer: SeratoCrate/LibraryTrack models, PythonBridge listCrates/listTracks, LibraryViewModel (dedicated worker), BatchViewModel.addLibraryTrack
- [ ] 04-03-PLAN.md — UI slice: kdWarning token, 6 Library views (HSplitView/OutlineGroup/track table/dot/CTA/empty state), ContentView TabView restructure, Makefile bundling, Serato version-byte human-verify gate

### Phase 5: Format Expansion + Distribution

**Goal**: The app supports M4A and MP4 files via bundled ffmpeg, and a signed, notarized DMG is published to GitHub Releases for direct download by DJs
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: FMT-04, FMT-05
**Success Criteria** (what must be TRUE):

  1. Dragging an M4A or MP4 file into the queue produces a correct Serato BeatGrid tag that Serato DJ Pro reads without error
  2. The GitHub Releases page contains a downloadable, signed `.dmg` that passes macOS Gatekeeper on a clean machine without any security warnings

**Plans**: TBD

---

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Python Analysis Core | 4/4 | Complete    | 2026-06-02 |
| 2. PythonBridge + Swift Integration | 5/5 | Complete    | 2026-06-03 |
| 3. Batch Queue + Drag & Drop UI | 2/2 | Complete   | 2026-06-04 |
| 4. Serato Library Browser | 0/3 | Planned | - |
| 5. Format Expansion + Distribution | 0/? | Not started | - |

---

## Coverage Map

| Requirement | Phase |
|-------------|-------|
| ANAL-01 | Phase 1 |
| ANAL-02 | Phase 1 |
| ANAL-03 | Phase 1 |
| FMT-01 | Phase 1 |
| FMT-02 | Phase 1 |
| FMT-03 | Phase 1 |
| SAFE-03 | Phase 1 |
| ANAL-04 | Phase 2 |
| SAFE-01 | Phase 2 |
| SAFE-02 | Phase 2 |
| INPUT-01 | Phase 3 |
| INPUT-02 | Phase 3 |
| BATCH-01 | Phase 3 |
| BATCH-02 | Phase 3 |
| UI-01 | Phase 3 |
| UI-02 | Phase 3 |
| UI-03 | Phase 3 |
| LIB-01 | Phase 4 |
| LIB-02 | Phase 4 |
| LIB-03 | Phase 4 |
| FMT-04 | Phase 5 |
| FMT-05 | Phase 5 |

**Total mapped: 22/22**

---

*Roadmap created: 2026-06-02*
*Last updated: 2026-06-04 — Phase 4 planned (3 plans in 3 waves)*
