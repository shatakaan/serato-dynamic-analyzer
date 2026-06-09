# Serato Dynamic Analyzer

A native macOS SwiftUI app that performs dynamic BPM/beatgrid analysis for Serato DJ — exactly what Rekordbox does, but Serato doesn't. The app bundles Python (librosa) for audio analysis, reads and writes Serato GEOB tags directly into music files, and provides a visual interface for individual tracks (drag and drop) as well as complete Serato library integration with batch processing.

**Core value:** A DJ drags a track in (or selects their Serato library), presses "Analyze" — and gets a beat-accurate dynamic beatgrid that Serato understands directly.

## Installation

### Download

Download the latest `SeratoDynamicAnalyzer-vX.Y.Z.dmg` from the [Releases page](https://github.com/shatakaan/serato-dynamic-analyzer/releases).

Open the DMG and drag `SeratoDynamicAnalyzer.app` to your Applications folder.

### First Launch — Gatekeeper Bypass Required

This app is ad-hoc signed (not notarized by Apple). macOS will block it on first launch. Use one of the two options below to open it:

**Option A: Right-click method (no Terminal required)**

1. Right-click `SeratoDynamicAnalyzer.app` in Finder.
2. Select "Open" from the context menu.
3. In the security dialog that appears, click "Open".

You only need to do this once. After the first approved launch, the app opens normally.

**Option B: Terminal command**

```
xattr -d com.apple.quarantine /Applications/SeratoDynamicAnalyzer.app
```

Then launch the app normally from Finder or Spotlight.

### System Requirements

- macOS 13 Ventura or later
- Apple Silicon (arm64) native; runs on Intel Macs via Rosetta 2

## Supported Audio Formats

- MP3
- M4A / AAC
- MP4 (audio track extraction)
- AIFF / AIF
- WAV

## What This Solves

Serato analyzes tracks statically (one BPM value for the entire track). For live recordings or songs with a human drummer, the tempo drifts — the beatgrid doesn't fit, and sync breaks. Rekordbox solves this with "Dynamic Analysis". Serato doesn't offer this.

This app performs dynamic beatgrid analysis using librosa and writes the result as a Serato-compatible `GEOB:Serato BeatGrid` tag directly into your audio files. Serato reads these tags natively.

## Development

### Build from Source

```
make release
```

This runs the full pipeline: Python venv setup, Swift build via Xcode, ad-hoc code signing, and DMG creation.

### Release

```
git tag vX.Y.Z
make publish
```

`make publish` builds the full release, pushes the tag to GitHub, and creates a GitHub Release with the DMG attached and auto-generated release notes.

Requires `gh` CLI authenticated (`gh auth login`).

## References

- [bvandrc/serato-tools](https://github.com/bvandrc/serato-tools) — reference Python CLI for Serato tag writing
- [Holzhaus/serato-tags](https://github.com/Holzhaus/serato-tags) — complete documentation of the Serato GEOB tag format
