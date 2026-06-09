"""
Tests for load_audio() — audio loading with format dispatch.

Plan 01-02 TDD RED phase.

Test coverage:
  1. MP3 dispatch — calls imageio_ffmpeg.get_ffmpeg_exe(), returns (array, sr)
  2. AIFF dispatch — calls soundfile.read directly, NOT imageio_ffmpeg
  3. WAV dispatch — calls soundfile.read directly, NOT imageio_ffmpeg
  4. Mono conversion — stereo soundfile output is downmixed to shape (N,)
  5. Unsupported format — ValueError raised before any I/O for .m4a
  6. ffmpeg error — RuntimeError with file path when returncode != 0
"""
import io
import struct
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_wav_bytes(n_samples: int = 882, sample_rate: int = 22050) -> bytes:
    """
    Build a minimal valid mono 16-bit PCM WAV in memory.

    Layout:
      RIFF chunk descriptor (12 bytes)
      fmt  sub-chunk (24 bytes: 8 header + 16 data)
      data sub-chunk (8 bytes header + n_samples * 2 bytes of silence)

    Total = 44 + n_samples * 2 bytes.
    """
    n_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * n_channels * bits_per_sample // 8
    block_align = n_channels * bits_per_sample // 8
    data_size = n_samples * block_align
    chunk_size = 36 + data_size  # rest of RIFF chunk after 'WAVE' tag

    header = struct.pack(
        '<4sI4s'   # RIFF, chunk_size, WAVE
        '4sI'      # fmt , subchunk1_size (16)
        'HHIIHH',  # audio_format, n_channels, sample_rate, byte_rate, block_align, bits_per_sample
        b'RIFF', chunk_size, b'WAVE',
        b'fmt ', 16,
        1,           # PCM
        n_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
    )
    data_header = struct.pack('<4sI', b'data', data_size)
    silence = b'\x00' * data_size

    return header + data_header + silence


WAV_FIXTURE_BYTES = _make_wav_bytes()


# ---------------------------------------------------------------------------
# Test 1: MP3 dispatch
# ---------------------------------------------------------------------------

class TestMp3Dispatch:
    """load_audio('track.mp3') calls imageio_ffmpeg.get_ffmpeg_exe()."""

    def test_mp3_calls_get_ffmpeg_exe_and_returns_array(self, tmp_path):
        """MP3 branch: imageio_ffmpeg.get_ffmpeg_exe() is called; returns (ndarray, int)."""
        import analyze

        # Create a fake .mp3 file so Path.resolve() resolves to a real path
        mp3_file = tmp_path / "track.mp3"
        mp3_file.write_bytes(b"\xff\xfb\x00\x00")  # Fake MP3 magic bytes

        fake_ffmpeg_path = "/fake/ffmpeg"
        fake_proc = MagicMock()
        fake_proc.returncode = 0
        fake_proc.stdout = WAV_FIXTURE_BYTES

        ffmpeg_called_with = []

        def fake_get_ffmpeg_exe():
            ffmpeg_called_with.append(True)
            return fake_ffmpeg_path

        with patch("analyze.imageio_ffmpeg.get_ffmpeg_exe", side_effect=fake_get_ffmpeg_exe), \
             patch("analyze.subprocess.run", return_value=fake_proc):
            audio, sr = analyze.load_audio(mp3_file)

        assert ffmpeg_called_with, "imageio_ffmpeg.get_ffmpeg_exe() was not called"
        assert isinstance(audio, np.ndarray), f"Expected ndarray, got {type(audio)}"
        assert isinstance(sr, int), f"Expected int sample rate, got {type(sr)}"
        assert audio.dtype == np.float32, f"Expected float32, got {audio.dtype}"


# ---------------------------------------------------------------------------
# Test 2: AIFF dispatch (no ffmpeg)
# ---------------------------------------------------------------------------

class TestAiffDispatch:
    """load_audio('track.aiff') uses soundfile directly — no ffmpeg."""

    def test_aiff_does_not_call_ffmpeg(self, tmp_path):
        """AIFF branch: imageio_ffmpeg.get_ffmpeg_exe() must NOT be called."""
        import analyze

        aiff_file = tmp_path / "track.aiff"
        aiff_file.write_bytes(b"FORM\x00\x00\x00\x08AIFF")  # Fake AIFF magic

        mock_audio = np.zeros(1000, dtype=np.float32)
        mock_sr = 44100

        ffmpeg_called = []

        def fake_get_ffmpeg_exe():
            ffmpeg_called.append(True)
            return "/fake/ffmpeg"

        with patch("analyze.imageio_ffmpeg.get_ffmpeg_exe", side_effect=fake_get_ffmpeg_exe), \
             patch("analyze.soundfile.read", return_value=(mock_audio, mock_sr)):
            audio, sr = analyze.load_audio(aiff_file)

        assert not ffmpeg_called, "imageio_ffmpeg.get_ffmpeg_exe() must NOT be called for AIFF"
        assert isinstance(audio, np.ndarray)
        assert sr == 22050  # resampled to 22050


# ---------------------------------------------------------------------------
# Test 3: WAV dispatch (no ffmpeg)
# ---------------------------------------------------------------------------

