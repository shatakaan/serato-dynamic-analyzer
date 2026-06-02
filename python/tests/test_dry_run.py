"""
pytest dry-run / SAFE-02 tests for analyze.py — Plan 02-01 TDD RED.

Tests cover:
  Test 1 (does not modify file): analyze_track(..., dry_run=True) must leave the
          source file mtime unchanged.
  Test 2 (result event has dry_run:true): result event emitted to stdout must
          contain dry_run == True when called with dry_run=True.
  Test 3 (no backup created): analyze_track(..., dry_run=True) must not create
          any .serato-backup file.

Tests are in RED state — failing because analyze_track() does not yet accept
the dry_run keyword argument.
"""
import json
import math
import struct
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Path setup — replicate test_cli.py pattern exactly
# ---------------------------------------------------------------------------

PYTHON_DIR = Path(__file__).parent.parent
ANALYZE_SCRIPT = PYTHON_DIR / 'analyze.py'

VENV_PYTHON = PYTHON_DIR / 'venv' / 'bin' / 'python3'
PYTHON_EXE = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable

sys.path.insert(0, str(PYTHON_DIR))
import analyze  # noqa: E402


# ---------------------------------------------------------------------------
# Audio fixture helper (same pattern as test_cli.py)
# ---------------------------------------------------------------------------

def _make_minimal_wav_bytes(n_samples: int = 22050, sample_rate: int = 22050) -> bytes:
    beat_period = sample_rate // 2
    samples = []
    for i in range(n_samples):
        beat_phase = i % beat_period
        envelope = math.exp(-beat_phase / 200.0)
        value = int(envelope * 32767 * math.sin(2 * math.pi * 440 * i / sample_rate))
        value = max(-32768, min(32767, value))
        samples.append(value)

    pcm_data = struct.pack(f'<{len(samples)}h', *samples)
    fmt_data = (
        struct.pack('<H', 1) +
        struct.pack('<H', 1) +
        struct.pack('<I', sample_rate) +
        struct.pack('<I', sample_rate * 2) +
        struct.pack('<H', 2) +
        struct.pack('<H', 16)
    )
    fmt_chunk = b'fmt ' + struct.pack('<I', len(fmt_data)) + fmt_data
    data_chunk = b'data' + struct.pack('<I', len(pcm_data)) + pcm_data
    riff_body = b'WAVE' + fmt_chunk + data_chunk
    return b'RIFF' + struct.pack('<I', len(riff_body)) + riff_body


# ---------------------------------------------------------------------------
# TestDryRun
# ---------------------------------------------------------------------------

class TestDryRun:
    """Tests for SAFE-02: dry_run parameter on analyze_track() (Plan 02-01 RED)."""

    def test_dry_run_does_not_modify_file(self, tmp_path):
        """analyze_track(..., dry_run=True) must not change the source file mtime."""
        wav_file = tmp_path / "track.wav"
        wav_file.write_bytes(_make_minimal_wav_bytes())
        mtime_before = wav_file.stat().st_mtime

        with patch.object(analyze, 'load_audio',
                          lambda p: (np.zeros(22050, dtype='float32'), 22050)), \
             patch.object(analyze, 'detect_beats',
                          lambda *a, **kw: [0.5, 1.0, 1.5, 2.0, 2.5]):
            analyze.analyze_track(wav_file, dry_run=True)

        mtime_after = wav_file.stat().st_mtime
        assert mtime_before == mtime_after, (
            "Source file was modified during dry run (mtime changed)"
        )

    def test_dry_run_result_event_has_dry_run_true(self, tmp_path, capsys):
        """Result event emitted by analyze_track(dry_run=True) must include dry_run:true."""
        wav_file = tmp_path / "track.wav"
        wav_file.write_bytes(_make_minimal_wav_bytes())

        with patch.object(analyze, 'load_audio',
                          lambda p: (np.zeros(22050, dtype='float32'), 22050)), \
             patch.object(analyze, 'detect_beats',
                          lambda *a, **kw: [0.5, 1.0, 1.5, 2.0, 2.5]):
            analyze.analyze_track(wav_file, dry_run=True)

        captured = capsys.readouterr()
        result_events = []
        for line in captured.out.splitlines():
            line = line.strip()
            if not line:
                continue
            parsed = json.loads(line)
            if parsed.get('type') == 'result':
                result_events.append(parsed)

        assert result_events, "No result event was emitted to stdout"
        assert result_events[0].get('dry_run') is True, (
            f"Result event missing dry_run:true — got: {result_events[0]}"
        )

    def test_dry_run_no_backup_created(self, tmp_path):
        """analyze_track(..., dry_run=True) must not create any .serato-backup file."""
        wav_file = tmp_path / "track.wav"
        wav_file.write_bytes(_make_minimal_wav_bytes())
        before = set(tmp_path.iterdir())

        with patch.object(analyze, 'load_audio',
                          lambda p: (np.zeros(22050, dtype='float32'), 22050)), \
             patch.object(analyze, 'detect_beats',
                          lambda *a, **kw: [0.5, 1.0, 1.5, 2.0, 2.5]):
            analyze.analyze_track(wav_file, dry_run=True)

        after = set(tmp_path.iterdir())
        new_files = after - before
        backup_files = [f for f in new_files if ".serato-backup" in f.name]
        assert backup_files == [], (
            f"Unexpected backup files created during dry run: {[f.name for f in backup_files]}"
        )
