"""
Serato Dynamic Analyzer — analyze.py
=====================================
Standalone Python CLI for dynamic BPM/beatgrid analysis using librosa.
Writes byte-exact Serato BeatGrid GEOB tags to MP3, AIFF, and WAV files.

GEOB format reference: https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_beatgrid.md
Decisions: .planning/phases/01-python-analysis-core/01-CONTEXT.md (D-01 through D-18)
Critical risks: .planning/research/PITFALLS.md (CR-1 through CR-5)

Footer byte: 0x00 (canonical value from Holzhaus serato_beatgrid.md spec)
  - PITFALLS.md CR-1 structural layout: "Footer: single null byte \\x00"
  - PITFALLS.md CR-2: "Always write the single trailing null byte \\x00 footer"

Struct packing: ALL calls use '>' prefix (big-endian) per CR-1, D-12.
ID3 version: Always save(v2_version=3) for ID3v2.3 per CR-5, D-13.
Atomic write: Temp file + os.replace() per CR-3, CR-4, D-14.
"""
import io
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

import imageio_ffmpeg
import numpy as np
import soundfile

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Onset offset correction: subtract 30ms from all beat positions to correct
# librosa's systematic lateness bias (~20-60ms documented in librosa issue #1052).
# Configurable constant; not exposed as a CLI arg in Phase 1 (D-18/discretion).
ONSET_OFFSET_SECONDS: float = 0.030

# Canonical GEOB footer byte per Holzhaus serato_beatgrid.md specification.
# Source: https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_beatgrid.md
# PITFALLS.md CR-1 and CR-2 both confirm this is a single null byte \x00.
# NOTE: ARCHITECTURE.md incorrectly states 0xFF — the Holzhaus spec is ground truth.
GEOB_FOOTER: bytes = b'\x00'

# Allowed file extensions for CLI path validation (T-01-03 mitigation)
ALLOWED_EXTENSIONS: frozenset = frozenset({'.mp3', '.aiff', '.aif', '.wav'})

# Supported extensions for load_audio() format dispatch (D-01, D-02, D-03, T-02-01)
# M4A is explicitly deferred to Phase 5 (FMT-04, FMT-05).
SUPPORTED_EXTENSIONS: set[str] = {'.mp3', '.aiff', '.aif', '.wav'}


# ---------------------------------------------------------------------------
# Audio Loading
# ---------------------------------------------------------------------------

def load_audio(path: "Path | str") -> "tuple[np.ndarray, int]":
    """
    Load an audio file and return a float32 mono array at 22050 Hz.

    Dispatch rules (D-01, D-02, D-03):
      - MP3  (.mp3):        ffmpeg → WAV pipe → soundfile.read(BytesIO)
      - AIFF (.aiff/.aif):  soundfile.read() directly (libsndfile handles AIFF natively)
      - WAV  (.wav):        soundfile.read() directly

    Security mitigations (T-02-01, T-02-03):
      - Path.resolve() expands symlinks before use
      - Suffix validated against SUPPORTED_EXTENSIONS before any I/O
      - subprocess.run cmd is always a list — no shell=True, no shell interpolation

    Args:
        path: Path to the audio file (str or Path).

    Returns:
        Tuple of (audio_float32_mono, sample_rate_int).
        Sample rate is always 22050 Hz (downsampled if needed for AIFF/WAV,
        forced to 22050 via ffmpeg -ar flag for MP3).

    Raises:
        ValueError: If the file extension is not in SUPPORTED_EXTENSIONS
                    (raised before any I/O — M4A, FLAC, etc. are unsupported in Phase 1).
        RuntimeError: If the ffmpeg subprocess returns a non-zero exit code (MP3 branch).
    """
    path = Path(path).resolve()

    # T-02-01: Validate suffix before any I/O — unsupported formats raise immediately
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported format: {path.suffix!r} — {path.name}. "
            f"Supported: {sorted(SUPPORTED_EXTENSIONS)}"
        )

    if path.suffix.lower() == '.mp3':
        # D-01, D-02: MP3 loading pipeline — ffmpeg via imageio_ffmpeg → WAV pipe → soundfile
        # imageio_ffmpeg ships a pre-built static ffmpeg binary; never hardcode a path.
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

        # -ar 22050: downsample to librosa default (reduces memory per MR-1 mitigation)
        # -ac 1: force mono from ffmpeg itself (belt-and-suspenders before soundfile.read)
        # T-02-03: cmd is a list — no shell=True, no shell interpolation of path
        cmd = [ffmpeg_exe, '-i', str(path), '-f', 'wav', '-ar', '22050', '-ac', '1', 'pipe:1']
        proc = subprocess.run(cmd, capture_output=True)

        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg failed for {path}: "
                f"{proc.stderr.decode(errors='replace')[:500]}"
            )

        audio, sr = soundfile.read(io.BytesIO(proc.stdout), dtype='float32')

        # Belt-and-suspenders: -ac 1 already forces mono, but downmix if needed
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        return audio, int(sr)

    else:
        # D-03: AIFF and WAV — soundfile handles them natively via libsndfile
        audio, sr = soundfile.read(str(path), dtype='float32', always_2d=False)

        # Downmix stereo/multichannel to mono
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        # Resample to 22050 Hz if needed (matches MP3 branch; reduces memory per MR-1)
        if sr != 22050:
            import librosa
            audio = librosa.resample(audio, orig_sr=sr, target_sr=22050)
            sr = 22050

        return audio, int(sr)


