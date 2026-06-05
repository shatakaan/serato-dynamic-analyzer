"""
pytest suite for python/library.py — Plan 04-01 TDD RED tests.

Covers:
  LIB-01: build_crate_tree (implied parents, hierarchy), list_crates IPC
  LIB-02: list_tracks IPC (path/filename/beatgrid_source/duration_sec fields)
  LIB-03: read_beatgrid_source (serato/tool/none)
  D-07:   pack_beatgrid version byte + decode_beatgrid both-versions (in test_geob.py)

All tests in this file are RED until Task 2 creates python/library.py.

Test infrastructure mirrors test_worker.py:
  - subprocess.Popen for IPC tests
  - tmp_path synthetic fixtures (NO dependency on ~/Music/_Serato_/)
  - SERATO_SUBCRATES_DIR env var to override library path in IPC tests
"""
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

PYTHON_DIR = Path(__file__).parent.parent
ANALYZE_SCRIPT = PYTHON_DIR / "analyze.py"

VENV_PYTHON = PYTHON_DIR / "venv" / "bin" / "python3"
PYTHON_EXE = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable

sys.path.insert(0, str(PYTHON_DIR))


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_synthetic_subcrates_dir(tmp_path: Path) -> Path:
    """
    Create a synthetic Subcrates directory with .crate files:
      - House.crate          (top-level, has own .crate file)
      - House%%Deep.crate    (child of House)
      - A%%B%%C.crate        (A->B->C; A and A%%B are implied parents with no own .crate)
    Returns the path to the Subcrates directory.
    """
    from serato_tools.crate import Crate

    subcrates = tmp_path / "Subcrates"
    subcrates.mkdir()

    # Create House.crate (no tracks needed for tree tests)
    house_crate = Crate(str(subcrates / "House.crate"))
    house_crate.save(str(subcrates / "House.crate"))

    # Create House%%Deep.crate
    deep_crate = Crate(str(subcrates / "House%%Deep.crate"))
    deep_crate.save(str(subcrates / "House%%Deep.crate"))

    # Create A%%B%%C.crate  (A and A%%B are implied parents)
    abc_crate = Crate(str(subcrates / "A%%B%%C.crate"))
    abc_crate.save(str(subcrates / "A%%B%%C.crate"))

    return subcrates


def _make_synthetic_crate_with_track(tmp_path: Path, track_path: str) -> Path:
    """
    Create a .crate file with one track entry pointing to `track_path`.
    Uses add_track() which internally calls format_filepath() to strip the
    leading slash (Serato storage format).
    Returns the path to the .crate file.
    """
    from serato_tools.crate import Crate

    subcrates = tmp_path / "Subcrates"
    subcrates.mkdir(exist_ok=True)

    crate_file = subcrates / "TestCrate.crate"
    crate = Crate(str(crate_file))
    # add_track uses format_filepath to normalize — pass without leading slash
    # because format_filepath strips the leading slash if present
    crate.data.append(("otrk", [("ptrk", track_path.lstrip("/"))]))
    crate.save(str(crate_file))
    return crate_file


def _make_minimal_mp3_with_geob(path: Path, version_bytes: bytes) -> None:
    """
    Create a minimal MP3 file with an ID3v2.3 GEOB:Serato BeatGrid tag
    whose version bytes are set to `version_bytes` (e.g. b'\x01\x00' or b'\x01\x01').
    """
    import mutagen.id3

    # Build a tiny-but-valid GEOB payload:
    # version_bytes (2) + count uint32 BE (1 terminal) + terminal 8 bytes + footer 0x00
    geob_data = bytearray(version_bytes)
    geob_data += struct.pack(">I", 1)          # 1 marker total (terminal)
    geob_data += struct.pack(">ff", 1.0, 120.0)  # terminal: position=1.0s, bpm=120.0
    geob_data += b"\x00"                        # footer

    # Write ID3 tag with GEOB frame
    tags = mutagen.id3.ID3()
    tags["GEOB:Serato BeatGrid"] = mutagen.id3.GEOB(
        encoding=0,
        mime="application/octet-stream",
        filename="",
        desc="Serato BeatGrid",
        data=bytes(geob_data),
    )
    tags.save(str(path), v2_version=3)
    # Append minimal MPEG frame header so mutagen.id3.ID3(path) doesn't fail
    with open(str(path), "ab") as f:
        f.write(bytes([0xFF, 0xFB, 0x90, 0x00]))
        f.write(b"\x00" * 413)


def _make_minimal_mp3_no_geob(path: Path) -> None:
    """Create a minimal MP3 file with no GEOB tags."""
    import mutagen.id3

    tags = mutagen.id3.ID3()
    tags.save(str(path), v2_version=3)
    with open(str(path), "ab") as f:
        f.write(bytes([0xFF, 0xFB, 0x90, 0x00]))
        f.write(b"\x00" * 413)


# ---------------------------------------------------------------------------
# LIB-01: build_crate_tree
# ---------------------------------------------------------------------------

