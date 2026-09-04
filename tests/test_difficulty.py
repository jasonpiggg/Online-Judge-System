from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from oj.ai_prompts import QUALITY_RULES
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
    assert problem.difficulty == expected
    assert problem.model_dump()["difficulty"] == expected


def test_unknown_new_labels_rejected_but_legacy_reads_survive(
    problem_payload: dict[str, Any],
) -> None:
    data = {**problem_payload, "difficulty": "自定义难度"}
    with pytest.raises(ValidationError, match="难度须为"):
        Problem.model_validate(data)
    assert Problem.model_validate(data, context={"legacy": True}).difficulty == ""
    assert normalize_difficulty("自定义难度") == ""
    for level in DIFFICULTIES:
        assert level["description"] in QUALITY_RULES
    assert Problem.model_json_schema()["properties"]["difficulty"]["enum"] == [
        level["value"] for level in DIFFICULTIES
    ]


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
    assert [p["difficulty"] for p in await store.list(True)] == ["简单", "简单", ""]
    problem = await store.get("p0")
    assert problem is not None and problem.difficulty == "简单"
    assert before == {p.name: p.read_bytes() for p in store.directory.iterdir()}


async def test_api_writes_and_drafts_use_canonical_levels(
    client: AsyncClient,
    app: Any,
    problem_payload: dict[str, Any],
) -> None:
    await login_admin(client)
    payload = {**problem_payload, "difficulty": "easy"}
    assert (await client.post("/api/problems/", json=payload)).status_code == 200
    assert (await client.get("/api/problems/sum_2")).json()["data"]["difficulty"] == "简单"
    payload["difficulty"] = "不明难度"
    assert (await client.put("/api/problems/sum_2", json=payload)).status_code == 400
    payload["difficulty"] = "medium"
    draft = (await client.post("/api/problem-drafts/", json={"problem": payload})).json()["data"]
    assert draft["problem"]["difficulty"] == "中等"
    payload["difficulty"] = "基础"
    await app.state.db.execute(
        "UPDATE problem_drafts SET problem_json=? WHERE id=?", (json.dumps(payload), draft["id"])
    )
    restored = (await client.get(f"/api/problem-drafts/{draft['id']}")).json()["data"]
    assert restored["problem"]["difficulty"] == "简单"
    draft["problem"]["difficulty"] = "easy"
    await app.state.db.execute(
        "UPDATE problem_draft_revisions SET snapshot_json=? WHERE draft_id=?",
        (json.dumps(draft), draft["id"]),
    )
    revisions = (await client.get(f"/api/problem-drafts/{draft['id']}/revisions")).json()["data"]
    assert revisions[0]["snapshot"]["problem"]["difficulty"] == "简单"