# ---------------------------------------------------------------------------
# Beat Detection
# ---------------------------------------------------------------------------

def detect_beats(
    audio: "np.ndarray",
    sr: int,
    bpm_min: int = 60,
    bpm_max: int = 200,
) -> "list[float]":
    """
    Detect beat positions in an audio signal using librosa.beat.plp() with
    frame-level tempo estimation via librosa.feature.tempo(aggregate=None).

    Algorithm (D-07, HR-3 mitigations):
      Step 1: Compute onset envelope — librosa.onset.onset_strength()
      Step 2: Compute frame-level tempo — librosa.feature.tempo(aggregate=None)
              Returns per-frame BPM array (not a single scalar) for variable-tempo tracks.
      Step 3: Compute PLP pulse — librosa.beat.plp()
              hop_length=512 reduces memory per MR-1 advice.
              win_length=384 follows bvandrc/serato-tools baseline (D-16).
              tempo_min/tempo_max from bpm_min/bpm_max arguments.
      Step 4: Extract beat frames — np.flatnonzero(librosa.util.localmax(pulse))
      Step 5: Convert frames to seconds — librosa.frames_to_time()
      Step 6: Apply onset offset correction — np.maximum(0.0, times - ONSET_OFFSET_SECONDS)
              Corrects librosa's systematic ~30ms lateness bias (HR-4, librosa issue #1052).
      Step 7: Guard — raise ValueError if fewer than 4 beats detected (D-08, T-03-02)
      Step 8: Return sorted list of beat positions in seconds

    Why plp() not beat_track() (D-07 locked decision):
      beat_track() assumes roughly constant tempo (Ellis 2007 dynamic programming).
      plp() (Predominant Local Pulse) extracts the predominant local pulse at each
      frame, making it robust to variable-tempo tracks (live recordings, human drums).

    Args:
        audio:   Float32 mono audio array (output of load_audio()).
        sr:      Sample rate in Hz (typically 22050).
        bpm_min: Minimum BPM hint for tempo estimation. Default 60.
        bpm_max: Maximum BPM hint for tempo estimation. Default 200.

    Returns:
        Sorted list of beat position timestamps in seconds (float),
        onset-offset-corrected, all values >= 0.0.

    Raises:
        ValueError: If fewer than 4 beats are detected in the audio (D-08, T-03-02).
                    Prevents writing an empty or near-empty beatgrid over existing data.
    """
    import librosa

    hop_length = 512  # Consistent throughout — reduces memory per MR-1

    # Step 1: Onset envelope (input to both tempo estimation and plp())
    oenv = librosa.onset.onset_strength(y=audio, sr=sr, hop_length=hop_length)

    # Step 2: Frame-level tempo — aggregate=None returns per-frame BPM array (D-07).
    # Use 5th/95th percentile of the per-frame distribution to tighten plp() bounds,
    # so the pulse tracker is driven by what the track actually contains.
    tempo_frames = librosa.feature.tempo(
        onset_envelope=oenv,
        sr=sr,
        hop_length=hop_length,
        aggregate=None,
    )
    plp_bpm_min = float(np.clip(np.percentile(tempo_frames, 5), bpm_min, bpm_max))
    plp_bpm_max = float(np.clip(np.percentile(tempo_frames, 95), bpm_min, bpm_max))
    if plp_bpm_min >= plp_bpm_max:  # degenerate (constant-tempo track)
        plp_bpm_min, plp_bpm_max = float(bpm_min), float(bpm_max)

    # Step 3: Predominant Local Pulse — variable-tempo beat extraction (D-07)
    # win_length=384: window in frames for PLP computation (bvandrc/serato-tools baseline)
    pulse = librosa.beat.plp(
        onset_envelope=oenv,
        sr=sr,
        hop_length=hop_length,
        win_length=384,
        tempo_min=plp_bpm_min,
        tempo_max=plp_bpm_max,
    )

    # Step 4: Extract beat frames — local maxima of the PLP pulse curve
    beat_frames = np.flatnonzero(librosa.util.localmax(pulse))

    # Step 5: Convert frames to seconds
    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop_length)

    # Step 6: Apply onset offset correction and clamp at 0.0 (HR-4, T-03-03)
    # np.maximum ensures no negative positions even when raw time < ONSET_OFFSET_SECONDS
    beat_times = np.maximum(0.0, beat_times - ONSET_OFFSET_SECONDS)

    # Step 7: Guard against degenerate results (D-08, T-03-02)
    if len(beat_times) < 4:
        raise ValueError(
            f"Fewer than 4 beats detected ({len(beat_times)}) — "
            f"refusing to write empty beatgrid (D-08). "
            f"Track may have no clear rhythm or onset envelope."
        )

    # Step 8: Return sorted list of float beat positions
    return sorted(beat_times.tolist())


