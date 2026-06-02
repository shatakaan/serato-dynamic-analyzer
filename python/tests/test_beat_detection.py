"""
Tests for detect_beats() in analyze.py.

TDD RED phase: These tests are written before detect_beats() is implemented.

Decision references:
  D-07 — librosa.beat.plp() + aggregate=None locked
  D-08 — refuse on zero BPM / fewer than 4 beats
  D-09 — 0.5 BPM delta threshold
  D-10 — 128-marker limit adaptive retry
  HR-4 — onset timing bias (ONSET_OFFSET_SECONDS correction)
  T-03-02 — ValueError on < 4 beats (threat mitigation)
  T-03-03 — non-negative beat positions (threat mitigation)
"""
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import numpy as np
import pytest

# Add the python directory to the path so we can import analyze
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import librosa submodules eagerly so they are all in sys.modules before any
# unittest.mock.patch() context managers run. librosa uses lazy submodule loading —
# plain `import librosa` only loads librosa.version. The first time patch() resolves
# e.g. 'librosa.beat.plp', Python must import librosa.beat, whose module-level code
# calls moved()(tempo) via the decorator library. If librosa.feature.tempo is already
# mocked at that point, decorator tries to set __qualname__ on the MagicMock → fails.
# Pre-importing all submodules below caches them in sys.modules, so patch() replaces
# already-loaded attributes instead of triggering a module load during __enter__.
import librosa          # noqa: E402
import librosa.beat     # noqa: E402 — pre-load to avoid __qualname__ mock collision
import librosa.feature  # noqa: E402
import librosa.onset    # noqa: E402
import librosa.util     # noqa: E402

from analyze import detect_beats, encode_markers, ONSET_OFFSET_SECONDS


class TestDetectBeatsPlpDispatch:
    """Test 1: detect_beats() calls librosa.beat.plp(), not beat_track()."""

    def test_plp_is_called_not_beat_track(self):
        """
        detect_beats() must use librosa.beat.plp() for beat extraction.
        librosa.beat.beat_track() must NOT be called at all (D-07: plp() locked decision).

        Note: We do NOT mock librosa.beat.beat_track because patching it triggers
        librosa.beat module re-import which fails when librosa.feature.tempo is already
        mocked (decorator tries to set __qualname__ on a MagicMock). Instead, we use
        unittest.mock.spy on beat_track via patch.object, which wraps the real object.
        """
        audio = np.zeros(22050, dtype=np.float32)
        sr = 22050

        n_frames = 100
        pulse = np.zeros(n_frames, dtype=np.float32)
        for frame in [10, 20, 30, 40, 50]:
            pulse[frame] = 1.0

        tempo_frames = np.full(n_frames, 120.0, dtype=np.float32)
        oenv = np.ones(n_frames, dtype=np.float32)

        with patch('librosa.onset.onset_strength', return_value=oenv), \
             patch('librosa.feature.tempo', return_value=tempo_frames) as mock_tempo, \
             patch('librosa.beat.plp', return_value=pulse) as mock_plp, \
             patch.object(librosa.beat, 'beat_track', wraps=librosa.beat.beat_track) as mock_beat_track, \
             patch('librosa.util.localmax', return_value=np.array(
                 [False]*9 + [True] + [False]*9 + [True] + [False]*9 + [True] +
                 [False]*9 + [True] + [False]*9 + [True] + [False]*(n_frames - 51)
             )), \
             patch('librosa.frames_to_time', return_value=np.array([0.5, 1.0, 1.5, 2.0, 2.5])):

            result = detect_beats(audio, sr=sr)

        # plp() must be called (D-07)
        assert mock_plp.called, "librosa.beat.plp() was not called — detect_beats() must use plp()"

        # beat_track() must NOT be called (D-07: plp() only, not beat_track())
        assert not mock_beat_track.called, (
            "librosa.beat.beat_track() was called — detect_beats() must use plp() only, "
            "not beat_track()"
        )

        # aggregate=None must be passed to feature.tempo (D-07: frame-level tempo)
        mock_tempo.assert_called_once()
        tempo_call_kwargs = mock_tempo.call_args[1]
        assert tempo_call_kwargs.get('aggregate') is None, (
            "librosa.feature.tempo() must be called with aggregate=None (D-07 locked decision)"
        )

        # Result must be a list of floats
        assert isinstance(result, list)
        assert all(isinstance(t, float) for t in result)


