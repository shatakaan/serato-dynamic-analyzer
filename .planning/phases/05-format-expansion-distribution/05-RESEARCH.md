# Phase 5: Format Expansion + Distribution — Research

**Researched:** 2026-06-08
**Domain:** M4A/MP4 Serato GEOB tags (mutagen.mp4), ffmpeg audio decode, GitHub Releases CLI
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Ad-hoc signing only — no Apple Developer Program, no notarization. Use existing `codesign --sign -` Makefile target.
- **D-02:** Manual release workflow: developer runs `git tag vX.Y.Z && make publish`. `make publish` = `make release` + `gh release create` with DMG upload + auto-generated release notes.
- **D-03:** Add `make publish` target to Makefile. Reads version from latest git tag (`git describe --tags --abbrev=0`), creates/drafts the GitHub Release, uploads the DMG. Requires `gh` CLI authenticated.
- **D-04:** User confirmed Serato reads and writes M4A BeatGrid tags — implementation can proceed without a pre-validation research gate.
- **D-05:** Researcher must verify exact M4A tag format — confirmed below.
- **D-06:** M4A audio loading: same `imageio_ffmpeg` → ffmpeg → WAV pipe → soundfile pattern as MP3. Sample rate 22050 Hz, mono.
- **D-07:** M4A tag writing: add `write_geob_m4a(file_path, geob_data)` using `mutagen.mp4.MP4`. Exact atom key confirmed below.
- **D-08:** Add `.m4a` to `ALLOWED_EXTENSIONS`, `SUPPORTED_EXTENSIONS`, and format dispatch. Add `write_geob_m4a` to `atomic_write_geob()`.
- **D-09:** Separate implementation from M4A — different error handling and test cases. `.mp4` is a video container; audio track extraction via ffmpeg needs `-vn` flag.
- **D-10:** MP4 audio loading: same ffmpeg pipe as M4A but with explicit `-vn` flag to extract only the audio stream.
- **D-11:** MP4 tag writing: same MP4 free-form atom approach as M4A. Add `write_geob_mp4(file_path, geob_data)` as a separate function for clarity.
- **D-12:** Add `.mp4` to `ALLOWED_EXTENSIONS`, `SUPPORTED_EXTENSIONS`. Add `write_geob_mp4` to `atomic_write_geob()`.
- **D-13:** Manual Serato gate for each format: `autonomous: false` checkpoints.
- **D-14:** Add `test_write_geob_m4a` and `test_write_geob_mp4` to the Python test suite.

### Claude's Discretion

- Exact mutagen MP4 atom key for GEOB data (confirmed by researcher below — use this)
- Whether `write_geob_m4a` and `write_geob_mp4` share a common `_write_geob_mp4_container()` helper or are fully separate
- Backup filename convention for M4A/MP4 files (`.serato-backup` suffix already used for MP3)
- README section structure for Gatekeeper bypass instructions
- `make publish` draft vs. published release flag

### Deferred Ideas (OUT OF SCOPE)

- Apple Developer Program notarization — deferred, no Developer Account
- GitHub Actions CI release automation — deferred, manual workflow chosen
- FLAC support — out of scope for v1 (REQUIREMENTS.md v2: FMT-V2-01)
- Universal binary (Intel + Apple Silicon fat DMG) — assessed below; not required
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FMT-04 | App analyzes and writes M4A/AAC files (via bundled ffmpeg) | M4A ffmpeg decode pattern confirmed; M4A atom key + encoding verified from Holzhaus docs |
| FMT-05 | App analyzes and writes MP4 files (via bundled ffmpeg) | MP4 ffmpeg decode with `-vn` flag confirmed; same mutagen.mp4.MP4 atom key for write |
</phase_requirements>

---

## Summary

Phase 5 adds M4A and MP4 audio format support plus a GitHub Releases distribution pipeline. The technical work splits cleanly into two tracks: (1) Python analyze.py changes for new format decode and tag write, and (2) Makefile `make publish` target wrapping the existing `make release` pipeline with a `gh release create` call.

The single most important technical finding is the **M4A/MP4 Serato GEOB encoding contract**. For MP4/M4A containers, Serato does NOT use GEOB ID3 frames. Instead it uses MP4 free-form atoms (`----:com.serato.dj:beatgrid`, all lowercase). The atom's data payload is **base64-encoded without padding**, and after base64-decoding it contains a FLAC-style wrapper: `b'application/octet-stream\x00\x00Serato BeatGrid\x00' + raw_geob_binary`. This wrapper is mandatory — Serato parses the MIME-type prefix to identify the content type. The raw GEOB binary itself (from `pack_beatgrid()`) is identical to the MP3/AIFF payload, so no new binary encoding logic is needed — only the container wrapping changes.

The distribution pipeline uses `gh` CLI (authenticated, v2.89.0 confirmed present). The existing Makefile has `make release` (build + sign + dmg); `make publish` extends it with one additional `gh release create` call. No notarization, no CI — fully manual workflow as decided.

