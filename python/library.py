"""
library.py — Serato Library Browser Python backend.

Provides:
  - build_crate_tree(subcrates_dir): parse .crate filenames into a nested tree
  - list_crates(): emit {"type":"crates","tree":[...]} for the worker IPC
  - list_tracks(crate_path): emit {"type":"tracks","crate":"...","tracks":[...]}
  - read_beatgrid_source(file_path): returns 'none'|'serato'|'tool'
  - _read_duration(file_path): returns float|None from mutagen info.length

Security:
  - list_tracks() validates crate_path is inside the Subcrates dir (T-04-PT)
  - All public functions wrap in try/except → emit_error (T-04-DOS)

IPC contract:
  Request:  {"cmd":"list_crates"}
  Response: {"type":"crates","tree":[{"name":"...","crate_path":"...|null","children":[...]},...]}

  Request:  {"cmd":"list_tracks","crate":"/path/to/Name.crate"}
  Response: {"type":"tracks","crate":"...","tracks":[{"path":"...","filename":"...","beatgrid_source":"...","duration_sec":...|null},...]}

Version byte constants (D-07):
  SERATO_VERSION_BYTES   = b'\x01\x00'  (Serato-written GEOB BeatGrid)
  OUR_TOOL_VERSION_BYTES = b'\x01\x01'  (this-tool-written GEOB BeatGrid)
"""
import json
import os
import sys
from pathlib import Path

# Version byte constants for GEOB BeatGrid differentiation (D-07, LIB-03)
SERATO_VERSION_BYTES: bytes = b"\x01\x00"
OUR_TOOL_VERSION_BYTES: bytes = b"\x01\x01"


# ---------------------------------------------------------------------------
# emit_json / emit_error — replicated from analyze.py pattern
# (Cannot import from analyze without risking __main__ block side effects;
#  these are short and must be self-contained in library.py)
# ---------------------------------------------------------------------------

def emit_json(event: dict) -> None:
    """Emit a JSONL event to stdout. flush=True is mandatory for Swift IPC."""
    print(json.dumps(event), flush=True)


def emit_error(file_path: str, msg: str) -> None:
    """Emit an error event per the IPC schema."""
    emit_json({"type": "error", "file": file_path, "msg": msg})


# ---------------------------------------------------------------------------
# Crate tree building (LIB-01)
# ---------------------------------------------------------------------------

def build_crate_tree(subcrates_dir: str) -> list[dict]:
    """
    Parse all .crate files in subcrates_dir into a nested tree structure.

    Serato encodes the hierarchy in the filename using '%%' as a path
    separator. E.g. 'House%%Deep.crate' = crate "Deep" under "House".
    Not all intermediate nodes have their own .crate file — these become
    implied parent nodes with crate_path=None.

    Returns a list of top-level node dicts, each with:
      {
        "name": str,
        "crate_path": str | None,  # None for implied parents
        "children": list | None,   # None for leaf nodes (no sub-crates)
      }
    """
    crate_files = sorted(
        f for f in os.listdir(subcrates_dir) if f.endswith(".crate")
    )

    nodes: dict[str, dict] = {}  # key (full %%-joined stem) -> node dict

    for fname in crate_files:
        stem = fname[: -len(".crate")]  # strip .crate suffix
        crate_path = os.path.join(subcrates_dir, fname)
        parts = stem.split("%%")

        for i, part in enumerate(parts):
            key = "%%".join(parts[: i + 1])
            if key not in nodes:
                nodes[key] = {
                    "name": part,
                    "key": key,
                    "crate_path": None,
                    "children_keys": [],
                }
            if i == len(parts) - 1:
                # This is the actual .crate file — record its path
                nodes[key]["crate_path"] = crate_path

    # Wire parent → child relationships
    for key in nodes:
        if "%%" in key:
            parent_key = "%%".join(key.split("%%")[:-1])
            if parent_key in nodes and key not in nodes[parent_key]["children_keys"]:
                nodes[parent_key]["children_keys"].append(key)

    def node_to_dict(key: str) -> dict:
        n = nodes[key]
        child_keys = sorted(n["children_keys"])
        children = [node_to_dict(c) for c in child_keys] if child_keys else None
        return {
            "name": n["name"],
            "crate_path": n["crate_path"],
            "children": children,
        }

    top_level = sorted(k for k in nodes if "%%" not in k)
    return [node_to_dict(k) for k in top_level]


# ---------------------------------------------------------------------------
# GEOB BeatGrid source detection (LIB-03)
# ---------------------------------------------------------------------------

def read_beatgrid_source(file_path: str) -> str:
    """
    Read the GEOB:Serato BeatGrid tag from file_path and return:
      'tool'   — version bytes are OUR_TOOL_VERSION_BYTES (0x01 0x01)
      'serato' — version bytes are SERATO_VERSION_BYTES (0x01 0x00) or any other value
      'none'   — no GEOB:Serato BeatGrid tag present, or read error

    Supports .mp3, .aiff, .aif, .wav. All other extensions return 'none'.
    """
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == ".mp3":
            import mutagen.id3
            tags = mutagen.id3.ID3(file_path)
        elif ext in (".aiff", ".aif"):
            import mutagen.aiff
            af = mutagen.aiff.AIFF(file_path)
            tags = af.tags
        elif ext == ".wav":
            import mutagen.wave
            wf = mutagen.wave.WAVE(file_path)
            tags = wf.tags
        else:
            return "none"

        if tags is None or "GEOB:Serato BeatGrid" not in tags:
            return "none"

        data = tags["GEOB:Serato BeatGrid"].data
        if len(data) < 2:
            return "none"

        if data[0:2] == OUR_TOOL_VERSION_BYTES:
            return "tool"
        else:
            return "serato"  # 0x01 0x00 or any other value = Serato
    except Exception:
        return "none"


