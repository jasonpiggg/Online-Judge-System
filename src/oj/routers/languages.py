from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from oj.auth import CurrentUser, get_current_user
from oj.errors import response
from oj.languages import add_language
from oj.schemas import Language

router = APIRouter(prefix="/api/languages")


@router.get("/")
async def list_languages(request: Request, include_metadata: bool = False) -> JSONResponse:
    rows = await request.app.state.db.fetchall("SELECT * FROM languages ORDER BY name")
    data: dict[str, object] = {"name": [row["name"] for row in rows]}
    if include_metadata:
        data["languages"] = [dict(row) for row in rows]
    return response(data=data)


@router.post("/")
async def register_language(
    request: Request,
    body: Language,
    _user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    await add_language(request.app.state.db, body)
    return response(200, "language registered", {"name": body.name})
