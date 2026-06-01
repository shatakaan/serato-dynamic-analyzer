# Research Summary: Serato Dynamic Analyzer

**Project:** Serato Dynamic Analyzer
**Domain:** Native macOS DJ utility — dynamic beatgrid analysis + Serato GEOB tag writing
**Researched:** 2026-06-01
**Confidence:** MEDIUM-HIGH

---

## Executive Summary

Serato DJ Pro has no native dynamic/variable-tempo beatgrid analysis. DJs who work with live recordings, vinyl rips, or variable-tempo music are manually fixing beatgrids — or not using beatgrids at all. The only existing automation is a handful of CLI Python scripts (bvandrc/serato-tools, gdhgdhgdh/serato-variable-tempo) that require Terminal and produce results with no visual feedback. The bar for a GUI tool that DJs will actually trust is high but achievable.

The correct architecture is: SwiftUI app (main process) + bundled CPython 3.12 subprocess (analysis + tag writing). The Python side uses librosa 0.11 for beat tracking and mutagen for GEOB tag writing. Swift spawns Python per track via Foundation Process, streams JSONL progress over stdout using AsyncStream, and drives a live-updating SwiftUI queue view. The Python bundle (~180–220MB including numpy/librosa/ffmpeg) ships inside the .app, signed and notarized — zero setup for the user.

The single highest risk is not the Swift code. It is byte-exact GEOB tag compliance: big-endian struct packing, explicit ID3v2.3 version, correct terminal marker format, and the 128-marker ceiling. A single error here produces a beatgrid that Serato silently ignores or corrupts — and the user may not notice until performing live. Validate the Python tag writer against real Serato before writing any Swift code. Everything else is standard macOS development.

---

## Recommended Stack

| Layer | Technology | Version | Rationale |
|-------|-----------|---------|-----------|
| UI + host app | SwiftUI + Foundation Process | macOS 13+ SDK | Native feel; Process API is stable for the subprocess pattern |
| Async streaming | Swift Concurrency (AsyncStream) | Swift 5.9+ | Bridges Pipe readabilityHandler to @MainActor without DispatchQueue |
| Python runtime | CPython (python.org framework) | 3.12.x | Relocatable, fully signable; avoid 3.13 until numpy/librosa wheels stabilize |
| Beat tracking | librosa | 0.11.x | Dynamic tempo API (plp() + frame-level beat_track()); used by bvandrc/serato-tools |
| Array math | numpy | 2.0.x | Core librosa dependency; pin to avoid ABI breakage |
| Audio decode | soundfile + bundled static ffmpeg | 0.12.x / 7.x | soundfile handles WAV/FLAC/AIFF; ffmpeg handles MP3 and M4A |
| Tag writing | mutagen | 1.47.x | First-class GEOB frame support; battle-tested in reference implementation |
| Build-time venv | uv (not shipped) | latest | Fastest pip-alternative with --relocatable venv flag |

**IPC:** Newline-delimited JSON over stdin/stdout pipes — zero infrastructure, highly debuggable.

**Do not use:** PythonKit (breaks stdout capture, blocks UI thread), Conda/Miniforge (500MB+ signing nightmare), audioread (removed in librosa 1.0), madmom (broken on Python 3.10+), beat-this/PyTorch (adds 500MB — revisit in v2).

---

## Table Stakes

Features DJs must see working before trusting a tool that writes to their audio files. Missing or broken = dead on arrival.

