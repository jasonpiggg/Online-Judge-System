from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from oj.ai_authoring import AuthoringError
from oj.ai_experience import complete_fields, merge_patch
from oj.schemas import Problem
from oj.web import install_web
from tests.conftest import login_admin
from tests.test_ai_http import configure, finish
from tests.test_ai_http import generated as generated  # noqa: F401 - shared fixture


async def configured(client: AsyncClient, app: FastAPI, problem_payload: dict[str, Any]) -> Any:
    await login_admin(client)
    manager = app.state.ai_authoring
    await configure(manager, "http://127.0.0.1:9999/v1")
    await manager.problems.create(Problem.model_validate(problem_payload))
    return manager


def full_payload(generated: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(generated)
    result["brute_solution"] = "print(sum(map(int,input().split())))"
    result["generator_code"] = "import json\nprint(json.dumps([f'{i} {-i}' for i in range(20)]))"
    return result


def fake_phases(
    manager: Any, generated: dict[str, Any], *, invalid_review: bool = False
) -> list[Any]:
    calls: list[Any] = []
    value = full_payload(generated)

    async def complete(config: Any, prompt: str, usage: Any = None) -> tuple[str, int, int, str]:
        calls.append((config, json.loads(prompt)))
        system = config["system_prompt"]
        if "Stage 1:" in system:
            result = {
                "problem": value["problem"],
                "reference_solution": value["reference_solution"],
            }
        elif "Stage 2:" in system:
            result = {k: v for k, v in value.items() if k not in {"problem", "reference_solution"}}
            result["testcases"] = value["problem"]["testcases"]
        else:
            result = {"patch": {}, "review": value["review"]}
            if invalid_review and len(calls) == 3:
                result["patch"] = {"reference_solution": "invalid syntax !!"}
            elif invalid_review:
                result["patch"] = {"reference_solution": value["reference_solution"]}
        text = json.dumps(result, ensure_ascii=False)
        if config.get("_on_content"):
            await config["_on_content"](text[:30])
            await config["_on_content"](text)
        if usage:
            await usage(10, 20, "provider", 5)
        return text, 10, 20, "provider"

    manager._stream_completion = complete
    return calls


async def test_web_auth_origin_and_revision(
    client: AsyncClient,
    app: FastAPI,
    problem_payload: dict[str, Any],
) -> None:
    assert (await client.get("/api/auth/me")).status_code == 401
    await configured(client, app, problem_payload)
    assert (await client.get("/api/auth/me")).json()["data"]["role"] == "admin"
    path = "/api/workspace-drafts/sum_2/python"
    assert (await client.put(path, json={"code": "x", "expected_revision": 0})).status_code == 200
    assert (await client.put(path, json={"code": "y", "expected_revision": 0})).status_code == 409
    assert (await client.get(path)).json()["data"]["code"] == "x"
    assert (await client.put(path, json={"code": "y", "expected_revision": 1})).status_code == 200
    for origin in ("https://evil.example", "null", "http://testserver/path", "http://[invalid"):
        assert (
            await client.put(path, json={"code": "z"}, headers={"Origin": origin})
        ).status_code == 403
    assert (
        await client.put(path, json={"code": "z"}, headers={"Origin": "http://testserver"})
    ).status_code == 200
    assert (
        await client.put(path, json={"code": "z"}, headers={"Sec-Fetch-Site": "cross-site"})
    ).status_code == 403
    assert (await client.get("/api/nonexistent")).status_code == 404
    assert (await client.get("/assets/missing.js")).status_code == 404
    switched = await client.put(path, json={"code": "must not save"}, headers={"X-OJ-User":"2"})
    assert switched.status_code == 401
    assert (await client.get(path)).json()["data"]["code"] == "z"


async def test_static_spa_and_missing_build(tmp_path: Path) -> None:
    app = FastAPI()
    install_web(app, tmp_path)
    async with AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://localhost"
    ) as client:
        assert (await client.get("/problems/sum_2")).status_code == 503
        (tmp_path / "index.html").write_text("<h1>OJ</h1>")
        assert "OJ" in (await client.get("/problems/sum_2")).text
        assert (await client.get("/index.html")).status_code == 200
        assert (await client.post("/missing")).status_code == 404
        assert (await client.get("/secret.env")).status_code == 404
        assert (
            await client.post("/missing", headers={"Origin": "http://localhost:5173"})
        ).status_code == 404