def test_build_crate_tree(tmp_path):
    """
    build_crate_tree() with House.crate, House%%Deep.crate, A%%B%%C.crate:
    - Returns top-level nodes "House" and "A"
    - "House" has one child "Deep" with non-None crate_path
    - "A" has one child "B" (implied parent, crate_path=None)
    - "B" has one child "C" with non-None crate_path
    """
    from library import build_crate_tree

    subcrates = _make_synthetic_subcrates_dir(tmp_path)
    tree = build_crate_tree(str(subcrates))

    top_names = {n["name"] for n in tree}
    assert "House" in top_names, f"Expected 'House' in top-level nodes, got: {top_names}"
    assert "A" in top_names, f"Expected 'A' in top-level nodes, got: {top_names}"

    house_node = next(n for n in tree if n["name"] == "House")
    assert house_node["crate_path"] is not None, "House should have a non-None crate_path"
    assert house_node["children"] is not None, "House should have children"
    child_names = [c["name"] for c in house_node["children"]]
    assert "Deep" in child_names, f"House should have child 'Deep', got: {child_names}"
    deep_node = next(c for c in house_node["children"] if c["name"] == "Deep")
    assert deep_node["crate_path"] is not None, "Deep should have a non-None crate_path"

    a_node = next(n for n in tree if n["name"] == "A")
    assert a_node["children"] is not None, "A should have children"
    b_node = next(c for c in a_node["children"] if c["name"] == "B")
    assert b_node is not None, "A should have a child B"
    assert b_node["children"] is not None, "B should have children"
    c_node = next(c for c in b_node["children"] if c["name"] == "C")
    assert c_node is not None, "B should have a child C"
    assert c_node["crate_path"] is not None, "C should have a non-None crate_path"


def test_crate_tree_implied_parent_path_none(tmp_path):
    """
    The implied "B" node under "A" (from A%%B%%C.crate with no A%%B.crate) must
    have crate_path == None.
    """
    from library import build_crate_tree

    subcrates = _make_synthetic_subcrates_dir(tmp_path)
    tree = build_crate_tree(str(subcrates))

    a_node = next(n for n in tree if n["name"] == "A")
    b_node = next(c for c in a_node["children"] if c["name"] == "B")
    assert b_node["crate_path"] is None, (
        f"Implied parent 'B' must have crate_path=None, got: {b_node['crate_path']}"
    )


# ---------------------------------------------------------------------------
# LIB-01: list_crates IPC
# ---------------------------------------------------------------------------

