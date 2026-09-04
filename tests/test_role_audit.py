from fastapi import FastAPI
from httpx import AsyncClient

from tests.conftest import login_admin


async def test_role_change_is_atomic_and_separate_from_access_logs(
    client: AsyncClient, app: FastAPI
) -> None:
    await login_admin(client)
    created = await client.post(
        "/api/users/", json={"username": "role-target", "password": "secret-123"}
    )
    target = created.json()["data"]["user_id"]
    for role in ["admin", "banned", "user"]:
        assert (
            await client.put(f"/api/users/{target}/role", json={"role": role})
        ).status_code == 200
    rows = await app.state.db.fetchall("SELECT * FROM role_change_logs ORDER BY id")
    assert [(r["old_role"], r["new_role"]) for r in rows] == [
        ("user", "admin"),
        ("admin", "banned"),
        ("banned", "user"),
    ]
    assert all(r["actor_id"] == 1 and r["target_id"] == int(target) and r["time"] for r in rows)
    assert await app.state.db.fetchall("SELECT * FROM access_logs") == []
    assert (await client.put("/api/users/999/role", json={"role": "admin"})).status_code == 404
    assert len(await app.state.db.fetchall("SELECT * FROM role_change_logs")) == 3


async def test_last_administrator_cannot_be_removed(client: AsyncClient) -> None:
    await login_admin(client)
    result = await client.put("/api/users/1/role", json={"role": "banned"})
    assert result.status_code == 409
    profile = await client.get("/api/users/1")
    assert profile.json()["data"]["role"] == "admin"
