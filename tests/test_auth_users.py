from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import login_admin


async def test_initial_admin_login_and_logout(client: AsyncClient) -> None:
    await login_admin(client)
    me = await client.get("/api/users/1")
    assert me.status_code == 200
    assert me.json()["data"]["role"] == "admin"
    assert "password" not in str(me.json()).lower()
    assert (await client.post("/api/auth/logout")).status_code == 200
    assert (await client.get("/api/users/1")).status_code == 401


async def test_register_permissions_and_ban(client: AsyncClient) -> None:
    created = await client.post(
        "/api/users/", json={"username": "alice", "password": "secret1"}
    )
    assert created.status_code == 200
    user_id = created.json()["data"]["user_id"]
    assert (await client.get(f"/api/users/{user_id}")).status_code == 401

    login = await client.post(
        "/api/auth/login", json={"username": "alice", "password": "secret1"}
    )
    assert login.status_code == 200
    assert (await client.get(f"/api/users/{user_id}")).status_code == 200
    assert (await client.get("/api/users/1")).status_code == 403
    assert (await client.get("/api/users/")).status_code == 403

    client.cookies.clear()
    await login_admin(client)
    users = await client.get("/api/users/", params={"page_size": 10})
    assert users.json()["data"]["total"] == 2
    assert (
        await client.put(f"/api/users/{user_id}/role", json={"role": "banned"})
    ).status_code == 200
    client.cookies.clear()
    banned = await client.post(
        "/api/auth/login", json={"username": "alice", "password": "secret1"}
    )
    assert banned.status_code == 403


async def test_validation_uses_400(client: AsyncClient) -> None:
    response = await client.post("/api/users/", json={"username": "x", "password": "1"})
    assert response.status_code == 400
    assert response.json()["code"] == 400

