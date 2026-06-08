# Phase 5: Format Expansion + Distribution - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-08
**Phase:** 5-format-expansion-distribution
**Areas discussed:** Code Signing, M4A/MP4 Serato-Kompatibilität, Release-Workflow

---

## Code Signing

| Option | Description | Selected |
|--------|-------------|----------|
| Apple Developer ID + Notarization ($99/yr) | Gatekeeper passes silently, no warning for user | |
| Ad-hoc signing + Gatekeeper-Bypass-Anleitung | Kostenlos, Gatekeeper zeigt Warning, User muss einmalig bypass ausführen | ✓ |
| Später entscheiden | Beide Pfade planen, Developer ID als optionaler Step | |

**User's choice:** Nein, kein Apple Developer Account, und auch keiner geplant. Ad-hoc Signing.

**Notes:** Success Criteria #2 ("passes Gatekeeper without security warnings") wurde angepasst zu: "GitHub Releases enthält ein ad-hoc-signiertes DMG + README-Sektion mit Gatekeeper-Bypass-Anleitung (xattr -d com.apple.quarantine oder rechtsklick → Öffnen)."

---

## M4A/MP4 Serato-Kompatibilität

| Option | Description | Selected |
|--------|-------------|----------|
| Serato unterstützt M4A (user nutzt es) | Direkt implementieren, Serato-Gate im Plan | ✓ |
| Unsicher — Research klärt das | Researcher verifiziert Holzhaus-Docs | |
| Assume it works | Direkt implementieren, kein expliziter Research | |

**User's choice:** Serato unterstützt M4A — user nutzt M4A-Dateien mit Serato.

| Option | Description | Selected |
|--------|-------------|----------|
| Eine Implementierung für M4A + MP4 | Beide MP4-Container, gleicher Code | |
| Separate Implementierungen | Unterschiedliche Fehlerbehandlung und Test-Cases | ✓ |

**User's choice:** Separat — M4A und MP4 bekommen eigene Funktionen und Tests.

**Notes:** Exaktes M4A-Tag-Format (Holzhaus-Docs, mutagen.mp4 Atom-Key) soll der Researcher klären. User weiß nicht ob es dasselbe GEOB-Format wie bei MP3 ist — researcher soll Holzhaus-Docs prüfen.

---

## Release-Workflow

| Option | Description | Selected |
|--------|-------------|----------|
| Manuell: git tag + make release + gh release create | Kein CI/CD-Setup, lokal bauen und hochladen | ✓ |
| GitHub Actions: Release bei git tag push | Automatisierter Build, braucht macOS-Runner ($) + Secrets | |

**User's choice:** Manuell — passt zum Setup ohne Apple Developer Account (keine Notarization-Secrets nötig).

| Option | Description | Selected |
|--------|-------------|----------|
| make publish als One-Command (release + gh upload) | Ein Befehl nach git tag | ✓ |
| Nur DMG, Upload manuell | Makefile endet bei DMG | |

**User's choice:** make publish Target — alles in einem Befehl nach git tag.

---

## Claude's Discretion

- Exakter mutagen MP4 Atom-Key für GEOB-Daten (Researcher bestätigt aus Holzhaus-Docs)
- Ob write_geob_m4a und write_geob_mp4 einen gemeinsamen Helper teilen oder vollständig getrennt sind
- Backup-Dateinamen-Konvention für M4A/MP4
- README-Sektions-Struktur für Gatekeeper-Bypass
- make publish: draft vs. published release Flag

## Deferred Ideas

- Apple Developer Program Notarisierung — kein Account, deferred
- GitHub Actions CI Release-Automatisierung — manueller Workflow gewählt
- FLAC-Unterstützung — v2 Requirement (FMT-V2-01)
- Universal Binary (Intel + Apple Silicon) — researcher soll bewerten ob nötig