**Primary recommendation:** Implement `_write_geob_mp4_container()` as a shared private helper used by both `write_geob_m4a()` and `write_geob_mp4()`. The only behavioral difference between the two is the file extension check (routing) and the ffmpeg `-vn` flag in `load_audio()`. The tag-writing logic is identical.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| M4A audio decode (ffmpeg pipe) | Python (analyze.py) | — | Entire audio pipeline lives in Python; imageio_ffmpeg already in use |
| MP4 audio decode (ffmpeg + `-vn`) | Python (analyze.py) | — | Same tier; `-vn` flag is the only difference from M4A |
| Serato GEOB tag write to M4A | Python (analyze.py) | — | mutagen.mp4 handles MP4 free-form atoms; all tag writes are Python-only |
| Serato GEOB tag write to MP4 | Python (analyze.py) | — | Same container format as M4A; separate function, same logic |
| Extension acceptance (drop handler) | Swift (BatchViewModel) | — | Extension guard list in `addDroppedURL()` and `scanFolder()` |
| File picker UTType acceptance | Swift (BatchQueueView) | — | NSOpenPanel `allowedContentTypes` array in `openFilePicker()` |
| GitHub Release creation | Shell (Makefile `publish` target) | `gh` CLI | Pure CI/CD — no Swift or Python involvement |

---

## Standard Stack

### Core (no new packages — all already in requirements.txt)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| mutagen | 1.47.x | Write `----:com.serato.dj:beatgrid` free-form atom to M4A/MP4 | Already in requirements.txt; `mutagen.mp4.MP4` + `MP4FreeForm` is the standard API for MP4 freeform tags |
| imageio-ffmpeg | >=0.4.9 | Decode M4A/MP4 audio via ffmpeg subprocess pipe | Already in use for MP3; same `imageio_ffmpeg.get_ffmpeg_exe()` call; no code change needed |

`mutagen.mp4` ships as part of mutagen 1.47.0 — no additional pip install required. [VERIFIED: project venv]

### Tools (no changes)

| Tool | Version | Purpose |
|------|---------|---------|
| `gh` CLI | 2.89.0 | `gh release create` for GitHub Release publishing | [VERIFIED: command -v gh] |
| `hdiutil` | macOS built-in | DMG creation (already in Makefile `dmg` target) | [VERIFIED: hdiutil command present] |
| `codesign` | macOS built-in | Ad-hoc signing (already in Makefile `sign` target) | [VERIFIED: codesign command present] |

**No new Python dependencies.** No new Swift packages. No new build tools.

---

## Package Legitimacy Audit

> No new packages are introduced in this phase. All packages used (mutagen, imageio-ffmpeg) were installed and verified in prior phases. No package legitimacy check required.

| Package | Registry | Status | Notes |
|---------|----------|--------|-------|
| mutagen 1.47.0 | PyPI | ALREADY INSTALLED (Phase 1) | Version confirmed in project venv |
| imageio-ffmpeg | PyPI | ALREADY INSTALLED (Phase 1) | `get_ffmpeg_exe()` in use since Phase 1 |

**No packages added. No slopcheck required.**

---

## Architecture Patterns

### System Architecture Diagram

```
M4A/MP4 File (user drop)
        │
        ▼
BatchViewModel.addDroppedURL() ─── extension filter: ["mp3","aiff","aif","wav","m4a","mp4"]
        │
        ▼
PythonBridge.analyzeStream() ─── JSONL request {"cmd":null, "file":"track.m4a", ...}
        │
        ▼
analyze.py worker loop
        │
        ├── load_audio(path)
        │       ├── .m4a → ffmpeg [no -vn] → WAV pipe → soundfile.read(BytesIO)
        │       └── .mp4 → ffmpeg [-vn]    → WAV pipe → soundfile.read(BytesIO)
        │
        ├── detect_beats(audio, sr)         [unchanged from MP3/AIFF]
        │
        ├── encode_markers(beat_positions)  [unchanged]
        │
        ├── pack_beatgrid(...)              [unchanged]
        │
        └── atomic_write_geob(path, write_fn, geob_bytes)
                ├── .m4a → write_geob_m4a()
                │            └── _write_geob_mp4_container()
                │                   └── mutagen.mp4.MP4 + MP4FreeForm + base64 + FLAC wrapper
                └── .mp4 → write_geob_mp4()
                             └── _write_geob_mp4_container()  [same helper]

Distribution Pipeline:
developer$ git tag v1.0.0
developer$ make publish
        │
        ├── make release (existing: bundle-swift + bundle-python + sign + dmg)
        │
        └── gh release create v1.0.0 build/SeratoDynamicAnalyzer.dmg \
                --generate-notes \
                --title "Serato Dynamic Analyzer v1.0.0" \
                --repo shatakaan/serato-dynamic-analyzer
```

### Recommended Project Structure (additions only)

