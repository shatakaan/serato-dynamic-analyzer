---
phase: 05-format-expansion-distribution
verified: 2026-06-09T22:30:00Z
status: passed
score: 9/9 must-haves verified + 2/2 human gates confirmed
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 7/9
  gaps_closed:
    - "Published DMG is ad-hoc-signed such that analysis actually runs on user machines (Gap 1 — venv/bin codesign step added)"
    - "load_audio() M4A and MP4 dispatch branches are covered by tests (Gap 2 — TestM4aDispatch + TestMp4Dispatch added)"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Open the app, drag a real .m4a track onto the batch queue, click Analyze All, then open the analyzed file in Serato DJ Pro"
    expected: "File enters queue (not filtered), analysis completes with Done status and BPM value, Serato DJ Pro displays a correctly positioned beatgrid that does not drift over the track (Serato gate D-13, Plan 01 Task 4)"
    why_human: "Serato DJ Pro beatgrid rendering requires a live Serato instance and a real audio file — cannot be verified by grep or pytest"
  - test: "Open the app, drag a real .mp4 video file onto the batch queue, click Analyze All, then open the analyzed file in Serato DJ Pro"
    expected: "File enters queue, analysis completes with Done status and BPM value, Serato DJ Pro displays a correctly positioned beatgrid (Serato gate D-13, Plan 02 Task 3)"
    why_human: "MP4 video decode (-vn) and Serato rendering require a live Serato instance — cannot be verified programmatically"
---

# Phase 05: Format Expansion + Distribution — Re-Verification Report

**Phase Goal:** The app supports M4A and MP4 files via bundled ffmpeg, and a signed, notarized DMG is published to GitHub Releases for direct download by DJs
**Verified:** 2026-06-09T22:30:00Z
**Status:** human_needed
**Re-verification:** Yes — after gap closure (Plan 04)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | M4A file dropped onto app is accepted into the queue | VERIFIED | BatchViewModel.swift line 169: `["mp3","aiff","aif","wav","m4a","mp4"].contains(ext)`; BatchQueueView.swift lines 99-100: `UTType.mpeg4Audio` in allowedContentTypes |
| 2 | analyze.py decodes M4A audio via ffmpeg (no -vn) and detects beats | VERIFIED | analyze.py line 126: `elif path.suffix.lower() == '.m4a'` branch, ffmpeg cmd list has no -vn. `-vn` appears exactly once in file (line 151, MP4 branch only). |
| 3 | write_geob_m4a() writes parseable `----:com.serato.dj:beatgrid` free-form atom | VERIFIED | analyze.py lines 609-640: `MP4_BEATGRID_KEY = '----:com.serato.dj:beatgrid'`, `_write_geob_mp4_container()` with FLAC wrapper + base64-no-padding; tests 11, 13, 14 pass (70/70 full suite). |
| 4 | Stored atom value base64-decodes to payload starting with FLAC wrapper prefix | VERIFIED | test_13_m4a_geob_encoding_contract asserts `decoded.startswith(b'application/octet-stream\x00\x00Serato BeatGrid\x00')`. PASSES. |
| 5 | Serato DJ Pro reads M4A BeatGrid tag and displays correct beatgrid (D-13) | HUMAN NEEDED | Cannot verify programmatically — requires live Serato DJ Pro with real audio file. Listed under Human Verification Required. |
| 6 | MP4 file dropped onto app is accepted; analyze.py decodes via ffmpeg -vn | VERIFIED | load_audio() line 146: `elif .mp4` with `-vn` at line 151. BatchViewModel includes "mp4" at both filter locations. test_12_mp4_write passes. |
| 7 | write_geob_mp4() writes parseable `----:com.serato.dj:beatgrid` atom | VERIFIED | analyze.py lines 643-645: `write_geob_mp4()` delegates to `_write_geob_mp4_container()`; `_select_write_fn()` dispatches `.mp4` at line 960. test_12 passes. |
| 8 | `make publish` creates a GitHub Release with DMG attached (SC-2 tooling half) | VERIFIED | Makefile line 37: publish in .PHONY; line 133: `publish: release`; lines 135-140: `git push origin $$VERSION` + `./scripts/push-all.sh` + `gh release create ... --generate-notes --repo shatakaan/serato-dynamic-analyzer`. `make -n publish` dry-run: no parse errors. |
| 9 | Published DMG is ad-hoc-signed such that analysis actually runs on user machines | VERIFIED | Makefile `sign` target now has 3 codesign steps: (1) .dylib/.so in venv, (2) venv/bin executables (`find "$(PYTHON_RUNTIME)/venv/bin" -type f -perm +111 \| xargs -I{} codesign --force --sign - --options runtime "{}"`), (3) outer .app with entitlements. Correct bottom-up order confirmed. `make -n sign` produces no parse errors. GAP 1 CLOSED. |

