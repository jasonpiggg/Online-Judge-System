from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import launch


@pytest.fixture
def runtime(tmp_path: Path, monkeypatch: Any) -> Path:
    monkeypatch.setattr(launch, "RUNTIME", tmp_path)
    monkeypatch.setattr(launch, "STATE", tmp_path / "processes.json")
    return tmp_path


def test_state_roundtrip_and_invalid_state(runtime: Path) -> None:
    assert launch.read_state() == {}
    launch.save_state({"backend": {"pid": 123}})
    assert launch.read_state() == {"backend": {"pid": 123}}
    launch.save_state({})
    launch.STATE.write_text("[]", encoding="utf-8")
    with pytest.raises(RuntimeError, match="No processes were stopped"):
        launch.read_state()
    assert not list(runtime.glob("*.tmp"))


@pytest.mark.parametrize("mismatch", ["none", "timestamp", "cwd", "command", "exe", "nan"])
def test_process_identity_prevents_pid_reuse(monkeypatch: Any, mismatch: str) -> None:
    proc = SimpleNamespace(
        create_time=lambda: 123.0,
        cwd=lambda: str(launch.ROOT if mismatch != "cwd" else launch.ROOT.parent),
        cmdline=lambda: [
            "python",
            *(launch.SERVICES["backend"][2] if mismatch != "command" else []),
        ],
        exe=lambda: "python.exe" if mismatch != "exe" else "other.exe",
    )
    monkeypatch.setattr(launch.psutil, "Process", lambda _pid: proc)
    created = 456.0 if mismatch == "timestamp" else float("nan") if mismatch == "nan" else 123.0
    record = {"pid": 123, "created": created, "executable": "python.exe"}
    assert (launch.owned_process("backend", record) is proc) == (mismatch == "none")
    assert launch.owned_process("backend", {}) is None


def test_duplicate_start_reuses_services(runtime: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(launch, "owned_process", lambda *_: SimpleNamespace(pid=123))
    monkeypatch.setattr(launch, "healthy", lambda _: True)
    monkeypatch.setattr(
        launch.subprocess, "Popen", lambda *_a, **_k: pytest.fail("duplicate process")
    )
    launch.start_services({"backend": {}, "frontend": {}}, timeout=1)


def test_foreign_port_never_kills_process(runtime: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(launch, "owned_process", lambda *_: None)
    monkeypatch.setattr(launch, "port_busy", lambda _: True)
    monkeypatch.setattr(launch, "stop_owned", lambda *_: pytest.fail("unowned process stopped"))
    with pytest.raises(RuntimeError, match="8000.*unmanaged"):
        launch.start_services({}, timeout=1)


def test_failed_frontend_preserves_existing_backend(runtime: Path, monkeypatch: Any) -> None:
    state = {"backend": {"pid": 123}}
    monkeypatch.setattr(
        launch,
        "owned_process",
        lambda role, _: SimpleNamespace(pid=123) if role == "backend" else None,
    )
    monkeypatch.setattr(launch, "healthy", lambda _: True)
    monkeypatch.setattr(launch, "port_busy", lambda _: True)
    monkeypatch.setattr(launch, "stop_owned", lambda *_: pytest.fail("existing service stopped"))
    with pytest.raises(RuntimeError, match="8501.*unmanaged"):
        launch.start_services(state, timeout=1)
    assert launch.read_state() == state


def test_lock_released_after_error(runtime: Path) -> None:
    with pytest.raises(ValueError), launch.launch_lock(timeout=1):
        raise ValueError("test")
    with launch.launch_lock(timeout=1):
        launch.save_state({})
    assert json.loads(launch.STATE.read_text(encoding="utf-8")) == {}