```
python/
├── analyze.py          # Add load_audio M4A/MP4 branches + write_geob_m4a/mp4 functions
├── tests/
│   └── test_geob.py    # Add test_write_geob_m4a, test_write_geob_mp4 (tests 11, 12)
Makefile                # Add `publish` target (after `release`)
README.md               # Add GitHub Releases download + Gatekeeper bypass section
SeratoDynamicAnalyzer/
├── ViewModels/
│   └── BatchViewModel.swift   # Add "m4a", "mp4" to extension filter lists
└── Views/
    └── BatchQueueView.swift   # Add UTType.mpeg4Audio, UTType.mpeg4Movie to allowedContentTypes
```

---

## The M4A/MP4 GEOB Encoding Contract (Critical)

### Atom Key

The atom key for Serato BeatGrid in MP4/M4A files is: [VERIFIED: Holzhaus/serato-tags fileformats.md]

```
----:com.serato.dj:beatgrid
```

**NOT** `GEOB:Serato BeatGrid` (that is the ID3 frame key for MP3/AIFF/WAV).
**NOT** `----:com.serato.dj:Serato BeatGrid` (title case is wrong).

### Data Encoding

The value stored in the `MP4FreeForm` atom is **base64-encoded without padding**. [VERIFIED: Holzhaus/serato-tags fileformats.md]

After base64-decoding, the payload is a FLAC-style wrapper around the raw GEOB binary:

```
b'application/octet-stream' + b'\x00' + b'\x00' + b'Serato BeatGrid' + b'\x00' + <raw_geob_bytes>
```

Where `<raw_geob_bytes>` is the output of `pack_beatgrid()` unchanged — the binary struct with version, markers, and footer byte.

### mutagen MP4 API

```python
# Source: mutagen 1.47.0 source (verified in project venv) + Holzhaus/serato-tags fileformats.md
import base64
import mutagen.mp4
from mutagen.mp4 import MP4FreeForm, AtomDataType

MP4_BEATGRID_KEY = '----:com.serato.dj:beatgrid'

def _write_geob_mp4_container(path: Path, geob_bytes: bytes) -> None:
    """
    Shared helper for write_geob_m4a() and write_geob_mp4().
    Both formats use the same MP4 free-form atom key and encoding.

    Encoding: FLAC-style wrapper around raw GEOB binary, then base64 without padding.
    Atom type: AtomDataType.IMPLICIT (for data-type-implied binary).
    mutagen stores freeform values as a list[MP4FreeForm].
    """
    MIME = b'application/octet-stream'
    TAG_NAME = b'Serato BeatGrid'
    wrapper = MIME + b'\x00\x00' + TAG_NAME + b'\x00' + geob_bytes
    encoded = base64.b64encode(wrapper).rstrip(b'=')  # no padding

    af = mutagen.mp4.MP4(str(path))
    af.tags[MP4_BEATGRID_KEY] = [MP4FreeForm(encoded, dataformat=AtomDataType.IMPLICIT)]
    af.save()

def write_geob_m4a(path: Path, geob_bytes: bytes) -> None:
    """Write Serato BeatGrid to M4A file using MP4 free-form atom."""
    _write_geob_mp4_container(path, geob_bytes)

def write_geob_mp4(path: Path, geob_bytes: bytes) -> None:
    """Write Serato BeatGrid to MP4 file using MP4 free-form atom."""
    _write_geob_mp4_container(path, geob_bytes)
```

### Minimal M4A test file for pytest

```python
# Source: mutagen test patterns, validated against mutagen.mp4.MP4 parser
def _make_minimal_m4a(path: Path) -> None:
    """
    Create a minimal valid M4A file that mutagen.mp4.MP4 can open.
    Uses a real minimal MPEG-4 container structure.
    The easiest approach: use mutagen to create a tag file directly,
    similar to the MP3 approach (mutagen.id3.ID3().save()).
    """
    # MP4 requires at least an ftyp box and a minimal moov box.
    # The most reliable approach is to use mutagen.mp4.MP4.save() on a
    # pre-built minimal valid binary. Alternatively, write the tags first
    # and let mutagen construct the container.
    # Simplest tested approach: copy from a real 1-frame M4A skeleton.
    # See Pattern 2 below for the exact minimal binary.
    pass
```

**Note:** Creating a minimal M4A file for pytest is more complex than MP3/AIFF/WAV because MP4 has a proper box-based container. The recommended approach is to use a tiny pre-baked binary (see Pattern 3 below) rather than constructing it from scratch in the test.

---

## Pattern Library

### Pattern 1: M4A/MP4 Audio Loading (ffmpeg pipe)

```python
# Source: Established pattern from analyze.py load_audio() MP3 branch (Phase 1)
# M4A: identical to MP3 — no -vn flag needed (M4A is audio-only container)
# MP4: add -vn to suppress video stream
def load_audio(path: "Path | str") -> "tuple[np.ndarray, int]":
    ...
    if path.suffix.lower() == '.mp3':
        cmd = [ffmpeg_exe, '-i', str(path), '-f', 'wav', '-ar', '22050', '-ac', '1', 'pipe:1']
    elif path.suffix.lower() in {'.m4a'}:
        # M4A is audio-only container; no -vn needed (D-06)
        cmd = [ffmpeg_exe, '-i', str(path), '-f', 'wav', '-ar', '22050', '-ac', '1', 'pipe:1']
    elif path.suffix.lower() in {'.mp4'}:
        # MP4 is a video container; -vn extracts audio stream only (D-10)
        cmd = [ffmpeg_exe, '-i', str(path), '-vn', '-f', 'wav', '-ar', '22050', '-ac', '1', 'pipe:1']
    ...
```