class TestDetectBeatsOnsetCorrection:
    """Test 2: Onset offset correction (HR-4, T-03-03)."""

    def test_onset_correction_applied(self):
        """
        Beat positions returned by detect_beats() must have ONSET_OFFSET_SECONDS subtracted.
        ONSET_OFFSET_SECONDS is the correction for librosa's systematic lateness bias (~30ms).
        """
        audio = np.zeros(22050, dtype=np.float32)
        sr = 22050

        n_frames = 100
        pulse = np.zeros(n_frames, dtype=np.float32)
        oenv = np.ones(n_frames, dtype=np.float32)
        tempo_frames = np.full(n_frames, 120.0, dtype=np.float32)

        # Simulate plp() → localmax → frames_to_time producing these times
        raw_times = np.array([1.0, 2.0, 3.0, 4.0])
        expected_corrected = [max(0.0, t - ONSET_OFFSET_SECONDS) for t in raw_times]

        with patch('librosa.onset.onset_strength', return_value=oenv), \
             patch('librosa.feature.tempo', return_value=tempo_frames), \
             patch('librosa.beat.plp', return_value=pulse), \
             patch('librosa.util.localmax', return_value=np.array([True] * 4 + [False] * (n_frames - 4))), \
             patch('librosa.frames_to_time', return_value=raw_times):

            result = detect_beats(audio, sr=sr)

        assert result == pytest.approx(sorted(expected_corrected), abs=1e-6), (
            f"Onset correction not applied correctly. "
            f"Expected {expected_corrected}, got {result}"
        )

    def test_onset_correction_matches_constant(self):
        """
        The applied correction must equal ONSET_OFFSET_SECONDS (the documented constant).
        This test ties the correction to the module-level constant, not a magic number.
        """
        audio = np.zeros(22050, dtype=np.float32)
        sr = 22050
        n_frames = 50
        oenv = np.ones(n_frames, dtype=np.float32)
        tempo_frames = np.full(n_frames, 120.0, dtype=np.float32)

        raw_times = np.array([2.0, 4.0, 6.0, 8.0])

        with patch('librosa.onset.onset_strength', return_value=oenv), \
             patch('librosa.feature.tempo', return_value=tempo_frames), \
             patch('librosa.beat.plp', return_value=np.zeros(n_frames)), \
             patch('librosa.util.localmax', return_value=np.array([True] * 4 + [False] * (n_frames - 4))), \
             patch('librosa.frames_to_time', return_value=raw_times):

            result = detect_beats(audio, sr=sr)

        for raw, corrected in zip(raw_times.tolist(), result):
            assert abs(corrected - (raw - ONSET_OFFSET_SECONDS)) < 1e-9, (
                f"Correction mismatch: {raw} - ONSET_OFFSET_SECONDS({ONSET_OFFSET_SECONDS}) "
                f"= {raw - ONSET_OFFSET_SECONDS}, got {corrected}"
            )


class TestDetectBeatsMinimumBeatGuard:
    """Test 3: Fewer than 4 beats → ValueError (D-08, T-03-02)."""

    def test_fewer_than_4_beats_raises_value_error(self):
        """
        If plp() produces fewer than 4 beat positions, detect_beats() must raise ValueError.
        This prevents writing an empty or near-empty beatgrid over an existing good grid (D-08).
        """
        audio = np.zeros(22050, dtype=np.float32)
        sr = 22050
        n_frames = 50
        oenv = np.ones(n_frames, dtype=np.float32)
        tempo_frames = np.full(n_frames, 120.0, dtype=np.float32)

        # Only 2 beat positions — below the minimum of 4
        sparse_times = np.array([1.0, 2.0])

        with patch('librosa.onset.onset_strength', return_value=oenv), \
             patch('librosa.feature.tempo', return_value=tempo_frames), \
             patch('librosa.beat.plp', return_value=np.zeros(n_frames)), \
             patch('librosa.util.localmax', return_value=np.array([True, True] + [False] * (n_frames - 2))), \
             patch('librosa.frames_to_time', return_value=sparse_times):

            with pytest.raises(ValueError) as exc_info:
                detect_beats(audio, sr=sr)

        error_msg = str(exc_info.value).lower()
        assert 'fewer than 4' in error_msg or 'zero bpm' in error_msg, (
            f"ValueError message should mention 'fewer than 4' or 'zero BPM', got: {exc_info.value}"
        )

    def test_zero_beats_raises_value_error(self):
        """
        If plp() produces zero beat positions (silent audio), detect_beats() raises ValueError.
        """
        audio = np.zeros(22050, dtype=np.float32)
        sr = 22050
        n_frames = 50
        oenv = np.zeros(n_frames, dtype=np.float32)
        tempo_frames = np.full(n_frames, 120.0, dtype=np.float32)

        with patch('librosa.onset.onset_strength', return_value=oenv), \
             patch('librosa.feature.tempo', return_value=tempo_frames), \
             patch('librosa.beat.plp', return_value=np.zeros(n_frames)), \
             patch('librosa.util.localmax', return_value=np.zeros(n_frames, dtype=bool)), \
             patch('librosa.frames_to_time', return_value=np.array([])):

            with pytest.raises(ValueError):
                detect_beats(audio, sr=sr)

    def test_exactly_4_beats_does_not_raise(self):
        """
        Exactly 4 beat positions should NOT raise ValueError.
        The guard is strictly < 4.
        """
        audio = np.zeros(22050, dtype=np.float32)
        sr = 22050
        n_frames = 50
        oenv = np.ones(n_frames, dtype=np.float32)
        tempo_frames = np.full(n_frames, 120.0, dtype=np.float32)

        four_times = np.array([0.5, 1.0, 1.5, 2.0])

        with patch('librosa.onset.onset_strength', return_value=oenv), \
             patch('librosa.feature.tempo', return_value=tempo_frames), \
             patch('librosa.beat.plp', return_value=np.zeros(n_frames)), \
             patch('librosa.util.localmax', return_value=np.array([True] * 4 + [False] * (n_frames - 4))), \
             patch('librosa.frames_to_time', return_value=four_times):

            # Should not raise
            result = detect_beats(audio, sr=sr)

        assert len(result) == 4