async def test_idempotency_concurrency_snapshot_and_cancel(
    client: AsyncClient,
    app: FastAPI,
    problem_payload: dict[str, Any],
) -> None:
    manager = await configured(client, app, problem_payload)
    gate = asyncio.Event()

    async def blocked(*_args: Any) -> Any:
        await gate.wait()
        return "{}", 0, 0, "estimated"

    manager._stream_completion = blocked
    body = {"requirement": "请创建一道初学者使用的两数求和题目", "workflow_version": 2}
    responses = await asyncio.gather(
        *[
            client.post("/api/ai/problem-tasks/", json=body, headers={"Idempotency-Key": "same"})
            for _ in range(4)
        ]
    )
    ids = {r.json()["data"]["task_id"] for r in responses}
    assert len(ids) == 1
    task_id = ids.pop()
    alias = await client.post(
        "/api/ai/problem-tasks/", json=body, headers={"Idempotency-Key": "alias"}
    )
    assert alias.json()["data"]["task_id"] == task_id
    changed = {**body, "requirement": "请创建另一道简单的数组求和练习题目"}
    assert (
        await client.post(
            "/api/ai/problem-tasks/", json=changed, headers={"Idempotency-Key": "same"}
        )
    ).status_code == 409
    assert (
        await client.post(
            "/api/ai/problem-tasks/", json=body, headers={"Idempotency-Key": "invalid key"}
        )
    ).status_code == 400
    second = await client.post("/api/ai/problem-tasks/", json=changed)
    assert second.status_code == 200
    third = await client.post(
        "/api/ai/problem-tasks/", json={**body, "requirement": "请创建第三道简单的数组求和练习题目"}
    )
    assert third.status_code == 429
    context = await manager.db.fetchone("SELECT * FROM ai_task_context WHERE task_id=?", (task_id,))
    assert b"test-key" not in context["config_snapshot"]
    detail = await client.get(f"/api/ai/problem-tasks/{task_id}")
    assert "encrypted_api_key" not in detail.text and "provider_url" not in detail.text
    await client.put(f"/api/ai/problem-tasks/{task_id}/cancel")
    assert (await client.get(f"/api/ai/problem-tasks/{task_id}/events")).text.count(
        "event: cancelled"
    ) == 1
    await manager.close()
    await manager.recover()


@pytest.mark.parametrize("repair", [False, True])
async def test_three_stage_quality_gate_and_bounded_repair(
    client: AsyncClient,
    app: FastAPI,
    problem_payload: dict[str, Any],
    generated: dict[str, Any],
    repair: bool,
) -> None:
    manager = await configured(client, app, problem_payload)
    calls = fake_phases(manager, generated, invalid_review=repair)
    manager.settings.ai_model_output_limits = {"mock": 2048}
    task_id = await manager.create_request(
        1, {"workflow_version": 2, "requirement": "创建简单求和题目包含正负数和边界"}
    )
    manager.settings.ai_model_output_limits = {"mock": 512}
    row = await finish(manager, task_id)
    assert row["status"] == "completed", row["error"]
    assert len(calls) == (4 if repair else 3)
    assert all(config["max_output_tokens"] == 2048 for config, _ in calls)
    result = json.loads(row["result"])
    assert result["verification"]["quality_gate_passed"]
    assert result["initial_problem"]["title"]
    assert result["verification"]["independent_oracle"]["generated_cases"] == 20
    detail = (await client.get(f"/api/ai/problem-tasks/{task_id}")).json()["data"]
    assert detail["repair_used"] == repair
    assert detail["preview"]["title"] == generated["problem"]["title"]
    assert (await client.get(f"/api/ai/problem-tasks/{task_id}/events")).status_code == 200


