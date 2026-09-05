from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from oj.ai_authoring import utcnow
from oj.auth import CurrentUser, get_current_user
from oj.errors import APIError, response
from oj.schemas import (
    AIModelConfig,
    AIProblemTaskCreate,
    AssistantConversationCreate,
    AssistantMessageCreate,
    DraftProblem,
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
        "SELECT kind,preview,version,stage_started_at,repair_used,payload,recovery_draft_id "
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
                "submission_id": payload.get("submission_id"),
                "workflow_version": payload.get("workflow_version", 1),
                "recovery_draft_id": context["recovery_draft_id"],
                "source_draft_id": payload.get("draft_id"),
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
        "SELECT id,problem_id,context_generation FROM ai_conversations "
        "WHERE user_id=? AND problem_id=?",
        (user.id, body.problem_id),
    )
    return response(data=dict(row))


async def owned_conversation(
    request: Request, conversation_id: str, user: CurrentUser
) -> tuple[str, int]:
    row = await request.app.state.db.fetchone(
        "SELECT problem_id,context_generation FROM ai_conversations WHERE id=? AND user_id=?",
        (conversation_id, user.id),
    )
    if not row:
        raise APIError(404, "conversation not found")
    return str(row["problem_id"]), int(row["context_generation"])


@router.post("/conversations/{conversation_id}/new")
async def new_conversation_topic(
    request: Request,
    conversation_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    await owned_conversation(request, conversation_id, user)
    generation = await request.app.state.ai_authoring.start_new_topic(user.id, conversation_id)
    return response(
        200,
        "new conversation started",
        {"id": conversation_id, "context_generation": generation},
    )


@router.get("/conversations/{conversation_id}/messages")
async def messages(
    request: Request,
    conversation_id: str,
    include_metadata: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=20),
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    _, generation = await owned_conversation(request, conversation_id, user)
    total = await request.app.state.db.fetchone(
        "SELECT COUNT(*) AS n FROM ai_task_context "
        "WHERE conversation_id=? AND context_generation=?",
        (conversation_id, generation),
    )
    limit = page_size if include_metadata else 50
    offset = (page - 1) * page_size if include_metadata else 0
    rows = await request.app.state.db.fetchall(
        "SELECT t.id,t.requirement,t.status,t.result,c.preview,c.payload,t.created_at "
        "FROM ai_tasks t JOIN ai_task_context c ON c.task_id=t.id WHERE c.conversation_id=? "
        "AND c.context_generation=? ORDER BY t.created_at DESC LIMIT ? OFFSET ?",
        (conversation_id, generation, limit, offset),
    )
    data = [
        {
            "task_id": r["id"],
            "message": r["requirement"],
            "status": r["status"],
            "text": (
                json.loads(r["result"] or "{}").get("text")
                or json.loads(r["preview"]).get("text", "")
            ),
            "code_snapshot": json.loads(r["payload"]).get("code", ""),
            "language": json.loads(r["payload"]).get("language"),
            "submission_id": json.loads(r["payload"]).get("submission_id"),
            "created_at": r["created_at"],
        }
        for r in reversed(rows)
    ]
    return response(
        data={"messages": data, "total": int(total["n"]), "page": page}
        if include_metadata
        else data
    )


@router.post("/conversations/{conversation_id}/messages")
async def create_message(
    request: Request,
    conversation_id: str,
    body: AssistantMessageCreate,
    user: CurrentUser = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None),
) -> JSONResponse:
    problem_id, _ = await owned_conversation(request, conversation_id, user)
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
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=100),
    include_metadata: bool = False,
    include_archived: bool = True,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    if page is not None and page_size is None:
        raise APIError(400, "page_size is required when page is provided")
    if include_metadata:
        current_page, size = page or 1, page_size or 50
        where = "user_id=? AND action!='assist'"
        if not include_archived:
            where += " AND archived_at IS NULL"
        total = await request.app.state.db.fetchone(
            f"SELECT COUNT(*) AS n FROM ai_tasks WHERE {where}",  # noqa: S608
            (user.id,),
        )
        list_sql = f"""SELECT id,draft_id,problem_id,action,target_section,status,progress,
                        input_tokens,output_tokens,cost,currency,created_at,updated_at,archived_at
                        FROM ai_tasks WHERE {where}
                        ORDER BY created_at DESC LIMIT ? OFFSET ?"""  # noqa: S608
        rows = await request.app.state.db.fetchall(
            list_sql,
            (user.id, size, (current_page - 1) * size),
        )
        return response(
            data={
                "tasks": [dict(row) for row in rows],
                "total": int(total["n"]),
                "page": current_page,
                "page_size": size,
            }
        )
    rows = await request.app.state.db.fetchall(
        """SELECT id,draft_id,problem_id,action,target_section,status,progress,
           input_tokens,output_tokens,cost,currency,created_at,updated_at
           FROM ai_tasks WHERE user_id=? AND action!='assist'
           ORDER BY created_at DESC LIMIT 50""",
        (user.id,),
    )
    return response(data=[dict(row) for row in rows])