| Feature | Why Non-Negotiable |
|---------|--------------------|
| Atomic write with pre-write backup | mutagen.save() is not atomic; a kill mid-write corrupts the file permanently |
| ID3v2.3 explicit (not v2.4) | mutagen can default to v2.4; Serato silently ignores v2.4 GEOB frames |
| Big-endian struct packing throughout | GEOB is big-endian; macOS is little-endian; wrong byte order silently corrupts positions |
| Correct terminal marker + 128-marker ceiling | Missing terminal = Serato ignores grid; >128 markers = truncated grid; both silent |
| Per-track status (Pending / Analyzing / Done / Failed) | DJs expect Serato-style inline analysis status; no status feels broken |
| Human-readable failure reasons per track | Serato's own "could not analyze" with no detail is a documented pain point — beat it |
| Serato-is-running detection and warning | Writing while Serato has a file open can corrupt it permanently |
| Drag and drop for files and folders | Universal macOS file-processing UX expectation |
| Serato library browser (crate tree) | DJs expect crate hierarchy; all peer tools (DJ.Studio, SetFlow) expose it |
| Batch queue with progress and retry | Rekordbox sets the reference: inline status, count, failures, retry per track |
| MP3 + AIFF format support | Serato recommends MP3 or AIFF/WAV; these dominate DJ libraries |
| "Skip already-analyzed tracks" toggle | DJs run analysis tools repeatedly on growing libraries; re-analyzing everything is a dealbreaker |
| BPM range input (default 60–200 BPM) | Without it, half-tempo/double-tempo errors on drum & bass or hip-hop are the first complaint |
| Round-trip read-back validation | Write the GEOB, immediately decode it, compare to input — catch format errors before Serato sees them |

**Differentiators (build after trust features):** Analysis confidence indicator, "review needed" queue, BPM timeline sparkline, dry-run/preview mode, beatgrid lock step.

**Defer to v2:** Manual beatgrid editor, waveform display, resume interrupted batch jobs, WAV/FLAC/M4A formats (add WAV before launch if trivial).

---

## Critical Warnings

Ordered by severity.

### 1. GEOB byte-exact compliance — validate before any Swift code

The tag format has four independent silent failure modes. Any one of them causes Serato to silently ignore or corrupt the beatgrid:

- **Big-endian required.** Use `struct.pack('>f', ...)` and `struct.pack('>I', ...)` throughout. Python defaults to little-endian on macOS.
- **ID3v2.3 required.** Always call `id3.save(v2_version=3)`. ID3v2.4 GEOB frames are silently ignored by Serato.
- **Terminal marker required.** Format: `[0x01 0x00 header][non-terminal markers][terminal marker][0x00 footer]`. Missing any part = Serato ignores the entire tag.
- **128-marker ceiling.** Serato enforces a hard limit. Consolidate adjacent same-tempo beats into single non-terminal markers with a `beats_till_next` count. Max 127 non-terminal + 1 terminal.

**Mitigation:** Mirror bvandrc/serato-tools struct layout exactly. Write a round-trip unit test (encode, decode, assert). Test on 3 real tracks in Serato before writing any Swift code.

### 2. mutagen.save() is not atomic — mid-write crash corrupts the audio file

No rollback exists. If the Python process is killed during a write, the file is left in a partial state. On an MP3 with a half-written ID3 header, the entire file may become unreadable.

**Mitigation:** Copy original to `<filename>.serato-backup` before every write. Write to a temp copy. Verify readable. Then `os.replace()` over original. Expose "restore from backup" in the UI. No exceptions for any format.

### 3. Python bundle signing must be bottom-up — one unsigned .so breaks notarization

The bundled Python.framework plus venv contains hundreds of `.so` and `.dylib` files. The deprecated `--deep` flag is not sufficient — each binary must be signed individually with `--options runtime --timestamp` before the outer .app is signed.

**Mitigation:** Build the signing script in Phase 2. Require `com.apple.security.cs.allow-unsigned-executable-memory` entitlement (Python JIT writes executable memory). Test the notarized DMG on a clean macOS VM before release.

### 4. Stdout pipe deadlock if not drained asynchronously

If Python produces output faster than Swift reads it, the ~65KB kernel pipe buffer fills and Python blocks. Swift also blocks waiting for process exit. The analysis hangs indefinitely — no error, no timeout, just a frozen UI.

**Mitigation:** Never call `readDataToEndOfFile()` synchronously. Always use `FileHandle.readabilityHandler` wrapped in `AsyncStream<String>`. Launch Python with `-u` and set `PYTHONUNBUFFERED=1` in the process environment.

### 5. librosa beat_track() alone is wrong for dynamic beatgrids; onset timing is biased late

`beat_track()` assumes roughly constant tempo and has a documented ~20–60ms systematic late-onset bias. For variable-tempo detection, `librosa.beat.plp()` (Predominant Local Pulse) is the correct API. If a track has no detectable onsets, `beat_track()` returns 0 BPM and an empty array — writing an empty GEOB tag over an existing correct grid destroys it.