class TestWavDispatch:
    """load_audio('track.wav') uses soundfile directly — no ffmpeg."""

    def test_wav_does_not_call_ffmpeg(self, tmp_path):
        """WAV branch: imageio_ffmpeg.get_ffmpeg_exe() must NOT be called."""
        import analyze

        wav_file = tmp_path / "track.wav"
        wav_file.write_bytes(WAV_FIXTURE_BYTES)

        mock_audio = np.zeros(1000, dtype=np.float32)
        mock_sr = 22050

        ffmpeg_called = []

        def fake_get_ffmpeg_exe():
            ffmpeg_called.append(True)
            return "/fake/ffmpeg"

        with patch("analyze.imageio_ffmpeg.get_ffmpeg_exe", side_effect=fake_get_ffmpeg_exe), \
             patch("analyze.soundfile.read", return_value=(mock_audio, mock_sr)):
            audio, sr = analyze.load_audio(wav_file)

        assert not ffmpeg_called, "imageio_ffmpeg.get_ffmpeg_exe() must NOT be called for WAV"
        assert isinstance(audio, np.ndarray)
        assert sr == 22050


# ---------------------------------------------------------------------------
# Test 4: Mono conversion
# ---------------------------------------------------------------------------

class TestMonoConversion:
    """Stereo soundfile output is downmixed to shape (N,)."""

    def test_stereo_aiff_downmixed_to_mono(self, tmp_path):
        """When soundfile.read returns (N, 2) array, load_audio returns shape (N,)."""
        import analyze

        aiff_file = tmp_path / "stereo.aiff"
        aiff_file.write_bytes(b"FORM\x00\x00\x00\x08AIFF")

        stereo_audio = np.zeros((1000, 2), dtype=np.float32)
        mock_sr = 22050

        with patch("analyze.imageio_ffmpeg.get_ffmpeg_exe", return_value="/fake/ffmpeg"), \
             patch("analyze.soundfile.read", return_value=(stereo_audio, mock_sr)):
            audio, sr = analyze.load_audio(aiff_file)

        assert audio.ndim == 1, f"Expected mono (ndim=1), got ndim={audio.ndim}, shape={audio.shape}"
        assert audio.shape[0] == 1000


# ---------------------------------------------------------------------------
# Test 5: Unsupported format raises ValueError
# ---------------------------------------------------------------------------

class TestUnsupportedFormat:
    """load_audio raises ValueError for truly unsupported formats before any I/O.

    M4A (.m4a) is now supported as of Phase 5 (FMT-04). Tests updated accordingly.
    """

    def test_unsupported_format_raises_value_error(self, tmp_path):
        """A genuinely unsupported extension (e.g. .xyz) must raise ValueError immediately."""
        import analyze

        xyz_file = tmp_path / "track.xyz"
        xyz_file.write_bytes(b"\x00\x00\x00\x20test")  # Fake content

        with pytest.raises(ValueError) as exc_info:
            analyze.load_audio(xyz_file)

        msg = str(exc_info.value).lower()
        assert "unsupported" in msg, (
            f"ValueError message should mention 'unsupported', got: {exc_info.value!r}"
        )

    def test_unsupported_format_no_io(self, tmp_path):
        """Verify no I/O occurs for unsupported format (soundfile.read must not be called)."""
        import analyze

        xyz_file = tmp_path / "track.xyz"
        xyz_file.write_bytes(b"\x00\x00\x00\x20test")

        with patch("analyze.soundfile.read") as mock_sf, \
             patch("analyze.subprocess.run") as mock_proc:
            with pytest.raises(ValueError):
                analyze.load_audio(xyz_file)
            mock_sf.assert_not_called()
            mock_proc.assert_not_called()


# ---------------------------------------------------------------------------
# Test 6: ffmpeg error raises RuntimeError with file path
# ---------------------------------------------------------------------------

class TestFfmpegError:
    """When ffmpeg returns non-zero exit code, RuntimeError includes file path."""

    def test_ffmpeg_failure_raises_runtime_error(self, tmp_path):
        """returncode=1 from subprocess.run must raise RuntimeError mentioning file path and 'ffmpeg'."""
        import analyze

        mp3_file = tmp_path / "broken.mp3"
        mp3_file.write_bytes(b"\xff\xfb\x00\x00")

        fake_proc = MagicMock()
        fake_proc.returncode = 1
        fake_proc.stderr = b"Invalid data found when processing input"

        with patch("analyze.imageio_ffmpeg.get_ffmpeg_exe", return_value="/fake/ffmpeg"), \
             patch("analyze.subprocess.run", return_value=fake_proc):
            with pytest.raises(RuntimeError) as exc_info:
                analyze.load_audio(mp3_file)

        error_msg = str(exc_info.value)
        assert "ffmpeg" in error_msg.lower(), (
            f"RuntimeError should mention 'ffmpeg', got: {error_msg!r}"
        )
        assert "broken.mp3" in error_msg or str(mp3_file) in error_msg, (
            f"RuntimeError should include the file path, got: {error_msg!r}"
        )