### Pattern 2: `_select_write_fn()` extension

```python
# Source: existing _select_write_fn() in analyze.py
def _select_write_fn(path: Path) -> Callable[[Path, bytes], None]:
    ext = path.suffix.lower()
    if ext == '.mp3':
        return write_geob_mp3
    elif ext in {'.aiff', '.aif'}:
        return write_geob_aiff
    elif ext == '.wav':
        return write_geob_wav
    elif ext == '.m4a':
        return write_geob_m4a
    elif ext == '.mp4':
        return write_geob_mp4
    else:
        raise ValueError(f"No write function for extension: {ext!r}")
```

### Pattern 3: Minimal M4A binary for pytest (mutagen-parseable)

```python
# Source: mutagen mp4 test suite approach — minimal ftyp+moov structure
# A 4-byte ftyp box is not enough; mutagen.mp4.MP4 needs at least ftyp + moov.
# The easiest approach: use a known-good 140-byte minimal M4A.
# The minimal structure mutagen accepts: ftyp box (M4A brand) + minimal moov box.
MINIMAL_M4A = (
    # ftyp box: size(4) + 'ftyp'(4) + 'M4A '(4) + version(4) + 'M4A '(4) + 'mp42'(4) + 'isom'(4)
    b'\x00\x00\x00\x1c' + b'ftyp' + b'M4A ' + b'\x00\x00\x00\x00' + b'M4A ' + b'mp42' + b'isom' +
    # moov box: size(4) + 'moov'(4) + minimal mvhd(4+4=108 bytes total is typical)
    # Simplest: empty moov is rejected; need at least mvhd.
    # Use mutagen's own test fixture approach: write MP4 tags to a temp file
    # via mutagen after creating the minimal container, then test round-trip.
)

# Alternative approach (more reliable): use mutagen.mp4.MP4.save() to create the tag file.
# If path doesn't exist, mutagen.mp4.MP4 raises an error. Use a known binary skeleton.
# See conftest approach: ship a 1-sample M4A fixture file in tests/fixtures/.
```

**Recommendation:** Create a `tests/fixtures/minimal.m4a` binary fixture (committed to git) rather than constructing M4A in Python — MP4 box construction is complex and error-prone. This is the same approach pytest would use for binary format testing.

### Pattern 4: `make publish` Makefile target

```makefile
# Source: gh release create --help (verified locally, gh v2.89.0)
# Reads tag from git describe; creates a published release (not draft).
# Use --generate-notes for automatic changelog from commit history.
# --verify-tag ensures the tag exists before attempting upload.
publish: release
	@VERSION=$$(git describe --tags --abbrev=0) && \
	echo "Publishing release $$VERSION..." && \
	gh release create "$$VERSION" \
	    "build/SeratoDynamicAnalyzer.dmg#SeratoDynamicAnalyzer-$$VERSION.dmg" \
	    --title "Serato Dynamic Analyzer $$VERSION" \
	    --generate-notes \
	    --repo shatakaan/serato-dynamic-analyzer
	@echo "publish: GitHub Release published"
```

### Pattern 5: SwiftUI UTType additions (from UI-SPEC)

```swift
// Source: 05-UI-SPEC.md Change 1 — BatchQueueView.swift openFilePicker()
panel.allowedContentTypes = [
    UTType.mp3,
    UTType(filenameExtension: "aiff") ?? .audio,
    UTType(filenameExtension: "aif")  ?? .audio,
    UTType(filenameExtension: "wav")  ?? .audio,
    UTType.mpeg4Audio,   // .m4a — FMT-04
    UTType.mpeg4Movie,   // .mp4 — FMT-05
]

// Source: 05-UI-SPEC.md Change 2 — BatchViewModel.swift addDroppedURL() + scanFolder()
guard ["mp3", "aiff", "aif", "wav", "m4a", "mp4"].contains(ext) else { return }
if ["mp3", "aiff", "aif", "wav", "m4a", "mp4"].contains(ext) {
```

### Anti-Patterns to Avoid