**Mitigation:** Use `plp()` for variable-tempo analysis; use `beat_track()` only for tempo estimation as input. Apply ~30ms onset offset correction. Detect zero-BPM / fewer-than-4-beats case and refuse to write — surface as a clear per-track error. Never overwrite an existing Serato beatgrid without explicit user confirmation.

---

## Suggested Build Order

### Phase 1 — Python Analysis Core (validate the central bet)

Build `analyze.py` as a standalone CLI script. Highest-risk component; zero Swift dependencies.

- Port bvandrc/serato-tools dynamic analysis into self-contained `analyze.py`
- Correct GEOB binary format: big-endian structs, ID3v2.3, terminal marker, 128-marker ceiling
- Atomic write with backup (copy-then-replace)
- Use `plp()` for variable-tempo; detect and refuse zero-BPM results
- Apply ~30ms onset offset correction
- Emit JSONL progress to stdout with `flush=True` on every print
- Round-trip validation: write tag, read it back, assert values match
- Manual test: 3 tracks (MP3, AIFF, one live recording) → open in Serato → beatgrid correct?

**Gate: Do not start Phase 2 until Serato accepts tags from this script on all 3 test tracks.**

Pitfalls addressed: CR-1 (endianness), CR-2 (terminal marker), CR-3 (Serato-open warning), CR-4 (atomic backup), CR-5 (ID3v2.3), HR-2 (128-marker limit), HR-3 (beat_track failures), HR-4 (onset bias)

### Phase 2 — PythonBridge (Swift process wrapper)

Build the Swift layer that launches `analyze.py` for a single hardcoded file. No library browser or batch queue yet.

- `PythonBridge` actor: `run(url: URL) async throws -> AnalysisResult`
- Locate bundled Python binary via `Bundle.main`
- `Process` with stdout/stderr Pipes; `AsyncStream<String>` via `readabilityHandler`
- Parse JSONL into typed events (progress, result, error)
- Handle exit codes, crash signals (SIGSEGV), 5-minute timeout guard
- Set PYTHONHOME, PATH, PYTHONUNBUFFERED before spawning
- Build and test signing script; notarize DMG; verify on clean VM

Pitfalls addressed: MR-3 (measure startup latency — pivot to persistent worker if >2s)

### Phase 3 — AnalysisOrchestrator + Batch Queue UI

Add concurrency control and observable state.

- `AnalysisOrchestrator` actor with `withThrowingTaskGroup` and slot-counting (max 2–4 parallel processes)
- `AnalysisQueueViewModel` (`@Observable`) with per-track `TrackAnalysisState`
- Track list with progress bars, status icons, human-readable error messages
- Start / pause / cancel batch controls
- "Skip already-analyzed tracks" toggle
- Serato-is-running detection → warning before any write
- BPM range input (default 60–200 BPM) passed as argument to analyze.py
- Test with 10 tracks; watch Activity Monitor for RAM (expect 200–400MB per process)

Pitfalls addressed: MR-1 (per-process isolation limits librosa memory leakage), MR-2 (DatabaseV2 stale cache — instruct user to restart Serato), MR-4 (document beatgrid lock step)

### Phase 4 — Serato Library Browser

Read existing crates and expose them in the UI.

- `read_library.py` one-shot script: parse `~/Music/_Serato_/database.V2` and `Subcrates/*.crate` (binary TLV), output JSON
- `SeratoLibraryReader` actor launching this script on app start; parse JSON response
- `LibraryViewModel` with crate tree and track list
- `LibraryView`: sidebar crate tree, main track table with filename/duration/existing BPM/status
- "Analyze Selected" → hand tracks to AnalysisOrchestrator
- End-to-end flow: browse library → select → analyze → write → verify in Serato

### Phase 5 — Polish, Differentiators, and Distribution

- Drag and drop for files and folders onto the queue window
- Analysis confidence indicator per track (inter-beat BPM variance)
- "Review needed" queue (high-variance tracks surfaced separately)
- BPM timeline sparkline (derived from analysis data, not audio waveform)
- Dry-run / preview mode (analyze without writing)
- Error state details: expandable messages, per-track Retry
- Concurrency slider in Settings
- App icon, menu bar, About window
- Signed + notarized DMG for GitHub Releases

