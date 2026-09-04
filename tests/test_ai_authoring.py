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
from oj.ai_experience import repair_scope
from oj.config import Settings
from tests.conftest import login_admin


def test_cost_calculation() -> None:
    assert calculate_cost(1_000, 500, 2.0, 4.0, 1_000) == 4.0


def test_targeted_repair_scopes_only_failed_assets() -> None:
    wrong = repair_scope("错误解法 2 未被有效卡错")
    assert set(wrong) == {"wrong_solutions", "problem.testcases", "review"}
    generator = repair_scope("随机数据生成器必须输出 20–100 组")
    assert set(generator) == {"generator_code", "review"}
    reference = repair_scope("参考解未通过")
    assert set(reference) == {
        "reference_solution",
        "problem.samples",
        "problem.testcases",
        "review",
    }


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

        async def aiter_bytes(self, **_kwargs: Any) -> Any:
            async for line in self.aiter_lines():
                yield (line + "\n").encode()

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


async def test_config_is_encrypted_and_not_returned(client: AsyncClient, app: FastAPI) -> None:
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

    async def slow_stream(
        _config: object, _prompt: str, _usage: object = None
    ) -> tuple[str, int, int, str]:
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

    another = await client.post(
        "/api/ai/problem-tasks/",
        json={"requirement": "创建另一道用于测试归档取消的简单求和题目"},
    )
    another_id = another.json()["data"]["task_id"]
    await asyncio.sleep(0.03)
    archived = await client.delete(f"/api/ai/problem-tasks/{another_id}")
    assert archived.status_code == 200
    assert archived.json()["data"]["status"] == "cancelled"
    row = await app.state.db.fetchone("SELECT archived_at FROM ai_tasks WHERE id=?", (another_id,))
    assert row["archived_at"] is not None

    draft = (await client.post("/api/problem-drafts/", json={})).json()["data"]
    linked = await client.post(
        "/api/ai/problem-tasks/",
        json={
            "requirement": "补全这个草稿并验证关联任务归档取消行为",
            "draft_id": draft["id"],
        },
    )
    linked_id = linked.json()["data"]["task_id"]
    await asyncio.sleep(0.03)
    assert (await client.delete(f"/api/problem-drafts/{draft['id']}")).status_code == 200
    linked_detail = await client.get(f"/api/ai/problem-tasks/{linked_id}")
    assert linked_detail.json()["data"]["status"] == "cancelled"


async def test_authoring_lists_archive_and_failed_candidate_recovery(
    client: AsyncClient, app: FastAPI
) -> None:
    await login_admin(client)
    now = "2026-09-05T00:00:00+00:00"
    candidate = {
        "kind": "candidate",
        "result_version": 2,
        "problem": {"id": "calculator", "title": "简易计算器", "description": "计算两个整数之和"},
        "reference_solution": "a,b=map(int,input().split());print(a+b)",
        "validation": {"status": "failed", "stage": "repair"},
    }
    await app.state.db.execute(
        "INSERT INTO ai_tasks(id,user_id,requirement,status,progress,stage,result,error,"
        "created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            "ai-recovery-test", 1, "创建一道简易计算器练习题", "failed", "命题失败", "repair",
            json.dumps(candidate, ensure_ascii=False), "修复 JSON 不完整", now, now,
        ),
    )
    await app.state.db.execute(
        "INSERT INTO ai_task_context(task_id,kind,payload,config_snapshot,fingerprint,preview) "
        "VALUES(?,?,?,?,?,?)",
        (
            "ai-recovery-test",
            "authoring",
            json.dumps({"requirement": "创建一道简易计算器练习题"}),
            b"x",
            "fp",
            "{}",
        ),
    )
    page = await client.get(
        "/api/ai/problem-tasks/",
        params={"page": 1, "page_size": 10, "include_metadata": True, "include_archived": False},
    )
    assert page.json()["data"]["total"] == 1
    assert isinstance((await client.get("/api/ai/problem-tasks/")).json()["data"], list)

    recovered = await client.post("/api/ai/problem-tasks/ai-recovery-test/save-draft")
    assert recovered.status_code == 200
    draft_id = recovered.json()["data"]["draft_id"]
    assert (await client.post("/api/ai/problem-tasks/ai-recovery-test/save-draft")).json()[
        "data"
    ]["draft_id"] == draft_id
    draft = (await client.get(f"/api/problem-drafts/{draft_id}")).json()["data"]
    assert draft["problem"]["title"] == "简易计算器"
    assert draft["status"] == "draft"

    await client.post("/api/users/", json={"username": "task-other", "password": "secret1"})
    await client.post(
        "/api/auth/login", json={"username": "task-other", "password": "secret1"}
    )
    assert (await client.delete("/api/ai/problem-tasks/ai-recovery-test")).status_code == 403
    assert (
        await client.post("/api/ai/problem-tasks/ai-recovery-test/save-draft")
    ).status_code == 403
    client.cookies.clear()
    await login_admin(client)
    assert (await client.delete("/api/ai/problem-tasks/ai-recovery-test")).status_code == 200
    assert (await client.delete("/api/ai/problem-tasks/ai-recovery-test")).status_code == 200
    hidden = await client.get(
        "/api/ai/problem-tasks/",
        params={"page": 1, "page_size": 10, "include_metadata": True, "include_archived": False},
    )
    assert hidden.json()["data"]["total"] == 0

    draft_page = await client.get(
        "/api/problem-drafts/",
        params={"page": 1, "page_size": 10, "include_metadata": True, "include_archived": False},
    )
    assert draft_page.json()["data"]["total"] == 1
    assert (await client.delete(f"/api/problem-drafts/{draft_id}")).status_code == 200
    assert (await client.delete(f"/api/problem-drafts/{draft_id}")).status_code == 200

    await app.state.db.execute(
        "INSERT INTO ai_tasks(id,user_id,requirement,status,progress,stage,result,"
        "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (
            "ai-cancelled-recovery",
            1,
            "恢复取消任务中的简易计算器成果",
            "cancelled",
            "任务已取消",
            "cancelled",
            json.dumps(candidate, ensure_ascii=False),
            now,
            now,
        ),
    )
    await app.state.db.execute(
        "INSERT INTO ai_task_context(task_id,kind,payload,config_snapshot,fingerprint,preview) "
        "VALUES(?,?,?,?,?,?)",
        ("ai-cancelled-recovery", "authoring", "{}", b"x", "cancelled-fp", "{}"),
    )
    cancelled_recovery = await client.post(
        "/api/ai/problem-tasks/ai-cancelled-recovery/save-draft"
    )
    assert cancelled_recovery.status_code == 200