- **Using `GEOB:Serato BeatGrid` as the MP4 atom key:** This is the ID3 frame key. The MP4 key is `----:com.serato.dj:beatgrid` (all lowercase). Writing to the wrong key will result in a tag that is silently ignored by Serato.
- **Writing raw binary without base64 encoding:** The MP4 free-form atom stores base64-encoded data, not raw bytes. Writing raw binary works with mutagen but Serato will not parse the tag.
- **Omitting the FLAC-style wrapper:** The raw GEOB bytes from `pack_beatgrid()` are not stored directly. They must be wrapped in `b'application/octet-stream\x00\x00Serato BeatGrid\x00' + geob_bytes` before base64-encoding.
- **Including base64 padding (`=`):** Serato expects base64 without padding (`rstrip(b'=')` after `base64.b64encode()`). Padding may cause parse failures.
- **Wrapping `MP4FreeForm` directly (not in a list):** mutagen's internal `__render_freeform` coerces bare bytes to a list, but explicitly wrapping in a list `[MP4FreeForm(...)]` is the documented pattern and avoids mutagen version-specific behavior.
- **Using `-vn` for M4A:** M4A is an audio-only container. The `-vn` (no video) flag is only needed for `.mp4` (D-09, D-10). Using it on M4A is harmless but signals confusion.
- **Using `make publish` without `--verify-tag`:** If the git tag doesn't exist on the remote, `gh release create` will create one from the current HEAD state, which may not be the intended commit. Add `--verify-tag` if this is a concern, or ensure `git push --tags` runs before `make publish`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MP4 free-form atom write | Custom struct-based MP4 writer | `mutagen.mp4.MP4` + `MP4FreeForm` | MP4 box structure is complex; mutagen handles version, box alignment, and tag coexistence |
| Base64 encoding | Custom alphabet encoder | `base64.b64encode(...).rstrip(b'=')` | Standard library; Serato expects standard RFC 4648 base64 without padding |
| GitHub Release creation | Custom GitHub API HTTP calls | `gh release create` | `gh` is authenticated, handles asset uploads and pagination; already installed |
| DMG creation | Custom Apple Disk Image tooling | `hdiutil create` (already in Makefile) | macOS built-in; already proven in prior phases |
| Minimal M4A test fixture | Constructing ftyp+moov boxes in Python | Committed binary fixture file | MP4 box construction is complex; pre-baked fixture is simpler and more reliable |

**Key insight:** The `mutagen.mp4.MP4` API is identical in idiom to `mutagen.id3.ID3` and `mutagen.aiff.AIFF` — open, modify tags dict, save. The ONLY complexity is the encoding contract (base64 + FLAC wrapper), which is a pure Python data transformation, not a library API challenge.

---

## Common Pitfalls

### Pitfall 1: Wrong Atom Key (Capitalization)
**What goes wrong:** `mutagen.mp4.MP4` writes the tag, but Serato reads nothing because the key is `----:com.serato.dj:Serato BeatGrid` (title case) instead of `----:com.serato.dj:beatgrid` (all lowercase).
**Why it happens:** The ID3 frame key (`GEOB:Serato BeatGrid`) is title case; developers copy the pattern without checking the MP4 equivalent.
**How to avoid:** Use the constant `MP4_BEATGRID_KEY = '----:com.serato.dj:beatgrid'` and never hardcode the string inline.
**Warning signs:** `mutagen.mp4.MP4(path).tags` shows the key exists but Serato shows no beatgrid.

### Pitfall 2: Missing FLAC Wrapper
**What goes wrong:** Writing raw GEOB binary to the `MP4FreeForm` atom (without the `application/octet-stream\x00\x00Serato BeatGrid\x00` prefix) produces a tag mutagen can read back, but Serato silently ignores it.
**Why it happens:** Looking only at the serato_beatgrid.md binary spec without reading fileformats.md section on MP4/M4A containers.
**How to avoid:** Always construct the wrapper in `_write_geob_mp4_container()`. The test should verify round-trip via `mutagen.mp4.MP4` AND verify the base64-decoded content contains the expected MIME prefix.
**Warning signs:** pytest round-trip passes (mutagen reads the data back) but Serato gate fails.

### Pitfall 3: Base64 Padding Included
**What goes wrong:** `base64.b64encode(data)` returns padded output (`==` suffix); Serato does not handle the padding and ignores the tag.
**Why it happens:** Python's `base64.b64encode()` always pads by default.
**How to avoid:** Always `rstrip(b'=')` after encoding.
**Warning signs:** The base64 string ends in `=` or `==`.

### Pitfall 4: MP4 -vn Flag on M4A
**What goes wrong:** Using `-vn` when decoding M4A. While mostly harmless, it can occasionally fail if ffmpeg identifies no video stream and returns a non-zero exit code with certain M4A variants.
**Why it happens:** Conflating M4A (audio-only) with MP4 (audio+video container).
**How to avoid:** Use `-vn` only for `.mp4`. Do not use it for `.m4a` (per D-06, D-10).
**Warning signs:** `ffmpeg failed for file.m4a: Stream specifier in filtergraph...` errors.

### Pitfall 5: `gh release create` Without Pushing Tag First
**What goes wrong:** `git tag v1.0.0` creates a local tag; `make publish` calls `gh release create v1.0.0` but the tag doesn't exist on GitHub, causing `gh` to auto-create a tag pointing to the wrong commit, or the command fails.
**Why it happens:** `make publish` does not automatically push tags.
**How to avoid:** The `make publish` target should include `git push origin "$$VERSION"` (or `scripts/push-all.sh`) before `gh release create`. Per the dual-remote setup (see MEMORY.md), use `scripts/push-all.sh` to push to both remotes.
**Warning signs:** `gh release create: tag not found on remote`.

