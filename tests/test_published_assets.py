from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.conftest import login_admin


async def publish(
    app: FastAPI,
    client: AsyncClient,
    problem: dict[str, Any],
    reference: str = "print(sum(map(int,input().split())))",
) -> dict[str, Any]:
    draft = (
        await client.post(
            "/api/problem-drafts/",
            json={
                "problem": problem,
                "requirement": "private requirement",
                "reference_solution": reference,
                "brute_solution": "oracle",
                "generator_code": "generator",
                "review": {
                    "coverage": {"basic": "cases"},
                    "wrong_solutions": [{"code": "print(0)", "reason": "constant"}],
                    "review": "editorial",
                    "private_extra": "secret",
                },
            },
        )
    ).json()["data"]
    await app.state.db.execute(
        "UPDATE problem_drafts SET status='ready' WHERE id=?", (draft["id"],)
    )
    result = await client.post(f"/api/problem-drafts/{draft['id']}/publish")
    assert result.status_code == 200, result.text
    return draft


async def test_round_trip_public_assets_and_private_draft_boundary(
    app: FastAPI, client: AsyncClient, problem_payload: dict[str, Any]
) -> None:
    await login_admin(client)
    original = await publish(app, client, problem_payload)
    await client.post("/api/users/", json={"username": "reader", "password": "password"})
    await client.post("/api/auth/login", json={"username": "reader", "password": "password"})
    data = (await client.get("/api/problems/sum_2/assets")).json()["data"]
    assert data["status"] == "current"
    assert "private" not in json.dumps(data)
    assert "verification" not in data["assets"]["review"]
    assert (await client.get(f"/api/problem-drafts/{original['id']}")).status_code == 404
    draft = (await client.post("/api/problems/sum_2/editing-draft")).json()["data"]
    for key, value in data["assets"].items():
        assert draft[key] == value
    assert draft["verification_summary"] is None if "verification_summary" in draft else True
    assert draft["status"] == "draft"
    again = (await client.post("/api/problems/sum_2/editing-draft")).json()["data"]
    assert again["id"] == draft["id"]
    updated = await client.put(
        f"/api/problem-drafts/{draft['id']}",
        json={
            **{
                k: draft[k]
                for k in (
                    "problem",
                    "reference_solution",
                    "brute_solution",
                    "generator_code",
                    "review",
                    "base_problem_id",
                )
            },
            "revision": draft["revision"],
            "reference_solution": "print(123)",
        },
    )
    assert updated.status_code == 200
    assert (await client.post("/api/problems/sum_2/editing-draft")).json()["data"][
        "reference_solution"
    ] == "print(123)"
    conflict = await client.put(
        f"/api/problem-drafts/{draft['id']}",
        json={
            "problem": problem_payload,
            **data["assets"],
            "revision": draft["revision"],
        },
    )
    assert conflict.status_code == 409
    await app.state.db.execute(
        "UPDATE problem_drafts SET status='ready' WHERE id=?", (draft["id"],)
    )
    assert (await client.post(f"/api/problem-drafts/{draft['id']}/publish")).status_code == 200
    assert (await client.get("/api/problems/sum_2/assets")).json()["data"]["assets"][
        "reference_solution"
    ] == "print(123)"
    await client.post("/api/auth/logout")
    assert (await client.get("/api/problems/sum_2/assets")).status_code == 401


async def test_stale_delete_recreate_and_reset(
    app: FastAPI, client: AsyncClient, problem_payload: dict[str, Any]
) -> None:
    await login_admin(client)
    await publish(app, client, problem_payload)
    changed = {**problem_payload, "title": "Changed"}
    assert (await client.put("/api/problems/sum_2", json=changed)).status_code == 200
    assert (await client.get("/api/problems/sum_2/assets")).json()["data"]["status"] == "stale"
    draft = (await client.post("/api/problems/sum_2/editing-draft")).json()["data"]
    assert not draft["reference_solution"]
    assert (await client.delete("/api/problems/sum_2")).status_code == 200
    assert (await client.get("/api/problems/sum_2/assets")).status_code == 404
    assert (await client.post("/api/problems/", json=problem_payload)).status_code == 200
    assert (await client.get("/api/problems/sum_2/assets")).json()["data"]["status"] == "missing"
    await publish(app, client, problem_payload, "replacement")
    replacement = (await client.post("/api/problems/sum_2/editing-draft")).json()["data"]
    assert replacement["id"] != draft["id"]
    assert replacement["reference_solution"] == "replacement"
    assert (await client.post("/api/reset/")).status_code == 200
    assert not await app.state.db.fetchall("SELECT * FROM published_problem_assets")


