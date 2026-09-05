from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI

from oj.database import Database
from oj.errors import APIError
from oj.judge import judge_code
from oj.languages import command_argv, validate_language
from oj.problem_store import ProblemStore
from oj.schemas import Language, Problem


async def test_seed_loading_atomic_failure_and_missing_operations(
    tmp_path: Path, problem_payload: dict[str, Any], monkeypatch: Any
) -> None:
    seeds = tmp_path / "seeds"
    await asyncio.to_thread(seeds.mkdir)
    await asyncio.to_thread(
        (seeds / "sum_2.json").write_text, json.dumps(problem_payload), encoding="utf-8"
    )
    store = ProblemStore(tmp_path / "data", seeds)
    await store.initialize()
    await store.initialize()
    assert len(await store.list(include_metadata=True)) == 1
    with pytest.raises(APIError):
        await store.get("../outside")
    model = Problem.model_validate(problem_payload)
    assert not await store.create(model)
    assert not await store.update(model.model_copy(update={"id": "missing"}))
    assert not await store.delete("missing")

    def failed_replace(*_args: Any) -> None:
        raise OSError("disk error")

    monkeypatch.setattr("oj.problem_store.os.replace", failed_replace)
    with pytest.raises(OSError):
        await store.update(model.model_copy(update={"title": "should not be saved"}))
    assert (await store.get("sum_2")).title == model.title
    assert not await asyncio.to_thread(lambda: list(store.directory.glob(".problem-*")))
    await store.reset()
    assert (await store.get("sum_2")).title == model.title


@pytest.mark.parametrize("command", ["", "python {invalid}", "bash {src}", "python {src} | cat"])
def test_command_rejections(command: str) -> None:
    with pytest.raises(ValueError):
        command_argv(command, src="main.py", exe="main")


@pytest.mark.parametrize(
    "run,compile",
    [("python -V", None), ("python {src}", "g++ {src}"), ("python {src}", "g++ {exe}")],
)
def test_language_requires_operands(run: str, compile: str | None) -> None:
    with pytest.raises(APIError):
        validate_language(Language(name="py", file_ext=".py", run_cmd=run, compile_cmd=compile))


def test_python_uses_current_managed_interpreter() -> None:
    import sys

    assert command_argv("python {src}", src="a.py", exe="a")[0] == sys.executable


async def test_newer_schema_refused(tmp_path: Path) -> None:
    db = Database(tmp_path / "oj.db")
    await db.initialize()
    await db.execute("PRAGMA user_version=999")
    with pytest.raises(RuntimeError, match="newer"):
        await db.initialize()


async def test_submission_recovery_failure_and_cancellation(
    app: FastAPI, monkeypatch: Any, problem_payload: dict[str, Any]
) -> None:
    manager = app.state.submissions
    await manager._evaluate(999)
    sid = await manager.create(1, "missing", "python", "print(1)")
    await manager.tasks[sid]
    assert (await manager.db.fetchone("SELECT status FROM submissions WHERE id=?", (sid,)))[
        0
    ] == "error"
    await manager.db.execute("UPDATE submissions SET status='pending' WHERE id=?", (sid,))
    await manager.recover()
    await manager.tasks[sid]
    await manager.problems.create(Problem.model_validate(problem_payload))
    started = asyncio.Event()

    async def slow(*_args: Any) -> Any:
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("oj.submissions.judge_code", slow)
    sid = await manager.create(1, "sum_2", "python", "print(1)")
    await started.wait()
    manager.schedule(sid)
    await manager.cancel_one(sid)
    await manager.cancel_one(sid)
    sid = await manager.create(1, "sum_2", "python", "print(1)")
    await manager.close()  # Real five-second graceful shutdown, then cancellation.
    assert not manager.tasks
    sid = await manager.create(1, "sum_2", "python", "print(1)")
    await manager.cancel_all()
    assert not manager.tasks


@pytest.mark.parametrize("mode", ["timeout", "flood", "cancel"])
async def test_compiler_limits_and_cleanup(
    problem_payload: dict[str, Any], mode: str, monkeypatch: Any
) -> None:
    language = Language(
        name="test", file_ext=".py", compile_cmd="python3 {src} {exe}", run_cmd="python3 {src}"
    )
    problem = Problem.model_validate(problem_payload)
    if mode == "timeout":
        monkeypatch.setattr("oj.judge.COMPILE_TIMEOUT_SECONDS", 0.2)
    source = "while True: pass" if mode != "flood" else "while True: print('x'*65536)"
    task = asyncio.create_task(judge_code(problem, language, source))
    if mode == "cancel":
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        result = await asyncio.wait_for(task, 5)
        assert result.cases[0].result == "CE"
        assert (
            "timed out" in result.compile_info["message"]
            if mode == "timeout"
            else "limit" in result.compile_info["message"]
        )
