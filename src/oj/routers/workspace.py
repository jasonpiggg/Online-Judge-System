from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import JSONResponse

from oj.auth import CurrentUser, get_current_user
from oj.errors import APIError, response
from oj.languages import get_language
from oj.schemas import WorkspaceDraftUpdate
from oj.submissions import now_iso

router = APIRouter(prefix="/api/workspace-drafts")


@router.get("/{problem_id}/{language}")
async def get_workspace_draft(
    request: Request,
    problem_id: str = Path(pattern=r"^[A-Za-z0-9_-]{1,64}$"),
    language: str = Path(pattern=r"^[a-z][a-z0-9_+-]{0,31}$"),
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    row = await request.app.state.db.fetchone(
        """SELECT problem_id,language,code,revision,updated_at FROM workspace_drafts
           WHERE user_id=? AND problem_id=? AND language=?""",
        (user.id, problem_id, language),
    )
    return response(data=dict(row) if row else None)


@router.put("/{problem_id}/{language}")
async def save_workspace_draft(
    request: Request,
    body: WorkspaceDraftUpdate,
    problem_id: str = Path(pattern=r"^[A-Za-z0-9_-]{1,64}$"),
    language: str = Path(pattern=r"^[a-z][a-z0-9_+-]{0,31}$"),
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    problem = await request.app.state.problems.get(problem_id)
    registered = await get_language(request.app.state.db, language)
    if problem is None or registered is None:
        raise APIError(404, "problem or language not found")
    updated_at = now_iso()
    await request.app.state.db.execute(
        """INSERT INTO workspace_drafts
           (user_id,problem_id,language,code,revision,updated_at) VALUES(?,?,?,?,1,?)
           ON CONFLICT(user_id,problem_id,language) DO UPDATE SET
           code=excluded.code,revision=workspace_drafts.revision+1,
           updated_at=excluded.updated_at""",
        (user.id, problem_id, language, body.code, updated_at),
    )
    row = await request.app.state.db.fetchone(
        """SELECT problem_id,language,code,revision,updated_at FROM workspace_drafts
           WHERE user_id=? AND problem_id=? AND language=?""",
        (user.id, problem_id, language),
    )
    return response(200, "draft saved", dict(row))


@router.delete("/{problem_id}/{language}")
async def delete_workspace_draft(
    request: Request,
    problem_id: str = Path(pattern=r"^[A-Za-z0-9_-]{1,64}$"),
    language: str = Path(pattern=r"^[a-z][a-z0-9_+-]{0,31}$"),
    user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    await request.app.state.db.execute(
        "DELETE FROM workspace_drafts WHERE user_id=? AND problem_id=? AND language=?",
        (user.id, problem_id, language),
    )
    return response(200, "draft deleted")
