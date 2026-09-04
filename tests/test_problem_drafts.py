from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient


async def _login(client: AsyncClient, username: str) -> None:
    await client.post("/api/users/", json={"username": username, "password": "secret1"})
    await client.post("/api/auth/login", json={"username": username, "password": "secret1"})


async def test_problem_draft_revision_conflict_and_isolation(
    client: AsyncClient, problem_payload: dict[str, Any]
) -> None:
    await _login(client, "alice")
    created = await client.post(
        "/api/problem-drafts/",
        json={"requirement": "创建一道两数之和练习题", "problem": problem_payload},
    )
    assert created.status_code == 200
    draft = created.json()["data"]
    draft_id = draft["id"]

    update = {
        "revision": 1,
        "requirement": "调整题目边界覆盖范围",
        "problem": {**problem_payload, "title": "整数求和"},
        "change_summary": "修改标题",
    }
    saved = await client.put(f"/api/problem-drafts/{draft_id}", json=update)
    assert saved.json()["data"]["revision"] == 2
    assert (await client.put(f"/api/problem-drafts/{draft_id}", json=update)).status_code == 409
    revisions = await client.get(f"/api/problem-drafts/{draft_id}/revisions")
    assert [item["revision"] for item in revisions.json()["data"]] == [2, 1]

    client.cookies.clear()
    await _login(client, "bob")
    assert (await client.get(f"/api/problem-drafts/{draft_id}")).status_code == 404
    assert (await client.delete(f"/api/problem-drafts/{draft_id}")).status_code == 404


async def test_only_verified_draft_can_publish(
    client: AsyncClient, app: FastAPI, problem_payload: dict[str, Any]
) -> None:
    await _login(client, "alice")
    created = await client.post(
        "/api/problem-drafts/",
        json={"requirement": "创建一份可以发布的题目草稿", "problem": problem_payload},
    )
    draft_id = created.json()["data"]["id"]
    blocked = await client.post(f"/api/problem-drafts/{draft_id}/publish")
    assert blocked.status_code == 409
    assert blocked.json()["error"] == {
        "id": "conflict",
        "title": "当前内容已发生变化",
        "message": "draft must pass verification before publishing",
        "suggestion": "刷新并比较最新版本后再保存，避免覆盖其他页面的修改。",
        "retryable": True,
    }

    await app.state.db.execute("UPDATE problem_drafts SET status='ready' WHERE id=?", (draft_id,))
    published = await client.post(f"/api/problem-drafts/{draft_id}/publish")
    assert published.status_code == 200
    assert (await client.get("/api/problems/sum_2")).status_code == 200


async def test_incomplete_draft_can_be_saved_but_not_published(client: AsyncClient) -> None:
    await _login(client, "drafting")
    created = await client.post("/api/problem-drafts/", json={})
    draft = created.json()["data"]
    saved = await client.put(
        f"/api/problem-drafts/{draft['id']}",
        json={
            "revision": draft["revision"],
            "problem": {
                "id": "partial_problem",
                "title": "只完成标题的草稿",
                "difficulty": "easy",
            },
            "change_summary": "保存未完成草稿",
        },
    )
    assert saved.status_code == 200
    data = saved.json()["data"]
    assert data["problem"]["title"] == "只完成标题的草稿"
    assert data["problem"]["difficulty"] == "简单"
    assert data["problem"]["description"] == ""
    assert (await client.post(f"/api/problem-drafts/{draft['id']}/publish")).status_code == 409


async def _wait_task(client: AsyncClient, task_id: str) -> dict[str, Any]:
    for _ in range(200):
        response = await client.get(f"/api/ai/problem-tasks/{task_id}")
        data = response.json()["data"]
        if data["status"] in {"completed", "failed", "cancelled"}:
            return data
        await asyncio.sleep(0.02)
    raise AssertionError("verification task did not finish")