# ---------------------------------------------------------------------------
# GEOB Encoding
# ---------------------------------------------------------------------------

def pack_beatgrid(
    non_terminal_markers: list[tuple[float, int]],
    terminal_marker: tuple[float, float],
    footer_byte: bytes,
) -> bytes:
    """
    Encode Serato BeatGrid markers to the canonical GEOB binary payload.

    Binary layout (all multi-byte values are big-endian per CR-1, D-12):
      [version: 2 bytes = \x01\x00]
      [count:   4 bytes = uint32 BE, TOTAL markers = len(non_terminal) + 1 (terminal)]
      [non-terminal marker 0: 8 bytes = >f position + >I beats_till_next] * N
      [terminal marker: 8 bytes = >f position + >f bpm]
      [footer: 1 byte = GEOB_FOOTER]

    Args:
        non_terminal_markers: List of (position_seconds, beats_till_next).
            position_seconds: float, seconds from track start (big-endian f32).
            beats_till_next: int, number of beats to the next marker (big-endian u32).
        terminal_marker: (position_seconds, bpm).
            position_seconds: float, seconds from track start (big-endian f32).
            bpm: float, local BPM at this position (big-endian f32).
        footer_byte: Must be GEOB_FOOTER (b'\\x00').

    Returns:
        bytes: The complete GEOB binary payload.

    Raises:
        ValueError: If both non_terminal_markers is empty AND terminal_marker is None.
    """
    if not non_terminal_markers and terminal_marker is None:
        raise ValueError(
            "pack_beatgrid requires at least a terminal_marker; "
            "both non_terminal_markers=[] and terminal_marker=None is invalid."
        )

    # Header: version (2 bytes) + total marker count including terminal (uint32 BE, 4 bytes)
    buf = bytearray(b'\x01\x00')
    buf += struct.pack('>I', len(non_terminal_markers) + 1)

    # Non-terminal markers: position as big-endian f32, beats_till_next as big-endian u32
    for position, beats_till_next in non_terminal_markers:
        buf += struct.pack('>fI', position, beats_till_next)  # CR-1: '>' prefix enforced

    # Terminal marker: position as big-endian f32, BPM as big-endian f32
    # Note: NOT beats_till_next — this is the terminal marker format (CR-2)
    term_pos, term_bpm = terminal_marker
    buf += struct.pack('>ff', term_pos, term_bpm)  # CR-1: '>' prefix enforced

    # Footer: canonical null byte from Holzhaus spec (CR-2, D-11)
    buf += footer_byte

    return bytes(buf)


