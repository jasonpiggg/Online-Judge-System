from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from oj.ai.prompts import QUALITY_RULES
from oj.difficulty import DIFFICULTIES, normalize_difficulty
from oj.problem_store import ProblemStore
from oj.schemas import Problem

from .conftest import login_admin


@pytest.mark.parametrize(
    "value,expected",
    [
        ("easy", "简单"),
        (" EASY ", "简单"),
        ("基础", "简单"),
        ("简单", "简单"),
        ("medium", "中等"),
        ("进阶", "中等"),
        ("hard", "困难"),
        ("expert", "挑战"),
        ("beginner", "入门"),
        ("unrated", ""),
        ("", ""),
    ],
)
def test_aliases_are_canonical(problem_payload: dict[str, Any], value: str, expected: str) -> None:
    problem = Problem.model_validate({**problem_payload, "difficulty": value})
    assert problem.difficulty == value
    assert normalize_difficulty(value) == expected
    assert problem.model_dump()["difficulty"] == value


def test_unknown_new_labels_rejected_but_legacy_reads_survive(
    problem_payload: dict[str, Any],
) -> None:
    data = {**problem_payload, "difficulty": "自定义难度"}
    assert Problem.model_validate(data).difficulty == "自定义难度"
    assert Problem.model_validate(data, context={"legacy": True}).difficulty == "自定义难度"
    for level in DIFFICULTIES:
        assert level["description"] in QUALITY_RULES
    assert "enum" not in Problem.model_json_schema()["properties"]["difficulty"]



async def test_legacy_store_does_not_rewrite_files(
    tmp_path: Path, problem_payload: dict[str, Any]
) -> None:
    store = ProblemStore(tmp_path / "problems", tmp_path / "seeds")
    store.directory.mkdir()
    for i, difficulty in enumerate(["easy", "基础", "自定义"]):
        data = {**problem_payload, "id": f"p{i}", "difficulty": difficulty}
        (store.directory / f"p{i}.json").write_text(json.dumps(data), encoding="utf-8")
    before = {p.name: p.read_bytes() for p in store.directory.iterdir()}
    await store.initialize()
    assert [p["difficulty"] for p in await store.list(True)] == ["easy", "基础", "自定义"]
    problem = await store.get("p0")
    assert problem is not None and problem.difficulty == "easy"
    assert before == {p.name: p.read_bytes() for p in store.directory.iterdir()}


async def test_api_writes_and_drafts_use_canonical_levels(
    client: AsyncClient,
    app: Any,
    problem_payload: dict[str, Any],
) -> None:
    await login_admin(client)
    payload = {**problem_payload, "difficulty": "easy"}
    assert (await client.post("/api/problems/", json=payload)).status_code == 200
    assert (await client.get("/api/problems/sum_2")).json()["data"]["difficulty"] == "easy"
    payload["difficulty"] = "不明难度"
    assert (await client.put("/api/problems/sum_2", json=payload)).status_code == 200
    payload["difficulty"] = "medium"
    draft = (await client.post("/api/problem-drafts/", json={"problem": payload})).json()["data"]
    assert draft["problem"]["difficulty"] == "medium"
    payload["difficulty"] = "基础"
    await app.state.db.execute(
        "UPDATE problem_drafts SET problem_json=? WHERE id=?", (json.dumps(payload), draft["id"])
    )
    restored = (await client.get(f"/api/problem-drafts/{draft['id']}")).json()["data"]
    assert restored["problem"]["difficulty"] == "基础"
    draft["problem"]["difficulty"] = "easy"
    await app.state.db.execute(
        "UPDATE problem_draft_revisions SET snapshot_json=? WHERE draft_id=?",
        (json.dumps(draft), draft["id"]),
    )
    revisions = (await client.get(f"/api/problem-drafts/{draft['id']}/revisions")).json()["data"]
    assert revisions[0]["snapshot"]["problem"]["difficulty"] == "easy"


def test_resume_comparison_preserves_custom_values() -> None:
    from oj.difficulty import comparable_problem

    raw = {"difficulty": "easy", "title": "original"}
    assert comparable_problem(raw) == {"difficulty": "简单", "title": "original"}
    assert raw["difficulty"] == "easy"
    assert comparable_problem({"difficulty": "custom"}) != comparable_problem({"difficulty": ""})
    assert comparable_problem(None) is None
