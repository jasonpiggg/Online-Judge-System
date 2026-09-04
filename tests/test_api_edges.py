from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests.conftest import login_admin
from tests.test_submissions import _wait_result


async def test_parallel_rate_limit_is_atomic(
    client: AsyncClient, problem_payload: dict[str, Any]
) -> None:
    await login_admin(client)
    await client.post("/api/problems/", json=problem_payload)
    responses = await asyncio.gather(
        *[
            client.post(
                "/api/submissions/",
                json={"problem_id": "sum_2", "language": "python", "code": "print(3)"},
            )
            for _ in range(6)
        ]
    )
    assert sorted(r.status_code for r in responses) == [200, 200, 200, 429, 429, 429]


async def test_permission_priority_before_bad_pagination(client: AsyncClient) -> None:
    await client.post("/api/users/", json={"username": "reader", "password": "secret1"})
    await client.post("/api/auth/login", json={"username": "reader", "password": "secret1"})
    for params in [
        {"user_id": 1, "page": 1},
        {"user_id": 1, "page": -1},
        {"all_users": True, "page": 0},
    ]:
        result = await client.get("/api/submissions/", params=params)
        assert result.status_code == 403


async def test_auth_session_rotation_expiry_and_ban(client: AsyncClient, app: FastAPI) -> None:
    await login_admin(client)
    cookie = client.cookies.get("oj_session")
    await login_admin(client)
    assert cookie != client.cookies.get("oj_session")
    assert await app.state.db.fetchone("SELECT * FROM sessions WHERE id=?", (cookie,)) is None
    await app.state.db.execute("UPDATE sessions SET expires_at='2000-01-01T00:00:00+00:00'")
    assert (await client.get("/api/problems/")).status_code == 401
    assert await app.state.db.fetchall("SELECT * FROM sessions") == []
    client.cookies.set("oj_session", "unknown", domain="testserver.local", path="/")
    assert (await client.get("/api/problems/")).status_code == 401
    client.cookies.clear()
    await login_admin(client)
    await app.state.db.execute("UPDATE users SET role='banned' WHERE id=1")
    assert (await client.get("/api/problems/")).status_code == 403


async def test_admin_boundary_matrix(client: AsyncClient, problem_payload: dict[str, Any]) -> None:
    assert (await client.get("/api/submissions/bad/log")).status_code == 401
    assert (
        await client.post("/api/auth/login", json={"username": "nobody", "password": "badpass"})
    ).status_code == 401
    await login_admin(client)
    assert (await client.get("/api/ai/model-config")).json()["data"] == {
        "api_key_configured": False,
        "source": "none",
        "system_configured": False,
        "personal_configured": False,
    }
    assert (
        await client.put(
            "/api/ai/model-config", json={"provider_url": "http://a.test", "model": "m"}
        )
    ).status_code == 400
    for method, path in [
        ("get", "/api/users/999"),
        ("get", "/api/submissions/999"),
        ("put", "/api/submissions/999/rejudge"),
        ("get", "/api/submissions/999/log"),
        ("delete", "/api/problems/missing"),
        ("get", "/api/ai/problem-tasks/missing"),
        ("put", "/api/ai/problem-tasks/missing/cancel"),
    ]:
        response = await client.request(method, path)
        assert response.status_code == response.json()["code"] == 404, path
    assert (await client.put("/api/problems/sum_2", json=problem_payload)).status_code == 404
    assert (
        await client.put("/api/problems/missing/log_visibility", json={"public_cases": True})
    ).status_code == 404
    for path in ["/api/users/", "/api/logs/access/", "/api/submissions/?user_id=1"]:
        assert (
            await client.get(
                path, params={"page": 1, **({"user_id": 1} if "submissions" in path else {})}
            )
        ).status_code == 400
    body = {"username": "duplicate", "password": "secret1"}
    assert (await client.post("/api/users/admin", json=body)).status_code == 200
    assert (await client.post("/api/users/", json=body)).status_code == 400
    assert (await client.get("/api/users/", params={"page": 1, "page_size": 1})).json()["data"][
        "total"
    ] == 2
    assert len((await client.get("/api/users/")).json()["data"]["users"]) == 2
    assert (await client.get("/api/languages/", params={"include_metadata": True})).json()["data"][
        "languages"
    ]
    assert (
        await client.post(
            "/api/submissions/",
            json={"problem_id": "missing", "language": "python", "code": "print(0)"},
        )
    ).status_code == 404