class TestDetectBeatsBpmRange:
    """Test 4: BPM range passed through to plp() (D-07)."""

    def test_bpm_range_passed_to_plp(self):
        """
        detect_beats(audio, sr, bpm_min=80, bpm_max=160) must pass
        tempo_min=80 and tempo_max=160 to librosa.beat.plp().
        """
        audio = np.zeros(22050, dtype=np.float32)
        sr = 22050
        n_frames = 100
        oenv = np.ones(n_frames, dtype=np.float32)
        tempo_frames = np.full(n_frames, 100.0, dtype=np.float32)
        beat_times = np.array([0.5, 1.0, 1.5, 2.0, 2.5])

        with patch('librosa.onset.onset_strength', return_value=oenv), \
             patch('librosa.feature.tempo', return_value=tempo_frames), \
             patch('librosa.beat.plp', return_value=np.zeros(n_frames)) as mock_plp, \
             patch('librosa.util.localmax', return_value=np.array([True] * 5 + [False] * (n_frames - 5))), \
             patch('librosa.frames_to_time', return_value=beat_times):

            detect_beats(audio, sr=sr, bpm_min=80, bpm_max=160)

        mock_plp.assert_called_once()
        plp_kwargs = mock_plp.call_args[1]
        assert plp_kwargs.get('tempo_min') == 80, (
            f"tempo_min not passed to plp(): expected 80, got {plp_kwargs.get('tempo_min')}"
        )
        assert plp_kwargs.get('tempo_max') == 160, (
            f"tempo_max not passed to plp(): expected 160, got {plp_kwargs.get('tempo_max')}"
        )

    def test_default_bpm_range_applied(self):
        """
        Default bpm_min=60 and bpm_max=200 must be applied when not specified.
        """
        audio = np.zeros(22050, dtype=np.float32)
        sr = 22050
        n_frames = 100
        oenv = np.ones(n_frames, dtype=np.float32)
        tempo_frames = np.full(n_frames, 120.0, dtype=np.float32)
        beat_times = np.array([0.5, 1.0, 1.5, 2.0])

        with patch('librosa.onset.onset_strength', return_value=oenv), \
             patch('librosa.feature.tempo', return_value=tempo_frames), \
             patch('librosa.beat.plp', return_value=np.zeros(n_frames)) as mock_plp, \
             patch('librosa.util.localmax', return_value=np.array([True] * 4 + [False] * (n_frames - 4))), \
             patch('librosa.frames_to_time', return_value=beat_times):

            detect_beats(audio, sr=sr)

        plp_kwargs = mock_plp.call_args[1]
        assert plp_kwargs.get('tempo_min') == 60
        assert plp_kwargs.get('tempo_max') == 200


