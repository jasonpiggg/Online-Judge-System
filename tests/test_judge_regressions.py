from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from oj.judge import judge_code
from oj.problem_store import ProblemStore
from oj.schemas import Credentials, Language, Problem, SubmissionCreate


async def test_whitespace_and_inheritance_roundtrip(
    tmp_path: Path, problem_payload: dict[str, Any]
) -> None:
    payload = {**problem_payload, "testcases": [{"input": "  x\n", "output": "  x\n"}]}
    problem = Problem.model_validate(payload)
    store = ProblemStore(tmp_path / "problems", tmp_path / "seeds")
    await store.initialize()
    await store.create(problem)
    saved = await store.get(problem.id)
    assert saved is not None
    assert saved.time_limit is None and saved.memory_limit is None
    assert saved.testcases[0].input == "  x\n"
    assert saved.testcases[0].output == "  x\n"
    language = Language(name="py", file_ext=".py", run_cmd="python {src}", time_limit=0.2)
    assert (await judge_code(saved, language, "while True: pass")).cases[0].result == "TLE"
    assert (await judge_code(saved, language, "print('x')")).cases[0].result == "WA"
    assert (await judge_code(saved, language, "print(input())")).cases[0].result == "AC"
    explicit = saved.model_copy(update={"time_limit": 3.0, "memory_limit": 128})
    await store.update(explicit)
    reloaded = await store.get(problem.id)
    assert reloaded is not None and reloaded.time_limit == 3.0
    credentials = Credentials.model_validate({"username": "alice", "password": " secret "})
    assert len(credentials.password) == 8
    submission = SubmissionCreate(problem_id="x", language="py", code="\nprint(1)\n")
    assert submission.code.startswith("\n")


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
async def test_output_flood_is_bounded(stream: str, problem_payload: dict[str, Any]) -> None:
    problem = Problem.model_validate({**problem_payload, "time_limit": 5})
    language = Language(name="py", file_ext=".py", run_cmd="python {src}")
    code = f"import sys\nwhile True: sys.{stream}.write('x' * 65536)"
    result = await asyncio.wait_for(judge_code(problem, language, code), timeout=4)
    assert {case.result for case in result.cases} == {"UNK"}


async def test_cancel_running_judge(problem_payload: dict[str, Any]) -> None:
    problem = Problem.model_validate(problem_payload)
    language = Language(name="py", file_ext=".py", run_cmd="python {src}")
    task = asyncio.create_task(judge_code(problem, language, "while True: pass"))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 3)


async def test_testcase_files_are_materialized_and_isolated(
    problem_payload: dict[str, Any],
) -> None:
    problem = Problem.model_validate(
        {
            **problem_payload,
            "testcases": [
                {
                    "input": "study.jsonl\n",
                    "output": "first\n",
                    "files": {"study.jsonl": "first\n"},
                },
                {"input": "study.jsonl\n", "output": "MISSING\n"},
            ],
        }
    )
    language = Language(name="py", file_ext=".py", run_cmd="python {src}")
    code = """\
from pathlib import Path
path = Path(input())
print(path.read_text().strip() if path.exists() else "MISSING")
"""
    result = await judge_code(problem, language, code)
    assert result.score == result.counts == 20


def test_testcase_file_names_reject_paths(problem_payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Problem.model_validate(
            {
                **problem_payload,
                "testcases": [
                    {
                        "input": "x\n",
                        "output": "x\n",
                        "files": {"../main.py": "print('injected')\n"},
                    }
                ],
            }
        )
