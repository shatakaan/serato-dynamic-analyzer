# Technology Stack: Serato Dynamic Analyzer

**Project:** Serato Dynamic Analyzer (native macOS SwiftUI + bundled Python subprocess)
**Researched:** 2026-06-01
**Overall confidence:** MEDIUM-HIGH (core stack HIGH; bundling/signing details MEDIUM due to Apple's evolving requirements)

---

## Recommended Stack

### Core Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| SwiftUI | macOS 13+ SDK | Native UI, drag-and-drop, progress reporting | Already decided; correct choice — no sandboxing constraint, native feel for DJ-on-Mac audience |
| Foundation Process | macOS 13+ | Spawn/manage Python subprocess | Built-in, well-understood; adequate for this use case. Swift Subprocess is the modern successor but still pre-stable as of mid-2026. |
| Swift Concurrency (async/await + AsyncStream) | Swift 5.9+ | Stream stdout progress from Python process | The right model for non-blocking progress reporting into SwiftUI. AsyncStream bridges Pipe callbacks to the async world cleanly. |

### Python Runtime

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| CPython Framework (python.org) | 3.12.x | Embedded Python runtime | python.org ships a `Python.framework` bundle that is fully signable. 3.12 is stable, broadly supported by all required libs. Avoid 3.13 — numpy/librosa wheels are still catching up. |
| uv (build-time tool) | latest | Create relocatable venv at build time | Fastest pip-alternative, supports `--relocatable` venv flag. Use `py-app-standalone` wrapper or manual `install_name_tool` step to fix `.dylib` absolute paths after creation. Do NOT ship uv itself — it is only needed at build time. |

### Audio Analysis (Python)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| librosa | 0.11.x | Beat tracking, onset detection, dynamic tempo | 0.11 has built-in time-varying (dynamic) tempo support via `librosa.feature.tempo()` + frame-level BPM passed into `librosa.beat.beat_track()`. The bvandrc/serato-tools reference implementation already uses librosa — adopt the same stack to stay close to the working reference. |
| numpy | 1.26.x / 2.0.x | Array math for beat positions | Core librosa dependency. 2.0 is stable; pin to avoid ABI breakage in the bundled venv. |
| soundfile | 0.12.x | Audio file decoding (WAV, FLAC, AIFF) | librosa's default backend. Fast, no subprocess required. Handles lossless formats well. |
| ffmpeg (static binary) | 7.x | Decode MP3, M4A/AAC | soundfile/libsndfile cannot decode MP3 or M4A. Bundle a static ffmpeg binary in `Contents/Resources/bin/`. librosa's audioread fallback was deprecated in 0.10 and removed in 1.0 — use `subprocess`/`soundfile.SoundFile` with ffmpeg pre-decode instead. |
| mutagen | 1.47.x | Read/write Serato GEOB tags | The proven tool for this job. GEOB frame support is first-class. bvandrc/serato-tools depends on it directly. taglib lacks first-class Python GEOB support; native Swift ID3 libraries have no GEOB implementations for Serato's binary format. |

### Tag Writing

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| mutagen | 1.47.x | Write `GEOB:Serato BeatGrid` to MP3 (ID3v2), M4A (MP4 free-form tags), FLAC (VorbisComment binary data) | mutagen handles all three container formats uniformly from Python. The Holzhaus documentation describes the exact binary struct; mutagen provides the raw GEOB frame insertion. This is byte-exact writable — critical requirement. |

---

## IPC Strategy: Swift ↔ Python

**Recommendation: stdin/stdout JSON lines over Foundation Process + Pipe**

Confidence: HIGH

### Why stdin/stdout JSON lines

- Zero extra infrastructure — no sockets, no HTTP server, no port conflicts
- The Python script emits newline-delimited JSON: progress events (`{"type":"progress","file":"x.mp3","pct":42}`), results (`{"type":"result",...}`), and errors (`{"type":"error","msg":"..."}`)
- Swift reads stdout asynchronously via `FileHandle.readabilityHandler` wrapped in an `AsyncStream<String>`, feeding directly into a SwiftUI `@MainActor` `@Observable` model
- stderr is captured separately for crash diagnostics — keep it human-readable, not JSON
- One Python process per analysis job. For batch jobs, spawn up to `ProcessInfo.processInfo.processorCount / 2` processes (avoid thrashing; each Python+librosa job is CPU-heavy)

### Why NOT the alternatives

| Option | Problem |
|--------|---------|
| PythonKit (in-process embedding) | Cannot capture stdout — confirmed limitation in Swift Forums. Python's GIL also blocks Swift UI thread. Signing is more complex (must link against Python.framework from Swift). |
| Unix socket / localhost HTTP | Over-engineered for a tool that processes one file at a time. Adds server lifecycle management, port-conflict risk, and zero throughput benefit for batch audio tasks. |
| XPC service | Correct architecture for a production tool, but adds 2-3 weeks of boilerplate for no practical gain here. Revisit in v2 if the analyzer becomes a persistent daemon. |
| stdin/stdout raw binary | Less debuggable than JSON lines; no self-describing schema. |

### Pipe Buffer Warning

For large audio files librosa may output a single large JSON result blob. **Drain the stdout Pipe asynchronously** — do not call `pipe.fileHandleForReading.readDataToEndOfFile()` synchronously or the process will deadlock when the kernel pipe buffer fills (~65 KB on macOS). Use `readabilityHandler` or Swift's new `swift-subprocess` package which handles this automatically.

---

## Python Bundling Strategy

**Recommendation: Embedded Python.framework + relocatable venv in `Contents/Resources/`**

Confidence: MEDIUM (signing step is fiddly; Apple's requirements evolve)

### Approach

```
MyApp.app/
  Contents/
    MacOS/
      MyApp                    (Swift binary)
    Frameworks/
      Python.framework/         (python.org 3.12 framework, stripped of IDLE/Tkinter)
    Resources/
      python/
        venv/                   (relocatable venv: librosa, numpy, soundfile, mutagen)
      bin/
        ffmpeg                  (static universal binary)
      scripts/
        analyze.py              (the analysis entry point)
```

### Build steps (CI/CD or Makefile)

1. Download Python 3.12 framework from python.org (or BeeWare's pre-stripped version from `beeware/Python-Apple-support`)
2. Use `install_name_tool` + `@rpath` to make all `.dylib` references relocatable (or use the `fractolog.com` 2025 recipe that patches the framework in place)
3. `uv venv --relocatable venv/` inside `Resources/python/`
4. `uv pip install librosa numpy soundfile mutagen --python venv/bin/python`
5. Copy `ffmpeg` static binary to `Resources/bin/`
6. At app launch: Swift sets `PYTHONHOME` and `PATH` environment vars pointing into the bundle before spawning the subprocess

### Alternatives Considered

| Approach | Why Not |
|----------|---------|
| py2app | Wraps Python as the main executable — doesn't fit our model where Swift is the app and Python is a helper |
| PyInstaller | Same problem; also generates bloated bundles with duplicate libs |
| Homebrew Python | Not bundleable; depends on Homebrew prefix being present on user's machine |
| Conda/Miniforge | Enormous bundle size (500MB+); complex signing of hundreds of dylibs |
| BeeWare Briefcase | Designed for Python-first apps; awkward when Swift is the host |

---

## Signing and Notarization Notes

Confidence: MEDIUM (requirements confirmed from Apple Developer docs + community posts; exact entitlement combinations may need iteration)

### Required Entitlements (`.entitlements` plist)

```xml
<key>com.apple.security.cs.allow-unsigned-executable-memory</key>
<true/>
```

Python's JIT/bytecode compilation at import time writes executable memory. Without this entitlement, Gatekeeper will kill the process on first launch under Hardened Runtime.

Optionally also include:
```xml
<key>com.apple.security.cs.disable-library-validation</key>
<true/>
```
Only if you hit `DYLD_LIBRARY_VALIDATION` errors for `.so` extension modules. Prefer signing all `.so` files correctly instead.

### Signing Order (critical — sign inner to outer)

1. Sign every `.so` and `.dylib` inside the venv and Python.framework
2. Sign the `ffmpeg` binary
3. Sign `Python.framework` as a whole (`--deep` is deprecated; sign each binary individually)
4. Sign the main `MyApp` binary
5. Sign the `.app` bundle

```bash
# Example: sign all .so and .dylib inside Resources
find MyApp.app/Contents/Resources -name "*.so" -o -name "*.dylib" | \
  xargs -I{} codesign --force --sign "Developer ID Application: ..." \
    --options runtime --timestamp {}
```

### Notarization Workflow

```
build → sign → zip (ditto -c -k -rsrc) → notarytool submit → staple → create .dmg → sign .dmg
```

Use `xcrun notarytool submit` (replaces deprecated `altool`). Staple the ticket before packaging in the DMG.

### Key Gotchas

- **All binaries must carry a secure timestamp** (`--timestamp` flag). Without it, notarization rejects.
- **Python.framework relocatability**: The framework bakes absolute paths into its `dylib`. Run `install_name_tool -change` or `otool -L` to verify no `/Library/Frameworks/Python.framework` references remain in the shipped bundle — they will break on user machines.
- **Universal binary vs. arm64**: If targeting both Intel and Apple Silicon, build fat binaries for Python.framework and ffmpeg, or provide separate download artifacts. numpy/librosa have universal wheels on PyPI as of 2024.
- **ffmpeg**: Use a static build (e.g., from `evermeet.cx` or build with `--disable-shared`). Dynamic ffmpeg pulls in dozens of dylibs that all need signing.
- **No App Store**: Sandboxing entitlement (`com.apple.security.app-sandbox`) must NOT be present — it would block arbitrary file access to the user's music library.

---

## Beat Detection Library Decision

**Recommendation: librosa 0.11 as primary, with beat-this as upgrade path**

Confidence: MEDIUM-HIGH

### librosa 0.11 (use now)

- Has `librosa.feature.tempo(aggregate=None)` for frame-level time-varying BPM
- `librosa.beat.beat_track(bpm=tempo_per_frame)` accepts the frame-level array — this is the dynamic beatgrid API
- Already used by bvandrc/serato-tools — adopt and extend, don't reinvent
- Python 3.12 compatible, active maintenance, PyPI wheels available

**Known limitations:** Onset-envelope approach can produce slightly delayed beats on rhythmically complex material. For typical DJ music (electronic, rock) accuracy is sufficient. For jazz/classical, consider the upgrade path below.

### beat-this (ISMIR 2024, CPJKU) — upgrade path

- Transformer-based deep learning model; state-of-the-art F1 on beat tracking benchmarks (2024)
- Does NOT require DBN postprocessing
- Requires PyTorch 2.0+ — adds ~500MB to bundle
- Python 3.12 compatible
- **Verdict**: Too heavy for v1 (~700MB total bundle). Revisit if librosa accuracy proves insufficient for live-recorded tracks in user testing.

### madmom — do not use

- Last release 0.16.1; no releases since 2020; issue tracker shows Python 3.10+ breaks `MutableSequence` import (not fixed in PyPI release)
- Would require Python 3.9 or a manual source patch — incompatible with the decided Python 3.12 environment
- Beat-this is its spiritual successor from the same CPJKU research group

### essentia — do not use for v1

- C++ library with Python bindings; non-trivial to build for Apple Silicon; binary wheels are inconsistently available
- Would significantly complicate the bundling step
- May be worth revisiting for key detection in v2

### aubio — do not use

- Beat tracking accuracy is lower than librosa in benchmarks; onset detection is strong but not the primary need here
- Less maintained than librosa on Python 3.12

---

## Audio Loading: AVFoundation vs librosa/ffmpeg

**Recommendation: ffmpeg (bundled static binary) → soundfile → librosa. Do NOT use AVFoundation.**

Confidence: HIGH

### Rationale

- AVFoundation decoding requires writing to a temp file (or streaming PCM over a socket), then passing to the Python subprocess. This adds a Swift ↔ filesystem round-trip with no benefit.
- librosa can decode via soundfile (WAV, FLAC, AIFF natively) and via a pre-decode step with a bundled ffmpeg binary for MP3 and M4A
- The Python analysis script controls the full pipeline: `ffmpeg -i input.m4a -f wav - | soundfile.read(...)` via subprocess pipe, or pre-convert to a temp WAV
- Keeps the entire audio pipeline in Python — simpler, no Swift audio code required
- AVFoundation would be the right choice only if the app needed to play back audio in the SwiftUI layer (not a v1 requirement)

### M4A/AAC handling

libsndfile (soundfile's backend) does NOT decode AAC. Use ffmpeg:
```python
import subprocess, soundfile, io
proc = subprocess.run(
    ["ffmpeg", "-i", str(path), "-f", "wav", "-"],
    capture_output=True
)
audio, sr = soundfile.read(io.BytesIO(proc.stdout))
```
Bundle `ffmpeg` at `Contents/Resources/bin/ffmpeg` and resolve its path at Python startup via `os.environ["FFMPEG_PATH"]` set by the Swift host before spawning.

---

## What NOT to Use and Why

| Technology | Verdict | Reason |
|------------|---------|--------|
| PythonKit | Avoid | Cannot capture stdout; GIL blocks UI thread; signing complexity; no practical advantage over subprocess |
| py2app / PyInstaller | Avoid for this project | Designed for Python-as-host apps; Swift-as-host pattern does not fit their model |
| Homebrew Python | Avoid | Not bundleable; breaks on machines without Homebrew or different prefix |
| Conda/Miniforge bundle | Avoid | 500MB+ for package manager overhead; signing hundreds of dylibs is impractical |
| localhost HTTP server | Avoid | Over-engineered; adds lifecycle complexity; not needed for file-at-a-time workloads |
| XPC service | Defer to v2 | Correct isolation architecture but 2–3 weeks of boilerplate for no v1 benefit |
| madmom | Avoid | Broken on Python 3.10+; effectively unmaintained |
| beat-this / PyTorch | Defer to v2 | Accurate but adds 500–700MB to bundle; disproportionate for v1 |
| essentia | Avoid for v1 | Build complexity on Apple Silicon; inconsistent binary wheels |
| audioread (librosa fallback) | Avoid | Deprecated in librosa 0.10, removed in 1.0; use ffmpeg pre-decode instead |
| App Store / Sandboxing | Not applicable | Incompatible with arbitrary file system access to user's music library — already excluded |
| Swift Subprocess package | Monitor | Excellent API; still pre-stable as of mid-2026. Evaluate at project start; adopt if stable, fall back to Foundation Process otherwise |

---

## Key Library Versions (Pin These)

```
# requirements.txt (for the bundled venv)
librosa==0.11.*
numpy==2.0.*
soundfile==0.12.*
mutagen==1.47.*
scipy==1.13.*        # librosa dependency; pin to avoid ABI surprises
scikit-learn==1.5.*  # librosa dependency
```

Python runtime: **3.12.x** (not 3.13 — ecosystem wheels still catching up)
ffmpeg: **7.x static universal** (not Homebrew dynamic build)

---

## Sources

- [serato-tools PyPI / bvandrc GitHub](https://github.com/bvandrc/serato-tools) — reference implementation confirms mutagen + librosa stack
- [Holzhaus/serato-tags](https://github.com/Holzhaus/serato-tags) — GEOB format specification
- [librosa 0.11 dynamic beat tracking example](http://librosa.org/doc/0.11.0/auto_examples/plot_dynamic_beat.html) — confirms frame-level tempo API
- [librosa advanced I/O formats](https://librosa.org/doc/0.11.0/ioformats.html) — audioread deprecation confirmed
- [beat-this ISMIR 2024 paper](https://arxiv.org/html/2407.21658v1) — CPJKU transformer beat tracker
- [madmom Python 3.10+ incompatibility (CPJKU/beat_this issue #9)](https://github.com/CPJKU/beat_this/issues/9) — confirmed broken
- [Making Python.org Python.framework Relocatable (Fractolog, May 2025)](https://www.fractolog.com/2025/05/making-python-org-python-framework-relocatable/) — current relocation recipe
- [BeeWare Python-Apple-support](https://github.com/beeware/Python-Apple-support) — pre-stripped, relocatable Python.framework builds
- [py-app-standalone (jlevy)](https://github.com/jlevy/py-app-standalone) — uv + install_name_tool approach for relocatable installs
- [How to make a Python script into a macOS app with py2app (sign & notarize)](https://stupidtech.io/2025/03/15/how-to-make-a-python-script-into-a-macos-app-with-py2app-code-sign-notarize/) — signing workflow reference (March 2025)
- [Apple: Allow Unsigned Executable Memory Entitlement](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.cs.allow-unsigned-executable-memory)
- [PythonKit stdout limitation (Swift Forums)](https://forums.swift.org/t/reading-stdout-from-pythonkit/54464)
- [swift-subprocess (swiftlang)](https://github.com/swiftlang/swift-subprocess)
- [BIFF.ai beat detection model rundown](https://biff.ai/a-rundown-of-open-source-beat-detection-models/)
