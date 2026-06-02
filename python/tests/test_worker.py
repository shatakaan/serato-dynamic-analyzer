"""
pytest worker mode tests for analyze.py — Plan 02-01 TDD RED.

Tests cover:
  Test 1 (ready signal): launch analyze.py --worker via subprocess; first stdout
          line must be parseable JSON with type == "ready".
  Test 2 (processes request): after ready signal, send one JSON-Lines request;
          assert at least one JSONL event (progress / error / result) is emitted.
  Test 3 (loops on multiple requests): send two requests sequentially; assert two
          separate response events are received.

Tests are in RED state — failing because --worker flag is not yet implemented in analyze.py.
"""
import json
import subprocess
import sys
from pathlib import Path

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
# TestWorkerMode
# ---------------------------------------------------------------------------

class TestWorkerMode:
    """Tests for analyze.py --worker persistent mode (Plan 02-01 RED → 02-02 GREEN)."""

    def test_worker_emits_ready_signal(self):
        """Launch with --worker; first stdout line must be {type: ready}."""
        proc = subprocess.Popen(
            [PYTHON_EXE, '-u', str(ANALYZE_SCRIPT), '--worker'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            first_line = proc.stdout.readline().strip()
        finally:
            proc.terminate()
            proc.wait()

        assert first_line, "No output received from --worker subprocess"
        event = json.loads(first_line)
        assert event["type"] == "ready"

    def test_worker_processes_request_and_emits_event(self, tmp_path):
        """After ready signal, send one request; assert at least one JSONL event is emitted."""
        proc = subprocess.Popen(
            [PYTHON_EXE, '-u', str(ANALYZE_SCRIPT), '--worker'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            # Consume ready signal
            proc.stdout.readline()
            # Send a request for a non-existent file — will emit an error event
            req = json.dumps({"file": "/nonexistent.mp3", "bpm_min": 60, "bpm_max": 200}) + "\n"
            proc.stdin.write(req)
            proc.stdin.flush()
            response_line = proc.stdout.readline().strip()
        finally:
            proc.terminate()
            proc.wait()

        assert response_line, "No response event received for request"
        event = json.loads(response_line)
        assert event["type"] in ("progress", "error", "result"), (
            f"Unexpected event type: {event['type']!r}"
        )

    def test_worker_loops_on_multiple_requests(self, tmp_path):
        """Send two requests sequentially; assert two separate final-events are received."""
        proc = subprocess.Popen(
            [PYTHON_EXE, '-u', str(ANALYZE_SCRIPT), '--worker'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            # Consume ready signal
            proc.stdout.readline()
            responses = []
            for _ in range(2):
                req = json.dumps({"file": "/nonexistent.mp3", "bpm_min": 60, "bpm_max": 200}) + "\n"
                proc.stdin.write(req)
                proc.stdin.flush()
                # Drain events for this request until we get a terminal event (error or result)
                while True:
                    line = proc.stdout.readline().strip()
                    if not line:
                        break
                    event = json.loads(line)
                    if event["type"] in ("error", "result"):
                        responses.append(event)
                        break
        finally:
            proc.terminate()
            proc.wait()

        assert len(responses) == 2, (
            f"Expected 2 terminal events, got {len(responses)}: {responses}"
        )
