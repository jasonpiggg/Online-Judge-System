from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from oj.auth import CurrentUser, get_current_user, require_admin
from oj.errors import APIError, response
from oj.evaluation import VERDICT_LABELS, evaluation_batch, private_evaluation
from oj.languages import get_language
from oj.pagination import page_window
from oj.route_security import AuthorizedRoute
from oj.schemas import SubmissionCreate
from oj.submissions import detail_from_row, now_iso, summary_from_row

router = APIRouter(route_class=AuthorizedRoute, prefix="/api/submissions")


async def visible_evaluations(
    request: Request, user: CurrentUser, rows: list[Any]
) -> dict[int, dict[str, Any]]:
    if user.role == "admin":
        return await evaluation_batch(request.app.state.db, rows)
    visibility = {}
    for problem_id in {row["problem_id"] for row in rows}:
        problem = await request.app.state.problems.get(problem_id)
        visibility[problem_id] = bool(problem and problem.public_cases)
    public = [row for row in rows if visibility[row["problem_id"]]]
    result = await evaluation_batch(request.app.state.db, public)
    result.update(
        {
            row["id"]: private_evaluation(dict(row))
            for row in rows
            if not visibility[row["problem_id"]]
        }
    )
    return result


@router.post("/")
async def submit(
    request: Request,
    body: SubmissionCreate,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    async with request.app.state.submissions.intake_lock:
        return await _submit_locked(request, body, user)


async def _submit_locked(
    request: Request, body: SubmissionCreate, user: CurrentUser
) -> JSONResponse:
    one_minute_ago = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    recent = await request.app.state.db.fetchone(
        "SELECT COUNT(*) AS n FROM submissions WHERE user_id=? AND problem_id=? AND created_at>=?",
        (user.id, body.problem_id, one_minute_ago),
    )
    if recent["n"] >= 3:
        raise APIError(429, "submission rate limit exceeded")
    problem = await request.app.state.problems.get(body.problem_id)
    language = await get_language(request.app.state.db, body.language)
    if problem is None or language is None:
        raise APIError(404, "problem or language not found")
    submission_id = await request.app.state.submissions.create(
        user.id, body.problem_id, body.language, body.code
    )
    return response(data={"submission_id": str(submission_id), "status": "pending"})


async def submission_reader(request: Request) -> CurrentUser:
    user = await get_current_user(request)
    if user.role != "admin":
        # Check identifiable scope violations before FastAPI validates pagination.
        query_id = request.query_params.get("user_id")
        try:
            other_user = query_id is not None and int(query_id) != user.id
        except ValueError:
            other_user = False
        if other_user or request.query_params.get("all_users", "").lower() in {
            "true",
            "1",
            "yes",
            "on",
        }:
            raise APIError(403, "permission denied")
    return user


@router.get("/")
async def list_submissions(
    request: Request,
    user_id: int | None = None,
    problem_id: str | None = None,
    status: str | None = Query(default=None, pattern="^(pending|success|error)$"),
    outcome: str | None = Query(default=None, pattern="^(passed|not_passed)$"),
    verdict: str | None = None,
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1),
    all_users: bool = False,
    include_metadata: bool = False,
    user: CurrentUser = Depends(submission_reader),
) -> JSONResponse:
    if verdict is not None and verdict not in VERDICT_LABELS:
        raise APIError(422, "invalid verdict")
    if all_users and user.role != "admin":
        raise APIError(403, "permission denied")
    if user_id is None and problem_id is None and not all_users:
        raise APIError(400, "user_id or problem_id is required")
    if page is not None and page_size is None:
        raise APIError(400, "page_size is required when page is provided")
    if user.role != "admin":
        if user_id is not None and user_id != user.id:
            raise APIError(403, "permission denied")
        user_id = user.id

    clauses: list[str] = []
    params: list[object] = []
    if user_id is not None:
        clauses.append("user_id=?")
        params.append(user_id)
    if problem_id is not None:
        clauses.append("problem_id=?")
        params.append(problem_id)
    if status is not None:
        clauses.append("status=?")
        params.append(status)
    if outcome == "passed":
        clauses.append("status='success' AND score=counts AND counts>0")
    elif outcome == "not_passed":
        clauses.append(
            "(status='error' OR (status='success' AND "
            "(score IS NULL OR counts IS NULL OR counts=0 OR score<counts)))"
        )
    if verdict == "AC":
        clauses.append("status='success' AND counts>0 AND score=counts")
    elif verdict == "partial":
        clauses.append("status='success' AND counts>0 AND score>0 AND score<counts")
    where = " AND ".join(clauses) or "1=1"
    if verdict is not None and verdict not in {"AC", "partial"}:
        # Classify only authorized, visible results before counting or paginating.
        # Bounded batches avoid loading source code for the entire submission history.
        matches: list[dict[str, Any]] = []
        total_matches = 0
        offset = 0
        start = ((page or 1) - 1) * page_size if page_size else 0
        while True:
            batch = await request.app.state.db.fetchall(
                "SELECT s.id,s.user_id,s.problem_id,s.language,s.status,s.score,s.counts,"  # noqa: S608
                "s.compile_info,s.created_at,s.problem_deleted,u.username FROM submissions s "
                f"LEFT JOIN users u ON u.id=s.user_id WHERE {where} "
                "ORDER BY s.id DESC LIMIT 500 OFFSET ?",
                [*params, offset],
            )
            if not batch:
                break
            visible = await visible_evaluations(request, user, batch)
            for row in batch:
                if visible[row["id"]]["verdict"] != verdict:
                    continue
                if total_matches >= start and (page_size is None or len(matches) < page_size):
                    item: dict[str, Any] = {
                        "submission_id": str(row["id"]),
                        "status": row["status"],
                    }
                    if row["status"] == "success":
                        item.update(score=row["score"], counts=row["counts"])
                    if include_metadata:
                        item.update(
                            {k: row[k] for k in ("user_id", "problem_id", "language", "created_at")}
                        )
                        item["problem_deleted"] = bool(row["problem_deleted"])
                        item["evaluation"] = visible[row["id"]]
                        item["username"] = row["username"]
                    matches.append(item)
                total_matches += 1
            offset += len(batch)
        return response(data={"total": total_matches, "submissions": matches})
    total = await request.app.state.db.fetchone(
        f"SELECT COUNT(*) AS n FROM submissions WHERE {where}",  # noqa: S608
        params,
    )
    sql = (
        "SELECT s.*,u.username FROM submissions s LEFT JOIN users u ON u.id=s.user_id "  # noqa: S608
        f"WHERE {where} ORDER BY s.id DESC"
    )
    if page_size is not None:
        page = page or 1
        sql += " LIMIT ? OFFSET ?"
        params.extend(page_window(page, page_size, total["n"]))
    rows = await request.app.state.db.fetchall(sql, params)
    evaluations = await visible_evaluations(request, user, rows) if include_metadata else {}
    items = []
    for row in rows:
        item = summary_from_row(row, include_metadata)
        if include_metadata:
            item["evaluation"] = evaluations[row["id"]]
            item["username"] = row["username"]
        items.append(item)
    return response(data={"total": total["n"], "submissions": items})


