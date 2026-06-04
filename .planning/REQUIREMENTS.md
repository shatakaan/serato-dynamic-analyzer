# Requirements: Serato Dynamic Analyzer

**Defined:** 2026-06-02
**Core Value:** Ein DJ zieht einen Track rein, drückt "Analyze" — und bekommt ein taktgenaues dynamisches Beatgrid, das Serato direkt versteht.

## v1 Requirements

### Analyse-Engine

- [x] **ANAL-01**: Nutzer kann Tracks dynamisch analysieren — Tempo-Variationen erkennen und als Serato-konformes Beatgrid-Tag speichern
- [x] **ANAL-02**: Nutzer kann BPM-Range vor der Analyse einstellen (Min/Max, Standard 60–200 BPM)
- [x] **ANAL-03**: Analyse überschreibt nur das Serato-BeatGrid-Tag — alle anderen Serato-Tags (Cues, Loops, Waveform) bleiben unverändert
- [x] **ANAL-04**: App erkennt, ob Serato DJ offen ist, und zeigt eine Warnung vor dem Schreibzugriff

### Dateiformate

- [x] **FMT-01**: App analysiert und schreibt MP3-Dateien (ID3v2 GEOB)
- [x] **FMT-02**: App analysiert und schreibt AIFF-Dateien
- [x] **FMT-03**: App analysiert und schreibt WAV-Dateien
- [ ] **FMT-04**: App analysiert und schreibt M4A/AAC-Dateien (über gebundeltes ffmpeg)
- [ ] **FMT-05**: App analysiert und schreibt MP4-Dateien (über gebundeltes ffmpeg)

### Datei-Sicherheit

- [x] **SAFE-01**: App erstellt automatisch ein Backup der Originaldatei vor jedem Schreibzugriff (sichtbar im UI)
- [x] **SAFE-02**: Nutzer kann einen Dry-Run durchführen — Analyse ohne Schreiben, zeigt was passieren würde
- [x] **SAFE-03**: App schreibt atomar (Temp-Datei zuerst, dann ersetzen) — kein korrupter Zustand bei Abbruch

### Datei-Import

- [x] **INPUT-01**: Nutzer kann einzelne Tracks per Drag & Drop in die App ziehen
- [x] **INPUT-02**: Nutzer kann Ordner per Drag & Drop hinzufügen — alle unterstützten Dateien werden gefunden

### Serato-Library

- [ ] **LIB-01**: App liest die bestehende Serato-Library ein (~/Music/Serato/)
- [ ] **LIB-02**: Nutzer kann in einem Crate-Browser Crates und Ordner durchsuchen und Tracks auswählen
- [ ] **LIB-03**: App zeigt pro Track an, ob bereits ein Beatgrid vorhanden ist (von Serato oder diesem Tool)

### Batch-Verarbeitung

- [x] **BATCH-01**: Nutzer kann mehrere Tracks gleichzeitig analysieren (2–4 parallel)
- [x] **BATCH-02**: Nutzer sieht Gesamtfortschritt der Batch-Verarbeitung (X von N Tracks fertig)

### Feedback & UI

- [x] **UI-01**: App zeigt pro Track einen Status: Pending / Analyzing / Done / Failed
- [x] **UI-02**: Bei fehlgeschlagenen Tracks zeigt die App eine spezifische, lesbare Fehlermeldung
- [x] **UI-03**: Nutzer kann ein Analyse-Log pro Track einsehen (erkannte BPM, Marker-Anzahl, Analysedauer)

## v2 Requirements

### Erweiterte Analyse

- **ANAL-V2-01**: Key-Erkennung (musikalischer Key / Camelot) pro Track
- **ANAL-V2-02**: Waveform-Visualisierung während/nach der Analyse
- **ANAL-V2-03**: Analyse-Konfidenz-Indikator und "Review needed"-Queue für unsichere Ergebnisse
- **ANAL-V2-04**: BPM-Sparkline (Tempo-Verlauf über die Track-Länge als Miniaturdiagramm)

### Erweiterte Formate

- **FMT-V2-01**: FLAC-Unterstützung (Tag-Format wenig dokumentiert, erst nach Validation)

### Erweiterte UI

- **UI-V2-01**: Cue-Point-Management (setzen, bearbeiten, auf Beat snappen)
- **UI-V2-02**: Bulk-Overwrite-Warnung (Tracks mit existierendem manuellem Grid gesondert kennzeichnen)

### Beat-Detection-Engine

- **ENGINE-V2-01**: beat-this (CPJKU Transformer-Modell) als alternatives Backend — höhere Genauigkeit, +500–700 MB Bundle

## Out of Scope

| Feature | Reason |
|---------|--------|
| Windows/Linux-Support | macOS only — bewusste Entscheidung für native SwiftUI UX |
| Mac App Store | Sandboxing inkompatibel mit freiem Dateisystem-Zugriff |
| Statische Beatgrid-Analyse | Serato bietet das bereits nativ |
| Cloud/Server-Verarbeitung | Alles lokal — keine Abhängigkeit von externen Diensten |
| Rekordbox-Unterstützung | Anderes Tag-Format, anderes Problem |
| Audio-Konvertierung | Kein DJ-Workflow-Tool, nur Analyse + Tag-Schreiben |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ANAL-01 | Phase 1 | In progress (Plan 01-01: encode_markers done; Plan 01-03 beat detection pending) |
| ANAL-02 | Phase 1 | In progress (Plan 01-04 CLI pending) |
| ANAL-03 | Phase 1 | Implemented (Plan 01-01: write functions only replace GEOB:Serato BeatGrid; test_7 asserts byte-exact preservation) |
| FMT-01 | Phase 1 | Implemented (Plan 01-01: write_geob_mp3 + atomic_write_geob; test_6 ID3v2.3 header verified) |
| FMT-02 | Phase 1 | Implemented (Plan 01-01: write_geob_aiff; test_9 mutagen AIFF round-trip verified) |
| FMT-03 | Phase 1 | Implemented (Plan 01-01: write_geob_wav; test_10 mutagen WAV round-trip verified) |
| SAFE-03 | Phase 1 | Implemented (Plan 01-01: atomic_write_geob temp+os.replace; test_8 OSError safety verified) |
| ANAL-04 | Phase 2 | Implemented (Plan 02-03: AnalysisViewModel.isSeratoRunning() checks NSWorkspace by bundleIdentifier com.serato.seratodj; startAnalysis() blocks write with showSeratoAlert=true) |
| SAFE-01 | Phase 2 | Implemented (Plan 02-02: create_backup() in analyze.py; Plan 02-03: AnalysisViewModel surfaces backupPath from result event) |
| SAFE-02 | Phase 2 | Implemented (Plan 02-02: dry_run param in analyze_track(); Plan 02-03: AnalysisViewModel.isDryRun @Published toggle) |
| INPUT-01 | Phase 3 | Complete |
| INPUT-02 | Phase 3 | Complete |
| BATCH-01 | Phase 3 | Complete |
| BATCH-02 | Phase 3 | Complete |
| UI-01 | Phase 3 | Complete |
| UI-02 | Phase 3 | Complete |
| UI-03 | Phase 3 | Complete |
| LIB-01 | Phase 4 | Pending |
| LIB-02 | Phase 4 | Pending |
| LIB-03 | Phase 4 | Pending |
| FMT-04 | Phase 5 | Pending |
| FMT-05 | Phase 5 | Pending |

**Coverage:**

- v1 requirements: 22 total
- Mapped to phases: 22 / 22
- Unmapped: 0

---
*Requirements defined: 2026-06-02*
*Last updated: 2026-06-02 — traceability filled by roadmapper*