async def test_basic_verification_allows_manual_draft_without_ai_assets(
    client: AsyncClient, problem_payload: dict[str, Any]
) -> None:
    await _login(client, "manual-author")
    created = await client.post(
        "/api/problem-drafts/",
        json={"requirement": "手工创建一份基础题", "problem": problem_payload},
    )
    draft_id = created.json()["data"]["id"]
    started = await client.post(
        f"/api/problem-drafts/{draft_id}/verify", json={"mode": "basic"}
    )
    task = await _wait_task(client, started.json()["data"]["task_id"])
    assert task["status"] == "completed"
    assert task["result"]["verification"]["level"] == "basic"
    assert task["result"]["verification"]["reference_passed"] is None
    assert task["result"]["verification"]["warnings"]
    draft = (await client.get(f"/api/problem-drafts/{draft_id}")).json()["data"]
    assert draft["status"] == "ready"
    assert draft["verification_level"] == "basic"
    assert (await client.post(f"/api/problem-drafts/{draft_id}/publish")).status_code == 200


async def test_edit_invalidates_basic_verification(
    client: AsyncClient, problem_payload: dict[str, Any]
) -> None:
    await _login(client, "verification-editor")
    created = await client.post(
        "/api/problem-drafts/",
        json={
            "requirement": "验证后继续编辑",
            "problem": {**problem_payload, "id": "verification_edit"},
        },
    )
    draft_id = created.json()["data"]["id"]
    started = await client.post(
        f"/api/problem-drafts/{draft_id}/verify", json={"mode": "basic"}
    )
    await _wait_task(client, started.json()["data"]["task_id"])
    verified = (await client.get(f"/api/problem-drafts/{draft_id}")).json()["data"]
    assert verified["status"] == "ready"

    updated = await client.put(
        f"/api/problem-drafts/{draft_id}",
        json={
            "requirement": verified["requirement"],
            "problem": {**verified["problem"], "title": "修改后的题目"},
            "reference_solution": verified["reference_solution"],
            "brute_solution": verified["brute_solution"],
            "generator_code": verified["generator_code"],
            "review": verified["review"],
            "revision": verified["revision"],
            "change_summary": "修改题目标题",
        },
    )
    assert updated.json()["data"]["status"] == "draft"
    current = (await client.get(f"/api/problem-drafts/{draft_id}")).json()["data"]
    assert current["verification_level"] is None
    assert current["verification_summary"] is None
    assert (await client.post(f"/api/problem-drafts/{draft_id}/publish")).status_code == 409


async def test_basic_verification_rejects_incorrect_reference_solution(
    client: AsyncClient, problem_payload: dict[str, Any]
) -> None:
    await _login(client, "bad-reference-author")
    created = await client.post(
        "/api/problem-drafts/",
        json={
            "requirement": "检查错误参考解",
            "problem": {**problem_payload, "id": "bad_reference_problem"},
            "reference_solution": "print(0)",
        },
    )
    draft_id = created.json()["data"]["id"]
    started = await client.post(
        f"/api/problem-drafts/{draft_id}/verify", json={"mode": "basic"}
    )
    task = await _wait_task(client, started.json()["data"]["task_id"])
    assert task["status"] == "failed"
    assert "参考解没有通过" in task["error"]
    assert (await client.get(f"/api/problem-drafts/{draft_id}")).json()["data"]["status"] == "draft"


async def test_legacy_verification_request_keeps_full_mode(
    client: AsyncClient, app: FastAPI, problem_payload: dict[str, Any]
) -> None:
    await _login(client, "legacy-verify")
    created = await client.post(
        "/api/problem-drafts/",
        json={"requirement": "兼容旧验证调用", "problem": problem_payload},
    )
    draft_id = created.json()["data"]["id"]
    started = await client.post(f"/api/problem-drafts/{draft_id}/verify")
    context = await app.state.db.fetchone(
        "SELECT payload FROM ai_task_context WHERE task_id=?",
        (started.json()["data"]["task_id"],),
    )
    assert '"verification_mode":"full"' in context["payload"]