@router.delete("/problem-tasks/{task_id}")
async def archive_problem_task(
    request: Request,
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    row = await request.app.state.db.fetchone("SELECT * FROM ai_tasks WHERE id=?", (task_id,))
    if row is None:
        raise APIError(404, "AI task not found")
    if user.role != "admin" and row["user_id"] != user.id:
        raise APIError(403, "permission denied")
    if row["status"] in {"pending", "running"}:
        await request.app.state.ai_authoring.cancel(task_id)
    await request.app.state.db.execute(
        "UPDATE ai_tasks SET archived_at=COALESCE(archived_at,?),updated_at=? WHERE id=?",
        (utcnow(), utcnow(), task_id),
    )
    current = await request.app.state.db.fetchone(
        "SELECT status,archived_at FROM ai_tasks WHERE id=?", (task_id,)
    )
    return response(
        200,
        "AI task archived",
        {"task_id": task_id, "status": current["status"], "archived": True},
    )


@router.post("/problem-tasks/{task_id}/save-draft")
async def save_problem_task_draft(
    request: Request,
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    task = await request.app.state.db.fetchone("SELECT * FROM ai_tasks WHERE id=?", (task_id,))
    if task is None:
        raise APIError(404, "AI task not found")
    if task["user_id"] != user.id:
        raise APIError(403, "only the task creator may recover its draft")
    if task["status"] not in {"failed", "cancelled"}:
        raise APIError(409, "only a failed or cancelled task can be saved as a recovery draft")
    context = await request.app.state.db.fetchone(
        "SELECT * FROM ai_task_context WHERE task_id=?", (task_id,)
    )
    if context is None or context["kind"] != "authoring":
        raise APIError(409, "this task has no recoverable authoring content")
    if context["recovery_draft_id"]:
        return response(
            data={
                "draft_id": context["recovery_draft_id"],
                "recovered_fields": [],
                "warnings": ["已返回此前保存的恢复草稿。"],
            }
        )
    try:
        result = json.loads(task["result"] or "{}")
    except (TypeError, json.JSONDecodeError):
        result = {}
    payload = json.loads(context["payload"] or "{}")
    try:
        preview = json.loads(context["preview"] or "{}")
    except (TypeError, json.JSONDecodeError):
        preview = {}
    raw_problem = result.get("problem") if isinstance(result.get("problem"), dict) else {}
    if not raw_problem:
        raw_problem = dict(payload.get("base_problem") or {})
        for field in DraftProblem.model_fields:
            if field in preview:
                raw_problem[field] = preview[field]
    recovered: dict[str, object] = {}
    omitted: list[str] = []
    for field in DraftProblem.model_fields:
        if field not in raw_problem:
            continue
        try:
            parsed = DraftProblem.model_validate(
                {field: raw_problem[field]}, context={"legacy": True}
            )
            recovered[field] = getattr(parsed, field)
        except ValueError:
            omitted.append(field)
    if user.role != "admin":
        recovered["public_cases"] = False
    required = (
        "id",
        "title",
        "description",
        "input_description",
        "output_description",
        "samples",
        "constraints",
        "testcases",
    )
    missing = [name for name in required if not recovered.get(name)]
    problem = DraftProblem.model_validate(recovered, context={"legacy": True}).model_dump()
    assets = payload.get("assets") if isinstance(payload.get("assets"), dict) else {}

    def asset(name: str) -> str:
        value = result.get(name, assets.get(name, ""))
        return value[:200_000] if isinstance(value, str) else ""

    review = {
        "recovery": {
            "task_id": task_id,
            "stage": task["stage"],
            "status": task["status"],
            "message": task["error"] or task["progress"],
            "omitted_fields": omitted,
            "missing_fields": missing,
        }
    }
    if isinstance(result.get("review"), str):
        review["ai_review"] = result["review"]
    for name in ("coverage", "wrong_solutions"):
        if name in result:
            review[name] = result[name]
    draft_id, now = "draft-" + secrets.token_urlsafe(12), utcnow()
    snapshot = {
        "id": draft_id,
        "base_problem_id": task["problem_id"],
        "status": "draft",
        "requirement": task["requirement"],
        "problem": problem,
        "reference_solution": asset("reference_solution"),
        "brute_solution": asset("brute_solution"),
        "generator_code": asset("generator_code"),
        "review": review,
        "revision": 1,
        "created_at": now,
        "updated_at": now,
    }
    async with request.app.state.db.connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute(
            "SELECT recovery_draft_id FROM ai_task_context WHERE task_id=?", (task_id,)
        )
        current = await cursor.fetchone()
        if current["recovery_draft_id"]:
            await db.rollback()
            return response(
                data={
                    "draft_id": current["recovery_draft_id"],
                    "recovered_fields": [],
                    "warnings": ["已返回此前保存的恢复草稿。"],
                }
            )
        await db.execute(
            """INSERT INTO problem_drafts
               (id,owner_id,base_problem_id,status,requirement,problem_json,
                reference_solution,brute_solution,generator_code,review_json,
                revision,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                draft_id, user.id, task["problem_id"], "draft", task["requirement"],
                json.dumps(problem, ensure_ascii=False), asset("reference_solution"),
                asset("brute_solution"), asset("generator_code"),
                json.dumps(review, ensure_ascii=False), 1, now, now,
            ),
        )
        await db.execute(
            """INSERT INTO problem_draft_revisions
               (draft_id,revision,source,snapshot_json,change_summary,created_at)
               VALUES(?,?,?,?,?,?)""",
            (
                draft_id,
                1,
                "ai_recovery",
                json.dumps(snapshot, ensure_ascii=False),
                "从失败的 AI 任务恢复",
                now,
            ),
        )
        await db.execute(
            "UPDATE ai_task_context SET recovery_draft_id=?,version=version+1 WHERE task_id=?",
            (draft_id, task_id),
        )
        await db.commit()
    warnings = [f"已忽略无法安全恢复的字段：{'、'.join(omitted)}"] if omitted else []
    if missing:
        warnings.append("草稿仍缺少必填字段：" + "、".join(missing))
    return response(
        200,
        "recoverable output saved as draft",
        {
            "draft_id": draft_id,
            "recovered_fields": sorted(recovered),
            "missing_fields": missing,
            "warnings": warnings,
        },
    )


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
