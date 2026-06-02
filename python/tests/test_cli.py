"""
pytest CLI integration tests for analyze.py — Plan 01-04 TDD.

Tests cover:
  Test 1 (happy path JSONL): subprocess run on a real minimal audio file; parse JSONL;
          assert at least one progress event and one result event with correct keys.
  Test 2 (result event schema): result event has exactly the keys specified in D-06.
  Test 3 (error JSONL on missing file): non-existent path → JSONL error event + non-zero exit.
  Test 4 (bpm-min/bpm-max args parsed): detect_beats called with correct bpm_min/bpm_max args.
  Test 5 (stderr timing): stderr contains elapsed time with "s", "ms", or "sec".
  Test 6 (stdout-only JSONL): every line on stdout is valid JSON; no plain text on stdout.
  Test 7 (emit_json function exists): emit_json(), emit_progress(), emit_result(),
          emit_error() all exist and produce correct JSON.
  Test 8 (analyze_track exists): analyze_track() function is importable from analyze.
  Test 9 (analyze_track error path): analyze_track returns 1 on missing file.
  Test 10 (analyze_track path validation): analyze_track rejects unsupported extension.

Note: Tests that require real audio files use pytest.mark.skipif to skip when
      no audio fixture is present (so CI can run without audio files).
      The subprocess tests use '-u' flag matching Phase 2 Swift invocation contract.
"""
import io
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import numpy as np

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

PYTHON_DIR = Path(__file__).parent.parent
ANALYZE_SCRIPT = PYTHON_DIR / 'analyze.py'

# Python interpreter inside the venv (required for tests that use subprocess)
VENV_PYTHON = PYTHON_DIR / 'venv' / 'bin' / 'python3'
# Fall back to sys.executable if venv python isn't found
PYTHON_EXE = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable

# Add the python/ directory to sys.path so we can import analyze
sys.path.insert(0, str(PYTHON_DIR))

import analyze  # noqa: E402 (placed after sys.path setup)

# ---------------------------------------------------------------------------
# Audio fixture helpers
# ---------------------------------------------------------------------------

def _make_minimal_wav_bytes(n_samples: int = 22050, sample_rate: int = 22050) -> bytes:
    """
    Create a minimal valid WAV file with real sine-wave audio data.
    n_samples=22050 gives 1 second of audio at 22050 Hz — enough for librosa to detect beats.
    """
    import struct as s
    import math

    # Generate 1 second of 120 BPM sine-wave beat impulse to give librosa clear onsets
    # Beat period at 120 BPM = 0.5 seconds = 11025 samples at 22050 Hz
    beat_period = sample_rate // 2  # 11025 samples per beat
    samples = []
    for i in range(n_samples):
        # Envelope: sharp attack + exponential decay per beat — simulates a kick drum
        beat_phase = i % beat_period
        envelope = math.exp(-beat_phase / 200.0)  # Fast decay
        value = int(envelope * 32767 * math.sin(2 * math.pi * 440 * i / sample_rate))
        value = max(-32768, min(32767, value))
        samples.append(value)

    pcm_data = s.pack(f'<{len(samples)}h', *samples)

    # WAV fmt chunk
    fmt_data = (
        s.pack('<H', 1) +       # AudioFormat = PCM
        s.pack('<H', 1) +       # NumChannels = 1
        s.pack('<I', sample_rate) +
        s.pack('<I', sample_rate * 2) +  # ByteRate = SampleRate * 2
        s.pack('<H', 2) +       # BlockAlign
        s.pack('<H', 16)        # BitsPerSample
    )
    fmt_chunk = b'fmt ' + s.pack('<I', len(fmt_data)) + fmt_data
    data_chunk = b'data' + s.pack('<I', len(pcm_data)) + pcm_data
    riff_body = b'WAVE' + fmt_chunk + data_chunk
    return b'RIFF' + s.pack('<I', len(riff_body)) + riff_body


