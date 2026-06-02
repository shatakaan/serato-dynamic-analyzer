"""
pytest backup / SAFE-01 tests for analyze.py — Plan 02-01 TDD RED.

Tests cover:
  Test 1 (backup created in same dir): create_backup(src) creates a file in the same
          directory whose name contains ".serato-backup".
  Test 2 (backup is copy of source): backup bytes match source bytes exactly.
  Test 3 (no backup in dry run): analyze_track(..., dry_run=True) must NOT create
          any .serato-backup file in the directory.

Tests are in RED state — failing because create_backup() does not exist yet and
analyze_track() does not accept the dry_run keyword argument.
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
# TestCreateBackup
# ---------------------------------------------------------------------------

class TestCreateBackup:
    """Tests for SAFE-01: create_backup() and dry_run backup suppression (Plan 02-01 RED)."""

    def test_backup_created_in_same_directory(self, tmp_path):
        """create_backup(src) must create a file in the same directory as src."""
        src = tmp_path / "track.mp3"
        src.write_bytes(b'\xff\xfb' + b'\x00' * 100)

        backup_path = analyze.create_backup(src)

        assert backup_path.exists(), "Backup file was not created"
        assert backup_path.parent == src.parent, (
            f"Backup parent {backup_path.parent} != source parent {src.parent}"
        )
        assert ".serato-backup" in backup_path.name, (
            f"'.serato-backup' not found in backup filename: {backup_path.name!r}"
        )

    def test_backup_file_is_copy_of_source(self, tmp_path):
        """Backup file bytes must exactly match source file bytes."""
        known_bytes = b'\xff\xfb' + b'\xDE\xAD\xBE\xEF' * 25
        src = tmp_path / "track.mp3"
        src.write_bytes(known_bytes)

        backup_path = analyze.create_backup(src)

        assert backup_path.read_bytes() == known_bytes, (
            "Backup file content does not match source"
        )

    def test_no_backup_in_dry_run(self, tmp_path):
        """analyze_track(..., dry_run=True) must not create any .serato-backup file."""
        wav_file = tmp_path / "track.wav"
        wav_file.write_bytes(_make_minimal_wav_bytes())
        before = set(tmp_path.iterdir())

        with patch.object(analyze, 'load_audio',
                          lambda p: (np.zeros(22050, dtype='float32'), 22050)), \
             patch.object(analyze, 'detect_beats',
                          lambda *a, **kw: [0.5, 1.0, 1.5, 2.0]):
            analyze.analyze_track(wav_file, dry_run=True)

        after = set(tmp_path.iterdir())
        new_files = after - before
        backup_files = [f for f in new_files if ".serato-backup" in f.name]
        assert backup_files == [], (
            f"Unexpected backup files created during dry run: {[f.name for f in backup_files]}"
        )