---

## Open Questions

Unresolved decisions that need investigation before they become architectural commitments.

| Question | When to Resolve | Stakes |
|----------|----------------|--------|
| Does Serato accept GEOB output from analyze.py? | Phase 1 gate | Critical: wrong format = project premise fails |
| What is Python+librosa startup time per subprocess on Apple Silicon? | Phase 2 measurement | If >2s, must pivot to persistent worker process; changes IPC architecture |
| Does AIFF GEOB write via mutagen work the same as MP3? | Phase 1 test (track 2) | AIFF is P0; if different, need separate write path |
| What is realistic RAM usage for 2–4 concurrent librosa processes? | Phase 3 test | If >1.5GB on 8GB MacBook, reduce concurrency or load in chunks |
| Does plp() produce better dynamic grids than beat_track() alone on typical DJ music? | Phase 1 calibration | Affects the tool's core differentiator |
| Can the signing pipeline be automated reliably in a Makefile/CI script? | Phase 2 | If not, distribution is blocked; needs iteration time |
| Should DatabaseV2 be updated programmatically after writing tags? | Phase 4 design | Removes "restart Serato" friction; adds complexity and corruption risk if Serato is open |

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Core libraries HIGH; Python bundling/signing MEDIUM — Apple requirements evolve |
| Features | HIGH | Gap in Serato confirmed by forum; competitor patterns well-documented |
| Architecture | HIGH | Swift Concurrency + subprocess is standard; Serato formats documented by Holzhaus + Mixxx |
| Pitfalls | HIGH | GEOB errors empirically documented in bvandrc, serato-variable-tempo, Holzhaus trackers |

**Overall confidence: MEDIUM-HIGH.** Unknowns are concentrated in build-time concerns (signing, startup latency) and librosa calibration — not fundamental feasibility. Execute Phase 1 to remove the biggest unknown.

---

## Sources

### Primary (HIGH confidence)
- [Holzhaus/serato-tags](https://github.com/Holzhaus/serato-tags) — GEOB binary format spec, reverse-engineered and validated by Mixxx
- [bvandrc/serato-tools](https://github.com/bvandrc/serato-tools) — reference Python implementation
- [gdhgdhgdh/serato-variable-tempo](https://github.com/gdhgdhgdh/serato-variable-tempo) — source of 128-marker limit discovery
- [librosa 0.11 documentation](https://librosa.org/doc/0.11.0/) — dynamic tempo API, plp(), frame-level beat_track
- [Mixxx Wiki — Serato Database Format](https://github.com/mixxxdj/mixxx/wiki/Serato-Database-Format) — TLV binary format for crate/database files
- [Apple Developer — Hardened Runtime entitlements](https://developer.apple.com/documentation/bundleresources/entitlements)

### Secondary (MEDIUM confidence)
- [Serato forum: variable BPM (April 2025)](https://serato.com/forum/discussion/2029107) — confirms gap is real and actively requested
- [BeeWare Python-Apple-support](https://github.com/beeware/Python-Apple-support) — relocatable Python.framework builds
- [Fractolog: Making Python.org Framework Relocatable (May 2025)](https://www.fractolog.com/2025/05/making-python-org-python-framework-relocatable/)
- [librosa issue #1052](https://github.com/librosa/librosa/issues/1052) — beats are systematically late
- [librosa issue #681](https://github.com/librosa/librosa/issues/681) — memory growth across repeated load() calls
- [mp3tag community: GEOB ID3 version mismatch](https://community.mp3tag.de/t/serato-dj-copied-tags-for-beatgrids-and-markers-to-another-format-version-of-track-wont-get-read/56466)

### Tertiary (LOW confidence — validate during implementation)
- [Holzhaus/serato-tags issue #3](https://github.com/Holzhaus/serato-tags/issues/3) — M4A tag format partially reverse-engineered; treat as incomplete until tested
- FLAC GEOB container documentation — less complete than MP3; needs testing

---

*Research completed: 2026-06-01*
*Ready for roadmap: yes*