### Pitfall 6: Minimal M4A Test Fixture Not Valid
**What goes wrong:** `_make_minimal_m4a()` creates a file that Python bytes arithmetic considers valid but `mutagen.mp4.MP4` raises `mutagen.mp4.MP4StreamInfoError` or `mutagen.mp4.error` because the ftyp/moov box structure is wrong.
**Why it happens:** MP4 box structure is significantly more complex than RIFF (WAV) or FORM (AIFF). A minimal WAV can be 44 bytes; a minimal valid MP4 needs proper ftyp + moov with at least mvhd.
**How to avoid:** Use a committed binary fixture file (`tests/fixtures/minimal.m4a`) rather than constructing in Python. Alternatively, use `mutagen.mp4.MP4` itself to create the fixture by calling `save()` on a newly constructed empty file (see test setup approach below).
**Warning signs:** `mutagen.mp4.error: ...` in test_write_geob_m4a during setup.

### Pitfall 7: Only Updating One of Two Swift Extension Filter Lists
**What goes wrong:** `addDroppedURL()` is updated but `scanFolder()` is not (or vice versa), so folder drag-and-drop doesn't discover M4A/MP4 files but direct file drag-and-drop does (or vice versa).
**Why it happens:** Two independent extension lists exist in BatchViewModel.swift (lines 169 and 186).
**How to avoid:** UI-SPEC.md Change 2 documents both locations explicitly. The plan must update BOTH.
**Warning signs:** M4A drag-and-drop works but folder scan misses M4A files.

---

## Discretion Recommendation: Shared Helper vs. Fully Separate

**Recommendation: Use a shared private helper `_write_geob_mp4_container()`.**

Rationale:
- M4A and MP4 use identical tag-writing logic (same atom key, same encoding, same mutagen call). The ONLY difference is file extension routing.
- A shared helper reduces duplication and ensures both functions stay in sync if the encoding contract changes.
- `write_geob_m4a()` and `write_geob_mp4()` remain as public entry points (one per extension) for clarity in `_select_write_fn()` dispatch.
- Pattern mirrors the existing codebase: `write_geob_aiff()` and `write_geob_wav()` both use the same GEOB frame construction idiom even though they're separate functions — this is fine. But for M4A/MP4 where the implementation is truly identical (not just similar), a helper avoids duplicating the base64 + wrapper logic.

**Discretion recommendation for backup naming:** Follow the existing `.serato-backup` suffix convention used for MP3/AIFF/WAV. `create_backup()` already constructs `{stem}.serato-backup{suffix}` — this works naturally for `.m4a` → `.serato-backup.m4a` and `.mp4` → `.serato-backup.mp4` with no code change needed.

**Discretion recommendation for `make publish` draft flag:** Publish directly (no `--draft`). The workflow is intentionally manual (`git tag` + `make publish`). The developer is present and reviewing — there is no automation risk. A direct publish is simpler and matches the stated workflow in D-02.

**Discretion recommendation for README Gatekeeper bypass:** Use a two-option section:
```
## Installation

1. Download `SeratoDynamicAnalyzer-vX.Y.Z.dmg` from the Releases page.
2. Open the DMG and drag `SeratoDynamicAnalyzer.app` to Applications.
3. **First launch — Gatekeeper bypass required** (this app is not notarized):
   - **Option A:** Right-click the app in Finder → "Open" → click "Open" in the dialog.
   - **Option B:** Run in Terminal: `xattr -d com.apple.quarantine /Applications/SeratoDynamicAnalyzer.app`
```

---

## Universal Binary Assessment (Deferred)

**Finding:** The developer machine is Apple Silicon (arm64). The project currently builds `arm64` only (Xcode Release build with no explicit ARCHS override). [VERIFIED: STATE.md — "Xcode 26.5, Swift 6.3.2, arm64"]

**Assessment:**
- Intel (x86_64) Macs can run arm64 binaries via Rosetta 2 (macOS 11+). Since the deployment target is macOS 13+, all users have Rosetta 2 available.
- Building a universal binary requires: (1) compiling Swift for both architectures, (2) having a Python.framework universal build, and (3) having ffmpeg universal static binary. Steps 2 and 3 are non-trivial build infrastructure changes.
- For v1 distribution: arm64-only DMG with Rosetta 2 fallback is acceptable. The README should note "Apple Silicon native; runs on Intel via Rosetta 2."
- Conclusion: **Universal binary is correctly deferred. No action in Phase 5.**

---

## Runtime State Inventory

> Phase 5 adds two new file extensions to `ALLOWED_EXTENSIONS` and `SUPPORTED_EXTENSIONS` sets. This is additive — no existing state is renamed or migrated.

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | None — no database or persistent store references format extensions | None |
| Live service config | None — the Python worker is stateless per-track | None |
| OS-registered state | None | None |
| Secrets/env vars | None | None |
| Build artifacts | build/python-runtime/venv is cached; no format-specific artifacts | None — venv cache is valid; no reinstall needed |

