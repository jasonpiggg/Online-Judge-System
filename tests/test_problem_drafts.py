from __future__ import annotations

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

    await app.state.db.execute(
        "UPDATE problem_drafts SET status='ready' WHERE id=?", (draft_id,)
    )
    published = await client.post(f"/api/problem-drafts/{draft_id}/publish")
    assert published.status_code == 200
    assert (await client.get("/api/problems/sum_2")).status_code == 200