**Score:** 9/9 truths verified (Truth 5 requires human confirmation; all technical truths pass)

### Re-verification: Gaps Closed

| Gap | Previous Status | Current Status | Evidence |
|-----|-----------------|----------------|----------|
| Gap 1 (BLOCKER): venv/bin executables unsigned | FAILED | CLOSED | Makefile sign target line 109: `find "$(PYTHON_RUNTIME)/venv/bin" -type f -perm +111 \| xargs -I{} codesign --force --sign - --options runtime "{}"`. 3 codesign steps verified. `make -n sign` clean. |
| Gap 2 (WARNING): No TestM4aDispatch / TestMp4Dispatch | FAILED | CLOSED | python/tests/test_audio_load.py lines 272-341: `TestM4aDispatch.test_m4a_calls_ffmpeg_without_vn` (asserts -vn absent) and `TestMp4Dispatch.test_mp4_calls_ffmpeg_with_vn` (asserts -vn present). Both PASS. 9/9 test_audio_load.py tests pass. Module docstring line 11 corrected from `.m4a` to `.xyz`. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `python/tests/fixtures/minimal.m4a` | Binary fixture for M4A round-trip tests | VERIFIED | 144-byte ftyp+moov container. No regression. |
| `python/tests/test_geob.py` | Tests 11, 13, 14 for M4A; test 12 for MP4 | VERIFIED | All 4 tests pass; 16/16 test_geob.py tests pass. |
| `python/analyze.py` | M4A decode, MP4 decode, container write functions, ALLOWED_EXTENSIONS updated | VERIFIED | All symbols confirmed: `MP4_BEATGRID_KEY`, `_write_geob_mp4_container`, `write_geob_m4a`, `write_geob_mp4`. ALLOWED_EXTENSIONS includes `.m4a` and `.mp4`. |
| `SeratoDynamicAnalyzer/ViewModels/BatchViewModel.swift` | m4a and mp4 in extension filter (both locations) | VERIFIED | Line 169 (addDroppedURL guard) and line 186 (scanFolder if-contains) both include "m4a" and "mp4". |
| `SeratoDynamicAnalyzer/Views/BatchQueueView.swift` | `UTType.mpeg4Audio` and `UTType.mpeg4Movie` in allowedContentTypes | VERIFIED | Lines 99-100 confirmed. |
| `Makefile` | publish target + 3-step sign target | VERIFIED | publish: lines 133-140. sign: 3 codesign steps at lines 106-114. |
| `README.md` | Installation section with Releases link and both Gatekeeper bypass options | VERIFIED | Line 11: Releases URL; line 19: Option A right-click; line 30: `xattr -d com.apple.quarantine`; line 38: Rosetta note. |
| `python/tests/test_audio_load.py` | TestM4aDispatch + TestMp4Dispatch + corrected docstring | VERIFIED | Lines 272-341. Both classes substantive (real assertions, not stubs). Docstring line 11: `.xyz`. 9/9 tests pass. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `_select_write_fn()` | `write_geob_m4a()` | `elif ext == '.m4a'` | WIRED | analyze.py line 958-959 |
| `_select_write_fn()` | `write_geob_mp4()` | `elif ext == '.mp4'` | WIRED | analyze.py line 960-961 |
| `write_geob_m4a()` | `_write_geob_mp4_container()` | direct call | WIRED | analyze.py line 640 |
| `write_geob_mp4()` | `_write_geob_mp4_container()` | direct call | WIRED | analyze.py line 645 |
| `_write_geob_mp4_container()` | `mutagen.mp4.MP4` | `af.tags[MP4_BEATGRID_KEY]` | WIRED | analyze.py line 634 |
| `Makefile sign target` | `venv/bin executables` | `find -perm +111 \| xargs codesign` | WIRED | Makefile line 109-110 (new — Gap 1 closure) |
| `Makefile publish target` | `scripts/push-all.sh` | shell call in recipe | WIRED | Makefile line 137 |
| `Makefile publish target` | `gh release create` | CLI call with --generate-notes | WIRED | Makefile lines 138-141 |
| `TestM4aDispatch` | `analyze.load_audio` | patch subprocess.run + capture call_args | WIRED | test_audio_load.py line 297 (new — Gap 2 closure) |
| `TestMp4Dispatch` | `analyze.load_audio` | assert -vn in cmd_used | WIRED | test_audio_load.py line 335 (new — Gap 2 closure) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All test_audio_load.py tests pass (incl. new M4A/MP4 dispatch) | `python/venv/bin/python -m pytest python/tests/test_audio_load.py -v -q` | 9 passed | PASS |
| Full test suite passes | `python/venv/bin/python -m pytest python/tests/ -q` | 70 passed in 11.70s | PASS |
| sign target has 3 codesign steps in correct order | `make -n sign` | .dylib/.so → venv/bin → outer .app, no parse errors | PASS |
| -vn appears only once (MP4 branch only) | `grep -n '\-vn' python/analyze.py` | Line 151 only (inside .mp4 elif block) | PASS |
| venv/bin codesign step before outer .app sign | Line numbers in Makefile | Line 109 (venv/bin) before line 111-113 (.app) | PASS |
| Stale docstring corrected | `grep 'for .m4a' test_audio_load.py` | 0 matches | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| FMT-04 | 05-01-PLAN.md | App analysiert und schreibt M4A/AAC-Dateien (über gebundeltes ffmpeg) | SATISFIED | analyze.py M4A decode + write_geob_m4a(); tests 11/13/14 pass; Swift accepts .m4a; TestM4aDispatch confirms no -vn flag |
| FMT-05 | 05-02-PLAN.md | App analysiert und schreibt MP4-Dateien (über gebundeltes ffmpeg) | SATISFIED | analyze.py MP4 decode with -vn + write_geob_mp4(); test 12 passes; TestMp4Dispatch confirms -vn present |

