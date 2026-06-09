"""
Pytest suite for GEOB encoding in analyze.py.
Tests 1-5 cover pack_beatgrid, decode_beatgrid, encode_markers, and requirements.txt.
Tests 6-10 cover write functions and atomic write safety.

Canonical references:
- Holzhaus/serato-tags serato_beatgrid.md: footer byte is \x00
- PITFALLS.md CR-1: big-endian struct packing
- PITFALLS.md CR-2: terminal marker is always last, footer always present
- PITFALLS.md CR-5: ID3v2.3 (header magic: ID3 0x03 0x00)
"""
import struct
import os
import sys
from pathlib import Path

# Add the python/ directory to sys.path so we can import analyze
PYTHON_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PYTHON_DIR))

import analyze


# ---------------------------------------------------------------------------
# Task 1 Tests: Encoding contracts
# ---------------------------------------------------------------------------

def test_1_endianness():
    """
    pack_beatgrid with one non-terminal marker (1.5s, 16 beats) and a terminal
    marker (4.5s, 128.0 BPM) must produce:
    - bytes[0:2] = b'\\x01\\x00' (version)
    - bytes[2:6] = uint32 BE total count == 2 (1 non-terminal + 1 terminal)
    - bytes[6:10] decode as big-endian float32 == 1.5 (non-terminal position)
    - bytes[10:14] decode as big-endian uint32 == 16 (beats_till_next)
    """
    data = analyze.pack_beatgrid(
        non_terminal_markers=[(1.5, 16)],
        terminal_marker=(4.5, 128.0),
        footer_byte=analyze.GEOB_FOOTER,
    )
    assert data[0:2] == b'\x01\x01', f"Version bytes wrong: {data[0:2].hex()} (D-07: our tool writes 0x01 0x01)"
    count = struct.unpack('>I', data[2:6])[0]
    assert count == 2, f"Total count field wrong: {count} (expected 2: 1 non-terminal + 1 terminal)"
    pos1 = struct.unpack('>f', data[6:10])[0]
    assert abs(pos1 - 1.5) < 1e-4, f"Position 1 wrong: {pos1}"
    beats = struct.unpack('>I', data[10:14])[0]
    assert beats == 16, f"beats_till_next wrong: {beats}"


def test_2_terminal_marker_encoding():
    """
    The terminal marker must encode position as big-endian float32 and BPM as
    big-endian float32 — NOT as position + beats_till_next.
    With one non-terminal (1.5s, 16) and terminal (4.5s, 128.0):
    - bytes[14:18] decode as big-endian float32 == 4.5  (2 version + 4 count + 8 non-terminal)
    - bytes[18:22] decode as big-endian float32 == 128.0
    """
    data = analyze.pack_beatgrid(
        non_terminal_markers=[(1.5, 16)],
        terminal_marker=(4.5, 128.0),
        footer_byte=analyze.GEOB_FOOTER,
    )
    # Terminal marker starts at offset 14 (2 version + 4 count + 8 non-terminal)
    term_pos = struct.unpack('>f', data[14:18])[0]
    term_bpm = struct.unpack('>f', data[18:22])[0]
    assert abs(term_pos - 4.5) < 1e-4, f"Terminal position wrong: {term_pos}"
    assert abs(term_bpm - 128.0) < 1e-4, f"Terminal BPM wrong: {term_bpm}"


def test_3_footer_byte():
    """
    The last byte must be the canonical Holzhaus spec footer: \\x00.
    Source: Holzhaus/serato-tags serato_beatgrid.md — 'Footer: single null byte \\x00'.
    Also confirmed in PITFALLS.md CR-1 structural layout and CR-2.
    """
    data = analyze.pack_beatgrid(
        non_terminal_markers=[(1.5, 16)],
        terminal_marker=(4.5, 128.0),
        footer_byte=analyze.GEOB_FOOTER,
    )
    assert data[-1:] == b'\x00', (
        f"Footer byte wrong: {data[-1:].hex()} (expected 00 per Holzhaus spec)"
    )
    assert analyze.GEOB_FOOTER == b'\x00', (
        f"GEOB_FOOTER constant wrong: {analyze.GEOB_FOOTER.hex()} (expected 00)"
    )


