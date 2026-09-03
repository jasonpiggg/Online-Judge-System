from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from oj.auth import CurrentUser, get_current_user
from oj.errors import APIError, response
from oj.schemas import AIModelConfig, AIProblemTaskCreate

router = APIRouter(prefix="/api/ai")


@router.get("/model-config")
async def get_model_config(
    request: Request, user: CurrentUser = Depends(get_current_user)
) -> JSONResponse:
    return response(data=await request.app.state.ai_authoring.get_config(user.id))


@router.put("/model-config")
async def model_config(
    request: Request,
    body: AIModelConfig,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    try:
        data = await request.app.state.ai_authoring.save_config(user.id, body)
    except ValueError as exc:
        raise APIError(400, str(exc)) from exc
    return response(200, "model config updated", data)


@router.post("/problem-tasks/")
async def create_problem_task(
    request: Request,
    body: AIProblemTaskCreate,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    config = await request.app.state.db.fetchone(
        "SELECT user_id FROM ai_configs WHERE user_id=?", (user.id,)
    )
    if config is None:
        raise APIError(400, "model configuration is required")
    if body.problem_id and await request.app.state.problems.get(body.problem_id) is None:
        raise APIError(404, "problem not found")
    task_id = await request.app.state.ai_authoring.create(
        user.id, body.requirement, body.problem_id
    )
    return response(200, "task created", {"task_id": task_id, "status": "pending"})


@router.get("/problem-tasks/{task_id}")
async def get_problem_task(
    request: Request,
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    row = await request.app.state.db.fetchone("SELECT * FROM ai_tasks WHERE id=?", (task_id,))
    if row is None:
        raise APIError(404, "AI task not found")
    if user.role != "admin" and row["user_id"] != user.id:
        raise APIError(403, "permission denied")
    result = json.loads(row["result"]) if row["result"] else None
    data = {
        "task_id": row["id"],
        "status": row["status"],
        "progress": row["progress"],
        "stage": row["stage"],
        "usage_details": json.loads(row["usage_details"]) if row["usage_details"] else None,
        "result": result,
        "error": row["error"],
        "usage": {
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "total_tokens": row["input_tokens"] + row["output_tokens"],
            "cost": row["cost"],
            "currency": "USD",
            "source": row["usage_source"],
        },
    }
    return response(data=data)


@router.put("/problem-tasks/{task_id}/cancel")
async def cancel_problem_task(
    request: Request,
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    row = await request.app.state.db.fetchone("SELECT * FROM ai_tasks WHERE id=?", (task_id,))
    if row is None:
        raise APIError(404, "AI task not found")
    if user.role != "admin" and row["user_id"] != user.id:
        raise APIError(403, "permission denied")
    if row["status"] in {"completed", "failed", "cancelled"}:
        raise APIError(409, "AI task has already finished")
    await request.app.state.ai_authoring.cancel(task_id)
    return response(200, "task cancelled", {"task_id": task_id, "status": "cancelled"})
