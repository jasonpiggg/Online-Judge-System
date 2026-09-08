from __future__ import annotations

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from oj.config import Settings


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "http://localhost:8501/path",
        "null",
        "http://user:pass@localhost:8501",
        "http://localhost:99999",
    ],
)
def test_streamlit_origins_reject_non_origin_values(origin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, streamlit_origins=[origin])


async def test_bridge_only_exposes_exact_auth_origins_and_methods(client: AsyncClient) -> None:
    origin = "http://127.0.0.1:8501"
    preflight = {
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    response = await client.options("/api/auth/login", headers=preflight)
    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
    for path, headers in [
        ("/api/problems/", preflight),
        ("/api/auth/login", {**preflight, "Origin": origin + ".evil.test"}),
        ("/api/auth/login", {**preflight, "Access-Control-Request-Method": "DELETE"}),
        ("/api/auth/login", {**preflight, "Access-Control-Request-Headers": "x-oj-user"}),
    ]:
        denied = await client.options(path, headers=headers)
        assert "access-control-allow-origin" not in denied.headers


async def test_bridge_cookie_login_identity_and_logout(client: AsyncClient) -> None:
    headers = {"Origin": "http://127.0.0.1:8501", "Sec-Fetch-Site": "same-site"}
    login = await client.post(
        "/api/auth/login",
        headers=headers,
        json={"username": "admin", "password": "admintestpassword"},
    )
    assert login.status_code == 200
    cookie = login.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    identity = await client.get("/api/auth/me", headers=headers)
    assert identity.json()["data"]["role"] == "admin"
    denied = await client.post("/api/problems/", headers=headers, content="{")
    assert denied.status_code == 403
    assert "access-control-allow-origin" not in denied.headers
    assert (await client.post("/api/auth/logout", headers=headers)).status_code == 200
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 401


async def test_bridge_cannot_bypass_cross_site_boundary(client: AsyncClient) -> None:
    r = await client.post(
        "/api/auth/login",
        headers={"Origin": "http://127.0.0.1:8501", "Sec-Fetch-Site": "cross-site"},
        json={"username": "admin", "password": "admintestpassword"},
    )
    assert r.status_code == 403