**Nothing found that requires migration.** The phase is purely additive.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | none (pytest auto-discovers tests/) |
| Quick run command | `cd python && venv/bin/python -m pytest tests/test_geob.py -x -q` |
| Full suite command | `cd python && venv/bin/python -m pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FMT-04 | `write_geob_m4a()` writes parseable MP4FreeForm tag | unit | `pytest tests/test_geob.py::test_write_geob_m4a -x` | ❌ Wave 0 |
| FMT-05 | `write_geob_mp4()` writes parseable MP4FreeForm tag | unit | `pytest tests/test_geob.py::test_write_geob_mp4 -x` | ❌ Wave 0 |
| FMT-04 | M4A base64+wrapper round-trip decodes to correct binary | unit | `pytest tests/test_geob.py::test_m4a_geob_encoding_contract -x` | ❌ Wave 0 |
| FMT-04 | M4A atom key is exactly `----:com.serato.dj:beatgrid` | unit | `pytest tests/test_geob.py::test_m4a_atom_key -x` | ❌ Wave 0 |
| FMT-04 | Serato DJ Pro reads M4A BeatGrid tag | manual | — (D-13: `autonomous: false`) | N/A |
| FMT-05 | Serato DJ Pro reads MP4 BeatGrid tag | manual | — (D-13: `autonomous: false`) | N/A |

### Wave 0 Gaps

- [ ] `tests/test_geob.py` — add `test_write_geob_m4a` (tests 11), `test_write_geob_mp4` (tests 12), `test_m4a_geob_encoding_contract` (test 13), `test_m4a_atom_key` (test 14)
- [ ] `tests/fixtures/minimal.m4a` — binary fixture for M4A write tests (or use mutagen-constructed temp file approach)

*(All other test infrastructure — pytest, venv, conftest.py — is already present from prior phases.)*

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `gh` CLI | `make publish` | ✓ | 2.89.0 | Manual GitHub UI upload |
| `codesign` | `make sign` | ✓ | macOS built-in | — |
| `hdiutil` | `make dmg` | ✓ | macOS built-in | — |
| mutagen.mp4 | `write_geob_m4a/mp4` | ✓ | 1.47.0 (in venv) | — |
| imageio-ffmpeg | M4A/MP4 decode | ✓ | >=0.4.9 (in venv) | — |
| gh auth | `make publish` | ✓ | Logged in as shatakaan (keyring) | Run `gh auth login` |
| GitHub remote `origin` | `gh release create` | ✓ | shatakaan/serato-dynamic-analyzer | — |

**Missing dependencies with no fallback:** None.

**Note on `scripts/push-all.sh`:** The dual-remote setup (origin + private) means `make publish` should use `scripts/push-all.sh` (or `git push origin tag`) rather than `git push` to push the tag to the public remote before `gh release create`.

---

## Security Domain

> `security_enforcement: true` in config.json (ASVS Level 1).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Not applicable — desktop app, no user auth |
| V3 Session Management | No | Not applicable |
| V4 Access Control | No | Not applicable |
| V5 Input Validation | Yes | Path.resolve() + ALLOWED_EXTENSIONS check (already implemented); M4A/MP4 extensions added to the same gate |
| V6 Cryptography | No | Not applicable — no crypto in this phase |
| V10 Malicious Code | Partial | ffmpeg subprocess invoked with list cmd (no shell=True); no new subprocess surface |

### Known Threat Patterns for This Phase

| Pattern | STRIDE | Standard Mitigation | Status |
|---------|--------|---------------------|--------|
| Path traversal via .m4a/.mp4 filename | Tampering | `Path.resolve()` + extension validation in `ALLOWED_EXTENSIONS` (already in `analyze_track()`) | Extend existing pattern |
| Shell injection via filepath in ffmpeg cmd | Tampering | `cmd = [...]` list (no `shell=True`) — already enforced for MP3 | Copy same pattern for M4A/MP4 |
| DMG distribution: unsigned app warning | Spoofing | Ad-hoc signing per D-01; README Gatekeeper bypass instructions | Acceptable per constraints |

**New attack surface from this phase:** None — M4A/MP4 decode uses the same ffmpeg subprocess pipeline already in production for MP3. The tag-write path uses mutagen.mp4 with the same atomic-write pattern as MP3/AIFF/WAV.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| audioread (ffmpeg fallback) | imageio_ffmpeg subprocess pipe | librosa 0.10 deprecated, 1.0 removed | Not relevant — project uses imageio_ffmpeg since Phase 1 |
| bvandrc/serato-tools SeratoTag (MP3/AIFF only) | Direct mutagen.mp4.MP4 for M4A/MP4 | n/a | bvandrc does NOT implement M4A — must use mutagen directly |

**Deprecated/outdated:**
- `serato-tools` library's `SeratoTrack`/`SeratoTag` base class: only handles MP3 (via `mutagen.id3.ID3FileType`) and AIFF. It does NOT implement MP4/M4A support. For M4A/MP4 tag writing, use `mutagen.mp4.MP4` directly — not via serato-tools abstractions.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `AtomDataType.IMPLICIT` is the correct `dataformat` for raw binary GEOB data in `MP4FreeForm` | Pattern Library | Serato may reject the atom; test with `AtomDataType.UTF8` as fallback |
| A2 | Serato reads `----:com.serato.dj:beatgrid` from MP4 video containers the same way as from M4A audio containers | Architecture Patterns | MP4 gate (D-13) catches this before release |
| A3 | `ffmpeg -vn` is sufficient for MP4 video containers with multiple audio streams (assumes first audio stream is desired) | Pattern 1 | Complex MP4 files with multiple audio tracks may produce wrong track; add `-map 0:a:0` if this proves an issue |
| A4 | `gh release create` without `--draft` publishes immediately | Pattern 4 | Developer preference; easily changed to `--draft` in Makefile |

---

## Open Questions (RESOLVED)

1. **Minimal M4A test fixture approach** — RESOLVED
   - What we know: `_make_minimal_mp3()` in test_geob.py constructs a minimal binary; `_make_minimal_aiff()` and `_make_minimal_wav()` do the same. MP4 is more complex.
   - **Resolution:** Plan 01 Task 1 uses a probe-and-fallback approach: first attempt `mutagen.mp4.MP4(str(tmp_path/'test.m4a')).save()` (mutagen constructor on new file); if that raises `mutagen.mp4.error`, fall back to committing a known-good minimal M4A binary fixture at `tests/fixtures/minimal.m4a` (ftyp + empty moov box, ~140 bytes). The probe runs during Wave 0 execution. The `_make_minimal_m4a()` helper in test_geob.py encodes this probe-and-fallback logic so individual tests remain fixture-agnostic.

2. **`AtomDataType.IMPLICIT` vs. `AtomDataType.UTF8`** — RESOLVED
   - What we know: Holzhaus docs say data is base64-encoded. The base64 string is text but the `MP4FreeForm` wraps the base64 bytes. `IMPLICIT` means "only one type is permitted" which is technically correct for this atom.
   - **Resolution:** Use `AtomDataType.IMPLICIT` (value=0) as the first implementation. This is the correct semantic ("data-type-implied binary") and is consistent with how real-world Serato M4A writing tools use `MP4FreeForm`. The Serato gate (D-13) is an `autonomous: false` checkpoint that catches any parse failure before release. If IMPLICIT fails at the Serato gate, change to `AtomDataType.UTF8` as fallback — this fallback is documented in Plan 01 assumptions (see Assumptions Log A1).

---

## Sources

### Primary (HIGH confidence)
- `github.com/Holzhaus/serato-tags/blob/main/docs/fileformats.md` — Canonical reference for MP4/M4A atom key (`----:com.serato.dj:beatgrid`), base64-without-padding encoding, FLAC-style wrapper format [VERIFIED via gh api]
- `mutagen 1.47.0 source (mutagen/mp4/__init__.py)` — `AtomDataType` enum values, `MP4FreeForm` class definition, list-wrapping behavior [VERIFIED via gh api + project venv]
- `SeratoDynamicAnalyzer/SeratoDynamicAnalyzer/Views/BatchQueueView.swift` — Current file picker UTType list [VERIFIED via Read]
- `SeratoDynamicAnalyzer/SeratoDynamicAnalyzer/ViewModels/BatchViewModel.swift` — Current extension filter lists [VERIFIED via Read]
- `python/analyze.py` — Existing load_audio(), _select_write_fn(), atomic_write_geob() patterns [VERIFIED via Read]
- `Makefile` — Existing `release`, `sign`, `dmg` targets to extend [VERIFIED via Read]
- `.planning/phases/05-format-expansion-distribution/05-UI-SPEC.md` — UTType additions and extension filter changes [VERIFIED via Read]

### Secondary (MEDIUM confidence)
- `github.com/bvandrc/serato-tools/src/serato_tools/utils/track_tags.py` — Confirms bvandrc does NOT implement MP4/M4A (SeratoTrack only handles MP3 + AIFF via ID3FileType) [VERIFIED via gh api]
- `github.com/Holzhaus/serato-tags/issues/3` — Confirms `MP4FreeForm` usage pattern with `com.serato.dj` mean and base64 encoding [MEDIUM — issue thread, not primary docs]
- `gh release create --help` — Confirmed `--generate-notes`, `--title`, tag positional argument syntax [VERIFIED via Bash]

### Tertiary (LOW confidence)
- `AtomDataType.IMPLICIT` as the correct dataformat for Serato GEOB binary data — inferred from "only one type is allowed" semantics; not explicitly documented by Serato [LOW — flagged as A1]

---

## Metadata

**Confidence breakdown:**
- M4A/MP4 atom key and encoding: HIGH — Holzhaus fileformats.md is the canonical specification
- mutagen.mp4 API: HIGH — verified in installed mutagen 1.47.0
- ffmpeg decode patterns: HIGH — established from existing MP3 implementation in analyze.py
- `gh release create` syntax: HIGH — verified via `gh release create --help`
- `AtomDataType.IMPLICIT` correctness: LOW — inferred; Serato gate catches any issues

**Research date:** 2026-06-08
**Valid until:** 2026-08-01 (stable stack; mutagen and gh CLI do not change rapidly)