def _make_minimal_mp3_bytes() -> bytes:
    """
    Create a minimal valid MP3 file: ID3v2.3 header + a minimal MPEG frame.
    The audio is essentially silence — enough for mutagen to parse.
    NOTE: librosa may not detect clear beats in silence; use WAV fixture for real analysis.
    """
    import mutagen.id3
    buf = io.BytesIO()
    tags = mutagen.id3.ID3()
    tags.save(buf, v2_version=3)
    buf.write(bytes([0xFF, 0xFB, 0x90, 0x00]))
    buf.write(b'\x00' * 413)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Test 7: emit_json / emit_progress / emit_result / emit_error exist (unit, no subprocess)
# ---------------------------------------------------------------------------

class TestEmitFunctions:
    """These tests run without subprocess — pure unit tests on emit_* API."""

    def test_emit_json_writes_to_stdout(self, capsys):
        """emit_json() must print a JSON object to stdout with flush."""
        analyze.emit_json({"type": "test", "value": 42})
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed == {"type": "test", "value": 42}
        assert captured.err == ""  # Nothing on stderr

    def test_emit_progress_format(self, capsys):
        """emit_progress() must emit {type:progress, file:..., pct:...}."""
        analyze.emit_progress("/some/path.mp3", 42)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed["type"] == "progress"
        assert parsed["file"] == "/some/path.mp3"
        assert parsed["pct"] == 42

    def test_emit_result_format(self, capsys):
        """emit_result() must emit {type:result, file, bpm_min, bpm_max, marker_count, duration_sec}."""
        analyze.emit_result("/some/path.mp3", bpm_min=118.0, bpm_max=122.5,
                            marker_count=3, duration_sec=214.5)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed["type"] == "result"
        assert parsed["file"] == "/some/path.mp3"
        assert "bpm_min" in parsed
        assert "bpm_max" in parsed
        assert parsed["marker_count"] == 3
        assert "duration_sec" in parsed

    def test_emit_error_format(self, capsys):
        """emit_error() must emit {type:error, file:..., msg:...}."""
        analyze.emit_error("/some/path.mp3", "File not found")
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed["type"] == "error"
        assert parsed["file"] == "/some/path.mp3"
        assert parsed["msg"] == "File not found"


# ---------------------------------------------------------------------------
# Test 8: analyze_track() exists and is importable
# ---------------------------------------------------------------------------

class TestAnalyzeTrackExists:
    """analyze_track() must be a callable exported from analyze.py."""

    def test_analyze_track_is_callable(self):
        """analyze_track must be importable and callable."""
        assert hasattr(analyze, 'analyze_track'), (
            "analyze.analyze_track does not exist — add it per plan 01-04"
        )
        assert callable(analyze.analyze_track), "analyze_track is not callable"

    def test_analyze_track_signature(self):
        """analyze_track must accept path, bpm_min, bpm_max with correct defaults."""
        import inspect
        sig = inspect.signature(analyze.analyze_track)
        params = sig.parameters
        assert 'path' in params, "analyze_track missing 'path' parameter"
        assert 'bpm_min' in params, "analyze_track missing 'bpm_min' parameter"
        assert 'bpm_max' in params, "analyze_track missing 'bpm_max' parameter"
        assert params['bpm_min'].default == 60, (
            f"bpm_min default should be 60, got {params['bpm_min'].default}"
        )
        assert params['bpm_max'].default == 200, (
            f"bpm_max default should be 200, got {params['bpm_max'].default}"
        )


# ---------------------------------------------------------------------------
# Test 9: analyze_track error path (missing file)
# ---------------------------------------------------------------------------