Both FMT-04 and FMT-05 are marked Complete in REQUIREMENTS.md.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `SeratoDynamicAnalyzer/Views/BatchQueueView.swift` | 147 | `Button {} label: { ... }` — empty action on filter button | INFO | Renders as interactive but does nothing. Pre-Phase-5 item; does not affect format support. (IN-02) |
| `python/analyze.py` | 808 | `analyze_track()` docstring still says "MP3, AIFF, WAV" — missing M4A and MP4 | INFO | Misleads callers; does not affect behavior. (WR-03) |
| `python/tests/test_geob.py` | 32 | test_1_endianness docstring claims `b'\x01\x00'` but assertion checks `b'\x01\x01'` | INFO | Docstring wrong; assertion is correct. (WR-04) |
| `Makefile` | 49 | Error message says "Python 3.12" but BREW_PYTHON points to python@3.11 | INFO | Confusing error output for operators. (WR-05) |
| `SeratoDynamicAnalyzer/ViewModels/BatchViewModel.swift` | 92-127 | Worker bridges receive tracks before `startWorker()` completes | WARNING | Race condition in 5-track batch scenario — pre-Phase-5 architectural issue; does not block format support. (CR-01) |

**Debt marker scan:** No TBD, FIXME, or XXX markers found in any Phase 5 modified files (Makefile, python/tests/test_audio_load.py, python/analyze.py, python/tests/test_geob.py).

**Regressions from Plan 04 changes:** None. 70/70 tests pass. All previously-verified key links intact.

### Human Verification Required

Both Serato gate checkpoints (Plan 01 Task 4 and Plan 02 Task 3) are blocking human-verify gates that cannot be confirmed programmatically.

### 1. M4A Serato Gate (D-13)

**Test:** Open the app, drag a real .m4a track onto the batch queue, click Analyze All, then open the analyzed file in Serato DJ Pro
**Expected:** File enters queue (not filtered), analysis completes with Done status and BPM value, Serato DJ Pro displays a correctly positioned beatgrid that does not drift over the track
**Why human:** Serato DJ Pro beatgrid rendering requires a live Serato instance and a real audio file — cannot be verified by grep or pytest

### 2. MP4 Serato Gate (D-13)

**Test:** Open the app, drag a real .mp4 video file onto the batch queue, click Analyze All, then open the analyzed file in Serato DJ Pro
**Expected:** File enters queue, analysis completes with Done status and BPM value, Serato DJ Pro displays a correctly positioned beatgrid; audio stream extracted correctly via ffmpeg -vn
**Why human:** MP4 video decode (-vn) and Serato rendering require a live Serato instance with a real MP4 video file

### Gaps Summary

No technical gaps remain. Both blockers from the previous verification have been closed:

- Gap 1 (BLOCKER): The `sign` target now signs venv/bin executables before the outer .app. Every `make publish` will produce a Gatekeeper-compatible DMG.
- Gap 2 (WARNING): TestM4aDispatch and TestMp4Dispatch are substantive, passing tests that guard the M4A/MP4 load_audio() branches. The stale `.m4a` docstring is corrected to `.xyz`.

Phase goal is technically achieved. Awaiting human confirmation of the two Serato beatgrid rendering gates.

---

_Verified: 2026-06-09T22:30:00Z_
_Verifier: Claude (gsd-verifier)_
_Re-verification: Yes — after Plan 04 gap closure_