@pytest.mark.parametrize("target", ["samples", "statement", "constraints", "testcases", "review"])
async def test_v2_sections_and_review(
    client: AsyncClient,
    app: FastAPI,
    problem_payload: dict[str, Any],
    target: str,
) -> None:
    manager = await configured(client, app, problem_payload)
    values = {
        "samples": {"samples": [{"input": "3 4", "output": "7"}]},
        "statement": {
            k: problem_payload[k]
            for k in ("title", "description", "input_description", "output_description")
        },
        "constraints": {"constraints": "|a|, |b| <= 10^9"},
        "testcases": {"testcases": problem_payload["testcases"]},
        "review": {},
    }

    async def stream(_config: Any, prompt: str, _usage: Any = None) -> Any:
        if target != "testcases":
            assert '"testcases"' not in prompt or target == "review"
        return (
            json.dumps({**values[target], "review": "内容完整，样例与要求保持一致。"}),
            10,
            20,
            "provider",
        )

    manager._stream_completion = stream
    task_id = await manager.create_request(
        1,
        {
            "workflow_version": 2,
            "problem_id": "sum_2",
            "requirement": "请完善当前题目所指定的部分",
            "action": "review" if target == "review" else "revise",
            "target_section": target,
        },
    )
    row = await finish(manager, task_id)
    assert row["status"] == "completed", row["error"]
    result = json.loads(row["result"])
    assert result["kind"] == ("review" if target == "review" else "section_patch")
    if target != "review":
        assert not result["verification"]["quality_gate_passed"]


async def test_assistant_context_isolation_history_and_duplicate(
    client: AsyncClient,
    app: FastAPI,
    problem_payload: dict[str, Any],
) -> None:
    manager = await configured(client, app, problem_payload)
    seen = []

    async def stream(config: Any, prompt: str, usage: Any = None) -> Any:
        seen.append(json.loads(prompt))
        assert "testcases" not in prompt
        assert config["max_output_tokens"] == 16384
        assert config["json_mode"] is False
        await config["_on_content"]("先检查输入")
        await usage(10, 20, "provider", 0)
        return "先检查输入的两个整数。", 10, 20, "provider"

    manager._stream_completion = stream
    chat = (await client.post("/api/ai/conversations/", json={"problem_id": "sum_2"})).json()[
        "data"
    ]["id"]
    assert (await client.post("/api/ai/conversations/", json={"problem_id": "sum_2"})).json()[
        "data"
    ]["id"] == chat
    path = f"/api/ai/conversations/{chat}/messages"
    body = {"message": "给我提示", "code": "print(1)", "language": "python"}
    reply = await client.post(path, json=body, headers={"Idempotency-Key": "message"})
    task_id = reply.json()["data"]["task_id"]
    await finish(manager, task_id)
    assert (await client.post(path, json=body, headers={"Idempotency-Key": "message"})).json()[
        "data"
    ]["task_id"] == task_id
    assert len((await client.get(path)).json()["data"]) == 1
    next_reply = await client.post(path, json={**body, "message": "再给一步提示"})
    await finish(manager, next_reply.json()["data"]["task_id"])
    assert len(seen[1]["history"]) == 1
    assert (await client.get(f"/api/ai/assistant-tasks/{task_id}")).status_code == 200
    assert (await client.get(f"/api/ai/assistant-tasks/{task_id}/events")).status_code == 200
    assert (await client.post(path, json={**body, "code": "中" * 100000})).status_code == 400
    assert (await client.post(path, json={**body, "submission_id": 99999})).status_code == 404
    await client.post("/api/users/", json={"username": "learner", "password": "password"})
    await client.post("/api/auth/login", json={"username": "learner", "password": "password"})
    assert (await client.get(path)).status_code == 404
    assert (await client.post(path, json=body)).status_code == 404
    assert (await client.get(f"/api/ai/assistant-tasks/{task_id}")).status_code == 403


@pytest.mark.parametrize("failure", ["empty", "network", "timeout", "invalid"])
async def test_assistant_failure_never_automatically_retries(
    client: AsyncClient,
    app: FastAPI,
    problem_payload: dict[str, Any],
    failure: str,
) -> None:
    manager = await configured(client, app, problem_payload)
    calls = 0

    async def broken(*_args: Any) -> Any:
        nonlocal calls
        calls += 1
        if failure == "network":
            raise httpx.ConnectError("connection failed")
        if failure == "timeout":
            raise TimeoutError
        if failure == "invalid":
            raise AuthoringError("模型输出达到 Token 上限")
        return "", 10, 30, "provider"

    manager._stream_completion = broken
    chat = (await client.post("/api/ai/conversations/", json={"problem_id": "sum_2"})).json()[
        "data"
    ]["id"]
    task_id = (
        await client.post(
            f"/api/ai/conversations/{chat}/messages", json={"message": "提示", "code": ""}
        )
    ).json()["data"]["task_id"]
    row = await finish(manager, task_id)
    assert row["status"] == "failed" and calls == 1