def test_4_round_trip():
    """
    decode_beatgrid(pack_beatgrid(markers, terminal)) must return marker list
    and terminal that match inputs to float precision (1e-4 tolerance).
    """
    non_terminal = [(1.5, 16), (3.0, 8)]
    terminal = (4.5, 128.0)
    data = analyze.pack_beatgrid(
        non_terminal_markers=non_terminal,
        terminal_marker=terminal,
        footer_byte=analyze.GEOB_FOOTER,
    )
    decoded_non_terminal, decoded_terminal = analyze.decode_beatgrid(data)

    assert len(decoded_non_terminal) == len(non_terminal), (
        f"Marker count wrong: {len(decoded_non_terminal)} vs {len(non_terminal)}"
    )
    for i, ((pos, beats), (dpos, dbeats)) in enumerate(
        zip(non_terminal, decoded_non_terminal)
    ):
        assert abs(pos - dpos) < 1e-4, f"Marker {i} position wrong: {dpos} vs {pos}"
        assert beats == dbeats, f"Marker {i} beats_till_next wrong: {dbeats} vs {beats}"

    assert abs(terminal[0] - decoded_terminal[0]) < 1e-4, (
        f"Terminal position wrong: {decoded_terminal[0]} vs {terminal[0]}"
    )
    assert abs(terminal[1] - decoded_terminal[1]) < 1e-4, (
        f"Terminal BPM wrong: {decoded_terminal[1]} vs {terminal[1]}"
    )


def test_5_requirements_txt():
    """
    python/requirements.txt must contain pinned versions for all required packages.
    """
    req_path = PYTHON_DIR / 'requirements.txt'
    assert req_path.exists(), f"requirements.txt not found at {req_path}"
    content = req_path.read_text()
    required = ['librosa==0.11', 'mutagen==1.47', 'soundfile==0.12', 'imageio-ffmpeg']
    for pkg in required:
        assert pkg in content, f"Missing '{pkg}' in requirements.txt"


# ---------------------------------------------------------------------------
# Task 2 Tests: Write functions and atomic safety
# ---------------------------------------------------------------------------

def _make_minimal_mp3(path: Path) -> None:
    """
    Create a minimal valid MP3 file with an ID3v2.3 tag and a tiny MPEG frame.
    This is sufficient for mutagen to parse tags without needing real audio data.
    """
    # ID3v2.3 header: "ID3" + version 2.3 + flags 0x00 + syncsafe size
    # We'll create a tag with no frames (just the header + padding)
    import mutagen.id3
    # Write an ID3 tag to the file, then append minimal MPEG frame bytes
    # Start with the ID3 tag structure (mutagen will write a proper header)
    tags = mutagen.id3.ID3()
    # ID3v2.3 uses v2_version=3
    tags.save(str(path), v2_version=3)
    # Append a minimal MPEG audio frame so the file has some audio data
    with open(str(path), 'ab') as f:
        # Minimal valid MP3 frame: sync word (0xFF 0xFB) + header + empty data
        # 0xFF 0xFB = MPEG1, Layer3, 128kbps, 44100Hz, stereo
        # Frame size for 128kbps/44100Hz = 417 bytes
        frame_header = bytes([0xFF, 0xFB, 0x90, 0x00])
        f.write(frame_header)
        f.write(b'\x00' * 413)  # Padding to fill out the frame


