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

from oj.evaluation import POINTS_PER_CASE
from oj.languages import command_argv
from oj.schemas import Language, Problem, TestCase

MAX_OUTPUT_BYTES = 1_000_000
MAX_PROCESS_COUNT = 32
COMPILE_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class CaseResult:
    id: int
    result: str
    time: float
    memory: float
    message: str = ""
    output: str = ""


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

    return limit


def _terminate_group(proc: asyncio.subprocess.Process) -> None:
    # Kill the group even when its leader exited, otherwise inherited pipes may stay open.
    with contextlib.suppress(ProcessLookupError):
        if os.name == "posix":
            getattr(os, "killpg")(  # noqa: B009 - unavailable in Windows type stubs
                proc.pid,
                getattr(signal, "SIGKILL"),  # noqa: B009
            )
        else:
            with contextlib.suppress(psutil.Error):
                for child in psutil.Process(proc.pid).children(recursive=True):
                    with contextlib.suppress(psutil.Error):
                        child.kill()
            if proc.returncode is None:
                proc.kill()


async def _kill_process(proc: asyncio.subprocess.Process) -> None:
    _terminate_group(proc)
    with contextlib.suppress(Exception):
        await proc.wait()


async def _communicate_bounded(
    proc: asyncio.subprocess.Process, input_data: bytes = b""
) -> tuple[bytes, bytes, bool]:
    exceeded = False

    async def read(stream: asyncio.StreamReader | None) -> bytes:
        nonlocal exceeded
        data = bytearray()
        if stream is None:
            return b""
        while chunk := await stream.read(65536):
            room = MAX_OUTPUT_BYTES - len(data)
            data.extend(chunk[:room])
            if len(chunk) > room:
                exceeded = True
                _terminate_group(proc)
                # Keep draining after SIGKILL so transport.wait_closed cannot deadlock.
        return bytes(data)

    async def write() -> None:
        if proc.stdin:
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                proc.stdin.write(input_data)
                await proc.stdin.drain()
                proc.stdin.close()
                await proc.stdin.wait_closed()

    stdout_task = asyncio.create_task(read(proc.stdout))
    stderr_task = asyncio.create_task(read(proc.stderr))
    stdin_task = asyncio.create_task(write())
    group = asyncio.gather(stdout_task, stderr_task, stdin_task)
    try:
        await asyncio.shield(group)
        await proc.wait()
    except asyncio.CancelledError:
        _terminate_group(proc)
        await group
        await proc.wait()
        raise
    finally:
        _terminate_group(proc)
    return stdout_task.result(), stderr_task.result(), exceeded


async def _peak_memory(proc: asyncio.subprocess.Process, limit_mb: int) -> tuple[float, bool, bool]:
    peak = 0.0
    memory_exceeded = False
    process_exceeded = False
    try:
        process = psutil.Process(proc.pid)
        while proc.returncode is None:
            with contextlib.suppress(psutil.Error):
                children = process.children(recursive=True)
                rss = process.memory_info().rss
                rss += sum(child.memory_info().rss for child in children)
                peak = max(peak, rss / 1024 / 1024)
                if peak > limit_mb:
                    memory_exceeded = True
                    await _kill_process(proc)
                    break
                if len(children) + 1 > MAX_PROCESS_COUNT:
                    process_exceeded = True
                    await _kill_process(proc)
                    break
            await asyncio.sleep(0.02)
    except psutil.Error:
        pass
    return peak, memory_exceeded, process_exceeded


def _process_options(memory_mb: int) -> dict[str, Any]:
    options: dict[str, Any] = {"start_new_session": True}
    if os.name == "posix":
        options["preexec_fn"] = _preexec(memory_mb)
    else:
        options.pop("start_new_session")
        options["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
    return options


async def _run_case(
    argv: list[str],
    testcase: TestCase,
    time_limit: float,
    memory_limit: int,
    case_id: int,
    directory: Path | None = None,
) -> CaseResult:
    started = time.perf_counter()
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={"PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8"},
        cwd=directory,
        **_process_options(memory_limit),
    )
    monitor = asyncio.create_task(_peak_memory(proc, memory_limit))
    timed_out = False
    try:
        stdout, stderr, output_exceeded = await asyncio.wait_for(
            _communicate_bounded(proc, testcase.input.encode()), timeout=time_limit
        )
    except asyncio.CancelledError:
        await _kill_process(proc)
        await monitor
        raise
    except TimeoutError:
        timed_out = True
        await _kill_process(proc)
        stdout, stderr = b"", b""
        output_exceeded = False
    peak, memory_exceeded, process_exceeded = await monitor
    elapsed = time.perf_counter() - started
    message = stderr.decode(errors="replace")[:4000]
    if directory:
        message = message.replace(str(directory), "<workspace>")
    actual_output = stdout.decode(errors="replace") if not timed_out else ""
    if timed_out:
        result = "TLE"
    elif output_exceeded:
        result, message = "UNK", "output limit exceeded"
    elif memory_exceeded or "MemoryError" in message or "bad_alloc" in message:
        result = "MLE"
    elif process_exceeded:
        result, message = "RE", "process limit exceeded"
    elif proc.returncode != 0:
        result = "RE"
    elif normalize_output(actual_output) == normalize_output(testcase.output):
        result = "AC"
    else:
        result = "WA"
    return CaseResult(
        case_id,
        result,
        round(elapsed, 4),
        round(peak, 3),
        message,
        actual_output,
    )


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
                    env={"PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8"},
                    cwd=directory,
                    **_process_options(512),
                )
                stdout, stderr, output_exceeded = await asyncio.wait_for(
                    _communicate_bounded(process), timeout=COMPILE_TIMEOUT_SECONDS
                )
            except TimeoutError:
                await _kill_process(process)
                message = f"compilation timed out after {COMPILE_TIMEOUT_SECONDS} seconds"
                return JudgeOutcome(
                    [CaseResult(1, "CE", COMPILE_TIMEOUT_SECONDS, 0, message)],
                    0,
                    len(problem.testcases) * POINTS_PER_CASE,
                    {"result": "error", "message": message},
                    {"result": "not_started", "message": ""},
                    "",
                )
            compiler_message = (stderr or stdout).decode(errors="replace")[:8000]
            compiler_message = compiler_message.replace(str(directory), "<workspace>")
            if output_exceeded:
                compiler_message = "compiler output limit exceeded"
            if process.returncode != 0 or output_exceeded:
                return JudgeOutcome(
                    [CaseResult(1, "CE", 0, 0, compiler_message)],
                    0,
                    len(problem.testcases) * POINTS_PER_CASE,
                    {"result": "error", "message": compiler_message},
                    {"result": "not_started", "message": ""},
                    "",
                )
            compile_info = {"result": "success", "message": compiler_message}

        argv = command_argv(language.run_cmd, src=str(source), exe=str(executable))
        time_limit = problem.time_limit or language.time_limit or 3.0
        memory_limit = problem.memory_limit or language.memory_limit or 128
        cases = [
            await _run_case(argv, testcase, time_limit, memory_limit, index, directory)
            for index, testcase in enumerate(problem.testcases, start=1)
        ]
        score = sum(POINTS_PER_CASE for case in cases if case.result == "AC")
        return JudgeOutcome(
            cases,
            score,
            len(cases) * POINTS_PER_CASE,
            compile_info,
            {"result": "finished", "message": f"{len(cases)} test cases finished"},
            "",
        )
