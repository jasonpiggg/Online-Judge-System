from __future__ import annotations

from datetime import datetime

import aiosqlite
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from oj.auth import CurrentUser, create_session, get_current_user, require_admin
from oj.errors import APIError, response
from oj.schemas import Credentials, RoleUpdate
from oj.security import hash_password, verify_password

router = APIRouter(prefix="/api")


async def _user_data(db: object, user_id: int) -> dict[str, object] | None:
    row = await db.fetchone(  # type: ignore[attr-defined]
        """SELECT u.id, u.username, u.role, u.join_time,
           COUNT(s.id) AS submit_count,
           COUNT(DISTINCT CASE WHEN s.status='success' AND s.score=s.counts
                          THEN s.problem_id END) AS resolve_count
           FROM users u LEFT JOIN submissions s ON s.user_id=u.id
           WHERE u.id=? GROUP BY u.id""",
        (user_id,),
    )
    if row is None:
        return None
    return {
        "user_id": str(row["id"]),
        "username": row["username"],
        "join_time": row["join_time"],
        "role": row["role"],
        "submit_count": row["submit_count"],
        "resolve_count": row["resolve_count"],
    }


async def _create_user(request: Request, body: Credentials, role: str) -> dict[str, object]:
    password_hash = await hash_password(body.password)
    try:
        user_id = await request.app.state.db.execute(
            "INSERT INTO users(username,password_hash,role,join_time) VALUES(?,?,?,?)",
            (body.username, password_hash, role, datetime.now().strftime("%Y-%m-%d")),
        )
    except aiosqlite.IntegrityError as exc:
        raise APIError(400, "username already exists") from exc
    data = await _user_data(request.app.state.db, user_id)
    assert data is not None
    return data


@router.post("/auth/login")
async def login(request: Request, body: Credentials) -> JSONResponse:
    row = await request.app.state.db.fetchone(
        "SELECT id,username,password_hash,role FROM users WHERE username=?", (body.username,)
    )
    if row is None or not await verify_password(body.password, row["password_hash"]):
        raise APIError(401, "invalid username or password")
    if row["role"] == "banned":
        raise APIError(403, "user is banned")
    old_session = request.cookies.get(request.app.state.settings.session_cookie)
    if old_session:
        await request.app.state.db.execute("DELETE FROM sessions WHERE id=?", (old_session,))
    session_id = await create_session(
        request.app.state.db, row["id"], request.app.state.settings.session_ttl_seconds
    )
    result = response(
        200,
        "login success",
        {"user_id": str(row["id"]), "username": row["username"], "role": row["role"]},
    )
    result.set_cookie(
        request.app.state.settings.session_cookie,
        session_id,
        max_age=request.app.state.settings.session_ttl_seconds,
        httponly=True,
        secure=request.app.state.settings.cookie_secure,
        samesite="lax",
    )
    return result


@router.post("/auth/logout")
async def logout(
    request: Request, _user: CurrentUser = Depends(get_current_user)
) -> JSONResponse:
    session_id = request.cookies.get(request.app.state.settings.session_cookie)
    await request.app.state.db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
    result = response(200, "logout success")
    result.delete_cookie(request.app.state.settings.session_cookie)
    return result


@router.post("/users/")
async def register(request: Request, body: Credentials) -> JSONResponse:
    return response(200, "register success", await _create_user(request, body, "user"))


@router.post("/users/admin")
async def create_admin(
    request: Request,
    body: Credentials,
    _admin: CurrentUser = Depends(require_admin),
) -> JSONResponse:
    data = await _create_user(request, body, "admin")
    return response(
        200,
        "success",
        {"user_id": data["user_id"], "username": data["username"]},
    )


@router.get("/users/{user_id}")
async def get_user(
    request: Request, user_id: int, user: CurrentUser = Depends(get_current_user)
) -> JSONResponse:
    if user.role != "admin" and user.id != user_id:
        raise APIError(403, "permission denied")
    data = await _user_data(request.app.state.db, user_id)
    if data is None:
        raise APIError(404, "user not found")
    return response(data=data)


@router.put("/users/{user_id}/role")
async def update_role(
    request: Request,
    user_id: int,
    body: RoleUpdate,
    _admin: CurrentUser = Depends(require_admin),
) -> JSONResponse:
    existing = await request.app.state.db.fetchone("SELECT id FROM users WHERE id=?", (user_id,))
    if existing is None:
        raise APIError(404, "user not found")
    await request.app.state.db.execute("UPDATE users SET role=? WHERE id=?", (body.role, user_id))
    return response(200, "role updated", {"user_id": str(user_id), "role": body.role})


@router.get("/users/")
async def list_users(
    request: Request,
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=100),
    _admin: CurrentUser = Depends(require_admin),
) -> JSONResponse:
    if page is not None and page_size is None:
        raise APIError(400, "page_size is required when page is provided")
    total_row = await request.app.state.db.fetchone("SELECT COUNT(*) AS n FROM users")
    sql = "SELECT id FROM users ORDER BY id"
    params: tuple[int, ...] = ()
    if page_size is not None:
        page = page or 1
        sql += " LIMIT ? OFFSET ?"
        params = (page_size, (page - 1) * page_size)
    rows = await request.app.state.db.fetchall(sql, params)
    users = [await _user_data(request.app.state.db, row["id"]) for row in rows]
    return response(data={"total": total_row["n"], "users": users})

