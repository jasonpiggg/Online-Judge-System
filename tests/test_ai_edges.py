from __future__ import annotations

import json
import socket
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from oj.ai_authoring import _is_private_host, validate_provider_url
from oj.schemas import GeneratedProblem, Problem
from tests.test_ai_http import configure, finish, generated  # noqa: F401 - shared fixture


async def test_provider_validation_errors(monkeypatch: Any) -> None:
    for url in ["https://public.example/v1?key=x", "https://public.example/#frag", "ftp://x"]:
        with pytest.raises(ValueError):
            await validate_provider_url(url, True)
    monkeypatch.setattr(
        "oj.ai_authoring.socket.getaddrinfo", lambda *_: [(2, 1, 6, "", ("127.0.0.1", 0))]
    )
    with pytest.raises(ValueError, match="private"):
        await validate_provider_url("https://a.example", False)
    monkeypatch.setattr(
        "oj.ai_authoring.socket.getaddrinfo", lambda *_: [(2, 1, 6, "", ("93.184.216.34", 0))]
    )
    assert await validate_provider_url("https://a.example/", False) == "https://a.example"

    def failed(*_: Any) -> Any:
        raise socket.gaierror()

    monkeypatch.setattr("oj.ai_authoring.socket.getaddrinfo", failed)
    assert _is_private_host("no.example")


@pytest.mark.parametrize(
    "mode", ["schema", "missing_language", "status", "missing_config", "reference"]
)
async def test_authoring_diagnostic_edges(
    app: FastAPI, generated: dict[str, Any], monkeypatch: Any, mode: str  # noqa: F811
) -> None:
    manager = app.state.ai_authoring
    await manager._author("missing-task")
    await configure(manager, "http://127.0.0.1:1234/v1")
    if mode == "missing_config":
        await manager.db.execute("DELETE FROM ai_configs")
    if mode == "schema":
        generated["problem"]["testcases"] = []
    if mode == "missing_language":
        await manager.db.execute("DELETE FROM languages WHERE name='python'")
    if mode == "reference":
        await manager.problems.create(Problem.model_validate(generated["problem"]))
    prompts = []

    async def stream(_config: Any, prompt: str, _usage: Any) -> Any:
        prompts.append(prompt)
        if mode == "status":
            request = httpx.Request("POST", "https://a.example/v1")
            raise httpx.HTTPStatusError(
                "private upstream body",
                request=request,
                response=httpx.Response(401, request=request),
            )
        return json.dumps(generated), 10, 20, "provider"

    monkeypatch.setattr(manager, "_stream_completion", stream)
    task_id = await manager.create(
        1, "检查边界条件和诊断脱敏", generated["problem"]["id"] if mode == "reference" else None
    )
    row = await finish(manager, task_id)
    assert row["status"] == ("completed" if mode == "reference" else "failed")
    assert "private upstream" not in (row["error"] or "")
    if mode == "reference":
        assert "Existing problem" in prompts[0]


def test_duplicate_wrong_algorithms_rejected(generated: dict[str, Any]) -> None:  # noqa: F811
    generated["wrong_solutions"][1] = generated["wrong_solutions"][0]
    with pytest.raises(ValidationError, match="互不重复"):
        GeneratedProblem.model_validate(generated)
