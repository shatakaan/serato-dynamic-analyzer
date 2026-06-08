---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_plan: 1
status: executing
stopped_at: Phase 4 complete
last_updated: "2026-06-08T00:00:00.000Z"
progress:
  total_phases: 5
  completed_phases: 4
  total_plans: 14
  completed_plans: 14
  percent: 80
---

# State: Serato Dynamic Analyzer

## Project Reference

**Core value:** Ein DJ zieht einen Track rein (oder wählt seine Serato-Library), drückt "Analyze" — und bekommt ein taktgenaues dynamisches Beatgrid, das Serato direkt versteht.

**Current focus:** Phase 05 — format-expansion-distribution

---

## Current Position

Phase: 05 (format-expansion-distribution) — NOT STARTED
**Status:** Phase 04 complete — ready for Phase 05

```
Progress: [x] [x] [x] [x] [ ]
           1   2   3   4   5
```

**Overall:** 4 of 5 phases complete

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases complete | 1 / 5 |
| Plans complete (phase 1) | 4 / 4 |
| Requirements implemented | 19 / 22 |
| Current phase | 2 |
| Session count | 5 |
| Phase 1 Plan 1 duration | 374s (~6 min) |
| Phase 1 Plan 1 tests | 10 / 10 passing |
| Phase 1 Plan 2 duration | 480s (~8 min) |
| Phase 1 Plan 2 tests | 7 / 7 passing (17 total) |
| Phase 1 Plan 3 duration | ~720s (~12 min) |
| Phase 1 Plan 3 tests | 12 / 12 passing (29 total) |
| Phase 1 Plan 4 duration | ~900s (~15 min) |
| Phase 1 Plan 4 tests | 16 / 16 new passing (45 total) |
| Phase 2 Plan 02-02 duration | ~497s (~8 min) |
| Phase 2 Plan 02-02 tests | 9 / 9 new passing (54 total) |
| Phase 2 Plan 02-03 duration | 419s (~7 min) |
| Phase 2 Plan 02-03 builds | 1 Xcode project, BUILD SUCCEEDED (Swift 6.3.2, macOS 13.0 target) |
| Phase 2 Plan 02-04 duration | 345s (~5 min) |
| Phase 2 Plan 02-04 builds | BUILD SUCCEEDED — ContentView.swift full UI, all acceptance criteria passed |

---

## Accumulated Context

### Key Decisions

| Decision | Rationale | Status |
|----------|-----------|--------|
| Python subprocess per track (not PythonKit) | Avoids Hardened Runtime conflicts; crash isolation per track; signable | Confirmed |
| analyze.py before any Swift code | GEOB byte-exact compliance is the highest-risk unknown; validate standalone first | Active constraint |
| librosa plp() for dynamic tempo, not beat_track() alone | beat_track() assumes constant tempo; plp() handles variable-tempo tracks correctly | Active |
| Atomic write: temp file + os.replace() | mutagen.save() is not atomic; mid-write crash corrupts the file permanently | Confirmed |
| ID3v2.3 explicitly (not v2.4) | Serato silently ignores v2.4 GEOB frames | Confirmed |
| Big-endian struct packing throughout | GEOB format is big-endian; macOS is little-endian | Confirmed |
| 128-marker ceiling with terminal marker | Hard Serato limit; missing terminal = grid silently ignored | Confirmed |
| GEOB_FOOTER = b'\x00' (not 0xFF) | Holzhaus serato_beatgrid.md is canonical; ARCHITECTURE.md had wrong value | Confirmed (01-01) |
| ONSET_OFFSET_SECONDS = 0.030 | Librosa systematic lateness ~30ms documented in issue #1052; configurable constant | Confirmed (01-01) |
| imageio_ffmpeg.get_ffmpeg_exe() always used for ffmpeg path | No hardcoded binary paths; imageio-ffmpeg ships its own static ffmpeg | Confirmed (01-02) |
| Module-level imports for imageio_ffmpeg, soundfile, numpy | Required for unittest.mock.patch to work; deferred imports (librosa) remain lazy | Confirmed (01-02) |
| MP3: subprocess.run with list cmd (no shell=True) → BytesIO → soundfile | T-02-03 mitigation; prevents shell interpolation of user-supplied file path | Confirmed (01-02) |
| librosa submodules pre-imported in tests to avoid __qualname__ MagicMock collision | patch() entering a submodule triggers its module-level code; pre-import prevents re-import during patch context | Confirmed (01-03) |
| detect_beats() uses plp() only — beat_track() not called | D-07 locked: plp() for variable-tempo; beat_track() assumes constant tempo | Confirmed (01-03) |
| hop_length=512 assigned as variable, passed consistently to all librosa calls | MR-1 mitigation; avoids repeated literals; one change point if value needs tuning | Confirmed (01-03) |
| emit_json() is the sole stdout writer; all other output to stderr | T-04-02 mitigation; JSONL purity required for Swift IPC contract | Confirmed (01-04) |
| analyze_track() orchestrator calls load_audio+detect_beats+encode_markers+pack_beatgrid+atomic_write_geob | Chains all Phase 1 pipeline steps in order; replaces ad-hoc inline code in old main() | Confirmed (01-04) |
| emit_result() optional fields added conditionally (only when backup_path not None / dry_run True) | Cleaner JSON schema than always-present null fields; backward compatible | Confirmed (02-02) |
| Eager librosa import in --worker branch before ready signal | Guarantees ready = Python env + librosa fully loaded, not just process started | Confirmed (02-02) |
| test_cli.py schema test uses issubset not equality | Phase 2 optional fields allowed without breaking Phase 1 test intent | Confirmed (02-02) |
| Xcode project created programmatically (project.pbxproj written directly) | No Xcode UI required; all source files in Sources build phase | Confirmed (02-03) |
| DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer required for xcodebuild | /usr/bin/xcodebuild fails with license error; direct path works; Xcode 26.5, Swift 6.3.2, arm64 | Confirmed (02-03) |
| ObservableObject + @Published for ViewModel (NOT @Observable) | @Observable requires macOS 14+; deployment target is 13.0 — confirmed by build success | Confirmed (02-03) |
| skipSeratoCheck Bool flag on AnalysisViewModel (not force: param) | Simpler call site from alert Continue button; flag is consumed and reset inside startAnalysis(); prevents Serato alert infinite loop (T-02-04-04) | Confirmed (02-04) |