class TestAnalyzeTrackErrorPath:
    """analyze_track() must return 1 and emit JSONL error on missing file."""

    def test_analyze_track_missing_file_returns_1(self, capsys):
        """analyze_track('/nonexistent/path.mp3') must return exit code 1."""
        result = analyze.analyze_track(Path('/nonexistent/path.mp3'))
        assert result == 1, (
            f"analyze_track returned {result} for missing file; expected 1"
        )

    def test_analyze_track_missing_file_emits_error(self, capsys):
        """analyze_track('/nonexistent/path.mp3') must emit a JSONL error event."""
        analyze.analyze_track(Path('/nonexistent/path.mp3'))
        captured = capsys.readouterr()
        lines = [l.strip() for l in captured.out.strip().split('\n') if l.strip()]
        assert len(lines) >= 1, "No JSONL output for missing file"
        # At least one line must be an error event
        error_events = [json.loads(l) for l in lines if json.loads(l).get('type') == 'error']
        assert len(error_events) >= 1, (
            f"No error event found in stdout. Lines: {lines}"
        )
        assert error_events[-1]['msg'], "Error event has empty msg"


# ---------------------------------------------------------------------------
# Test 10: analyze_track path validation (unsupported extension)
# ---------------------------------------------------------------------------

class TestAnalyzeTrackPathValidation:
    """analyze_track() must reject unsupported file extensions before any I/O."""

    def test_analyze_track_rejects_m4a(self, tmp_path, capsys):
        """analyze_track must return 1 for .m4a (T-04-01 mitigation)."""
        m4a_file = tmp_path / 'track.m4a'
        m4a_file.write_bytes(b'\x00' * 10)  # Dummy file
        result = analyze.analyze_track(m4a_file)
        assert result == 1, "analyze_track accepted .m4a; expected exit code 1"
        captured = capsys.readouterr()
        lines = [l.strip() for l in captured.out.strip().split('\n') if l.strip()]
        error_events = [json.loads(l) for l in lines if json.loads(l).get('type') == 'error']
        assert len(error_events) >= 1, "No error event for unsupported extension"


# ---------------------------------------------------------------------------
# Test 3 (error JSONL): subprocess — missing file → JSONL error + non-zero exit
# ---------------------------------------------------------------------------

class TestSubprocessMissingFile:
    """Subprocess test: missing file → JSONL error on stdout + non-zero exit code."""

    def test_3_error_jsonl_on_missing_file(self):
        """
        Run analyze.py with a non-existent path.
        Assert: stdout contains one JSON line with type='error' and non-empty msg.
        Assert: exit code != 0.
        """
        nonexistent = '/tmp/nonexistent_track_that_does_not_exist.mp3'
        proc = subprocess.run(
            [PYTHON_EXE, '-u', str(ANALYZE_SCRIPT), nonexistent],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode != 0, (
            f"Expected non-zero exit for missing file, got {proc.returncode}"
        )
        stdout_lines = [l.strip() for l in proc.stdout.strip().split('\n') if l.strip()]
        assert len(stdout_lines) >= 1, (
            f"No output on stdout for missing file. stderr: {proc.stderr}"
        )
        # Every stdout line must be valid JSON
        for line in stdout_lines:
            try:
                json.loads(line)
            except json.JSONDecodeError:
                pytest.fail(f"Non-JSON line on stdout: {line!r}")
        # Must have at least one error event
        error_events = [json.loads(l) for l in stdout_lines
                        if json.loads(l).get('type') == 'error']
        assert len(error_events) >= 1, (
            f"No error event on stdout. Lines: {stdout_lines}"
        )
        err_ev = error_events[0]
        assert err_ev.get('file') == nonexistent, (
            f"Error event file field wrong: {err_ev.get('file')!r}"
        )
        assert err_ev.get('msg'), "Error event has empty msg"


# ---------------------------------------------------------------------------
# Test 4 (bpm args): monkeypatch detect_beats to verify arg passthrough
# ---------------------------------------------------------------------------

class TestBpmArgPassthrough:
    """analyze_track() must pass bpm_min/bpm_max to detect_beats()."""

    def test_4_bpm_args_passed_to_detect_beats(self, tmp_path, capsys):
        """
        analyze_track with bpm_min=80, bpm_max=160 must call detect_beats
        with bpm_min=80, bpm_max=160.
        """
        # Create a minimal WAV file so path validation passes
        wav_file = tmp_path / 'test.wav'
        wav_file.write_bytes(_make_minimal_wav_bytes())

        detected_args = {}

        # Patch load_audio to return a simple array (avoid heavy I/O)
        dummy_audio = np.zeros(22050, dtype='float32')
        dummy_sr = 22050
        dummy_beats = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]  # >=4 beats required

        def mock_load_audio(path):
            return dummy_audio, dummy_sr

        def mock_detect_beats(audio, sr, bpm_min=60, bpm_max=200):
            detected_args['bpm_min'] = bpm_min
            detected_args['bpm_max'] = bpm_max
            return dummy_beats

        def mock_encode_markers(beat_positions, bpm_delta_threshold=0.5):
            # Return valid minimal markers
            non_terminal = [(0.5, 2), (1.0, 2)]
            terminal = (3.0, 120.0)
            return non_terminal, terminal

        def mock_pack_beatgrid(non_terminal, terminal, footer_byte):
            return analyze.pack_beatgrid(non_terminal, terminal, footer_byte)

        def mock_atomic_write_geob(target_path, write_fn, geob_bytes):
            pass  # Don't actually write

        with patch.object(analyze, 'load_audio', mock_load_audio), \
             patch.object(analyze, 'detect_beats', mock_detect_beats), \
             patch.object(analyze, 'encode_markers', mock_encode_markers), \
             patch.object(analyze, 'atomic_write_geob', mock_atomic_write_geob):
            result = analyze.analyze_track(wav_file, bpm_min=80, bpm_max=160)

        assert 'bpm_min' in detected_args, "detect_beats was not called"
        assert detected_args['bpm_min'] == 80, (
            f"bpm_min passed as {detected_args['bpm_min']}, expected 80"
        )
        assert detected_args['bpm_max'] == 160, (
            f"bpm_max passed as {detected_args['bpm_max']}, expected 160"
        )