def decode_beatgrid(data: bytes) -> tuple[list[tuple[float, int]], tuple[float, float]]:
    """
    Inverse of pack_beatgrid. Parses the GEOB binary payload back into markers.

    The format does not self-describe the marker count, so this function
    determines the count from the byte length:
      total_bytes = 2 (version) + 4 (count uint32) + N * 8 (non-terminal) + 8 (terminal) + 1 (footer)
      count = read from bytes [2:6] as uint32 BE = total markers including terminal

    Args:
        data: bytes, the complete GEOB binary payload (including header and footer).

    Returns:
        Tuple of (non_terminal_markers, terminal_marker) where:
          - non_terminal_markers: list of (position_seconds: float, beats_till_next: int)
          - terminal_marker: (position_seconds: float, bpm: float)

    Raises:
        ValueError: If the data is too short, has wrong length, or footer is wrong.
    """
    if len(data) < 15:
        raise ValueError(
            f"GEOB data too short: {len(data)} bytes (minimum 15: 6 header + 8 terminal + 1 footer)"
        )

    # Verify version bytes
    if data[0:2] != b'\x01\x00':
        raise ValueError(f"GEOB version bytes wrong: {data[0:2].hex()} (expected 0100)")

    # Read total marker count (includes terminal) as uint32 BE
    total_markers = struct.unpack('>I', data[2:6])[0]
    if total_markers < 1:
        raise ValueError(f"GEOB marker count {total_markers} invalid: must be >= 1 (terminal required)")

    n_non_terminal = total_markers - 1  # last marker is always terminal

    # Validate total length
    expected_len = 6 + total_markers * 8 + 1
    if len(data) != expected_len:
        raise ValueError(
            f"GEOB data length {len(data)} inconsistent with total_markers={total_markers}: "
            f"expected {expected_len} bytes"
        )

    # Verify footer
    if data[-1:] != GEOB_FOOTER:
        raise ValueError(
            f"GEOB footer wrong: {data[-1:].hex()} (expected {GEOB_FOOTER.hex()})"
        )

    offset = 6  # skip version (2) + count (4)

    # Parse non-terminal markers
    non_terminal = []
    for _ in range(n_non_terminal):
        position, beats_till_next = struct.unpack('>fI', data[offset:offset + 8])
        non_terminal.append((position, beats_till_next))
        offset += 8

    # Parse terminal marker (8 bytes: position + BPM, both big-endian f32)
    term_pos, term_bpm = struct.unpack('>ff', data[offset:offset + 8])
    terminal = (term_pos, term_bpm)

    return non_terminal, terminal