async def test_filters_logs_visibility_and_private_summary(
    client: AsyncClient, app: FastAPI, problem_payload: dict[str, Any]
) -> None:
    await login_admin(client)
    await client.post("/api/problems/", json=problem_payload)
    created = await client.post(
        "/api/submissions/", json={"problem_id": "sum_2", "language": "python", "code": "print(3)"}
    )
    sid = created.json()["data"]["submission_id"]
    await _wait_result(client, sid)
    assert (await client.get(f"/api/submissions/{sid}/log")).status_code == 200
    audit = await client.get("/api/logs/access/", params={"problem_id": "sum_2", "page_size": 1})
    assert len(audit.json()["data"]) == 1
    audit_page = await client.get(
        "/api/logs/access/",
        params={
            "problem_id": "sum_2",
            "page": 1,
            "page_size": 1,
            "include_metadata": True,
        },
    )
    assert audit_page.json()["data"]["total"] == 1
    assert len(audit_page.json()["data"]["logs"]) == 1
    blank_scope = await client.get("/api/logs/access/", params={"page": 2, "page_size": 1})
    assert blank_scope.status_code == 400
    filtered = await client.get(
        "/api/submissions/",
        params={"user_id": 1, "problem_id": "sum_2", "status": "success", "page_size": 1},
    )
    assert filtered.json()["data"]["total"] == 1
    assert set(filtered.json()["data"]["submissions"][0]) == {
        "submission_id",
        "status",
        "score",
        "counts",
    }
    user = await client.post("/api/users/", json={"username": "other", "password": "secret1"})
    uid = user.json()["data"]["user_id"]
    await client.put("/api/problems/sum_2/log_visibility", json={"public_cases": True})
    await app.state.db.execute(
        "INSERT INTO ai_tasks(id,user_id,requirement,status,progress,created_at,updated_at) "
        "VALUES('owned',1,'test','pending','','','')"
    )
    await client.post("/api/auth/login", json={"username": "other", "password": "secret1"})
    assert (await client.get(f"/api/submissions/{sid}/log")).status_code == 200
    assert (await client.get(f"/api/submissions/{sid}")).status_code == 403
    assert (await client.get("/api/submissions/", params={"user_id": uid})).json()["data"][
        "total"
    ] == 0
    for path in ["/api/ai/problem-tasks/owned", "/api/ai/problem-tasks/owned/cancel"]:
        result = await client.request("PUT" if path.endswith("cancel") else "GET", path)
        assert result.status_code == 403
    assert (await client.get("/api/logs/access/")).status_code == 403
    assert (await client.put(f"/api/submissions/{sid}/rejudge")).status_code == 403
    count = len(await app.state.db.fetchall("SELECT * FROM access_logs"))
    assert (await client.get("/api/submissions/not-number/log")).status_code == 400
    assert len(await app.state.db.fetchall("SELECT * FROM access_logs")) == count


async def test_general_editor_cannot_bypass_log_admin_permission(
    client: AsyncClient, problem_payload: dict[str, Any]
) -> None:
    await client.post("/api/users/", json={"username": "editor", "password": "secret1"})
    await client.post("/api/auth/login", json={"username": "editor", "password": "secret1"})
    assert (
        await client.post("/api/problems/", json={**problem_payload, "public_cases": True})
    ).status_code == 403
    assert (await client.post("/api/problems/", json=problem_payload)).status_code == 200
    assert (
        await client.put("/api/problems/sum_2", json={**problem_payload, "public_cases": True})
    ).status_code == 403
    await login_admin(client)
    await client.put("/api/problems/sum_2/log_visibility", json={"public_cases": True})
    await client.post("/api/auth/login", json={"username": "editor", "password": "secret1"})
    assert (await client.put("/api/problems/sum_2", json=problem_payload)).status_code == 200
    assert (await client.get("/api/problems/sum_2")).json()["data"]["public_cases"] is True


async def test_lifespan_and_sanitized_error(app: FastAPI, monkeypatch: Any) -> None:
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        ) as client:
            assert (await client.get("/health")).json() == {"status": "ok"}
            await login_admin(client)

            async def broken(*_a: Any, **_kw: Any) -> Any:
                raise RuntimeError("SECRET-SERVER-PATH")

            monkeypatch.setattr(app.state.problems, "list", broken)
            response = await client.get("/api/problems/")
            assert response.status_code == 500 and "SECRET" not in response.text