def test_preview_never_parses_unfinished_values() -> None:
    assert complete_fields('{"title":"完整标题","description":"未完成') == {"title": "完整标题"}
    assert complete_fields('{"samples":[{"input":"a","output":"b"}]}')["samples"][0]["input"] == "a"
    assert (
        merge_patch({"problem": {"title": "a"}}, {"problem": {"title": "b"}})["problem"]["title"]
        == "b"
    )
    with pytest.raises(ValueError):
        merge_patch({"title": "x"}, {"secret": "x"})


async def test_local_verify_without_model_and_stale_draft(
    client: AsyncClient,
    app: FastAPI,
    generated: dict[str, Any],
) -> None:
    await login_admin(client)
    data = full_payload(generated)
    draft = (
        await client.post(
            "/api/problem-drafts/",
            json={
                "problem": data["problem"],
                "reference_solution": data["reference_solution"],
                "brute_solution": data["brute_solution"],
                "generator_code": data["generator_code"],
                "review": {k: data[k] for k in ("review", "coverage", "wrong_solutions")},
            },
        )
    ).json()["data"]
    created = await client.post(f"/api/problem-drafts/{draft['id']}/verify")
    assert created.status_code == 200
    row = await finish(app.state.ai_authoring, created.json()["data"]["task_id"])
    assert row["status"] == "completed", row["error"]
    assert row["input_tokens"] == row["output_tokens"] == 0
    assert (await client.post(f"/api/problem-drafts/{draft['id']}/publish")).status_code == 200


async def test_resume_reuses_completed_stage_and_rejects_changed_context(
    client: AsyncClient,
    app: FastAPI,
    problem_payload: dict[str, Any],
    generated: dict[str, Any],
) -> None:
    manager = await configured(client, app, problem_payload)
    calls = fake_phases(manager, generated)
    original = manager._stream_completion

    async def failing(config: Any, prompt: str, usage: Any = None) -> Any:
        if "Stage 2:" in config["system_prompt"]:
            raise httpx.ConnectError("interrupted")
        return await original(config, prompt, usage)

    manager._stream_completion = failing
    body = {"workflow_version": 2, "requirement": "创建简单求和题目覆盖边界"}
    old = await manager.create_request(1, body)
    assert (await finish(manager, old))["status"] == "failed"
    assert len(calls) == 1
    manager._stream_completion = original
    resumed = await manager.create_request(1, {**body, "resume_task_id": old})
    assert (await finish(manager, resumed))["status"] == "completed"
    assert len(calls) == 3  # Only assets and review were repeated.
    with pytest.raises(Exception, match="需求或目标"):
        await manager.create_request(1, {**body, "resume_task_id": old, "requirement": "different"})


async def test_snapshot_keeps_original_model_and_submission_permissions(
    client: AsyncClient,
    app: FastAPI,
    problem_payload: dict[str, Any],
) -> None:
    manager = await configured(client, app, problem_payload)
    chat = (await client.post("/api/ai/conversations/", json={"problem_id": "sum_2"})).json()[
        "data"
    ]["id"]
    submit = await client.post(
        "/api/submissions/", json={"problem_id": "sum_2", "language": "python", "code": "print(3)"}
    )
    body = {
        "message": "解释错误",
        "code": "print(3)",
        "submission_id": int(submit.json()["data"]["submission_id"]),
    }
    captured = []

    async def completion(config: Any, prompt: str, _usage: Any = None) -> Any:
        captured.append((config["model"], json.loads(prompt)))
        return "请检查输入。", 10, 20, "provider"

    manager._stream_completion = completion
    task = (await client.post(f"/api/ai/conversations/{chat}/messages", json=body)).json()["data"][
        "task_id"
    ]
    await finish(manager, task)
    assert captured[0][0] == "mock"
    assert "submission" in captured[0][1]
    assert "testcases" not in captured[0][1]