async def test_history_matching_ambiguity_and_no_unpublished_leak(
    app: FastAPI, client: AsyncClient, problem_payload: dict[str, Any]
) -> None:
    await login_admin(client)
    first = await publish(app, client, problem_payload, "first")
    await app.state.db.execute("DELETE FROM published_problem_assets")
    data = (await client.get("/api/problems/sum_2/assets")).json()["data"]
    assert data["assets"]["reference_solution"] == "first"
    second = await publish(app, client, problem_payload, "second")
    await app.state.db.execute("DELETE FROM published_problem_assets")
    data = (await client.get("/api/problems/sum_2/assets")).json()["data"]
    assert data["status"] == "ambiguous"
    assert {s["source_draft_id"] for s in data["sources"]} == {first["id"], second["id"]}
    await app.state.db.execute(
        "UPDATE problem_drafts SET status='draft' WHERE id=?", (second["id"],)
    )
    data = (await client.get("/api/problems/sum_2/assets")).json()["data"]
    assert data["status"] == "current" and data["assets"]["reference_solution"] == "first"
    await client.put("/api/problems/sum_2", json={**problem_payload, "title": "different"})
    assert (await client.get("/api/problems/sum_2/assets")).json()["data"]["status"] == "missing"


async def test_failed_publish_does_not_replace_assets(
    app: FastAPI, client: AsyncClient, problem_payload: dict[str, Any], monkeypatch: Any
) -> None:
    await login_admin(client)
    await publish(app, client, problem_payload, "old")
    draft = (await client.post("/api/problems/sum_2/editing-draft")).json()["data"]
    await app.state.db.execute(
        "UPDATE problem_drafts SET status='ready',reference_solution='new' WHERE id=?",
        (draft["id"],),
    )

    async def fail(_problem: Any) -> bool:
        return False

    monkeypatch.setattr(app.state.problems, "update", fail)
    assert (await client.post(f"/api/problem-drafts/{draft['id']}/publish")).status_code == 409
    assert (await client.get("/api/problems/sum_2/assets")).json()["data"]["assets"][
        "reference_solution"
    ] == "old"


def test_review_schema_omits_absent_assets_and_protected_fields(
    problem_payload: dict[str, Any],
) -> None:
    from oj.ai_sections import DraftReviewCandidate, draft_review_schema, merge_draft_review

    baseline = DraftReviewCandidate.model_validate(
        {"problem": problem_payload, "reference_solution": "x"}
    )
    schema = draft_review_schema(baseline)
    assert set(schema["properties"]["patch"]["properties"]) == {"problem", "reference_solution"}
    assert "id" not in schema["$defs"]["DraftProblem"]["properties"]
    with pytest.raises(ValueError, match="coverage"):
        merge_draft_review(baseline, {"coverage": {"basic": "new"}})


async def test_early_v9_upgrade_preserves_assets_and_allows_editing(
    app: FastAPI, client: AsyncClient, problem_payload: dict[str, Any]
) -> None:
    await login_admin(client)
    original = await publish(app, client, problem_payload)
    await app.state.db.execute("ALTER TABLE published_problem_assets DROP COLUMN deleted_at")
    await app.state.db.execute("PRAGMA user_version=9")
    await app.state.db.initialize()
    await app.state.db.initialize()
    assert (await app.state.db.fetchone("PRAGMA user_version"))[0] == 10
    result = await client.post("/api/problems/sum_2/editing-draft")
    assert result.status_code == 200, result.text
    assert result.json()["data"]["reference_solution"] == original["reference_solution"]
    assert (await client.delete("/api/problems/sum_2")).status_code == 200
    assert (await client.post("/api/problems/", json=problem_payload)).status_code == 200
    recreated = await client.post("/api/problems/sum_2/editing-draft")
    assert recreated.status_code == 200, recreated.text
    assert recreated.json()["data"]["id"] != result.json()["data"]["id"]
    assert not recreated.json()["data"]["reference_solution"]