class TestDetectBeats128MarkerLimit:
    """Test 5: 128-marker limit respected by encode_markers() (HR-2, D-10)."""

    def test_128_marker_limit_respected(self):
        """
        When detect_beats() produces 300 beat positions with wildly varying BPM,
        encode_markers() must return at most 127 non-terminal + 1 terminal = 128 total.
        This tests the adaptive threshold retry in encode_markers() (D-10).
        """
        # Generate 300 synthetic beat positions with varying inter-beat intervals.
        # Formula from plan: i * (60.0 / (120 + i % 10)) for i in range(300)
        # But start from i=1 (i=0 gives position 0.0)
        # Actually, use cumulative positions to get sensible timestamps
        positions = []
        t = 0.0
        for i in range(1, 301):
            bpm = 120 + (i % 10)  # BPM varies from 120 to 129
            interval = 60.0 / bpm
            t += interval
            positions.append(t)

        assert len(positions) == 300

        non_terminal, terminal = encode_markers(positions, bpm_delta_threshold=0.5)
        total_markers = len(non_terminal) + 1  # +1 for terminal

        assert total_markers <= 128, (
            f"encode_markers() returned {total_markers} markers, exceeding the 128-marker limit. "
            f"The adaptive threshold retry (D-10) must reduce this to <=128."
        )

    def test_128_marker_limit_simple_varying(self):
        """
        Additional test: 300 positions from the plan's exact formula stress the algorithm.
        """
        positions_raw = [i * (60.0 / (120 + i % 10)) for i in range(1, 301)]
        # Make them cumulative (monotonically increasing)
        positions = sorted(set(positions_raw))
        if len(positions) < 4:
            pytest.skip("Not enough unique positions for this test")

        non_terminal, terminal = encode_markers(positions, bpm_delta_threshold=0.5)
        total = len(non_terminal) + 1

        assert total <= 128, (
            f"128-marker limit exceeded: {total} markers produced for {len(positions)} positions"
        )


class TestDetectBeatsNonNegativePositions:
    """Test 6: Beat positions are non-negative after onset correction (T-03-03)."""

    def test_positions_clamped_at_zero(self):
        """
        If ONSET_OFFSET_SECONDS subtraction would produce a negative position
        (e.g., raw time 0.01s - 0.03s correction = -0.02s), detect_beats() must
        clamp to 0.0, not return a negative value.
        """
        audio = np.zeros(22050, dtype=np.float32)
        sr = 22050
        n_frames = 50
        oenv = np.ones(n_frames, dtype=np.float32)
        tempo_frames = np.full(n_frames, 120.0, dtype=np.float32)

        # Raw times smaller than ONSET_OFFSET_SECONDS will produce negative after correction
        # ONSET_OFFSET_SECONDS = 0.030
        raw_times = np.array([0.01, 1.0, 2.0, 3.0])  # 0.01 - 0.030 = -0.02 → must clamp to 0.0

        with patch('librosa.onset.onset_strength', return_value=oenv), \
             patch('librosa.feature.tempo', return_value=tempo_frames), \
             patch('librosa.beat.plp', return_value=np.zeros(n_frames)), \
             patch('librosa.util.localmax', return_value=np.array([True] * 4 + [False] * (n_frames - 4))), \
             patch('librosa.frames_to_time', return_value=raw_times):

            result = detect_beats(audio, sr=sr)

        assert all(t >= 0.0 for t in result), (
            f"All beat positions must be non-negative after onset correction. Got: {result}"
        )
        # The first position (0.01 - 0.030 = -0.02) should be clamped to 0.0
        assert result[0] == pytest.approx(0.0, abs=1e-9), (
            f"Position {raw_times[0]} - {ONSET_OFFSET_SECONDS} = {raw_times[0] - ONSET_OFFSET_SECONDS} "
            f"should be clamped to 0.0, got {result[0]}"
        )

    def test_all_positions_non_negative_general(self):
        """
        All positions returned by detect_beats() must be >= 0.0 (T-03-03 threat mitigation).
        """
        audio = np.zeros(22050, dtype=np.float32)
        sr = 22050
        n_frames = 50
        oenv = np.ones(n_frames, dtype=np.float32)
        tempo_frames = np.full(n_frames, 120.0, dtype=np.float32)

        # Reasonable positive raw times (no clamping needed here)
        raw_times = np.array([0.5, 1.0, 1.5, 2.0, 2.5, 3.0])

        with patch('librosa.onset.onset_strength', return_value=oenv), \
             patch('librosa.feature.tempo', return_value=tempo_frames), \
             patch('librosa.beat.plp', return_value=np.zeros(n_frames)), \
             patch('librosa.util.localmax', return_value=np.array([True] * 6 + [False] * (n_frames - 6))), \
             patch('librosa.frames_to_time', return_value=raw_times):

            result = detect_beats(audio, sr=sr)

        assert all(t >= 0.0 for t in result)
        assert isinstance(result, list)
        assert all(isinstance(t, float) for t in result)
