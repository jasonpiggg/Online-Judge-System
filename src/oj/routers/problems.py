from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from oj.auth import CurrentUser, get_current_user, require_admin
from oj.errors import APIError, response
from oj.schemas import Problem

router = APIRouter(prefix="/api/problems")


@router.get("/")
async def list_problems(
    request: Request, _user: CurrentUser = Depends(get_current_user)
) -> JSONResponse:
    return response(data=await request.app.state.problems.list())


@router.post("/")
async def add_problem(
    request: Request,
    body: Problem,
    _user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
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
    return response(data=problem.model_dump())


@router.put("/{problem_id}")
async def update_problem(
    request: Request,
    problem_id: str,
    body: Problem,
    _user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    if body.id != problem_id:
        raise APIError(400, "problem id does not match path")
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