def encode_markers(
    beat_positions_seconds: list[float],
    bpm_delta_threshold: float = 0.5,
) -> tuple[list[tuple[float, int]], tuple[float, float]]:
    """
    Convert a list of beat positions (already onset-offset-corrected) into
    Serato BeatGrid non-terminal and terminal markers.

    Consolidation rule (D-09): Create a new non-terminal marker only when the
    local BPM differs from the last marker's BPM by more than bpm_delta_threshold.
    This limits the number of markers for long/variable-tempo tracks.

    128-marker ceiling (HR-2, D-10): Serato enforces a maximum of 128 markers
    (127 non-terminal + 1 terminal). If the initial consolidation produces too
    many markers, the threshold is doubled and consolidation is retried recursively.

    Args:
        beat_positions_seconds: List of beat positions in seconds (sorted ascending).
            Must have at least 4 entries (D-08).
        bpm_delta_threshold: BPM change threshold to trigger a new marker. Default 0.5.

    Returns:
        Tuple of (non_terminal_markers, terminal_marker) where:
          - non_terminal_markers: list of (position_seconds: float, beats_till_next: int)
          - terminal_marker: (position_seconds: float, bpm: float)

    Raises:
        ValueError: If beat_positions_seconds has fewer than 4 entries (D-08).
    """
    if len(beat_positions_seconds) < 4:
        raise ValueError(
            f"encode_markers requires at least 4 beat positions, "
            f"got {len(beat_positions_seconds)} (D-08: refuse to write near-empty grids)"
        )

    beats = beat_positions_seconds

    # Compute local BPM at each beat position (except the last)
    # local_bpm[i] = 60.0 / (beats[i+1] - beats[i])
    local_bpms = []
    for i in range(len(beats) - 1):
        gap = beats[i + 1] - beats[i]
        if gap <= 0:
            gap = 1e-6  # Protect against zero/negative gaps
        local_bpms.append(60.0 / gap)

    # Build non-terminal markers using consolidation
    # A new marker is created when BPM changes by more than bpm_delta_threshold
    # from the BPM of the current (last) marker.
    non_terminal: list[tuple[float, int]] = []
    last_marker_idx = 0  # Beat index where the current (last) marker was placed
    last_marker_bpm = local_bpms[0]

    for i in range(1, len(beats) - 1):  # Don't process the last beat (it becomes terminal)
        current_bpm = local_bpms[i] if i < len(local_bpms) else local_bpms[-1]
        if abs(current_bpm - last_marker_bpm) > bpm_delta_threshold:
            # BPM changed enough — emit the current marker
            beats_till_next = i - last_marker_idx  # integer beat distance to this new marker
            non_terminal.append((beats[last_marker_idx], beats_till_next))
            last_marker_idx = i
            last_marker_bpm = current_bpm

    # Always emit the final segment from last_marker_idx to the terminal.
    # Without this, the last tempo region has no non-terminal marker, causing
    # Serato to misalign the grid past the last BPM change.
    last_idx = len(beats) - 1
    non_terminal.append((beats[last_marker_idx], last_idx - last_marker_idx))

    # The terminal marker is always the last beat position
    # BPM at the terminal = local BPM from second-to-last to last beat
    if len(beats) >= 2:
        gap = beats[-1] - beats[-2]
        if gap <= 0:
            gap = 1e-6
        term_bpm = 60.0 / gap
    else:
        term_bpm = local_bpms[-1]

    terminal = (beats[last_idx], term_bpm)

    # 128-marker ceiling check (HR-2, D-10)
    # Max non-terminal = 127 (reserving 1 slot for the mandatory terminal marker)
    if len(non_terminal) >= 128:
        # Adaptively increase threshold and retry (recursive)
        return encode_markers(
            beat_positions_seconds=beat_positions_seconds,
            bpm_delta_threshold=bpm_delta_threshold * 2,
        )

    return non_terminal, terminal


# ---------------------------------------------------------------------------
# GEOB Write Functions (per-format)
# ---------------------------------------------------------------------------

def write_geob_mp3(path: Path, geob_bytes: bytes) -> None:
    """
    Write the GEOB:Serato BeatGrid frame to an MP3 file using mutagen.

    Requirements:
    - Opens with mutagen.id3.ID3 (creating a new tag if none exists)
    - Saves with v2_version=3 (ID3v2.3) — MANDATORY per CR-5, D-13
    - Only replaces GEOB:Serato BeatGrid; all other GEOB frames are preserved (D-15)
    - Does NOT call tags.save(str(path)) directly — caller uses atomic_write_geob

    Args:
        path: Path to the MP3 file (typically a temp file copy, not the original).
        geob_bytes: The GEOB binary payload from pack_beatgrid().
    """
    import mutagen.id3

    try:
        tags = mutagen.id3.ID3(str(path))
    except mutagen.id3.ID3NoHeaderError:
        tags = mutagen.id3.ID3()

    # Construct the GEOB frame for the BeatGrid only; all other frames untouched (D-15)
    tags['GEOB:Serato BeatGrid'] = mutagen.id3.GEOB(
        encoding=0,
        mime='application/octet-stream',
        filename='',
        desc='Serato BeatGrid',
        data=geob_bytes,
    )

    # v2_version=3 is MANDATORY: Serato silently ignores ID3v2.4 GEOB frames (CR-5)
    tags.save(str(path), v2_version=3)