def _make_minimal_aiff(path: Path) -> None:
    """
    Create a minimal valid AIFF file that mutagen.aiff.AIFF can open.
    AIFF files consist of: FORM chunk header + COMM chunk + optionally SSND chunk.
    """
    import struct as s
    # AIFF COMM chunk: sampleRate as 80-bit extended
    # Minimal AIFF-C or AIFF:
    # FORM + size + AIFF marker + COMM chunk
    comm_data = (
        s.pack('>h', 1) +         # numChannels = 1 (mono)
        s.pack('>I', 0) +          # numSampleFrames = 0
        s.pack('>h', 16) +         # sampleSize = 16 bits
        bytes([0x40, 0x0e, 0xac, 0x44, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])  # 44100 Hz as 80-bit extended
    )
    comm_chunk = b'COMM' + s.pack('>I', len(comm_data)) + comm_data

    # SSND chunk (sound data chunk) - required for valid AIFF
    ssnd_data = s.pack('>II', 0, 0)  # offset=0, blockSize=0
    ssnd_chunk = b'SSND' + s.pack('>I', len(ssnd_data)) + ssnd_data

    form_body = b'AIFF' + comm_chunk + ssnd_chunk
    form_chunk = b'FORM' + s.pack('>I', len(form_body)) + form_body

    path.write_bytes(form_chunk)


def _make_minimal_wav(path: Path) -> None:
    """
    Create a minimal valid WAV file that mutagen.wave.WAVE can open.
    """
    import struct as s
    # fmt chunk
    fmt_data = (
        s.pack('<H', 1) +       # AudioFormat = PCM
        s.pack('<H', 1) +       # NumChannels = 1
        s.pack('<I', 44100) +   # SampleRate = 44100
        s.pack('<I', 88200) +   # ByteRate = SampleRate * NumChannels * BitsPerSample/8
        s.pack('<H', 2) +       # BlockAlign = NumChannels * BitsPerSample/8
        s.pack('<H', 16)        # BitsPerSample = 16
    )
    fmt_chunk = b'fmt ' + s.pack('<I', len(fmt_data)) + fmt_data

    # data chunk with 0 samples
    data_chunk = b'data' + s.pack('<I', 0)

    riff_body = b'WAVE' + fmt_chunk + data_chunk
    riff_chunk = b'RIFF' + s.pack('<I', len(riff_body)) + riff_body

    path.write_bytes(riff_chunk)


def _make_minimal_m4a(path: Path) -> None:
    """
    Create a minimal valid M4A file that mutagen.mp4.MP4 can open.
    Strategy: copy the committed binary fixture at tests/fixtures/minimal.m4a.
    See RESEARCH.md Open Question 1 and Pitfall 6.
    """
    import shutil
    fixture = Path(__file__).parent / 'fixtures' / 'minimal.m4a'
    if not fixture.exists():
        raise FileNotFoundError(f"Binary fixture not found: {fixture}")
    shutil.copy2(str(fixture), str(path))


# ---------------------------------------------------------------------------
# Phase 5 Tests: M4A/MP4 write round-trips (tests 11, 13, 14)
# ---------------------------------------------------------------------------

def test_11_m4a_write(tmp_path):
    """write_geob_m4a() must write a parseable MP4FreeForm atom at the correct key."""
    import mutagen.mp4
    m4a_file = tmp_path / 'test.m4a'
    _make_minimal_m4a(m4a_file)
    geob_bytes = analyze.pack_beatgrid(
        non_terminal_markers=[(1.0, 8)],
        terminal_marker=(2.0, 120.0),
        footer_byte=analyze.GEOB_FOOTER,
    )
    analyze.write_geob_m4a(m4a_file, geob_bytes)
    # Round-trip: mutagen must read the key back
    af = mutagen.mp4.MP4(str(m4a_file))
    assert '----:com.serato.dj:beatgrid' in af.tags, \
        "MP4FreeForm atom not found at expected key"