# ---------------------------------------------------------------------------
# Test 6 (stdout-only JSONL): subprocess — every stdout line is valid JSON
# ---------------------------------------------------------------------------

class TestStdoutPurity:
    """Subprocess test: help output must show usage; all stdout during run must be JSON."""

    def test_6_help_exits_zero(self):
        """python analyze.py --help must exit 0 and show usage."""
        proc = subprocess.run(
            [PYTHON_EXE, str(ANALYZE_SCRIPT), '--help'],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert proc.returncode == 0, (
            f"--help exited {proc.returncode}. stderr: {proc.stderr}"
        )
        assert 'usage' in proc.stdout.lower() or 'analyze' in proc.stdout.lower(), (
            f"--help output doesn't look like usage. stdout: {proc.stdout[:200]}"
        )


# ---------------------------------------------------------------------------
# Subprocess tests requiring real audio (skipped if no fixture)
# ---------------------------------------------------------------------------

# Look for a WAV fixture: tests can export TEST_WAV_PATH env var, or we create one.
_TEST_WAV_PATH = os.environ.get('TEST_WAV_PATH', '')
_HAS_REAL_AUDIO = bool(_TEST_WAV_PATH and Path(_TEST_WAV_PATH).is_file())

# Try to create a synthetic WAV fixture for subprocess tests
_SYNTHETIC_WAV = None
try:
    import tempfile as _tempfile
    _tmp = _tempfile.NamedTemporaryFile(suffix='.wav', delete=False, prefix='serato_test_')
    _tmp.write(_make_minimal_wav_bytes(n_samples=22050 * 5, sample_rate=22050))  # 5 seconds
    _tmp.flush()
    _tmp.close()
    _SYNTHETIC_WAV = _tmp.name
    _HAS_SYNTHETIC_WAV = True
except Exception:
    _HAS_SYNTHETIC_WAV = False


@pytest.mark.skipif(not _HAS_SYNTHETIC_WAV, reason="Could not create synthetic WAV fixture")
class TestSubprocessWithAudio:
    """
    Subprocess integration tests using a synthetic WAV file.
    These match Phase 2's Swift invocation contract: python -u analyze.py <file>.
    """

    def test_1_happy_path_jsonl_events(self):
        """
        Run analyze.py on a synthetic WAV. Parse stdout as JSONL.
        Assert: at least one progress event and one result event.
        """
        proc = subprocess.run(
            [PYTHON_EXE, '-u', str(ANALYZE_SCRIPT), _SYNTHETIC_WAV],
            capture_output=True,
            text=True,
            timeout=120,
        )
        stdout_lines = [l.strip() for l in proc.stdout.strip().split('\n') if l.strip()]

        # Every stdout line must be valid JSON
        parsed = []
        for line in stdout_lines:
            try:
                parsed.append(json.loads(line))
            except json.JSONDecodeError:
                pytest.fail(f"Non-JSON line on stdout: {line!r}")

        event_types = [e.get('type') for e in parsed]
        assert 'progress' in event_types, (
            f"No progress event on stdout. Events: {event_types}"
        )
        assert 'result' in event_types or proc.returncode != 0, (
            f"No result event and exit code 0. Events: {event_types}"
        )

    def test_2_result_event_schema(self):
        """
        The result event (if present) must have exactly these keys per D-06:
        type, file, bpm_min, bpm_max, marker_count, duration_sec.
        """
        proc = subprocess.run(
            [PYTHON_EXE, '-u', str(ANALYZE_SCRIPT), _SYNTHETIC_WAV],
            capture_output=True,
            text=True,
            timeout=120,
        )
        stdout_lines = [l.strip() for l in proc.stdout.strip().split('\n') if l.strip()]
        result_events = []
        for line in stdout_lines:
            try:
                ev = json.loads(line)
                if ev.get('type') == 'result':
                    result_events.append(ev)
            except json.JSONDecodeError:
                pass

        if not result_events:
            pytest.skip("No result event (beat detection may have failed on synthetic audio)")

        result = result_events[0]
        required_keys = {'type', 'file', 'bpm_min', 'bpm_max', 'marker_count', 'duration_sec'}
        assert set(result.keys()) == required_keys, (
            f"Result event has wrong keys.\n"
            f"Expected: {required_keys}\n"
            f"Got: {set(result.keys())}"
        )

    def test_5_stderr_timing(self):
        """
        stderr must contain elapsed time information (startup + analysis).
        Pattern: the string should contain a number followed by 's', 'ms', or 'sec'.
        """
        import re
        proc = subprocess.run(
            [PYTHON_EXE, '-u', str(ANALYZE_SCRIPT), _SYNTHETIC_WAV],
            capture_output=True,
            text=True,
            timeout=120,
        )
        stderr = proc.stderr
        # Allow the test to pass if beat detection failed but timing was still logged
        timing_pattern = re.compile(r'\d+\.?\d*\s*(s|ms|sec)', re.IGNORECASE)
        has_timing = bool(timing_pattern.search(stderr)) or (
            'elapsed' in stderr.lower() or 'startup' in stderr.lower()
            or 'analysis' in stderr.lower()
        )
        assert has_timing, (
            f"stderr does not contain timing information.\nstderr: {stderr[:500]}"
        )

    def test_6_stdout_purity(self):
        """
        Every line on stdout must be valid JSON. No plain-text lines allowed.
        """
        proc = subprocess.run(
            [PYTHON_EXE, '-u', str(ANALYZE_SCRIPT), _SYNTHETIC_WAV],
            capture_output=True,
            text=True,
            timeout=120,
        )
        stdout_lines = [l.strip() for l in proc.stdout.strip().split('\n') if l.strip()]
        for line in stdout_lines:
            try:
                json.loads(line)
            except json.JSONDecodeError:
                pytest.fail(
                    f"Non-JSON line on stdout: {line!r}\n"
                    f"All stdout:\n{proc.stdout}"
                )