def write_geob_aiff(path: Path, geob_bytes: bytes) -> None:
    """
    Write the GEOB:Serato BeatGrid frame to an AIFF file using mutagen.

    AIFF stores ID3 tags in the FORM chunk. mutagen.aiff.AIFF exposes them
    via .tags (an ID3 object), same API as mutagen.id3.ID3.

    Args:
        path: Path to the AIFF file (typically a temp file copy, not the original).
        geob_bytes: The GEOB binary payload from pack_beatgrid().
    """
    import mutagen.aiff
    import mutagen.id3

    af = mutagen.aiff.AIFF(str(path))
    if af.tags is None:
        af.add_tags()

    # Same GEOB frame construction as write_geob_mp3; only BeatGrid is replaced (D-15)
    af.tags['GEOB:Serato BeatGrid'] = mutagen.id3.GEOB(
        encoding=0,
        mime='application/octet-stream',
        filename='',
        desc='Serato BeatGrid',
        data=geob_bytes,
    )

    # v2_version=3 for ID3v2.3 compliance (CR-5, D-13)
    af.tags.save(str(path), v2_version=3)


def write_geob_wav(path: Path, geob_bytes: bytes) -> None:
    """
    Write the GEOB:Serato BeatGrid frame to a WAV file using mutagen.

    WAV files use ID3 tags in the ID3 chunk (RIFF container).
    mutagen.wave.WAVE exposes them via .tags.

    Args:
        path: Path to the WAV file (typically a temp file copy, not the original).
        geob_bytes: The GEOB binary payload from pack_beatgrid().
    """
    import mutagen.wave
    import mutagen.id3

    wf = mutagen.wave.WAVE(str(path))
    if wf.tags is None:
        wf.add_tags()

    # Same GEOB frame construction; only BeatGrid is replaced (D-15)
    wf.tags['GEOB:Serato BeatGrid'] = mutagen.id3.GEOB(
        encoding=0,
        mime='application/octet-stream',
        filename='',
        desc='Serato BeatGrid',
        data=geob_bytes,
    )

    # v2_version=3 for ID3v2.3 compliance (CR-5, D-13)
    wf.tags.save(str(path), v2_version=3)


def create_backup(source_path: Path) -> Path:
    """
    Create a .serato-backup copy of the source audio file before writing (SAFE-01).

    The backup file is placed in the same directory as the source, with name:
        {stem}.serato-backup{suffix}

    Uses shutil.copy2 to preserve metadata (mtime, permissions).

    Args:
        source_path: Path to the source audio file.

    Returns:
        Path to the created backup file.

    Raises:
        PermissionError, OSError: propagated to the caller (analyze_track will catch and emit error).
    """
    backup_path = source_path.parent / (source_path.stem + ".serato-backup" + source_path.suffix)
    shutil.copy2(str(source_path), str(backup_path))
    return backup_path


def atomic_write_geob(
    target_path: Path,
    write_fn: Callable[[Path, bytes], None],
    geob_bytes: bytes,
) -> None:
    """
    Safely write GEOB tags to a file using a temp file + os.replace() pattern.

    This ensures the original file is either fully intact or fully replaced —
    never in a partially-written state (CR-3, CR-4, D-14, SAFE-03).

    Protocol:
    1. Create a NamedTemporaryFile in the same directory as target_path.
    2. Copy target_path to the temp file (shutil.copy2 preserves all existing tags).
    3. Call write_fn(tmp_path, geob_bytes) to write the BeatGrid to the copy.
    4. Call os.replace(tmp_path, target_path) — atomic POSIX rename.
    5. If any exception occurs before os.replace, delete the temp file; original intact.

    NOTE: This does NOT create a .serato-backup file — that is a Phase 2 (SAFE-01)
    responsibility. Phase 1 only guarantees atomicity (SAFE-03).

    Args:
        target_path: Path to the target audio file (the file to be updated).
        write_fn: One of write_geob_mp3, write_geob_aiff, or write_geob_wav.
        geob_bytes: The GEOB binary payload from pack_beatgrid().

    Raises:
        OSError: If os.replace() fails (original file remains intact).
        Any exception from write_fn is propagated; original file remains intact.
    """
    suffix = target_path.suffix
    tmp_path = None
    try:
        # Create temp file in same directory so os.replace() is a same-filesystem rename
        with tempfile.NamedTemporaryFile(
            suffix=suffix,
            dir=target_path.parent,
            delete=False,
        ) as tmp:
            tmp_path = tmp.name

        # Copy original file to temp (preserves all existing tags and audio data)
        shutil.copy2(str(target_path), tmp_path)

        # Write the BeatGrid to the temp copy (not the original)
        write_fn(Path(tmp_path), geob_bytes)

        # Atomic POSIX rename — original is replaced only if this succeeds (D-14)
        os.replace(tmp_path, str(target_path))
        tmp_path = None  # Successfully replaced; no cleanup needed

    except Exception:
        # Clean up temp file if it exists; original file is untouched (CR-3, CR-4)
        if tmp_path is not None and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