### Open Questions

| Question | Stakes | Resolve in |
|----------|--------|------------|
| Does Serato accept GEOB output from analyze.py? | Critical — project premise | RESOLVED: GATE PASSED on 3 tracks (MP3, MP3, AIFF) |
| Python+librosa startup time per subprocess on Apple Silicon? | If >2s, must pivot to persistent worker process | RESOLVED: 3.73s (Track A), 2.39s (Track B) — Phase 2 MUST use persistent worker |
| Does AIFF GEOB write via mutagen work the same as MP3? | AIFF write tested via pytest (test_9); mutagen API works. Manual Serato test still needed. | RESOLVED: AIFF gate passed (Unbenannt.aif, 1.63s) |
| Realistic RAM usage for 2-4 concurrent librosa processes? | May need to reduce default concurrency | Phase 3 test |
| Can the signing pipeline be automated in a Makefile/CI? | Blocks distribution if not | Phase 2 |

### Architecture Constraints

- **Phase 1 gate PASSED:** Serato DJ Pro accepts GEOB tags from analyze.py on all 3 test tracks (MP3 house, MP3 funk, AIFF). Phase 2 can begin.
- **Python startup confirmed >2s:** Phase 2 MUST use a persistent Python worker process with stdin/stdout RPC instead of spawning one process per track (Track A: 3.73s, Track B: 2.39s)
- **Signing is bottom-up:** every .so and .dylib in python-runtime/ must be individually signed before the outer .app bundle; `--deep` is insufficient
- **Required entitlement:** `com.apple.security.cs.allow-unsigned-executable-memory` (Python JIT writes executable memory)
- **No DispatchQueue or OperationQueue:** all new Swift code uses async/await, actors, and TaskGroup (macOS 13+ target)
- **@Observable ViewModels only (not ObservableObject):** requires macOS 14+; check minimum deployment target decision at Phase 2

### Todos

- [x] Set up Xcode project and Swift package structure (Phase 2) — DONE: 02-03 complete, BUILD SUCCEEDED
- [ ] Build and test signing script (Phase 2)
- [ ] Test notarized DMG on clean macOS 13 VM (Phase 2)
- [x] Measure librosa startup latency on Apple Silicon (Phase 1) — DONE: 3.73s MP3, 2.39s MP3, 1.63s AIFF
- [x] Validate GEOB round-trip: write tag, decode it, assert values match (Phase 1) — done via test_4_round_trip
- [x] Manual Serato gate: run analyze.py on 3 real tracks (MP3, AIFF, live recording), open in Serato, verify beatgrid (Phase 1 gate, plan 01-04) — GATE PASSED

### Blockers

(None currently)

---

## Session Continuity

**Last session:** 2026-06-08
**Stopped at:** Phase 4 complete — library loads, crate tree displays, pipeLines fix committed
**Next action:** Plan and execute Phase 05 — M4A/MP4 via ffmpeg + signed notarized DMG

**Phase 4 IPC fix:** FileHandle.bytes.lines leaves stale DispatchSource on IPC pipes after cancellation. Library commands (listCrates/listTracks) now use pipeLines() — a readabilityHandler-based AsyncStream. See memory feedback_filehandle_bytes_lines.md.

**Build note:** Always use `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild` — the /usr/bin/xcodebuild symlink fails with a license error.

---

*State initialized: 2026-06-02*
*Last updated: 2026-06-02 — Phase 2 Plan 02-02 complete*