def test_list_crates_ipc(tmp_path):
    """
    Spawn analyze.py --worker, send {"cmd":"list_crates"}, assert one line with
    type=="crates" and a "tree" list.
    Uses SERATO_SUBCRATES_DIR env var to point to synthetic fixtures.
    """
    subcrates = _make_synthetic_subcrates_dir(tmp_path)
    env = os.environ.copy()
    env["SERATO_SUBCRATES_DIR"] = str(subcrates)

    proc = subprocess.Popen(
        [PYTHON_EXE, "-u", str(ANALYZE_SCRIPT), "--worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        # Consume ready signal
        ready_line = proc.stdout.readline().strip()
        assert ready_line, "No ready signal from worker"
        ready_event = json.loads(ready_line)
        assert ready_event["type"] == "ready", f"Expected ready, got: {ready_event}"

        # Send list_crates command
        req = json.dumps({"cmd": "list_crates"}) + "\n"
        proc.stdin.write(req)
        proc.stdin.flush()

        response_line = proc.stdout.readline().strip()
    finally:
        proc.terminate()
        proc.wait()

    assert response_line, "No response received for list_crates command"
    event = json.loads(response_line)
    assert event["type"] == "crates", f"Expected type 'crates', got: {event['type']!r}"
    assert "tree" in event, f"Expected 'tree' key in crates event, got keys: {list(event.keys())}"
    assert isinstance(event["tree"], list), f"Expected 'tree' to be a list"


# ---------------------------------------------------------------------------
# LIB-02: list_tracks IPC
# ---------------------------------------------------------------------------

def test_list_tracks_ipc(tmp_path):
    """
    Spawn analyze.py --worker, send {"cmd":"list_tracks","crate":"<path>"}, assert
    one line type=="tracks" with a "tracks" list whose items carry
    path, filename, beatgrid_source, duration_sec.
    """
    # Create a fake MP3 file inside tmp_path
    fake_mp3 = tmp_path / "test_track.mp3"
    _make_minimal_mp3_no_geob(fake_mp3)

    crate_file = _make_synthetic_crate_with_track(tmp_path, str(fake_mp3))

    env = os.environ.copy()
    # SERATO_SUBCRATES_DIR not needed here since we're passing crate_path directly
    subcrates_dir = crate_file.parent
    env["SERATO_SUBCRATES_DIR"] = str(subcrates_dir)

    proc = subprocess.Popen(
        [PYTHON_EXE, "-u", str(ANALYZE_SCRIPT), "--worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        # Consume ready signal
        proc.stdout.readline()

        # Send list_tracks command
        req = json.dumps({"cmd": "list_tracks", "crate": str(crate_file)}) + "\n"
        proc.stdin.write(req)
        proc.stdin.flush()

        response_line = proc.stdout.readline().strip()
    finally:
        proc.terminate()
        proc.wait()

    assert response_line, "No response received for list_tracks command"
    event = json.loads(response_line)
    assert event["type"] == "tracks", f"Expected type 'tracks', got: {event['type']!r}"
    assert "tracks" in event, f"Expected 'tracks' key in event"
    assert isinstance(event["tracks"], list), "Expected tracks to be a list"

    if event["tracks"]:
        track = event["tracks"][0]
        required_keys = {"path", "filename", "beatgrid_source", "duration_sec"}
        missing = required_keys - set(track.keys())
        assert not missing, f"Track record missing keys: {missing}. Got: {list(track.keys())}"


# ---------------------------------------------------------------------------
# LIB-03: read_beatgrid_source
# ---------------------------------------------------------------------------

def test_beatgrid_source_serato(tmp_path):
    """
    A GEOB:Serato BeatGrid with version bytes 0x01 0x00 → read_beatgrid_source() returns 'serato'.
    """
    from library import read_beatgrid_source

    mp3_file = tmp_path / "serato_track.mp3"
    _make_minimal_mp3_with_geob(mp3_file, b"\x01\x00")

    result = read_beatgrid_source(str(mp3_file))
    assert result == "serato", f"Expected 'serato' for 0x01 0x00 version bytes, got: {result!r}"


def test_beatgrid_source_tool(tmp_path):
    """
    A GEOB:Serato BeatGrid with version bytes 0x01 0x01 → read_beatgrid_source() returns 'tool'.
    """
    from library import read_beatgrid_source

    mp3_file = tmp_path / "tool_track.mp3"
    _make_minimal_mp3_with_geob(mp3_file, b"\x01\x01")

    result = read_beatgrid_source(str(mp3_file))
    assert result == "tool", f"Expected 'tool' for 0x01 0x01 version bytes, got: {result!r}"


def test_beatgrid_source_none(tmp_path):
    """
    A file with no GEOB:Serato BeatGrid tag → read_beatgrid_source() returns 'none'.
    """
    from library import read_beatgrid_source

    mp3_file = tmp_path / "no_beatgrid.mp3"
    _make_minimal_mp3_no_geob(mp3_file)

    result = read_beatgrid_source(str(mp3_file))
    assert result == "none", f"Expected 'none' for file with no BeatGrid tag, got: {result!r}"


# ---------------------------------------------------------------------------
# LIB-02: track path reconstruction (Pitfall 3)
# ---------------------------------------------------------------------------

def test_track_path_reconstruction(tmp_path):
    """
    A relpath "Users/x/Music/t.mp3" (no leading slash as stored in .crate)
    must reconstruct to "/Users/x/Music/t.mp3" (Pitfall 3 — Serato strips leading slash).

    This tests the library.py list_tracks() behavior via IPC: the path field in
    the tracks list must start with '/'.
    """
    # Create a fake MP3 at a specific path structure
    music_dir = tmp_path / "Users" / "x" / "Music"
    music_dir.mkdir(parents=True)
    fake_mp3 = music_dir / "t.mp3"
    _make_minimal_mp3_no_geob(fake_mp3)

    # Build a crate with a relpath (no leading slash) — mimic Serato storage
    subcrates = tmp_path / "Subcrates"
    subcrates.mkdir()

    from serato_tools.crate import Crate
    crate_file = subcrates / "Test.crate"
    crate = Crate(str(crate_file))
    # Directly append the otrk entry with a relative path (no leading slash)
    rel_path = str(fake_mp3).lstrip("/")
    crate.data.append(("otrk", [("ptrk", rel_path)]))
    crate.save(str(crate_file))

    env = os.environ.copy()
    env["SERATO_SUBCRATES_DIR"] = str(subcrates)

    proc = subprocess.Popen(
        [PYTHON_EXE, "-u", str(ANALYZE_SCRIPT), "--worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        proc.stdout.readline()  # ready signal

        req = json.dumps({"cmd": "list_tracks", "crate": str(crate_file)}) + "\n"
        proc.stdin.write(req)
        proc.stdin.flush()

        response_line = proc.stdout.readline().strip()
    finally:
        proc.terminate()
        proc.wait()

    assert response_line, "No response received"
    event = json.loads(response_line)
    assert event["type"] == "tracks", f"Expected type 'tracks', got: {event['type']!r}"
    assert event["tracks"], "Expected at least one track in response"

    track_path = event["tracks"][0]["path"]
    assert track_path.startswith("/"), (
        f"Track path must start with '/' (Pitfall 3), got: {track_path!r}"
    )