async def test_failure_keeps_versioned_candidate_envelope(app: FastAPI) -> None:
    now = "2026-09-05T00:00:00+00:00"
    await app.state.db.execute(
        "INSERT INTO ai_tasks(id,user_id,requirement,status,progress,stage,result,"
        "created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (
            "ai-candidate-envelope",
            1,
            "创建一道简易计算器练习题",
            "running",
            "正在修复",
            "repair",
            json.dumps({"kind": "candidate", "result_version": 2, "problem": {"title": "计算器"}}),
            now,
            now,
        ),
    )

    async def fail_after_candidate(_task_id: str) -> None:
        raise ai_module.AuthoringError("错误解法 2 未被有效卡错；修复 JSON 不完整")

    app.state.ai_authoring._author = fail_after_candidate
    await app.state.ai_authoring._run("ai-candidate-envelope")
    row = await app.state.db.fetchone(
        "SELECT status,result FROM ai_tasks WHERE id='ai-candidate-envelope'"
    )
    retained = json.loads(row["result"])
    assert row["status"] == "failed"
    assert retained["kind"] == "candidate"
    assert retained["result_version"] == 2
    assert retained["validation"]["stage"] == "repair"


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
        "brute_solution": "values=list(map(int,input().split()))\nprint(sum(values))",
        "generator_code": (
            "import json\n"
            "print(json.dumps([f'{i} {-i}\\n' for i in range(1, 21)]))"
        ),
        "review": "覆盖零、正负数和整数边界，参考解法为 O(1)。",
        "coverage": {
            "basic": "正数基本求和",
            "boundary": "包含零与负数",
            "scale": "最大整数输入 O(1)",
        },
        "wrong_solutions": [
            {"code": "a,b=map(int,input().split());print(a-b)", "reason": "将求和误写为求差"},
            {
                "code": "a,b=map(int,input().split());print(abs(a)+abs(b))",
                "reason": "错误地忽略了负数符号",
            },
        ],
    }

    async def mock_stream(
        _config: object, _prompt: str, _usage: object = None
    ) -> tuple[str, int, int, str]:
        await asyncio.sleep(0)
        return json.dumps(generated, ensure_ascii=False), 100, 200, "provider"

    app.state.ai_authoring._stream_completion = mock_stream
    created = await client.post(
        "/api/ai/problem-tasks/",
        json={"requirement": "创建一道覆盖正数、负数与边界值的两数求和题"},
    )
    task_id = created.json()["data"]["task_id"]
    for _ in range(300):
        detail = await client.get(f"/api/ai/problem-tasks/{task_id}")
        if detail.json()["data"]["status"] != "running":
            if detail.json()["data"]["status"] != "pending":
                break
        await asyncio.sleep(0.03)
    data = detail.json()["data"]
    assert data["status"] == "completed"
    assert data["result"]["problem"]["id"] == "ai_sum"
    assert data["result"]["verification"]["independent_oracle"]["generated_cases"] == 20
    assert data["result"]["verification"]["mutation_score"] == 100
    assert data["usage"] == {
        "input_tokens": 200,
        "output_tokens": 400,
        "total_tokens": 600,
        "cost": 1.0,
        "currency": "USD",
        "source": "provider",
    }
    drafts = await client.get("/api/problem-drafts/")
    assert drafts.json()["data"][0]["status"] == "ready"
