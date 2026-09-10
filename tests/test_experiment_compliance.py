from __future__ import annotations

import inspect
from typing import Any

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient

from scripts.reset_password import reset_password
from tests.conftest import login_admin


def test_every_course_api_endpoint_is_async(app: Any) -> None:
    """A synchronous course route would invalidate the entire functional score."""

    # FastAPI 0.116+ keeps included routers deferred, so inspect both direct routes
    # and the source routers rather than depending on one framework representation.
    routes = []
    for route in app.routes:
        included = getattr(route, "original_router", None)
        routes.extend(included.routes if included is not None else [route])
    course_routes = [
        route
        for route in routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/")
    ]
    assert course_routes
    assert all(inspect.iscoroutinefunction(route.endpoint) for route in course_routes)


async def test_extension_parameter_errors_follow_course_http_400_contract(
    client: AsyncClient,
) -> None:
    await login_admin(client)
    result = await client.get(
        "/api/submissions/", params={"user_id": 1, "verdict": "not-a-verdict"}
    )
    assert result.status_code == result.json()["code"] == 400


async def test_authentication_precedes_malformed_json(client: AsyncClient, app: Any) -> None:
    headers = {"content-type": "application/json"}
    for path in ("/api/problems/", "/api/users/admin", "/api/submissions/"):
        result = await client.post(path, content="{", headers=headers)
        assert result.status_code == result.json()["code"] == 401
    await client.post("/api/users/", json={"username": "regular", "password": "secret1"})
    await client.post("/api/auth/login", json={"username": "regular", "password": "secret1"})
    assert (await client.post("/api/users/admin", content="{", headers=headers)).status_code == 403
    assert (await client.post("/api/problems/", content="{", headers=headers)).status_code == 400
    await app.state.db.execute("UPDATE users SET role='banned' WHERE username='regular'")
    assert (await client.post("/api/problems/", content="{", headers=headers)).status_code == 403


@pytest.mark.parametrize("password", ["a" * 72, "密" * 24, "🙂" * 18])
async def test_password_byte_boundary(client: AsyncClient, password: str) -> None:
    credentials = {"username": "boundary", "password": password}
    assert (await client.post("/api/users/", json=credentials)).status_code == 200
    assert (await client.post("/api/auth/login", json=credentials)).status_code == 200
    credentials["password"] += "X"
    assert (await client.post("/api/auth/login", json=credentials)).status_code == 400
    credentials["username"] = "too_long"
    assert (await client.post("/api/users/", json=credentials)).status_code == 400


async def test_large_course_pagination(client: AsyncClient) -> None:
    await login_admin(client)
    for path, scope, key in (
        ("/api/users/", {}, "users"),
        ("/api/submissions/", {"user_id": 1}, "submissions"),
        ("/api/logs/access/", {"user_id": 1}, None),
    ):
        for size in (101, 10**40):
            result = await client.get(path, params={**scope, "page_size": size})
            assert result.status_code == 200
            empty = await client.get(path, params={**scope, "page_size": size, "page": 10**40})
            assert empty.status_code == 200
            data = empty.json()["data"]
            assert (data[key] if key else data) == []


async def test_operator_reset_revokes_sessions(client: AsyncClient, app: Any) -> None:
    await login_admin(client)
    await reset_password(app.state.db, "admin", "changed-password")
    assert (await client.get("/api/users/1")).status_code == 401
    result = await client.post(
        "/api/auth/login", json={"username": "admin", "password": "changed-password"}
    )
    assert result.status_code == 200


def test_empty_records_keep_public_log_lookup(monkeypatch: Any) -> None:
    from streamlit.testing.v1 import AppTest

    from frontend.client import ApiClient

    def request(_self: Any, _method: str, path: str, **_kwargs: Any) -> dict[str, Any]:
        data: Any = [] if path == "/api/problems/" else {"total": 0, "submissions": []}
        return {"code": 200, "msg": "success", "data": data}

    monkeypatch.setattr(ApiClient, "request", request)
    view = AppTest.from_string('''
import streamlit as st
from frontend.records import records_page
from frontend.client import ApiClient
st.session_state.user = {"user_id": "2", "role": "user"}
records_page(ApiClient())
''').run()
    assert not view.exception
    assert any(widget.label == "公开提交 ID" for widget in view.text_input)
