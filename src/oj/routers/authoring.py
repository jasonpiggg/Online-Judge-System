from __future__ import annotations

import json
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from oj.auth import CurrentUser, get_current_user
from oj.difficulty import normalize_difficulty
from oj.errors import APIError, response
from oj.schemas import Problem, ProblemDraftCreate, ProblemDraftUpdate, ProblemDraftVerify
from oj.submissions import now_iso

router = APIRouter(prefix="/api/problem-drafts")


def _normalize_problem(problem: dict[str, Any]) -> dict[str, Any]:
    if "difficulty" in problem:
        problem["difficulty"] = normalize_difficulty(problem["difficulty"])
    return problem


def _normalize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    if isinstance(snapshot.get("problem"), dict):
        _normalize_problem(snapshot["problem"])
    return snapshot


def _decode(row: Any) -> dict[str, Any]:
    review = json.loads(row["review_json"])
    verification = review.get("verification", {}) if isinstance(review, dict) else {}
    level = verification.get("level")
    if not level and verification.get("quality_gate_passed"):
        level = "full"
    return {
        "id": row["id"],
        "base_problem_id": row["base_problem_id"],
        "status": row["status"],
        "requirement": row["requirement"],
        "problem": _normalize_problem(json.loads(row["problem_json"])),
        "reference_solution": row["reference_solution"],
        "brute_solution": row["brute_solution"],
        "generator_code": row["generator_code"],
        "review": review,
        "verification_level": level,
        "verification_summary": verification or None,
        "revision": row["revision"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _snapshot(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


async def _owned_draft(request: Request, draft_id: str, user_id: int) -> Any:
    row = await request.app.state.db.fetchone(
        "SELECT * FROM problem_drafts WHERE id=? AND owner_id=?", (draft_id, user_id)
    )
    if row is None:
        raise APIError(404, "problem draft not found")
    return row


@router.get("/")
async def list_problem_drafts(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    rows = await request.app.state.db.fetchall(
        """SELECT * FROM problem_drafts WHERE owner_id=?
           ORDER BY updated_at DESC LIMIT ?""",
        (user.id, limit),
    )
    return response(data=[_decode(row) for row in rows])


@router.post("/")
async def create_problem_draft(
    request: Request,
    body: ProblemDraftCreate,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    if body.base_problem_id and await request.app.state.problems.get(body.base_problem_id) is None:
        raise APIError(404, "base problem not found")
    draft_id = "draft-" + secrets.token_urlsafe(12)
    now = now_iso()
    problem = body.problem.model_dump() if body.problem else {}
    review = dict(body.review)
    # A report only applies to the exact revision that was checked. Keep editorial
    # notes, but never carry a publishable verification onto modified content.
    review.pop("verification", None)
    data = {
        "id": draft_id,
        "base_problem_id": body.base_problem_id,
        "status": "draft",
        "requirement": body.requirement,
        "problem": problem,
        "reference_solution": body.reference_solution,
        "brute_solution": body.brute_solution,
        "generator_code": body.generator_code,
        "review": review,
        "revision": 1,
        "created_at": now,
        "updated_at": now,
    }
    async with request.app.state.db.connect() as db:
        await db.execute(
            """INSERT INTO problem_drafts
               (id,owner_id,base_problem_id,status,requirement,problem_json,
                reference_solution,brute_solution,generator_code,review_json,
                revision,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                draft_id,
                user.id,
                body.base_problem_id,
                "draft",
                body.requirement,
                _snapshot(problem),
                body.reference_solution,
                body.brute_solution,
                body.generator_code,
                _snapshot(review),
                1,
                now,
                now,
            ),
        )
        await db.execute(
            """INSERT INTO problem_draft_revisions
               (draft_id,revision,source,snapshot_json,change_summary,created_at)
               VALUES(?,?,?,?,?,?)""",
            (draft_id, 1, "user", _snapshot(data), "创建草稿", now),
        )
        await db.commit()
    return response(200, "problem draft created", data)


@router.get("/{draft_id}")
async def get_problem_draft(
    request: Request,
    draft_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    return response(data=_decode(await _owned_draft(request, draft_id, user.id)))


@router.put("/{draft_id}")
async def update_problem_draft(
    request: Request,
    draft_id: str,
    body: ProblemDraftUpdate,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    now = now_iso()
    problem = body.problem.model_dump() if body.problem else {}
    review = dict(body.review)
    # A report only applies to the exact revision that was checked. Keep editorial
    # notes, but never carry a publishable verification onto modified content.
    review.pop("verification", None)
    async with request.app.state.db.connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute(
            "SELECT * FROM problem_drafts WHERE id=? AND owner_id=?", (draft_id, user.id)
        )
        current = await cursor.fetchone()
        if current is None:
            raise APIError(404, "problem draft not found")
        if current["revision"] != body.revision:
            raise APIError(409, "problem draft was updated elsewhere; reload before saving")
        new_revision = body.revision + 1
        await db.execute(
            """UPDATE problem_drafts SET base_problem_id=?,status='draft',requirement=?,
               problem_json=?,reference_solution=?,brute_solution=?,generator_code=?,
               review_json=?,revision=?,updated_at=? WHERE id=?""",
            (
                body.base_problem_id,
                body.requirement,
                _snapshot(problem),
                body.reference_solution,
                body.brute_solution,
                body.generator_code,
                _snapshot(review),
                new_revision,
                now,
                draft_id,
            ),
        )
        updated = {
            "id": draft_id,
            "base_problem_id": body.base_problem_id,
            "status": "draft",
            "requirement": body.requirement,
            "problem": problem,
            "reference_solution": body.reference_solution,
            "brute_solution": body.brute_solution,
            "generator_code": body.generator_code,
            "review": review,
            "revision": new_revision,
            "created_at": current["created_at"],
            "updated_at": now,
        }
        await db.execute(
            """INSERT INTO problem_draft_revisions
               (draft_id,revision,source,snapshot_json,change_summary,created_at)
               VALUES(?,?,?,?,?,?)""",
            (draft_id, new_revision, "user", _snapshot(updated), body.change_summary, now),
        )
        await db.commit()
    return response(200, "problem draft updated", updated)


@router.get("/{draft_id}/revisions")
async def list_problem_draft_revisions(
    request: Request,
    draft_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    await _owned_draft(request, draft_id, user.id)
    rows = await request.app.state.db.fetchall(
        """SELECT revision,source,snapshot_json,change_summary,created_at
           FROM problem_draft_revisions WHERE draft_id=? ORDER BY revision DESC""",
        (draft_id,),
    )
    return response(
        data=[
            {
                "revision": row["revision"],
                "source": row["source"],
                "snapshot": _normalize_snapshot(json.loads(row["snapshot_json"])),
                "change_summary": row["change_summary"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    )


@router.post("/{draft_id}/publish")
async def publish_problem_draft(
    request: Request,
    draft_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    row = await _owned_draft(request, draft_id, user.id)
    if row["status"] != "ready":
        raise APIError(409, "draft must pass verification before publishing")
    problem = Problem.model_validate_json(row["problem_json"], context={"legacy": True})
    existing = await request.app.state.problems.get(problem.id)
    # Publishing a draft must obey the same log-visibility policy as direct edits.
    if user.role != "admin" and problem.public_cases != (
        existing.public_cases if existing else False
    ):
        raise APIError(403, "only administrators may change log visibility")
    succeeded = (
        await request.app.state.problems.update(problem)
        if existing
        else await request.app.state.problems.create(problem)
    )
    if not succeeded:
        raise APIError(409, "problem could not be published")
    await request.app.state.db.execute(
        "UPDATE problem_drafts SET status='published',updated_at=? WHERE id=?",
        (now_iso(), draft_id),
    )
    return response(200, "problem draft published", {"id": problem.id})


@router.post("/{draft_id}/verify")
async def verify_problem_draft(
    request: Request,
    draft_id: str,
    body: ProblemDraftVerify | None = None,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    row = await _owned_draft(request, draft_id, user.id)
    mode = body.mode if body else "full"
    task_id = await request.app.state.ai_authoring.create_request(
        user.id,
        {
            "draft_id": draft_id,
            "problem_id": row["base_problem_id"],
            "requirement": (
                "检查当前草稿的字段、排版、样例与可运行性"
                if mode == "basic"
                else "验证当前草稿的参考解、测试与独立对拍资产"
            ),
            "action": "verify",
            "target_section": "all",
            "workflow_version": 2,
            "verification_mode": mode,
        },
        request.headers.get("idempotency-key"),
    )
    return response(data={"task_id": task_id})


@router.delete("/{draft_id}")
async def archive_problem_draft(
    request: Request,
    draft_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    await _owned_draft(request, draft_id, user.id)
    await request.app.state.db.execute(
        "UPDATE problem_drafts SET status='archived',updated_at=? WHERE id=?",
        (now_iso(), draft_id),
    )
    return response(200, "problem draft archived", {"id": draft_id})
