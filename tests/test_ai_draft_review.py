from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from oj.ai_authoring import AuthoringError
from tests.conftest import login_admin


async def prepare(
    app: FastAPI, client: AsyncClient, problem: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    await login_admin(client)
    created = await client.post(
        "/api/problem-drafts/",
        json={
            "problem": problem,
            "brute_solution": "old oracle",
            "generator_code": "old generator",
        },
    )
    draft_id = created.json()["data"]["id"]
    task = {
        "draft_id": draft_id,
        "user_id": 1,
        "problem_id": None,
        "requirement": "更新已有草稿并保留验证资产",
        "action": "revise",
        "target_section": "all",
    }
    result = {
        "problem": {**problem, "title": "AI revised title"},
        "reference_solution": "print(3)",
        "brute_solution": "print(1 + 2)",
        "generator_code": "print('[]')",
        "review": "Mock persistence test, not a real quality evaluation.",
        "coverage": {},
        "wrong_solutions": [],
        "verification": {"quality_gate_passed": True},
    }
    # Fixture represents the persisted paid result immediately before draft finalization.
    await app.state.db.execute(
        """INSERT INTO ai_tasks
           (id,user_id,requirement,status,progress,result,input_tokens,output_tokens,cost,
            draft_id,created_at,updated_at) VALUES(?,1,?,'completed','done',?,10,20,0.5,?,?,?)""",
        ("review-task", task["requirement"], json.dumps(result), draft_id, "now", "now"),
    )
    return task, result


@pytest.mark.parametrize("with_assets", [True, False])
async def test_verified_assets_match_saved_draft_and_revision(
    app: FastAPI, client: AsyncClient, problem_payload: dict[str, Any], with_assets: bool
) -> None:
    task, result = await prepare(app, client, problem_payload)
    if not with_assets:
        result.pop("brute_solution")
        result.pop("generator_code")
        result["verification"]["quality_gate_passed"] = False
    await app.state.ai_authoring._save_ready_draft(task, "review-task", result, 1)
    saved = (await client.get(f"/api/problem-drafts/{task['draft_id']}")).json()["data"]
    revisions = (
        await client.get(f"/api/problem-drafts/{task['draft_id']}/revisions")
    ).json()["data"]
    assert saved["revision"] == 2
    assert saved["status"] == ("ready" if with_assets else "draft")
    for field in ("reference_solution", "brute_solution", "generator_code"):
        assert saved[field] == result.get(field, "") == revisions[0]["snapshot"][field]


@pytest.mark.parametrize(
    "change",
    ["revision", "archived", "published", "deleted", "owner", "race_revision", "race_archive"],
)
async def test_late_ai_write_preserves_newer_draft_and_paid_result(
    app: FastAPI,
    client: AsyncClient,
    problem_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    task, result = await prepare(app, client, problem_payload)
    db = app.state.db
    draft_id = task["draft_id"]

    async def mutate() -> None:
        if change in {"revision", "race_revision"}:
            await db.execute(
                "UPDATE problem_drafts SET revision=2,requirement='new manual edit' WHERE id=?",
                (draft_id,),
            )
        elif change in {"archived", "published", "race_archive"}:
            await db.execute(
                "UPDATE problem_drafts SET status=? WHERE id=?",
                ("archived" if change == "race_archive" else change, draft_id),
            )
        elif change == "deleted":
            await db.execute("DELETE FROM problem_drafts WHERE id=?", (draft_id,))
        else:
            task["user_id"] = 999

    original_fetch = db.fetchone
    if change.startswith("race_"):
        async def race_fetch(sql: str, params: Any = ()) -> Any:
            row = await original_fetch(sql, params)
            if sql == "SELECT * FROM problem_drafts WHERE id=?":
                await mutate()  # Simulate an edit after reading, before the SQL update.
            return row

        monkeypatch.setattr(db, "fetchone", race_fetch)
    else:
        await mutate()
    with pytest.raises(AuthoringError, match="AI 结果和用量已保留"):
        await app.state.ai_authoring._save_ready_draft(task, "review-task", result, 1)
    saved = await original_fetch("SELECT * FROM problem_drafts WHERE id=?", (draft_id,))
    if change == "deleted":
        assert saved is None
    else:
        assert saved["brute_solution"] == "old oracle"
        assert saved["generator_code"] == "old generator"
        if change in {"revision", "race_revision"}:
            assert saved["revision"] == 2 and saved["requirement"] == "new manual edit"
        if change in {"archived", "published", "race_archive"}:
            assert saved["status"] == ("archived" if change == "race_archive" else change)
    retained = await original_fetch("SELECT * FROM ai_tasks WHERE id='review-task'")
    assert json.loads(retained["result"]) == result
    assert retained["output_tokens"] == 20 and retained["cost"] == 0.5
    assert not await db.fetchall("SELECT * FROM verification_runs")
    assert not await db.fetchall("SELECT * FROM problem_draft_revisions WHERE source='ai'")


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("admin", [False, True])
async def test_draft_publish_cannot_bypass_log_visibility_policy(
    app: FastAPI,
    client: AsyncClient,
    problem_payload: dict[str, Any],
    existing: bool,
    admin: bool,
) -> None:
    await login_admin(client)
    if existing:
        assert (await client.post("/api/problems/", json=problem_payload)).status_code == 200
    if not admin:
        await client.post("/api/users/", json={"username": "alice", "password": "secret1"})
        await client.post("/api/auth/login", json={"username": "alice", "password": "secret1"})
    response = await client.post(
        "/api/problem-drafts/", json={"problem": {**problem_payload, "public_cases": True}}
    )
    draft_id = response.json()["data"]["id"]
    await app.state.db.execute("UPDATE problem_drafts SET status='ready' WHERE id=?", (draft_id,))
    published = await client.post(f"/api/problem-drafts/{draft_id}/publish")
    assert published.status_code == (200 if admin else 403)
    stored = await app.state.problems.get(problem_payload["id"])
    if admin:
        assert stored.public_cases is True
    elif existing:
        assert stored.public_cases is False
    else:
        assert stored is None