def test_12_mp4_write(tmp_path):
    """write_geob_mp4() must write a parseable MP4FreeForm atom at the correct key.

    Uses _make_minimal_m4a() with a .mp4 extension — M4A and MP4 share the MP4
    box container format, so the same fixture works for both (D-11, FMT-05).
    """
    import mutagen.mp4
    mp4_file = tmp_path / 'test.mp4'
    _make_minimal_m4a(mp4_file)
    geob_bytes = analyze.pack_beatgrid(
        non_terminal_markers=[(1.0, 8)],
        terminal_marker=(2.0, 120.0),
        footer_byte=analyze.GEOB_FOOTER,
    )
    analyze.write_geob_mp4(mp4_file, geob_bytes)
    af = mutagen.mp4.MP4(str(mp4_file))
    assert '----:com.serato.dj:beatgrid' in af.tags, \
        "MP4FreeForm atom not found at expected key after write_geob_mp4()"


def test_13_m4a_geob_encoding_contract(tmp_path):
    """
    After write_geob_m4a(), base64-decoding the stored atom value must yield a
    payload starting with b'application/octet-stream\\x00\\x00Serato BeatGrid\\x00'.
    """
    import base64
    import mutagen.mp4
    m4a_file = tmp_path / 'contract.m4a'
    _make_minimal_m4a(m4a_file)
    geob_bytes = analyze.pack_beatgrid(
        non_terminal_markers=[(1.0, 8)],
        terminal_marker=(2.0, 120.0),
        footer_byte=analyze.GEOB_FOOTER,
    )
    analyze.write_geob_m4a(m4a_file, geob_bytes)
    af = mutagen.mp4.MP4(str(m4a_file))
    stored = bytes(af.tags['----:com.serato.dj:beatgrid'][0])
    decoded = base64.b64decode(stored + b'==')  # add padding for decode
    expected_prefix = b'application/octet-stream\x00\x00Serato BeatGrid\x00'
    assert decoded.startswith(expected_prefix), \
        f"FLAC wrapper missing. Decoded prefix: {decoded[:40]!r}"


def test_14_m4a_atom_key(tmp_path):
    """The MP4 atom key must be exactly '----:com.serato.dj:beatgrid' (all lowercase)."""
    import mutagen.mp4
    m4a_file = tmp_path / 'atomkey.m4a'
    _make_minimal_m4a(m4a_file)
    geob_bytes = analyze.pack_beatgrid(
        non_terminal_markers=[(1.0, 8)],
        terminal_marker=(2.0, 120.0),
        footer_byte=analyze.GEOB_FOOTER,
    )
    analyze.write_geob_m4a(m4a_file, geob_bytes)
    af = mutagen.mp4.MP4(str(m4a_file))
    keys = list(af.tags.keys())
    assert '----:com.serato.dj:beatgrid' in keys, \
        f"Wrong atom key. Found: {keys}"
    assert '----:com.serato.dj:Serato BeatGrid' not in keys, \
        "Title-case key was written — must be all lowercase"


def test_6_mp3_write_id3v23(tmp_path):
    """
    write_geob_mp3() must produce a file whose ID3 tag header starts with
    ID3 0x03 0x00 (ID3v2.3 magic bytes at positions 3-4 of the file).
    """
    mp3_file = tmp_path / 'test.mp3'
    _make_minimal_mp3(mp3_file)

    # Generate some valid GEOB bytes
    geob_bytes = analyze.pack_beatgrid(
        non_terminal_markers=[(1.0, 8)],
        terminal_marker=(2.0, 120.0),
        footer_byte=analyze.GEOB_FOOTER,
    )
    analyze.write_geob_mp3(mp3_file, geob_bytes)

    # Read the first bytes of the resulting file
    raw = mp3_file.read_bytes()
    assert raw[0:3] == b'ID3', f"Expected ID3 magic, got: {raw[0:3].hex()}"
    assert raw[3] == 0x03, (
        f"Expected ID3v2.3 (0x03), got version byte: 0x{raw[3]:02x} "
        f"(0x04 = ID3v2.4, which Serato silently ignores — CR-5)"
    )
    assert raw[4] == 0x00, f"Expected flags byte 0x00, got: 0x{raw[4]:02x}"


