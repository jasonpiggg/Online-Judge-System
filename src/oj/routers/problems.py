from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from oj.auth import CurrentUser, get_current_user, require_admin
from oj.errors import APIError, response
from oj.schemas import LogVisibility, Problem

router = APIRouter(prefix="/api/problems")


@router.get("/")
async def list_problems(
    request: Request,
    include_metadata: bool = False,
    include_progress: bool = False,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    problems = await request.app.state.problems.list(include_metadata)
    if include_progress:
        rows = await request.app.state.db.fetchall(
            """SELECT problem_id,COUNT(*) AS attempts,MAX(created_at) AS last_attempt,
               MAX(CASE WHEN status='success' AND score=counts AND counts>0
                   THEN 1 ELSE 0 END) AS passed,
               MAX(CASE WHEN status='success' AND counts>0
                   THEN CAST(score AS REAL)/counts ELSE 0 END) AS best_ratio
               FROM submissions WHERE user_id=? GROUP BY problem_id""",
            (user.id,),
        )
        progress = {row["problem_id"]: dict(row) for row in rows}
        for problem in problems:
            problem["progress"] = progress.get(
                problem["id"],
                {"attempts": 0, "last_attempt": None, "passed": 0, "best_ratio": 0},
            )
    return response(data=problems)


@router.post("/")
async def add_problem(
    request: Request,
    body: Problem,
    _user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    if body.public_cases and _user.role != "admin":
        raise APIError(403, "only administrators may publish logs")
    if not await request.app.state.problems.create(body):
        raise APIError(409, "problem id already exists")
    return response(200, "add success", {"id": body.id})


@router.get("/{problem_id}")
async def get_problem(
    request: Request,
    problem_id: str,
    _user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    problem = await request.app.state.problems.get(problem_id)
    if problem is None:
        raise APIError(404, "problem not found")
    data = problem.model_dump()
    # Preserve course defaults on the wire; explicitly expose inheritance for the editor.
    data["limit_inheritance"] = {
        "time_limit": problem.time_limit is None,
        "memory_limit": problem.memory_limit is None,
    }
    data["time_limit"] = problem.time_limit if problem.time_limit is not None else 3.0
    data["memory_limit"] = problem.memory_limit if problem.memory_limit is not None else 128
    return response(data=data)


@router.put("/{problem_id}")
async def update_problem(
    request: Request,
    problem_id: str,
    body: Problem,
    _user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    if body.id != problem_id:
        raise APIError(400, "problem id does not match path")
    if _user.role != "admin":
        current = await request.app.state.problems.get(problem_id)
        if current:
            if (
                "public_cases" in body.model_fields_set
                and body.public_cases != current.public_cases
            ):
                raise APIError(403, "only administrators may change log visibility")
            body = body.model_copy(update={"public_cases": current.public_cases})
    if not await request.app.state.problems.update(body):
        raise APIError(404, "problem not found")
    return response(200, "update success", {"id": body.id})


@router.delete("/{problem_id}")
async def delete_problem(
    request: Request,
    problem_id: str,
    _admin: CurrentUser = Depends(require_admin),
) -> JSONResponse:
    if not await request.app.state.problems.delete(problem_id):
        raise APIError(404, "problem not found")
    return response(200, "delete success", {"id": problem_id})


@router.put("/{problem_id}/log_visibility")
async def update_log_visibility(
    request: Request,
    problem_id: str,
    body: LogVisibility,
    _admin: CurrentUser = Depends(require_admin),
) -> JSONResponse:
    problem = await request.app.state.problems.get(problem_id)
    if problem is None:
        raise APIError(404, "problem not found")
    updated = problem.model_copy(update={"public_cases": body.public_cases})
    await request.app.state.problems.update(updated)
    return response(
        200,
        "log visibility updated",
        {"problem_id": problem_id, "public_cases": body.public_cases},
    )
