from __future__ import annotations

import os

import pytest
from fastapi import FastAPI

from oj.judge import judge_code
from oj.languages import get_language
from oj.schemas import Problem

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.name != "posix", reason="Linux resource limits required"),
]


async def test_linux_python_tle(app: FastAPI, problem_payload: dict[str, object]) -> None:
    problem = Problem.model_validate({**problem_payload, "time_limit": 0.1})
    language = await get_language(app.state.db, "python")
    assert language is not None
    result = await judge_code(problem, language, "while True: pass")
    assert {case.result for case in result.cases} == {"TLE"}


async def test_linux_cpp_accept_and_compile_error(
    app: FastAPI, problem_payload: dict[str, object]
) -> None:
    problem = Problem.model_validate(problem_payload)
    language = await get_language(app.state.db, "cpp")
    assert language is not None
    accepted = await judge_code(
        problem,
        language,
        "#include <iostream>\nint main(){long long a,b;std::cin>>a>>b;std::cout<<a+b;}",
    )
    assert accepted.score == accepted.counts
    failed = await judge_code(problem, language, "int main( { return 0; }")
    assert failed.compile_info is not None
    assert failed.compile_info["result"] == "error"
    assert failed.cases[0].result == "CE"

