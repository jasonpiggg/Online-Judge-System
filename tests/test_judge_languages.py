from __future__ import annotations

import shutil

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from oj.errors import APIError
from oj.judge import judge_code, normalize_output
from oj.languages import command_argv, get_language, validate_language
from oj.schemas import Language, Problem
from tests.conftest import login_admin


def test_output_normalization() -> None:
    assert normalize_output("3  \r\n\r\n") == "3"
    assert normalize_output("1 \n2\n") == "1\n2"


def test_command_security() -> None:
    source, executable = "/workspace/a.py", "/workspace/a"
    assert command_argv("python3 {src}", src=source, exe=executable)[1] == source
    with pytest.raises(ValueError):
        command_argv("python3 {src}; rm -rf /", src=source, exe=executable)
    with pytest.raises(APIError):
        validate_language(Language(name="bad", file_ext=".x", run_cmd="bash {src}"))


async def test_language_api(client: AsyncClient, app: FastAPI) -> None:
    listing = await client.get("/api/languages/")
    assert listing.json()["data"]["name"] == ["cpp", "python"]
    assert (await client.post("/api/languages/", json={})).status_code == 401
    await login_admin(client)
    payload = {
        "name": "python_alt",
        "file_ext": ".py",
        "run_cmd": "python3 {src}",
        "time_limit": 2,
        "memory_limit": 128,
    }
    assert (await client.post("/api/languages/", json=payload)).status_code == 200
    assert (await client.post("/api/languages/", json=payload)).status_code == 409
    assert await get_language(app.state.db, "python_alt") is not None


async def test_python_judge(problem_payload: dict[str, object]) -> None:
    problem = Problem.model_validate(problem_payload)
    language = Language(name="py", file_ext=".py", run_cmd="python {src}")
    accepted = await judge_code(problem, language, "a,b=map(int,input().split())\nprint(a+b)")
    assert accepted.score == accepted.counts == 20
    wrong = await judge_code(problem, language, "print(0)")
    assert {case.result for case in wrong.cases} == {"WA"}
    runtime = await judge_code(problem, language, "raise RuntimeError('x')")
    assert {case.result for case in runtime.cases} == {"RE"}


@pytest.mark.skipif(shutil.which("g++") is None, reason="C++ compiler required")
async def test_cpp_compiler_temporary_directory(problem_payload: dict[str, object]) -> None:
    problem = Problem.model_validate(problem_payload)
    language = Language(
        name="cpp",
        file_ext=".cpp",
        compile_cmd="g++ {src} -O2 -std=c++14 -o {exe}",
        run_cmd="{exe}",
    )
    accepted = await judge_code(
        problem,
        language,
        "#include <iostream>\nint main(){int a,b;std::cin>>a>>b;std::cout<<a+b;}",
    )
    assert accepted.compile_info is not None
    assert accepted.compile_info["result"] == "success", accepted.compile_info
    assert accepted.score == accepted.counts == 20
    failed = await judge_code(problem, language, "int main( { return 0; }")
    assert failed.cases[0].result == "CE"
    assert failed.compile_info is not None
    assert failed.compile_info["message"]
