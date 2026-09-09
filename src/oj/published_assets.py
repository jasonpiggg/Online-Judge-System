"""Published editorial assets, separate from private drafts and the course problem schema."""

from __future__ import annotations

import json
from typing import Any

import aiosqlite

from oj.schemas import Problem


def problem_snapshot(problem: Problem) -> str:
    return json.dumps(problem.model_dump(), ensure_ascii=False, sort_keys=True)


def draft_assets(row: Any) -> dict[str, Any]:
    review = json.loads(row["review_json"])
    # Explicit publication allowlist: no private requirement, task, usage or verification.
    return {
        "reference_solution": row["reference_solution"],
        "brute_solution": row["brute_solution"],
        "generator_code": row["generator_code"],
        "review": {
            key: review[key] for key in ("review", "coverage", "wrong_solutions") if key in review
        },
    }


async def resolve_assets(db: aiosqlite.Connection, problem: Problem) -> dict[str, Any]:
    cursor = await db.execute(
        "SELECT * FROM published_problem_assets WHERE problem_id=?", (problem.id,)
    )
    row = await cursor.fetchone()
    await cursor.close()
    snapshot = problem_snapshot(problem)
    if row:
        if row["problem_json"] is None:  # Tombstone blocks historical same-ID recovery.
            return {"status": "missing", "sources": []}
        return {
            "status": "current" if row["problem_json"] == snapshot else "stale",
            "assets": json.loads(row["assets_json"]),
            "source_draft_id": row["source_draft_id"],
            "source_revision": row["source_revision"],
            "published_at": row["published_at"],
            "sources": [],
        }
    cursor = await db.execute(
        "SELECT * FROM problem_drafts WHERE status='published' "
        "AND json_extract(problem_json,'$.id')=? ORDER BY updated_at DESC,id DESC",
        (problem.id,),
    )
    sources = []
    for legacy in await cursor.fetchall():
        try:
            original = Problem.model_validate_json(legacy["problem_json"], context={"legacy": True})
        except ValueError:
            continue
        if problem_snapshot(original) == snapshot:
            sources.append(
                {
                    "source_draft_id": legacy["id"],
                    "source_revision": legacy["revision"],
                    "published_at": legacy["updated_at"],
                    "assets": draft_assets(legacy),
                }
            )
    await cursor.close()
    if not sources:
        return {"status": "missing", "sources": []}
    distinct = {json.dumps(source["assets"], sort_keys=True) for source in sources}
    if len(distinct) == 1:
        return {"status": "current", **sources[0], "sources": []}
    return {"status": "ambiguous", "sources": sources}


async def save_assets(db: aiosqlite.Connection, problem: Problem, row: Any, stamp: str) -> None:
    await db.execute(
        "INSERT INTO published_problem_assets "
        "(problem_id,problem_json,assets_json,source_draft_id,source_revision,published_at) "
        "VALUES(?,?,?,?,?,?) ON CONFLICT(problem_id) DO UPDATE SET "
        "problem_json=excluded.problem_json,assets_json=excluded.assets_json,"
        "source_draft_id=excluded.source_draft_id,source_revision=excluded.source_revision,"
        "published_at=excluded.published_at",
        (
            problem.id,
            problem_snapshot(problem),
            json.dumps(draft_assets(row), ensure_ascii=False),
            row["id"],
            row["revision"],
            stamp,
        ),
    )


async def forget_assets(db: aiosqlite.Connection, problem_id: str, stamp: str) -> None:
    await db.execute(
        "INSERT INTO published_problem_assets(problem_id,published_at,deleted_at) VALUES(?,?,?) "
        "ON CONFLICT(problem_id) DO UPDATE SET problem_json=NULL,assets_json='{}',"
        "source_draft_id=NULL,source_revision=NULL,published_at=excluded.published_at,"
        "deleted_at=excluded.deleted_at",
        (problem_id, stamp, stamp),
    )
