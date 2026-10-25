"""Starting and stopping the jevtester server, with a stand-in for jevtester."""

import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from ironsworn_tui import decide
from ironsworn_tui.decide import DecideError, jevtester_server
from ironsworn_tui.settings import Settings

# A stand-in for `jevtester serve`: it answers /api/targets, and starts a child process that
# lives as long as it does, like the jevtester process that `uv run` starts.
FAKE_SERVER = """
import json, os, subprocess, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
open(sys.argv[2], "w").write(str(child.pid))

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"targets": []}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

HTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
"""


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        jevtester_project=tmp_path,
        target="decision-1@foundry",
        campaigns_dir=tmp_path / "campaigns",
        jevtester_config=tmp_path / "jevtester.toml",
    )


def _use_command(monkeypatch: pytest.MonkeyPatch, make: Callable[[int], list[str]]) -> None:
    """Replace the serve command with one built from the port."""

    def command(settings: Settings, port: int) -> list[str]:
        return make(port)

    monkeypatch.setattr(decide, "serve_command", command)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_server_starts_and_its_whole_process_group_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    script = tmp_path / "fake_server.py"
    script.write_text(FAKE_SERVER)
    child_pid_file = tmp_path / "child.pid"
    _use_command(
        monkeypatch, lambda port: [sys.executable, str(script), str(port), str(child_pid_file)]
    )
    with jevtester_server(_settings(tmp_path)) as client:
        assert client.base_url.startswith("http://127.0.0.1:")
        child_pid = int(child_pid_file.read_text())
        assert _alive(child_pid)
    deadline = time.monotonic() + 5
    while _alive(child_pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not _alive(child_pid)


def test_server_that_exits_reports_its_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _use_command(
        monkeypatch,
        lambda port: [sys.executable, "-c", "print('config is broken'); raise SystemExit(2)"],
    )
    with (
        pytest.raises(DecideError, match="config is broken"),
        jevtester_server(_settings(tmp_path)),
    ):
        pass


def test_missing_command_raises_decide_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _use_command(monkeypatch, lambda port: [str(tmp_path / "nope")])
    with pytest.raises(DecideError, match="can't start"), jevtester_server(_settings(tmp_path)):
        pass
