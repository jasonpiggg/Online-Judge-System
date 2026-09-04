from __future__ import annotations

import asyncio
import copy
import json
import socket
from contextlib import asynccontextmanager
from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from oj.schemas import AIModelConfig, GeneratedProblem


@pytest.fixture
def generated(problem_payload: dict[str, Any]) -> dict[str, Any]:
    result = {
        "problem": copy.deepcopy(problem_payload),
        "reference_solution": "a,b=map(int,input().split());print(a+b)",
        "review": "求和 O(1)，覆盖符号和整数边界，有限用例不是数学证明。",
        "coverage": {
            "basic": "测试点 1：普通正数",
            "boundary": "测试点 2-4：零与负数",
            "scale": "测试点 5：最大输入整数 O(1)",
        },
        "wrong_solutions": [
            {"code": "a,b=map(int,input().split());print(a-b)", "reason": "把加法写成减法"},
            {
                "code": "a,b=map(int,input().split());print(abs(a)+abs(b))",
                "reason": "忽略整数负号导致错误",
            },
        ],
    }
    result["problem"]["testcases"] = [
        {"input": f"{a} {b}\n", "output": f"{a + b}\n"}
        for a, b in [(1, 2), (-5, 8), (0, 0), (-7, -9), (10**9, -(10**9))]
    ]
    return result


@asynccontextmanager
async def provider(generated: dict[str, Any], *, mode: str = "ok") -> Any:
    """Real loopback HTTP/SSE server; no HTTPX or stream function replacement."""
    api = FastAPI()
    calls: list[dict[str, Any]] = []
    disconnected = asyncio.Event()

    @api.post("/v1/chat/completions")
    async def complete(request: Request) -> StreamingResponse:
        calls.append(await request.json())
        assert request.headers["authorization"] == "Bearer test-key"

        async def events() -> Any:
            try:
                payload = (
                    json.dumps(generated, ensure_ascii=False) if mode != "invalid" else "bad json"
                )
                for part in [payload[:20], payload[20:]]:
                    yield (
                        "data: " + json.dumps({"choices": [{"delta": {"content": part}}]}) + "\n\n"
                    )
                    if mode == "slow":
                        await asyncio.sleep(30)
                if mode != "estimate":
                    usage = {"prompt_tokens": 10, "completion_tokens": 20}
                    if mode == "cached":
                        usage["prompt_tokens_details"] = {"cached_tokens": 6}
                        usage["completion_tokens_details"] = {"reasoning_tokens": 12}
                    yield "data: " + json.dumps({"usage": usage}) + "\n\n"
                if mode == "truncated":
                    yield 'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\n'
                yield "data: [DONE]\n\n"
            finally:
                disconnected.set()

        return StreamingResponse(events(), media_type="text/event-stream")

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(api, log_level="error", lifespan="off"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:  # noqa: ASYNC110 - uvicorn exposes a bool, not an Event
        await asyncio.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}/v1", calls, disconnected
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        sock.close()


async def configure(manager: Any, url: str) -> None:
    await manager.save_config(
        1,
        AIModelConfig(
            provider_url=url,
            model="mock",
            api_key="test-key",
            input_price=1,
            output_price=2,
            price_unit=1000,
        ),
    )


async def finish(manager: Any, task_id: str) -> Any:
    task = manager.tasks.get(task_id)
    if task:
        await asyncio.wait_for(task, 30)
    return await manager.db.fetchone("SELECT * FROM ai_tasks WHERE id=?", (task_id,))


@pytest.mark.parametrize("mode", ["ok", "estimate"])
async def test_real_two_phase_http(app: FastAPI, generated: dict[str, Any], mode: str) -> None:
    manager = app.state.ai_authoring
    async with provider(generated, mode=mode) as (url, calls, _):
        await configure(manager, url)
        task_id = await manager.create(1, "包含负数边界的求和题目", None)
        row = await finish(manager, task_id)
    assert row["status"] == "completed", row["error"]
    assert len(calls) == 2
    assert "Critically inspect" in calls[1]["messages"][1]["content"]
    result = json.loads(row["result"])
    assert result["verification"]["reference_passed"]
    assert len(result["verification"]["wrong_solutions"]) == 2
    if mode == "ok":
        assert (row["input_tokens"], row["output_tokens"], row["cost"]) == (20, 40, 0.1)
    assert row["usage_source"] == ("provider" if mode == "ok" else "estimated")
    assert "test-key" not in json.dumps(dict(row))


@pytest.mark.parametrize("mode", ["cancel", "timeout", "invalid", "bad_reference", "bad_wrong"])
async def test_real_http_failures(app: FastAPI, generated: dict[str, Any], mode: str) -> None:
    manager = app.state.ai_authoring
    if mode == "bad_reference":
        generated["problem"]["samples"][0]["output"] = "wrong"
    if mode == "bad_wrong":
        generated["wrong_solutions"][0]["code"] = "raise Exception('not a valid algorithm')"
    async with provider(generated, mode="slow" if mode in {"cancel", "timeout"} else mode) as (
        url,
        calls,
        disconnected,
    ):
        await configure(manager, url)
        if mode == "timeout":
            manager.settings.ai_stage_timeout_seconds = 1.0
        task_id = await manager.create(1, "覆盖失败和取消的求和题目", None)
        if mode == "cancel":
            for _ in range(100):
                row = await manager.db.fetchone(
                    "SELECT output_tokens FROM ai_tasks WHERE id=?", (task_id,)
                )
                if row["output_tokens"]:
                    break
                await asyncio.sleep(0.01)
            await manager.cancel(task_id)
        row = await finish(manager, task_id)
        await asyncio.wait_for(disconnected.wait(), 2)
    assert row["status"] == ("cancelled" if mode == "cancel" else "failed")
    assert row["output_tokens"] > 0
    assert len(calls) == (1 if mode in {"cancel", "timeout"} else 2)
    assert "test-key" not in json.dumps(dict(row))


async def test_config_key_retention_and_restart(app: FastAPI) -> None:
    manager = app.state.ai_authoring
    url = "http://127.0.0.1:1234/v1"
    with pytest.raises(ValueError, match="首次"):
        await manager.save_config(1, AIModelConfig(provider_url=url, model="mock"))
    await configure(manager, url)
    await manager.save_config(1, AIModelConfig(provider_url=url, model="changed"))
    row = await manager.db.fetchone("SELECT * FROM ai_configs WHERE user_id=1")
    assert manager.cipher.decrypt(row["encrypted_api_key"]) == b"test-key"
    await manager.db.execute(
        "INSERT INTO ai_tasks "
        "(id,user_id,requirement,status,progress,created_at,updated_at,input_tokens) "
        "VALUES ('orphan',1,'test','running','generating','','',42)"
    )
    await manager.recover()
    row = await manager.db.fetchone("SELECT * FROM ai_tasks WHERE id='orphan'")
    assert row["status"] == "failed" and row["input_tokens"] == 42
    assert not manager.tasks


def test_quality_schema(generated: dict[str, Any]) -> None:
    GeneratedProblem.model_validate(generated)
    generated["problem"]["testcases"].append(generated["problem"]["testcases"][0])
    with pytest.raises(ValidationError, match="互不重复"):
        GeneratedProblem.model_validate(generated)
