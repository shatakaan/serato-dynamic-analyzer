# Phase 5: Format Expansion + Distribution - Context

**Gathered:** 2026-06-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Add M4A and MP4 audio format support (FMT-04, FMT-05) via the existing `imageio_ffmpeg` decode pipeline, and publish the first distributable DMG on GitHub Releases with ad-hoc signing and Gatekeeper-bypass instructions for users.

No Apple Developer Program / notarization — ad-hoc signing only. No GitHub Actions CI. No FLAC, no key detection, no UI changes beyond format acceptance.

</domain>

<decisions>
## Implementation Decisions

### Code Signing + Distribution

- **D-01:** **Ad-hoc signing only** — no Apple Developer Program, no notarization. Use existing `codesign --sign -` Makefile target. Success Criteria #2 is adjusted: "GitHub Releases contains a downloadable, ad-hoc-signed DMG with a README installation section that explains the one-time Gatekeeper bypass (`xattr -d com.apple.quarantine <path>.dmg` or right-click → Open)."
- **D-02:** **Manual release workflow**: developer runs `git tag vX.Y.Z && make publish`. `make publish` = `make release` (existing: bundle-swift + bundle-python + sign + dmg) + `gh release create` with DMG upload + auto-generated release notes.
- **D-03:** Add `make publish` target to Makefile. It reads the version from the latest git tag (`git describe --tags --abbrev=0`), creates/drafts the GitHub Release, and uploads the DMG. Requires `gh` CLI authenticated.

### M4A Support (FMT-04)

- **D-04:** **User confirmed Serato reads and writes M4A BeatGrid tags** — implementation can proceed without a pre-validation research gate on format support.
- **D-05:** **Researcher must verify exact M4A tag format** — check Holzhaus serato-tags docs for how Serato stores `GEOB:Serato BeatGrid` in MP4 containers (likely a free-form atom, e.g., `----:com.serato.dj:Serato BeatGrid` via `mutagen.mp4.MP4`). The binary payload should be identical to the MP3 GEOB data.
- **D-06:** M4A **audio loading**: same `imageio_ffmpeg` → ffmpeg → WAV pipe → soundfile pattern as MP3 (same `load_audio()` function, add `.m4a` branch). Sample rate 22050 Hz, mono, same as MP3 path.
- **D-07:** M4A **tag writing**: add `write_geob_m4a(file_path, geob_data)` function in `analyze.py` using `mutagen.mp4.MP4`. Exact atom key to be confirmed by researcher from Holzhaus docs.
- **D-08:** Add `.m4a` to `ALLOWED_EXTENSIONS`, `SUPPORTED_EXTENSIONS`, and the `analyze_track()` format dispatch. Add `write_geob_m4a` to `atomic_write_geob()`.

### MP4 Support (FMT-05)

- **D-09:** **Separate implementation from M4A** — different error handling and test cases. `.mp4` is a video container; audio track extraction via ffmpeg may need `-vn` (no video) flag.
- **D-10:** MP4 **audio loading**: same ffmpeg pipe as M4A but with explicit `-vn` flag to extract only the audio stream.
- **D-11:** MP4 **tag writing**: same MP4 free-form atom approach as M4A (same container format). Add `write_geob_mp4(file_path, geob_data)` as a separate function for clarity. Both M4A and MP4 write to `mutagen.mp4.MP4` — the difference is the extension check and the ffmpeg decode flag.
- **D-12:** Add `.mp4` to `ALLOWED_EXTENSIONS`, `SUPPORTED_EXTENSIONS`. Add `write_geob_mp4` to `atomic_write_geob()`.

### Validation Gates (both formats)

- **D-13:** Each format gets a **manual Serato gate** in the plan: analyze a real .m4a file and a real .mp4 file, open in Serato DJ Pro, verify beatgrid displays correctly. These are `autonomous: false` checkpoints, same pattern as Phase 1's gate.
- **D-14:** Add `test_write_geob_m4a` and `test_write_geob_mp4` to the Python test suite (mutagen round-trip, analogous to `test_9` and `test_10` for AIFF/WAV).

### Claude's Discretion

- Exact mutagen MP4 atom key for GEOB data (researcher confirms from Holzhaus docs)
- Whether `write_geob_m4a` and `write_geob_mp4` share a common `_write_geob_mp4_container()` helper or are fully separate
- Backup filename convention for M4A/MP4 files (`.serato-backup` suffix already used for MP3)
- README section structure for Gatekeeper bypass instructions
- `make publish` draft vs. published release flag

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Format Specification (M4A/MP4 tags)
- `https://github.com/Holzhaus/serato-tags` — Holzhaus serato-tags documentation. **MUST check the M4A/MP4 section** for the exact free-form atom key used by Serato to store `GEOB:Serato BeatGrid` in MP4 containers.
- `https://github.com/bvandrc/serato-tools` — Reference Python implementation. Check if bvandrc's serato-tools has M4A write support — may have the exact mutagen API call.

