from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

from oj.ai_authoring import utcnow
from oj.auth import CurrentUser, get_current_user
from oj.errors import APIError, response
from oj.schemas import (
    AIModelConfig,
    AIProblemTaskCreate,
    AssistantConversationCreate,
    AssistantMessageCreate,
)

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


@router.delete("/model-config")
async def delete_model_config(
    request: Request, user: CurrentUser = Depends(get_current_user)
) -> JSONResponse:
    data = await request.app.state.ai_authoring.delete_personal_config(user.id)
    return response(200, "personal model configuration removed", data)


@router.post("/problem-tasks/")
async def create_problem_task(
    request: Request,
    body: AIProblemTaskCreate,
    user: CurrentUser = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None),
) -> JSONResponse:
    task_id = await request.app.state.ai_authoring.create_request(
        user.id, body.model_dump(), idempotency_key
    )
    row = await request.app.state.db.fetchone("SELECT status FROM ai_tasks WHERE id=?", (task_id,))
    return response(200, "task created", {"task_id": task_id, "status": row["status"]})


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
        "draft_id": row["draft_id"],
        "problem_id": row["problem_id"],
        "requirement": row["requirement"],
        "action": row["action"],
        "target_section": row["target_section"],
        "status": row["status"],
        "progress": row["progress"],
        "stage": row["stage"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "usage_details": json.loads(row["usage_details"]) if row["usage_details"] else None,
        "result": result,
        "error": row["error"],
        "usage": {
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "total_tokens": row["input_tokens"] + row["output_tokens"],
            "cost": row["cost"],
            "currency": row["currency"],
            "source": row["usage_source"],
        },
    }
    context = await request.app.state.db.fetchone(
        "SELECT kind,preview,version,stage_started_at,repair_used,payload "
        "FROM ai_task_context WHERE task_id=?",
        (task_id,),
    )
    if context:
        payload = json.loads(context["payload"])
        data.update(
            {
                "kind": context["kind"],
                "preview": json.loads(context["preview"]),
                "version": context["version"],
                "stage_started_at": context["stage_started_at"],
                "repair_used": bool(context["repair_used"]),
                "code_snapshot": payload.get("code") if context["kind"] == "assistant" else None,
                "language": payload.get("language"),
                "workflow_version": payload.get("workflow_version", 1),
            }
        )
    return response(data=data)


@router.get("/problem-tasks/{task_id}/events")
@router.get("/assistant-tasks/{task_id}/events")
async def task_events(
    request: Request,
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    await get_problem_task(request, task_id, user)

    async def events() -> AsyncIterator[str]:
        signature = ""
        previous_stage = ""
        while not await request.is_disconnected():
            try:
                current = await get_current_user(request)
                if current.id != user.id:
                    raise APIError(401, "session changed")
                reply = await get_problem_task(request, task_id, current)
            except APIError:
                yield 'event: failed\ndata: {"access_lost":true}\n\n'
                return
            data = json.loads(bytes(reply.body))["data"]
            encoded = json.dumps(data, ensure_ascii=False)
            if encoded != signature:
                status = data["status"]
                event = (
                    status
                    if status in {"completed", "failed", "cancelled"}
                    else ("delta" if data.get("kind") == "assistant" else "preview")
                )
                # Each update is a complete durable snapshot: reconnect needs no paid replay.
                sequence = data.get("version", 0) * 4
                if data["stage"] != previous_stage:
                    yield f"id: {sequence}\nevent: stage\ndata: {encoded}\n\n"
                    previous_stage = data["stage"]
                yield f"id: {sequence + 1}\nevent: usage\ndata: {encoded}\n\n"
                yield f"id: {sequence + 2}\nevent: {event}\ndata: {encoded}\n\n"
                signature = encoded
                if status in {"completed", "failed", "cancelled"}:
                    return
            else:
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/conversations/")
async def conversation(
    request: Request,
    body: AssistantConversationCreate,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    if await request.app.state.problems.get(body.problem_id) is None:
        raise APIError(404, "problem not found")
    await request.app.state.db.execute(
        "INSERT INTO ai_conversations(id,user_id,problem_id,created_at) VALUES(?,?,?,?) "
        "ON CONFLICT(user_id,problem_id) DO NOTHING",
        ("chat-" + secrets.token_urlsafe(12), user.id, body.problem_id, utcnow()),
    )
    row = await request.app.state.db.fetchone(
        "SELECT id,problem_id FROM ai_conversations WHERE user_id=? AND problem_id=?",
        (user.id, body.problem_id),
    )
    return response(data=dict(row))


async def owned_conversation(request: Request, conversation_id: str, user: CurrentUser) -> str:
    row = await request.app.state.db.fetchone(
        "SELECT problem_id FROM ai_conversations WHERE id=? AND user_id=?",
        (conversation_id, user.id),
    )
    if not row:
        raise APIError(404, "conversation not found")
    return str(row["problem_id"])


@router.get("/conversations/{conversation_id}/messages")
async def messages(
    request: Request,
    conversation_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    await owned_conversation(request, conversation_id, user)
    rows = await request.app.state.db.fetchall(
        "SELECT t.id,t.requirement,t.status,t.result,c.preview,c.payload,t.created_at "
        "FROM ai_tasks t JOIN ai_task_context c ON c.task_id=t.id WHERE c.conversation_id=? "
        "ORDER BY t.created_at DESC LIMIT 50",
        (conversation_id,),
    )
    return response(
        data=[
            {
                "task_id": r["id"],
                "message": r["requirement"],
                "status": r["status"],
                "text": (
                    json.loads(r["result"] or "{}").get("text")
                    or json.loads(r["preview"]).get("text", "")
                ),
                "code_snapshot": json.loads(r["payload"]).get("code", ""),
                "created_at": r["created_at"],
            }
            for r in reversed(rows)
        ]
    )


@router.post("/conversations/{conversation_id}/messages")
async def create_message(
    request: Request,
    conversation_id: str,
    body: AssistantMessageCreate,
    user: CurrentUser = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None),
) -> JSONResponse:
    problem_id = await owned_conversation(request, conversation_id, user)
    task_id = await request.app.state.ai_authoring.create_request(
        user.id,
        {**body.model_dump(), "problem_id": problem_id},
        idempotency_key,
        kind="assistant",
        conversation_id=conversation_id,
    )
    return response(data={"task_id": task_id})


@router.get("/assistant-tasks/{task_id}")
async def assistant_task(
    request: Request,
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    return await get_problem_task(request, task_id, user)


@router.get("/problem-tasks/")
async def list_problem_tasks(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    rows = await request.app.state.db.fetchall(
        """SELECT id,draft_id,problem_id,action,target_section,status,progress,
           input_tokens,output_tokens,cost,currency,created_at,updated_at
           FROM ai_tasks WHERE user_id=? AND action!='assist'
           ORDER BY created_at DESC LIMIT 50""",
        (user.id,),
    )
    return response(data=[dict(row) for row in rows])


@router.put("/problem-tasks/{task_id}/cancel")
@router.put("/assistant-tasks/{task_id}/cancel")
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
    current = await request.app.state.db.fetchone(
        "SELECT status FROM ai_tasks WHERE id=?", (task_id,)
    )
    if current["status"] == "completed":
        raise APIError(409, "AI task has already finished")
    return response(200, "task cancelled", {"task_id": task_id, "status": "cancelled"})