def test_7_preserve_other_tags(tmp_path):
    """
    After write_geob_mp3(), all GEOB frames other than 'GEOB:Serato BeatGrid'
    must be byte-for-byte identical to before the write.
    """
    import mutagen.id3

    mp3_file = tmp_path / 'test_preserve.mp3'
    _make_minimal_mp3(mp3_file)

    # Add a GEOB:Serato Cues frame to the file
    cues_data = b'\x01\x00' + b'\xde\xad\xbe\xef' * 4  # Fake but distinctive bytes
    tags = mutagen.id3.ID3(str(mp3_file))
    tags['GEOB:Serato Cues 0'] = mutagen.id3.GEOB(
        encoding=0,
        mime='application/octet-stream',
        filename='',
        desc='Serato Cues 0',
        data=cues_data,
    )
    tags.save(str(mp3_file), v2_version=3)

    # Read back the original cues bytes
    before_tags = mutagen.id3.ID3(str(mp3_file))
    cues_before = bytes(before_tags['GEOB:Serato Cues 0'].data)

    # Now write the BeatGrid
    geob_bytes = analyze.pack_beatgrid(
        non_terminal_markers=[(1.0, 8)],
        terminal_marker=(2.0, 120.0),
        footer_byte=analyze.GEOB_FOOTER,
    )
    analyze.write_geob_mp3(mp3_file, geob_bytes)

    # Read back the cues frame and verify it's unchanged
    after_tags = mutagen.id3.ID3(str(mp3_file))
    assert 'GEOB:Serato Cues 0' in after_tags, "GEOB:Serato Cues 0 frame was deleted!"
    cues_after = bytes(after_tags['GEOB:Serato Cues 0'].data)
    assert cues_before == cues_after, (
        f"GEOB:Serato Cues 0 was modified!\n"
        f"Before: {cues_before.hex()}\n"
        f"After:  {cues_after.hex()}"
    )


def test_8_atomic_write_safety(tmp_path, monkeypatch):
    """
    If os.replace() raises OSError, the original file must be unmodified.
    The temp file is left behind; the original is never replaced.
    """
    import mutagen.id3

    mp3_file = tmp_path / 'original.mp3'
    _make_minimal_mp3(mp3_file)

    # Record original content
    original_content = mp3_file.read_bytes()

    # Monkeypatch os.replace to raise
    def fail_replace(src, dst):
        raise OSError("Simulated replace failure")

    monkeypatch.setattr('os.replace', fail_replace)

    geob_bytes = analyze.pack_beatgrid(
        non_terminal_markers=[(1.0, 8)],
        terminal_marker=(2.0, 120.0),
        footer_byte=analyze.GEOB_FOOTER,
    )

    try:
        analyze.atomic_write_geob(mp3_file, analyze.write_geob_mp3, geob_bytes)
    except OSError:
        pass  # Expected

    # Original file must be unmodified
    assert mp3_file.read_bytes() == original_content, (
        "Original file was modified despite os.replace() failure!"
    )


def test_9_aiff_write(tmp_path):
    """
    write_geob_aiff() must produce a file that mutagen.aiff.AIFF can open
    and that contains a GEOB:Serato BeatGrid frame.
    """
    import mutagen.aiff

    aiff_file = tmp_path / 'test.aiff'
    _make_minimal_aiff(aiff_file)

    geob_bytes = analyze.pack_beatgrid(
        non_terminal_markers=[(1.0, 8)],
        terminal_marker=(2.0, 120.0),
        footer_byte=analyze.GEOB_FOOTER,
    )
    analyze.write_geob_aiff(aiff_file, geob_bytes)

    af = mutagen.aiff.AIFF(str(aiff_file))
    assert af.tags is not None, "AIFF file has no tags after write"
    assert 'GEOB:Serato BeatGrid' in af.tags, (
        f"GEOB:Serato BeatGrid not found in AIFF tags. Present: {list(af.tags.keys())}"
    )