### Existing Implementation
- `python/analyze.py` — Current format dispatch in `load_audio()` (MP3 via ffmpeg, AIFF/WAV via soundfile) and `atomic_write_geob()` (format dispatch to write functions). **Read before adding M4A/MP4 branches.** Lines ~52–130.
- `python/requirements.txt` — Current Python dependencies. `imageio_ffmpeg` already present. `mutagen` already present. No new dependencies expected.
- `Makefile` — Current `sign`, `dmg`, and `release` targets. Read before adding `publish` target.

### Prior Phase Patterns
- `.planning/phases/01-python-analysis-core/01-CONTEXT.md` — D-01–D-06: audio loading decisions, ffmpeg usage pattern, atomic write pattern. M4A/MP4 implementation must follow the same patterns.
- `.planning/phases/02-pythonbridge-swift-integration/02-CONTEXT.md` — D-10/D-13: Makefile signing decisions. `make publish` extends `make sign + dmg`.

### Requirements
- `.planning/REQUIREMENTS.md` — FMT-04 (M4A/AAC via bundled ffmpeg), FMT-05 (MP4 via bundled ffmpeg)
- `.planning/ROADMAP.md` Phase 5 — Success criteria (2 items, adjusted per D-01)

### Swift Format Acceptance (if needed)
- `SeratoDynamicAnalyzer/ViewModels/BatchViewModel.swift` — `addDroppedURL` and the file extension filter. M4A/MP4 extensions must be added to the accepted-types list.
- `SeratoDynamicAnalyzer/ContentView.swift` — Drag-and-drop accepted content types (UTType). `.m4a` = `UTType.mpeg4Audio`, `.mp4` = `UTType.mpeg4Movie`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `load_audio()` in `analyze.py`: existing MP3 branch (`imageio_ffmpeg` → ffmpeg → WAV pipe → soundfile.read(BytesIO)) is the exact pattern to copy for M4A and MP4.
- `atomic_write_geob()` in `analyze.py`: dispatches to format-specific write functions. Adding `.m4a` and `.mp4` branches here follows the established pattern.
- `imageio_ffmpeg.get_ffmpeg_exe()`: already in use — no new ffmpeg binary needed. M4A/MP4 decode uses the same binary.

### Established Patterns
- **ffmpeg pipe decode**: `cmd = [ffmpeg_exe, '-i', str(path), '-f', 'wav', '-ar', '22050', '-ac', '1', 'pipe:1']` — MP3 branch in `load_audio()`. M4A uses the same command; MP4 adds `-vn`.
- **mutagen tag write pattern**: MP3 uses `mutagen.id3.ID3`, AIFF uses `mutagen.aiff.AIFF`. M4A/MP4 will use `mutagen.mp4.MP4` — same open-modify-save idiom.
- **Atomic write**: `atomic_write_geob()` writes to temp file, then `os.replace()`. Already handles MP3, AIFF, WAV — add M4A and MP4 dispatch here.
- **Ad-hoc signing**: `codesign --sign -` already in Makefile. No change needed for distribution path.

### Integration Points
- SwiftUI drag-and-drop: `BatchViewModel.addDroppedURL()` checks file extensions. Need to add `.m4a` and `.mp4` to accepted extensions AND to the `UTType` list in ContentView.
- Python ALLOWED_EXTENSIONS set: gate for all incoming file paths in analyze.py worker mode.

</code_context>

<specifics>
## Specific Ideas

- `make publish` as a one-command release: `git tag vX.Y.Z` → `make publish` → DMG on GitHub Releases
- Gatekeeper bypass: `xattr -d com.apple.quarantine SeratoDynamicAnalyzer.dmg` OR right-click → Open. Both options in README.
- M4A and MP4 are separate implementations (separate load function branches, separate write functions, separate test cases) despite sharing the MP4 container format.

</specifics>

<deferred>
## Deferred Ideas

- Apple Developer Program notarization — deferred, no Developer Account
- GitHub Actions CI release automation — deferred, manual workflow chosen
- FLAC support — out of scope for v1 (REQUIREMENTS.md v2: FMT-V2-01)
- Universal binary (Intel + Apple Silicon fat DMG) — researcher should assess; likely not needed since developer machine is Apple Silicon

None: discussion stayed within phase scope.

</deferred>

---

*Phase: 5-format-expansion-distribution*
*Context gathered: 2026-06-08*
