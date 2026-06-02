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
import sys
import tempfile
from pathlib import Path
from typing import Callable

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
      [header: 2 bytes]
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

    # Header: version bytes 0x01 0x00
    buf = bytearray(b'\x01\x00')

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
      total_bytes = 2 (header) + N * 8 (non-terminal) + 8 (terminal) + 1 (footer)
      N = (len(data) - 11) / 8

    Args:
        data: bytes, the complete GEOB binary payload (including header and footer).

    Returns:
        Tuple of (non_terminal_markers, terminal_marker) where:
          - non_terminal_markers: list of (position_seconds: float, beats_till_next: int)
          - terminal_marker: (position_seconds: float, bpm: float)

    Raises:
        ValueError: If the data is too short, has wrong length, or footer is wrong.
    """
    if len(data) < 11:
        raise ValueError(
            f"GEOB data too short: {len(data)} bytes (minimum 11: 2 header + 8 terminal + 1 footer)"
        )

    # Verify header
    if data[0:2] != b'\x01\x00':
        raise ValueError(f"GEOB header wrong: {data[0:2].hex()} (expected 0100)")

    # Verify footer
    if data[-1:] != GEOB_FOOTER:
        raise ValueError(
            f"GEOB footer wrong: {data[-1:].hex()} (expected {GEOB_FOOTER.hex()})"
        )

    # Calculate marker count
    # Length = 2 (header) + N*8 (non-terminal) + 8 (terminal) + 1 (footer) = N*8 + 11
    payload_len = len(data) - 11  # exclude header, terminal marker, footer
    if payload_len < 0 or payload_len % 8 != 0:
        raise ValueError(
            f"GEOB data length {len(data)} is inconsistent: "
            f"payload after header/footer must be multiple of 8 bytes"
        )

    n_non_terminal = payload_len // 8

    offset = 2  # skip header

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

    # The terminal marker is always the last beat position
    last_idx = len(beats) - 1
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

def _emit(event: dict) -> None:
    """Emit a JSONL event to stdout (line-flushed for pipe buffering)."""
    print(json.dumps(event), flush=True)


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


def main(argv: list[str] | None = None) -> int:
    """
    CLI entry point. Usage: python analyze.py <audio_file> [--bpm-min 60] [--bpm-max 200]
    Returns 0 on success, 1 on error.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description='Serato Dynamic Analyzer — writes dynamic beatgrid GEOB tags'
    )
    parser.add_argument('file', help='Audio file path (MP3, AIFF, WAV)')
    parser.add_argument('--bpm-min', type=float, default=60.0, help='Minimum BPM hint')
    parser.add_argument('--bpm-max', type=float, default=200.0, help='Maximum BPM hint')
    args = parser.parse_args(argv)

    try:
        target_path = _resolve_path(args.file)
    except ValueError as e:
        _emit({'type': 'error', 'file': args.file, 'msg': str(e)})
        return 1

    _emit({'type': 'progress', 'file': str(target_path), 'pct': 0})

    try:
        # Import librosa here (heavy import — only load when needed)
        import librosa
        import numpy as np

        _emit({'type': 'progress', 'file': str(target_path), 'pct': 5})

        # Audio loading (D-02, D-03)
        ext = target_path.suffix.lower()
        if ext == '.mp3':
            # MP3: ffmpeg → wav pipe → soundfile (D-02)
            import imageio_ffmpeg
            import soundfile
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            import subprocess
            result = subprocess.run(
                [ffmpeg_exe, '-i', str(target_path), '-f', 'wav', '-'],
                capture_output=True,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"ffmpeg failed (exit {result.returncode}): "
                    f"{result.stderr.decode(errors='replace')[:500]}"
                )
            y, sr = soundfile.read(io.BytesIO(result.stdout), dtype='float32')
            if y.ndim > 1:
                y = y.mean(axis=1)  # Downmix to mono
        else:
            # AIFF/WAV: soundfile handles natively (D-03)
            y, sr = librosa.load(str(target_path), sr=None, mono=True)

        _emit({'type': 'progress', 'file': str(target_path), 'pct': 20})

        # Beat tracking: plp() for variable-tempo (D-07, HR-3)
        # Step 1: frame-level tempo estimation
        tempo_frames = librosa.feature.tempo(
            y=y, sr=sr, aggregate=None,
            prior=librosa.rhythm.tempo_frequencies(
                n_tempo=180, sr=sr,
            ) if hasattr(librosa.rhythm, 'tempo_frequencies') else None,
        )

        _emit({'type': 'progress', 'file': str(target_path), 'pct': 40})

        # Step 2: predominant local pulse (variable tempo beat tracking)
        pulse = librosa.beat.plp(y=y, sr=sr, tempo_min=args.bpm_min, tempo_max=args.bpm_max)
        beat_frames = librosa.util.peak_pick(
            pulse, pre_max=3, post_max=3, pre_avg=3, post_avg=5, delta=0.1, wait=10
        )
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)

        _emit({'type': 'progress', 'file': str(target_path), 'pct': 65})

        # Apply onset offset correction (HR-4, ONSET_OFFSET_SECONDS)
        beat_times = [max(0.0, t - ONSET_OFFSET_SECONDS) for t in beat_times.tolist()]

        # Refuse to write if too few beats (D-08, HR-3)
        if len(beat_times) < 4:
            _emit({
                'type': 'error',
                'file': str(target_path),
                'msg': (
                    f"Too few beats detected: {len(beat_times)} "
                    f"(minimum 4 required, D-08). Track may have no clear rhythm."
                )
            })
            return 1

        _emit({'type': 'progress', 'file': str(target_path), 'pct': 75})

        # Encode markers (consolidation + 128-marker limit)
        non_terminal, terminal = encode_markers(beat_times)

        # Pack the GEOB payload
        geob_bytes = pack_beatgrid(
            non_terminal_markers=non_terminal,
            terminal_marker=terminal,
            footer_byte=GEOB_FOOTER,
        )

        _emit({'type': 'progress', 'file': str(target_path), 'pct': 90})

        # Write atomically using per-format write function
        write_fn = _select_write_fn(target_path)
        atomic_write_geob(target_path, write_fn, geob_bytes)

        # Calculate duration and BPM range for result event
        duration_sec = float(len(y)) / sr
        bpm_values = [60.0 / (beat_times[i+1] - beat_times[i])
                      for i in range(len(beat_times) - 1)]
        bpm_min_actual = min(bpm_values) if bpm_values else 0.0
        bpm_max_actual = max(bpm_values) if bpm_values else 0.0

        _emit({'type': 'progress', 'file': str(target_path), 'pct': 100})
        _emit({
            'type': 'result',
            'file': str(target_path),
            'bpm_min': round(bpm_min_actual, 1),
            'bpm_max': round(bpm_max_actual, 1),
            'marker_count': len(non_terminal) + 1,  # +1 for terminal
            'duration_sec': round(duration_sec, 1),
        })
        return 0

    except Exception as e:
        _emit({'type': 'error', 'file': str(target_path), 'msg': str(e)})
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