def test_10_wav_write(tmp_path):
    """
    write_geob_wav() must produce a file that mutagen.wave.WAVE can open
    and that contains a GEOB:Serato BeatGrid frame.
    """
    import mutagen.wave

    wav_file = tmp_path / 'test.wav'
    _make_minimal_wav(wav_file)

    geob_bytes = analyze.pack_beatgrid(
        non_terminal_markers=[(1.0, 8)],
        terminal_marker=(2.0, 120.0),
        footer_byte=analyze.GEOB_FOOTER,
    )
    analyze.write_geob_wav(wav_file, geob_bytes)

    wf = mutagen.wave.WAVE(str(wav_file))
    assert wf.tags is not None, "WAV file has no tags after write"
    assert 'GEOB:Serato BeatGrid' in wf.tags, (
        f"GEOB:Serato BeatGrid not found in WAV tags. Present: {list(wf.tags.keys())}"
    )


# ---------------------------------------------------------------------------
# Task 1 Phase 4 Tests: Version byte differentiation (D-07)
# ---------------------------------------------------------------------------

def test_tool_version_byte():
    """
    pack_beatgrid() output bytes[0:2] must be b'\\x01\\x01' (not b'\\x01\\x00').
    After D-07: our tool writes byte[1]=0x01 to distinguish from Serato's 0x01 0x00.
    RED until Task 2 changes the version byte in pack_beatgrid().
    """
    data = analyze.pack_beatgrid(
        non_terminal_markers=[(1.0, 8)],
        terminal_marker=(2.0, 120.0),
        footer_byte=analyze.GEOB_FOOTER,
    )
    assert data[0:2] == b'\x01\x01', (
        f"Expected version bytes 0x01 0x01 (this-tool marker, D-07), "
        f"got: {data[0:2].hex()} — pack_beatgrid must be updated to write b'\\x01\\x01'"
    )


def test_decode_both_versions():
    """
    decode_beatgrid() must round-trip beatgrids with EITHER version byte pattern:
      b'\\x01\\x00' (Serato-written)  AND  b'\\x01\\x01' (this-tool-written).
    RED until Task 2 updates decode_beatgrid() to accept both.
    """
    non_terminal = [(1.5, 16)]
    terminal = (4.5, 128.0)

    # Build a reference payload using pack_beatgrid (now writes 0x01 0x01)
    data_new = analyze.pack_beatgrid(
        non_terminal_markers=non_terminal,
        terminal_marker=terminal,
        footer_byte=analyze.GEOB_FOOTER,
    )

    # Build a payload manually with old version bytes 0x01 0x00 (Serato format)
    data_old = bytearray(b'\x01\x00')
    data_old += struct.pack('>I', len(non_terminal) + 1)
    for pos, beats in non_terminal:
        data_old += struct.pack('>fI', pos, beats)
    data_old += struct.pack('>ff', terminal[0], terminal[1])
    data_old += b'\x00'
    data_old = bytes(data_old)

    # Round-trip the old (Serato) version
    nt_old, t_old = analyze.decode_beatgrid(data_old)
    assert len(nt_old) == len(non_terminal), (
        f"Old version byte decode: wrong marker count {len(nt_old)} vs {len(non_terminal)}"
    )
    assert abs(nt_old[0][0] - 1.5) < 1e-4, f"Old version: position wrong: {nt_old[0][0]}"
    assert abs(t_old[1] - 128.0) < 1e-4, f"Old version: terminal BPM wrong: {t_old[1]}"

    # Round-trip the new (this-tool) version — will fail if decode_beatgrid only accepts 0x01 0x00
    nt_new, t_new = analyze.decode_beatgrid(data_new)
    assert len(nt_new) == len(non_terminal), (
        f"New version byte decode: wrong marker count {len(nt_new)} vs {len(non_terminal)}"
    )
    assert abs(nt_new[0][0] - 1.5) < 1e-4, f"New version: position wrong: {nt_new[0][0]}"
    assert abs(t_new[1] - 128.0) < 1e-4, f"New version: terminal BPM wrong: {t_new[1]}"