# ---------------------------------------------------------------------------
# CLI Entry Point (Phase 1 interface per D-04 through D-06)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# JSONL Emission (D-05, D-06, T-04-02)
# These are the ONLY functions that write to stdout.
# All other output (diagnostics, timing, warnings) goes to sys.stderr.
# ---------------------------------------------------------------------------

def emit_json(event: dict) -> None:
    """
    Emit a JSONL event to stdout.

    This is the sole stdout writer in analyze.py (T-04-02 mitigation).
    All other output MUST go to sys.stderr. flush=True ensures Swift's
    FileHandle.readabilityHandler receives lines in real time (D-05).
    """
    print(json.dumps(event), flush=True)


def emit_progress(file_path: str, pct: int) -> None:
    """Emit a progress event per D-06 JSONL schema."""
    emit_json({"type": "progress", "file": file_path, "pct": pct})


def emit_result(
    file_path: str,
    bpm_min: float,
    bpm_max: float,
    marker_count: int,
    duration_sec: float,
    backup_path: "str | None" = None,
    dry_run: bool = False,
) -> None:
    """Emit a result event per D-06 JSONL schema.

    Optional fields added in Phase 2:
      backup_path: path to .serato-backup file (present only when dry_run=False and write succeeded)
      dry_run: True if this was a dry run (no write was performed)
    """
    event = {
        "type": "result",
        "file": file_path,
        "bpm_min": round(bpm_min, 2),
        "bpm_max": round(bpm_max, 2),
        "marker_count": marker_count,
        "duration_sec": round(duration_sec, 2),
    }
    if backup_path is not None:
        event["backup_path"] = backup_path
    if dry_run:
        event["dry_run"] = True
    emit_json(event)


def emit_error(file_path: str, msg: str) -> None:
    """Emit an error event per D-06 JSONL schema."""
    emit_json({"type": "error", "file": file_path, "msg": msg})




