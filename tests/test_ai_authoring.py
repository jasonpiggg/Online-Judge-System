from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

import oj.ai_authoring as ai_module
from oj.ai_authoring import calculate_cost, validate_provider_url
from oj.config import Settings
from tests.conftest import login_admin


def test_cost_calculation() -> None:
    assert calculate_cost(1_000, 500, 2.0, 4.0, 1_000) == 4.0


async def test_provider_url_and_generated_local_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        await validate_provider_url("http://example.com/v1", False)
    with pytest.raises(ValueError, match="credentials"):
        await validate_provider_url("https://user:pass@example.com/v1", False)
    settings = Settings(database_path=tmp_path / "oj.db")
    first = ai_module._key(settings)
    assert first == ai_module._key(settings)
    assert ai_module._extract_json('```json\n{"ok": true}\n```') == {"ok": True}


async def test_stream_parser_uses_provider_usage(app: FastAPI, monkeypatch: Any) -> None:
    class FakeResponse:
        async def __aenter__(self) -> FakeResponse:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        async def aiter_lines(self) -> Any:
            yield 'data: {"choices":[{"delta":{"content":"{\\"ok\\":"}}]}'
            yield (
                'data: {"choices":[{"delta":{"content":"true}"}}],'
                '"usage":{"prompt_tokens":7,"completion_tokens":3}}'
            )
            yield "data: [DONE]"

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def stream(self, *_args: object, **_kwargs: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(ai_module.httpx, "AsyncClient", FakeClient)
    encrypted = app.state.ai_authoring.cipher.encrypt(b"key")
    parsed = await app.state.ai_authoring._stream_completion(
        {"encrypted_api_key": encrypted, "provider_url": "https://example.com/v1", "model": "mock"},
        "prompt",
    )
    text, prompt_tokens, completion_tokens, source = parsed
    assert text == '{"ok":true}'
    assert (prompt_tokens, completion_tokens, source) == (7, 3, "provider")


async def test_config_is_encrypted_and_not_returned(
    client: AsyncClient, app: FastAPI
) -> None:
    await login_admin(client)
    config = {
        "provider_url": "http://127.0.0.1:9999/v1",
        "model": "mock-model",
        "api_key": "super-secret-key",
        "input_price": 1,
        "output_price": 2,
        "price_unit": 1000,
    }
    result = await client.put("/api/ai/model-config", json=config)
    assert result.status_code == 200
    assert "super-secret-key" not in result.text
    row = await app.state.db.fetchone("SELECT encrypted_api_key FROM ai_configs WHERE user_id=1")
    assert b"super-secret-key" not in row["encrypted_api_key"]


async def test_task_cancel_is_real(client: AsyncClient, app: FastAPI) -> None:
    await login_admin(client)
    await client.put(
        "/api/ai/model-config",
        json={
            "provider_url": "http://127.0.0.1:9999/v1",
            "model": "mock-model",
            "api_key": "key",
        },
    )

    async def slow_stream(_config: object, _prompt: str) -> tuple[str, int, int, str]:
        await asyncio.sleep(30)
        return "{}", 0, 0, "estimated"

    app.state.ai_authoring._stream_completion = slow_stream
    created = await client.post(
        "/api/ai/problem-tasks/",
        json={"requirement": "创建一道用于测试取消行为的简单求和题目"},
    )
    task_id = created.json()["data"]["task_id"]
    await asyncio.sleep(0.03)
    cancelled = await client.put(f"/api/ai/problem-tasks/{task_id}/cancel")
    assert cancelled.status_code == 200
    detail = await client.get(f"/api/ai/problem-tasks/{task_id}")
    assert detail.json()["data"]["status"] == "cancelled"
    assert task_id not in app.state.ai_authoring.tasks
    assert (await client.put(f"/api/ai/problem-tasks/{task_id}/cancel")).status_code == 409


async def test_task_requires_config_and_valid_reference(client: AsyncClient) -> None:
    await login_admin(client)
    no_config = await client.post(
        "/api/ai/problem-tasks/", json={"requirement": "创建一道足够详细的数组练习题"}
    )
    assert no_config.status_code == 400
    await client.put(
        "/api/ai/model-config",
        json={
            "provider_url": "http://127.0.0.1:9999/v1",
            "model": "mock-model",
            "api_key": "key",
        },
    )
    missing = await client.post(
        "/api/ai/problem-tasks/",
        json={"requirement": "基于不存在的题目进行改编并增加边界测试", "problem_id": "missing"},
    )
    assert missing.status_code == 404


async def test_generated_problem_is_locally_verified(
    client: AsyncClient, app: FastAPI, problem_payload: dict[str, object]
) -> None:
    await login_admin(client)
    await client.put(
        "/api/ai/model-config",
        json={
            "provider_url": "http://127.0.0.1:9999/v1",
            "model": "mock-model",
            "api_key": "key",
            "input_price": 1,
            "output_price": 2,
            "price_unit": 1000,
        },
    )
    generated = {
        "problem": {
            **problem_payload,
            "id": "ai_sum",
            "testcases": [
                {"input": "0 0\n", "output": "0\n"},
                {"input": "1 2\n", "output": "3\n"},
                {"input": "-5 8\n", "output": "3\n"},
                {"input": "-7 -9\n", "output": "-16\n"},
                {"input": "1000000000 -1000000000\n", "output": "0\n"},
            ],
        },
        "reference_solution": "a,b=map(int,input().split())\nprint(a+b)",
        "review": "覆盖零、正负数和整数边界，参考解法为 O(1)。",
    }

    async def mock_stream(_config: object, _prompt: str) -> tuple[str, int, int, str]:
        await asyncio.sleep(0)
        return json.dumps(generated, ensure_ascii=False), 100, 200, "provider"

    app.state.ai_authoring._stream_completion = mock_stream
    created = await client.post(
        "/api/ai/problem-tasks/",
        json={"requirement": "创建一道覆盖正数、负数与边界值的两数求和题"},
    )
    task_id = created.json()["data"]["task_id"]
    for _ in range(100):
        detail = await client.get(f"/api/ai/problem-tasks/{task_id}")
        if detail.json()["data"]["status"] != "running":
            if detail.json()["data"]["status"] != "pending":
                break
        await asyncio.sleep(0.03)
    data = detail.json()["data"]
    assert data["status"] == "completed"
    assert data["result"]["problem"]["id"] == "ai_sum"
    assert data["usage"] == {
        "input_tokens": 100,
        "output_tokens": 200,
        "total_tokens": 300,
        "cost": 0.5,
        "currency": "USD",
        "source": "provider",
    }
