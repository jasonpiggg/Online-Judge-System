from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Request

from oj.database import Database
from oj.errors import APIError


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    role: str


def utcnow() -> datetime:
    return datetime.now(UTC)


async def create_session(db: Database, user_id: int, ttl_seconds: int) -> str:
    session_id = secrets.token_urlsafe(32)
    expires = (utcnow() + timedelta(seconds=ttl_seconds)).isoformat()
    await db.execute(
        "INSERT INTO sessions(id, user_id, expires_at) VALUES(?,?,?)",
        (session_id, user_id, expires),
    )
    return session_id


async def get_current_user(request: Request) -> CurrentUser:
    settings = request.app.state.settings
    session_id = request.cookies.get(settings.session_cookie)
    if not session_id:
        raise APIError(401, "authentication required")
    row = await request.app.state.db.fetchone(
        """SELECT users.id, users.username, users.role, sessions.expires_at
           FROM sessions JOIN users ON users.id = sessions.user_id
           WHERE sessions.id = ?""",
        (session_id,),
    )
    if row is None or datetime.fromisoformat(row["expires_at"]) <= utcnow():
        if row is not None:
            await request.app.state.db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        raise APIError(401, "authentication required")
    if row["role"] == "banned":
        raise APIError(403, "user is banned")
    expected_user = request.headers.get("x-oj-user")
    if expected_user is not None and expected_user != str(row["id"]):
        raise APIError(401, "账户已在其他页面切换，请重新登录或刷新页面")
    return CurrentUser(id=row["id"], username=row["username"], role=row["role"])


async def require_admin(request: Request) -> CurrentUser:
    user = await get_current_user(request)
    if user.role != "admin":
        raise APIError(403, "administrator permission required")
    return user