# ---------------------------------------------------------------------------
# Duration reading
# ---------------------------------------------------------------------------

def _read_duration(file_path: str) -> "float | None":
    """
    Read audio duration in seconds from mutagen's info.length.
    Returns None on failure or unsupported format.
    """
    try:
        import mutagen
        audio = mutagen.File(file_path)
        if audio is not None and hasattr(audio, "info") and audio.info is not None:
            return float(audio.info.length)
        return None
    except Exception:
        return None


def _read_bpm(file_path: str) -> "float | None":
    """
    Read the BPM value from the first BeatGrid marker in the GEOB:Serato BeatGrid tag.
    Returns None if no tag is present, the tag has no markers, or reading fails.
    Supports .mp3, .aiff, .aif, .wav.
    """
    import struct

    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == ".mp3":
            import mutagen.id3
            tags = mutagen.id3.ID3(file_path)
        elif ext in (".aiff", ".aif"):
            import mutagen.aiff
            af = mutagen.aiff.AIFF(file_path)
            tags = af.tags
        elif ext == ".wav":
            import mutagen.wave
            wf = mutagen.wave.WAVE(file_path)
            tags = wf.tags
        else:
            return None

        if tags is None or "GEOB:Serato BeatGrid" not in tags:
            return None

        data = tags["GEOB:Serato BeatGrid"].data
        # BeatGrid binary layout (after 2-byte version header):
        #   4 bytes big-endian uint32 = marker count
        #   For each marker: 4 bytes float32 position_sec + 4 bytes float32 bpm
        # (Holzhaus spec — first marker bpm is the canonical display value)
        if len(data) < 2 + 4 + 4 + 4:
            return None
        offset = 2  # skip version bytes
        marker_count = struct.unpack_from(">I", data, offset)[0]
        offset += 4
        if marker_count == 0:
            return None
        # First marker: position_sec (float32) + bpm (float32)
        _position, bpm = struct.unpack_from(">ff", data, offset)
        if bpm <= 0:
            return None
        return float(bpm)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# IPC command handlers (D-05)
# ---------------------------------------------------------------------------

def list_crates() -> None:
    """
    Resolve the Serato Subcrates directory, build the crate tree, and emit:
      {"type":"crates","tree":[...]}

    Path resolution order:
      1. SERATO_SUBCRATES_DIR environment variable (for tests / overrides)
      2. ~/Music/_Serato_/Subcrates (default Serato location)

    Wraps everything in try/except to keep the worker alive on errors (T-04-DOS).
    """
    try:
        subcrates_dir_env = os.environ.get("SERATO_SUBCRATES_DIR")
        if subcrates_dir_env:
            subcrates_dir = subcrates_dir_env
        else:
            subcrates_dir = os.path.expanduser("~/Music/_Serato_/Subcrates")

        if not os.path.isdir(subcrates_dir):
            emit_json({"type": "crates", "tree": []})
            return

        tree = build_crate_tree(subcrates_dir)
        emit_json({"type": "crates", "tree": tree})
    except Exception as exc:
        emit_error("", f"list_crates failed: {exc}")


def list_tracks(crate_path: str) -> None:
    """
    Open the .crate file at crate_path, read its track list, and emit:
      {"type":"tracks","crate":"<crate_path>","tracks":[...]}

    Each track dict contains: path, filename, beatgrid_source, duration_sec.

    Security (T-04-PT): validates crate_path resolves inside the Subcrates dir
    before opening. Emits error and returns if validation fails.

    Wraps everything in try/except to keep the worker alive on errors (T-04-DOS).
    """
    try:
        from serato_tools.crate import Crate

        # T-04-PT: Input validation — crate_path must be inside the Subcrates dir
        subcrates_dir_env = os.environ.get("SERATO_SUBCRATES_DIR")
        if subcrates_dir_env:
            subcrates_dir = os.path.realpath(subcrates_dir_env)
        else:
            subcrates_dir = os.path.realpath(
                os.path.expanduser("~/Music/_Serato_/Subcrates")
            )

        resolved_path = os.path.realpath(crate_path)
        if not resolved_path.startswith(subcrates_dir + os.sep) and resolved_path != subcrates_dir:
            emit_error(
                crate_path,
                f"list_tracks: crate_path is outside the Subcrates directory (T-04-PT): {crate_path!r}",
            )
            return

        crate = Crate(crate_path)
        raw_paths = crate.tracks()  # list[str] — relative paths without leading /

        tracks = []
        for relpath in raw_paths:
            full_path = "/" + relpath.lstrip("/")  # Pitfall 3: prepend leading slash
            filename = os.path.basename(full_path)
            source = read_beatgrid_source(full_path)
            duration = _read_duration(full_path)
            bpm = _read_bpm(full_path)
            tracks.append(
                {
                    "path": full_path,
                    "filename": filename,
                    "beatgrid_source": source,
                    "duration_sec": duration,
                    "bpm": bpm,
                }
            )

        emit_json({"type": "tracks", "crate": crate_path, "tracks": tracks})
    except Exception as exc:
        emit_error(crate_path, f"list_tracks failed: {exc}")
