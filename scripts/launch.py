"""Start/stop this checkout's local OJ services without keeping terminals open."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psutil

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "var" / "launcher"
STATE = RUNTIME / "processes.json"
URL = "http://127.0.0.1:8501"
SERVICES = {
    "backend": (
        8000,
        "/health",
        [
            "-m",
            "uvicorn",
            "oj.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
    ),
    "frontend": (
        8501,
        "/_stcore/health",
        [
            "-m",
            "streamlit",
            "run",
            "frontend/app.py",
            "--server.address",
            "127.0.0.1",
            "--server.port",
            "8501",
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ],
    ),
}


@contextlib.contextmanager
def launch_lock(timeout: float = 120) -> Iterator[None]:
    """Serialize simultaneous double clicks and stop requests across processes."""
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with (RUNTIME / "launcher.lock").open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + timeout
        while True:
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Another launcher is busy. Try again shortly.") from None
                time.sleep(0.2)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_state() -> dict[str, Any]:
    if not STATE.exists():
        return {}
    try:
        value = json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, OSError):
        raise RuntimeError(
            f"Cannot read launcher state: {STATE}. No processes were stopped."
        ) from None


def save_state(state: dict[str, Any]) -> None:
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(STATE)


def owned_process(role: str, record: Any) -> psutil.Process | None:
    """PID alone is unsafe after reboot/reuse. Verify timestamp, command and checkout."""
    if not isinstance(record, dict):
        return None
    try:
        proc = psutil.Process(int(record["pid"]))
        if not abs(proc.create_time() - float(record["created"])) <= 0.01:
            return None
        if Path(proc.cwd()).resolve() != ROOT:
            return None
        if proc.cmdline()[1:] != SERVICES[role][2]:
            return None
        if os.path.normcase(proc.exe()) != os.path.normcase(record["executable"]):
            return None
        return proc
    except (psutil.Error, KeyError, ValueError, TypeError, OSError):
        return None


def healthy(role: str) -> bool:
    port, path, _ = SERVICES[role]
    # Loopback checks must not use system proxy settings.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}{path}", timeout=2) as response:  # noqa: S310
            data = response.read(4096)
            if response.status != 200:
                return False
            return json.loads(data).get("status") == "ok" if role == "backend" else data == b"ok"
    except (OSError, ValueError, urllib.error.URLError):
        return False


def port_busy(port: int) -> bool:
    with socket.socket() as sock:
        try:
            if os.name == "nt":
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


def stop_owned(role: str, record: Any) -> None:
    proc = owned_process(role, record)
    if proc is None:
        return
    # Includes the Windows venv redirector's child and active judge subprocesses.
    family = [*proc.children(recursive=True), proc]
    for member in reversed(family):
        with contextlib.suppress(psutil.NoSuchProcess):
            member.terminate()
    _, alive = psutil.wait_procs(family, timeout=5)
    for member in alive:
        with contextlib.suppress(psutil.NoSuchProcess):
            member.kill()
    psutil.wait_procs(alive, timeout=3)


def start_services(state: dict[str, Any], timeout: float) -> None:
    launched: list[str] = []
    try:
        for role, (port, _, arguments) in SERVICES.items():
            proc = owned_process(role, state.get(role))
            if proc is None:
                if port_busy(port):
                    raise RuntimeError(
                        f"Port {port} is occupied by an unmanaged program. "
                        "Close the earlier manual service or conflicting program and retry."
                    )
                env = os.environ.copy()
                env["PYTHONPATH"] = os.pathsep.join(
                    [str(ROOT / "src"), str(ROOT), env.get("PYTHONPATH", "")]
                )
                env["OJ_API_URL"] = "http://127.0.0.1:8000"
                env["PYTHONUNBUFFERED"] = "1"
                env["PYTHONIOENCODING"] = "utf-8"
                options: dict[str, Any] = {}
                if os.name == "nt":
                    options["creationflags"] = subprocess.CREATE_NO_WINDOW
                else:
                    options["start_new_session"] = True
                with (RUNTIME / f"{role}.log").open("ab") as log:
                    child = subprocess.Popen(  # noqa: S603 - fixed executable/module arguments
                        [sys.executable, *arguments],
                        cwd=ROOT,
                        env=env,
                        stdin=subprocess.DEVNULL,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        **options,
                    )
                proc = psutil.Process(child.pid)
                state[role] = {
                    "pid": proc.pid,
                    "created": proc.create_time(),
                    "executable": proc.exe(),
                }
                launched.append(role)
                save_state(state)
            deadline = time.monotonic() + timeout
            while not healthy(role):
                if owned_process(role, state.get(role)) is None or time.monotonic() > deadline:
                    raise RuntimeError(
                        f"{role} did not become ready. See {RUNTIME / f'{role}.log'}"
                    )
                time.sleep(0.3)
            print(f"{role}: ready (PID {proc.pid}, port {port})", flush=True)
    except BaseException:
        # Roll back only processes created by this invocation; preserve existing services.
        for role in reversed(launched):
            stop_owned(role, state.get(role))
            state.pop(role, None)
        save_state(state)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop", "status"], nargs="?", default="start")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--timeout", type=float, default=45)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 120:
        parser.error("--timeout must be between 1 and 120 seconds")
    try:
        with launch_lock():
            state = read_state()
            if args.action == "start":
                start_services(state, args.timeout)
            elif args.action == "stop":
                for role in reversed(SERVICES):
                    stop_owned(role, state.get(role))
                save_state({})
                print("OJ stopped. Closing tasks may be interrupted; saved data is retained.")
            else:
                for role in SERVICES:
                    running = owned_process(role, state.get(role)) is not None and healthy(role)
                    print(f"{role}: {'ready' if running else 'not running / not ready'}")
        if args.action == "start":
            print(f"OJ is ready: {URL}")
            if not args.no_browser and not webbrowser.open(URL):
                print(f"Could not open the browser automatically. Open {URL} manually.")
        return 0
    except (RuntimeError, OSError, psutil.Error) as exc:
        print(f"Launcher error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