@router.get("/{submission_id}")
async def get_submission(
    request: Request,
    submission_id: int,
    include_metadata: bool = False,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    row = await request.app.state.db.fetchone(
        "SELECT s.*,u.username FROM submissions s LEFT JOIN users u ON u.id=s.user_id WHERE s.id=?",
        (submission_id,),
    )
    if row is None:
        raise APIError(404, "submission not found")
    if user.role != "admin" and row["user_id"] != user.id:
        raise APIError(403, "permission denied")
    data = detail_from_row(row, include_metadata)
    if include_metadata:
        data["evaluation"] = (await visible_evaluations(request, user, [row]))[submission_id]
        data["username"] = row["username"]
    return response(data=data)


@router.put("/{submission_id}/rejudge")
async def rejudge(
    request: Request,
    submission_id: int,
    _admin: CurrentUser = Depends(require_admin),
) -> JSONResponse:
    row = await request.app.state.db.fetchone(
        "SELECT id,problem_id,problem_deleted FROM submissions WHERE id=?", (submission_id,)
    )
    if row is None:
        raise APIError(404, "submission not found")
    if row["problem_deleted"] or await request.app.state.problems.get(row["problem_id"]) is None:
        raise APIError(
            409, "the problem was deleted; this historical submission cannot be rejudged"
        )
    await request.app.state.submissions.cancel_one(submission_id)
    async with request.app.state.db.connect() as db:
        await db.execute("DELETE FROM submission_cases WHERE submission_id=?", (submission_id,))
        await db.execute(
            """UPDATE submissions SET status='pending',score=NULL,counts=NULL,
               compile_info=NULL,run_info=NULL,error_info=NULL,updated_at=? WHERE id=?""",
            (now_iso(), submission_id),
        )
        await db.commit()
    request.app.state.submissions.schedule(submission_id)
    return response(
        200,
        "rejudge started",
        {"submission_id": str(submission_id), "status": "pending"},
    )
