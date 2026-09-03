from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

from oj.languages import command_argv
from oj.schemas import Language, Problem, TestCase

MAX_OUTPUT_BYTES = 1_000_000


@dataclass(frozen=True)
class CaseResult:
    id: int
    result: str
    time: float
    memory: float
    message: str = ""


@dataclass(frozen=True)
class JudgeOutcome:
    cases: list[CaseResult]
    score: int
    counts: int
    compile_info: dict[str, str] | None
    run_info: dict[str, str]
    error_info: str


def normalize_output(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in normalized.split("\n")).rstrip("\n")


def _preexec(memory_mb: int) -> Any:
    def limit() -> None:
        import resource

        memory_bytes = memory_mb * 1024 * 1024
        set_limit = getattr(resource, "setrlimit")  # noqa: B009 - portable type checking
        set_limit(getattr(resource, "RLIMIT_AS"), (memory_bytes, memory_bytes))  # noqa: B009
        set_limit(getattr(resource, "RLIMIT_CORE"), (0, 0))  # noqa: B009
        set_limit(  # noqa: B009
            getattr(resource, "RLIMIT_FSIZE"),  # noqa: B009
            (MAX_OUTPUT_BYTES, MAX_OUTPUT_BYTES),
        )
        set_limit(getattr(resource, "RLIMIT_NPROC"), (32, 32))  # noqa: B009

    return limit


async def _kill_process(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        if os.name == "posix":
            getattr(os, "killpg")(  # noqa: B009 - unavailable in Windows type stubs
                proc.pid, getattr(signal, "SIGKILL")  # noqa: B009
            )
        else:
            proc.kill()
    with contextlib.suppress(Exception):
        await proc.wait()


async def _peak_memory(proc: asyncio.subprocess.Process, limit_mb: int) -> tuple[float, bool]:
    peak = 0.0
    exceeded = False
    try:
        process = psutil.Process(proc.pid)
        while proc.returncode is None:
            with contextlib.suppress(psutil.Error):
                rss = process.memory_info().rss
                rss += sum(child.memory_info().rss for child in process.children(recursive=True))
                peak = max(peak, rss / 1024 / 1024)
                if peak > limit_mb:
                    exceeded = True
                    await _kill_process(proc)
                    break
            await asyncio.sleep(0.02)
    except psutil.Error:
        pass
    return peak, exceeded


def _process_options(memory_mb: int) -> dict[str, Any]:
    options: dict[str, Any] = {"start_new_session": True}
    if os.name == "posix":
        options["preexec_fn"] = _preexec(memory_mb)
    else:
        options.pop("start_new_session")
        options["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
    return options


async def _run_case(
    argv: list[str], testcase: TestCase, time_limit: float, memory_limit: int, case_id: int
) -> CaseResult:
    started = time.perf_counter()
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={"PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8"},
        **_process_options(memory_limit),
    )
    monitor = asyncio.create_task(_peak_memory(proc, memory_limit))
    timed_out = False
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(testcase.input.encode()), timeout=time_limit
        )
    except asyncio.CancelledError:
        await _kill_process(proc)
        await monitor
        raise
    except TimeoutError:
        timed_out = True
        await _kill_process(proc)
        stdout, stderr = b"", b""
    peak, memory_exceeded = await monitor
    elapsed = time.perf_counter() - started
    message = stderr.decode(errors="replace")[:4000]
    if timed_out:
        result = "TLE"
    elif memory_exceeded or "MemoryError" in message or "bad_alloc" in message:
        result = "MLE"
    elif proc.returncode != 0:
        result = "RE"
    elif len(stdout) > MAX_OUTPUT_BYTES:
        result, message = "UNK", "output limit exceeded"
    elif normalize_output(stdout.decode(errors="replace")) == normalize_output(testcase.output):
        result = "AC"
    else:
        result = "WA"
    return CaseResult(case_id, result, round(elapsed, 4), round(peak, 3), message)


async def judge_code(problem: Problem, language: Language, code: str) -> JudgeOutcome:
    with tempfile.TemporaryDirectory(prefix="atelier-oj-") as temp:
        directory = Path(temp)
        source = directory / f"main{language.file_ext}"
        executable = directory / ("program.exe" if os.name == "nt" else "program")
        await asyncio.to_thread(source.write_text, code, encoding="utf-8")
        compile_info: dict[str, str] | None = None
        if language.compile_cmd:
            argv = command_argv(language.compile_cmd, src=str(source), exe=str(executable))
            try:
                process = await asyncio.create_subprocess_exec(
                    *argv,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    **_process_options(512),
                )
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
            except TimeoutError:
                await _kill_process(process)
                return JudgeOutcome(
                    [CaseResult(1, "CE", 15, 0, "compilation timed out")],
                    0,
                    len(problem.testcases) * 10,
                    {"result": "error", "message": "compilation timed out"},
                    {"result": "not_started", "message": ""},
                    "",
                )
            compiler_message = (stderr or stdout).decode(errors="replace")[:8000]
            if process.returncode != 0:
                return JudgeOutcome(
                    [CaseResult(1, "CE", 0, 0, compiler_message)],
                    0,
                    len(problem.testcases) * 10,
                    {"result": "error", "message": compiler_message},
                    {"result": "not_started", "message": ""},
                    "",
                )
            compile_info = {"result": "success", "message": compiler_message}

        argv = command_argv(language.run_cmd, src=str(source), exe=str(executable))
        time_limit = problem.time_limit or language.time_limit or 3.0
        memory_limit = problem.memory_limit or language.memory_limit or 128
        cases = [
            await _run_case(argv, testcase, time_limit, memory_limit, index)
            for index, testcase in enumerate(problem.testcases, start=1)
        ]
        score = sum(10 for case in cases if case.result == "AC")
        return JudgeOutcome(
            cases,
            score,
            len(cases) * 10,
            compile_info,
            {"result": "finished", "message": f"{len(cases)} test cases finished"},
            "",
        )
