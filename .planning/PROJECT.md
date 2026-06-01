# Serato Dynamic Analyzer

## What This Is

Eine native macOS SwiftUI App, die dynamische BPM/Beatgrid-Analyse für Serato DJ durchführt — genau das, was Rekordbox kann, aber Serato nicht. Die App bundelt Python (librosa) für die Audio-Analyse, liest und schreibt Serato GEOB-Tags direkt in die Musikdateien, und bietet eine visuelle Oberfläche für Einzeltracks (Drag & Drop) sowie die komplette Serato-Library-Integration mit Batch-Verarbeitung.

## Core Value

Ein DJ zieht einen Track rein (oder wählt seine Serato-Library), drückt "Analyze" — und bekommt ein taktgenaues dynamisches Beatgrid, das Serato direkt versteht.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Dynamische Beatgrid-Analyse: Tempo-Variationen eines Tracks erkennen und als Serato-konformes Beatgrid berechnen
- [ ] Serato GEOB Tags schreiben: Ergebnis als "Serato BeatGrid" GEOB-Tag direkt in die Audiodatei (MP3, M4A, FLAC, etc.) schreiben
- [ ] Drag & Drop: Einzelne Tracks oder Ordner per Drag & Drop in die App ziehen
- [ ] Serato-Library-Integration: Bestehende Serato-Bibliothek einlesen (Crates, Ordner) und Tracks daraus auswählen
- [ ] Batch-Verarbeitung: Mehrere Tracks gleichzeitig analysieren
- [ ] Fortschritts-UI: Live-Fortschrittsanzeige, Analyse-Log und Fehleranzeige pro Track

### Out of Scope

- Windows/Linux-Support — macOS only, bewusste Entscheidung für native UX
- Mac App Store — Sandboxing inkompatibel mit dem nötigen freien Dateizugriff
- Key-Erkennung, Waveform-Anzeige, Cue-Point-Management — v2-Features, nicht v1
- Cloud/Server-Verarbeitung — alles lokal auf dem Rechner des DJs
- Statische Beatgrid-Analyse — Serato macht das bereits; wir ergänzen nur das Fehlende

## Context

**Das Problem:** Serato analysiert Tracks nur statisch (ein BPM-Wert für den gesamten Track). Bei Live-Aufnahmen oder Songs mit menschlichem Schlagzeug weicht das Tempo ab, das Beatgrid passt nicht — Sync funktioniert nicht. Rekordbox löst das mit "Dynamic Analysis". Serato bietet das nicht.

**Bestehende Werkzeuge (alle CLI-only, kein echtes Tool für Endnutzer):**
- [bvandrc/serato-tools](https://github.com/bvandrc/serato-tools) — Python CLI, dynamische Analyse mit librosa, schreibt Serato-Tags
- [gdhgdhgdh/serato-variable-tempo](https://github.com/gdhgdhgdh/serato-variable-tempo) — Python CLI mit Vamp Plugins, max. 128 Marker pro Track
- [Holzhaus/serato-tags](https://github.com/Holzhaus/serato-tags) — vollständige Dokumentation des Serato GEOB-Tag-Formats (Basis für alle anderen)

**Serato-Tags:** Serato speichert Beatgrid-Daten als GEOB-Tag "Serato BeatGrid" in ID3v2 (MP3) bzw. äquivalenten Format-Tags. Binärformat ist durch Holzhaus dokumentiert und kann mit `mutagen` (Python) geschrieben werden.

**Serato-Library:** Liegt typischerweise unter `~/Music/Serato/`. Crates und Track-Daten sind als proprietäre Binärdateien gespeichert, aber auch hier gibt es Reverse-Engineering (Holzhaus, bvandrc).

**Analyse-Engine:** Python (librosa + numpy) wird als eingebetteter Subprozess gebundelt. Das ist der schnellste Weg und nutzt die erprobte Basis von bvandrc/serato-tools. Bundle-Größe ~200MB ist akzeptabel für ein direktes Download-Tool.

## Constraints

- **Tech**: SwiftUI (macOS 13 Ventura+), eingebettetes Python 3.12 mit librosa/numpy/mutagen
- **Kompatibilität**: Serato GEOB-Tag-Format muss byte-genau eingehalten werden — falsche Tags machen Tracks in Serato unbrauchbar
- **Distribution**: GitHub Releases + signiertes .dmg — kein App Store, kein Sandboxing
- **Audio-Formate**: Mindestens MP3 und M4A/AAC (Serato-Hauptformate); FLAC und MP4 nice-to-have
- **Abhängigkeit**: Holzhaus-Dokumentation als Tag-Format-Referenz; bvandrc-Implementierung als Code-Referenz

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python bundeln statt native Audio-Analyse | librosa ist battle-tested für Beat-Detection; spart Wochen Entwicklungszeit; kann später durch nativen Swift/C++ Code ersetzt werden | — Pending |
| SwiftUI statt Electron/Web | Native macOS UX, kein Overhead, passt zur Zielgruppe (DJs auf Mac) | — Pending |
| Kein App Store | Freier Dateisystem-Zugriff nötig (beliebige Ordner/Library), Sandboxing nicht praktikabel | — Pending |
| bvandrc/serato-tools als Referenz-Implementierung | Hat die Kernfunktion bereits funktionsfähig, dokumentiert die Tag-Schreiblogik | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-01 after initialization*