def analyze_track(
    path: "Path | str",
    bpm_min: int = 60,
    bpm_max: int = 200,
    dry_run: bool = False,
) -> int:
    """
    Full analysis pipeline orchestrator.

    Chains: load_audio → detect_beats → encode_markers → pack_beatgrid → atomic_write_geob.
    Emits JSONL progress/result/error events on stdout; logs timing to stderr.

    Args:
        path: Path to the audio file (MP3, AIFF, WAV).
        bpm_min: Minimum BPM hint for tempo estimation. Default 60.
        bpm_max: Maximum BPM hint for tempo estimation. Default 200.
        dry_run: If True, analysis runs but no file is written and no backup is created (SAFE-02).
                 Result event will contain dry_run:true. Default False.

    Returns:
        0 on success, 1 on any failure.

    Security (T-04-01): Path is resolved and validated against ALLOWED_EXTENSIONS
    before any I/O. Unsupported extensions return exit code 1 with an error event.
    """
    t_start = time.perf_counter()

    path = Path(path)
    path_str = str(path)

    # T-04-01: Validate path before any I/O
    resolved = path.resolve()
    if not resolved.is_file():
        emit_error(path_str, f"Path is not a file: {resolved}")
        return 1
    if resolved.suffix.lower() not in ALLOWED_EXTENSIONS:
        emit_error(
            path_str,
            f"Unsupported file extension: {resolved.suffix!r}. "
            f"Allowed: {sorted(ALLOWED_EXTENSIONS)}"
        )
        return 1

    # Step 1: Load audio (10%)
    emit_progress(path_str, 10)
    try:
        audio, sr = load_audio(resolved)
    except Exception as exc:
        emit_error(path_str, f"Audio loading failed: {exc}")
        return 1

    # Step 2: Detect beats (30%)
    emit_progress(path_str, 30)
    try:
        beat_positions = detect_beats(audio, sr, bpm_min=bpm_min, bpm_max=bpm_max)
    except ValueError as exc:
        emit_error(path_str, f"Beat detection failed: {exc}")
        return 1
    except Exception as exc:
        emit_error(path_str, f"Beat detection error: {exc}")
        return 1

    # Step 3: Encode markers (60%)
    emit_progress(path_str, 60)
    try:
        non_terminal, terminal = encode_markers(beat_positions)
    except Exception as exc:
        emit_error(path_str, f"Marker encoding failed: {exc}")
        return 1

    # Step 4: Pack GEOB and write atomically (80%)
    # dry_run=True: pack bytes (so result is meaningful) but skip backup + write (SAFE-02)
    emit_progress(path_str, 80)
    try:
        geob_bytes = pack_beatgrid(non_terminal, terminal, GEOB_FOOTER)
        if not dry_run:
            backup_path_obj = create_backup(resolved)
            backup_path_str = str(backup_path_obj)
            write_fn = _select_write_fn(resolved)
            atomic_write_geob(resolved, write_fn, geob_bytes)
        else:
            backup_path_str = None
    except Exception as exc:
        emit_error(path_str, f"GEOB write failed: {exc}")
        return 1

    # Step 5: Done (100%)
    emit_progress(path_str, 100)

    # Compute BPM range from beat intervals
    if len(beat_positions) >= 2:
        local_bpms = [
            60.0 / (beat_positions[i + 1] - beat_positions[i])
            for i in range(len(beat_positions) - 1)
        ]
        bpm_min_val = min(local_bpms)
        bpm_max_val = max(local_bpms)
    else:
        bpm_min_val = bpm_max_val = 0.0

    # Compute elapsed and log to stderr (not stdout — T-04-02)
    elapsed = time.perf_counter() - t_start
    print(
        f"[analyze.py] {resolved.name}: elapsed={elapsed:.2f}s startup+analysis",
        file=sys.stderr,
        flush=True,
    )
    if elapsed > 2.0:
        print(
            "[analyze.py] WARNING: elapsed > 2s — consider persistent worker process for Phase 2",
            file=sys.stderr,
            flush=True,
        )

    # Emit result event (stdout JSONL)
    duration_sec = float(audio.shape[0]) / sr
    emit_result(
        path_str,
        bpm_min=bpm_min_val,
        bpm_max=bpm_max_val,
        marker_count=len(non_terminal) + 1,  # +1 for terminal marker
        duration_sec=duration_sec,
        backup_path=backup_path_str,
        dry_run=dry_run,
    )
    return 0


def _resolve_path(arg: str) -> Path:
    """
    Resolve and validate an input file path (T-01-03 mitigation).
    Uses pathlib.Path.resolve() to expand symlinks; asserts the result is a file
    with an allowed extension.
    """
    p = Path(arg).resolve()
    if not p.is_file():
        raise ValueError(f"Path is not a file: {p}")
    if p.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file extension: {p.suffix!r}. "
            f"Allowed: {sorted(ALLOWED_EXTENSIONS)}"
        )
    return p


def _select_write_fn(path: Path) -> Callable[[Path, bytes], None]:
    """Select the correct per-format write function based on file extension."""
    ext = path.suffix.lower()
    if ext == '.mp3':
        return write_geob_mp3
    elif ext in {'.aiff', '.aif'}:
        return write_geob_aiff
    elif ext == '.wav':
        return write_geob_wav
    else:
        raise ValueError(f"No write function for extension: {ext!r}")



if __name__ == '__main__':
    import argparse as _argparse
    _parser = _argparse.ArgumentParser(description='Serato Dynamic BPM Analyzer')
    _parser.add_argument('file', type=str, help='Audio file to analyze (MP3, AIFF, WAV)')
    _parser.add_argument('--bpm-min', type=int, default=60, help='Minimum BPM (default 60)')
    _parser.add_argument('--bpm-max', type=int, default=200, help='Maximum BPM (default 200)')
    _args = _parser.parse_args()
    sys.exit(analyze_track(Path(_args.file), _args.bpm_min, _args.bpm_max))
