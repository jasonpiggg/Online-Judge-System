from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from oj.auth import CurrentUser, get_current_user, require_admin
from oj.errors import APIError, response

router = APIRouter(prefix="/api")


@router.get("/logs/roles/")
async def role_logs(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    include_metadata: bool = False,
    _admin: CurrentUser = Depends(require_admin),
) -> JSONResponse:
    rows = await request.app.state.db.fetchall(
        """SELECT l.id,l.actor_id,l.target_id,l.old_role,l.new_role,l.time,
           a.username AS actor_name,t.username AS target_name
           FROM role_change_logs l LEFT JOIN users a ON a.id=l.actor_id
           LEFT JOIN users t ON t.id=l.target_id ORDER BY l.id DESC LIMIT ? OFFSET ?""",
        (page_size, (page - 1) * page_size),
    )
    logs = [dict(row) for row in rows]
    if not include_metadata:
        return response(data=logs)
    total = await request.app.state.db.fetchone("SELECT COUNT(*) AS n FROM role_change_logs")
    return response(data={"logs": logs, "total": int(total["n"])})


async def _audit(request: Request, user_id: int, problem_id: str, status: int) -> None:
    await request.app.state.db.execute(
        """INSERT INTO access_logs(user_id,problem_id,action,time,status)
           VALUES(?,?,'view_logs',?,?)""",
        (user_id, problem_id, datetime.now().strftime("%Y-%m-%d"), str(status)),
    )


@router.get("/submissions/{submission_id}/log")
async def submission_log(
    request: Request,
    submission_id: int,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    submission = await request.app.state.db.fetchone(
        "SELECT user_id,problem_id,score,counts FROM submissions WHERE id=?", (submission_id,)
    )
    if submission is None:
        raise APIError(404, "submission not found")
    problem = await request.app.state.problems.get(submission["problem_id"])
    allowed = bool(
        user.role == "admin"
        or submission["user_id"] == user.id
        or (problem and problem.public_cases)
    )
    await _audit(request, user.id, submission["problem_id"], 200 if allowed else 403)
    if not allowed:
        raise APIError(403, "permission denied")
    rows = await request.app.state.db.fetchall(
        """SELECT case_id,result,time,memory FROM submission_cases
           WHERE submission_id=? ORDER BY case_id""",
        (submission_id,),
    )
    details = [
        {
            "id": row["case_id"],
            "result": row["result"],
            "time": row["time"],
            "memory": row["memory"],
        }
        for row in rows
    ]
    return response(
        data={"details": details, "score": submission["score"], "counts": submission["counts"]}
    )


@router.get("/logs/access/")
async def access_logs(
    request: Request,
    user_id: int | None = None,
    problem_id: str | None = None,
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=100),
    include_metadata: bool = False,
    _admin: CurrentUser = Depends(require_admin),
) -> JSONResponse:
    if page is not None and page_size is None:
        raise APIError(400, "page_size is required when page is provided")
    clauses: list[str] = []
    params: list[object] = []
    if user_id is not None:
        clauses.append("user_id=?")
        params.append(user_id)
    if problem_id is not None:
        clauses.append("problem_id=?")
        params.append(problem_id)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    count_params = tuple(params)
    sql = f"SELECT user_id,problem_id,action,time,status FROM access_logs{where} ORDER BY id DESC"  # noqa: S608
    if page_size is not None:
        page = page or 1
        sql += " LIMIT ? OFFSET ?"
        params.extend((page_size, (page - 1) * page_size))
    rows = await request.app.state.db.fetchall(sql, params)
    logs = [
        {
            "user_id": str(row["user_id"]),
            "problem_id": row["problem_id"],
            "action": row["action"],
            "time": row["time"],
            "status": row["status"],
        }
        for row in rows
    ]
    if not include_metadata:
        return response(data=logs)
    total = await request.app.state.db.fetchone(
        f"SELECT COUNT(*) AS n FROM access_logs{where}",  # noqa: S608
        count_params,
    )
    return response(data={"logs": logs, "total": int(total["n"])})
