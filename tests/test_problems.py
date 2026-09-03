from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import login_admin


async def test_problem_crud(client: AsyncClient, problem_payload: dict[str, object]) -> None:
    assert (await client.get("/api/problems/")).status_code == 401
    await login_admin(client)
    created = await client.post("/api/problems/", json=problem_payload)
    assert created.status_code == 200
    assert (await client.post("/api/problems/", json=problem_payload)).status_code == 409

    detail = await client.get("/api/problems/sum_2")
    assert detail.json()["data"]["time_limit"] == 3.0
    assert detail.json()["data"]["hint"] == ""
    assert (await client.get("/api/problems/")).json()["data"] == [
        {"id": "sum_2", "title": "两数之和"}
    ]

    changed = dict(problem_payload, title="求和")
    assert (await client.put("/api/problems/sum_2", json=changed)).status_code == 200
    assert (await client.put("/api/problems/other", json=changed)).status_code == 400
    assert (await client.delete("/api/problems/sum_2")).status_code == 200
    assert (await client.get("/api/problems/sum_2")).status_code == 404


async def test_only_admin_can_delete(
    client: AsyncClient, problem_payload: dict[str, object]
) -> None:
    await client.post("/api/users/", json={"username": "alice", "password": "secret1"})
    await client.post(
        "/api/auth/login", json={"username": "alice", "password": "secret1"}
    )
    assert (await client.post("/api/problems/", json=problem_payload)).status_code == 200
    assert (await client.delete("/api/problems/sum_2")).status_code == 403


async def test_problem_validation_and_safe_id(
    client: AsyncClient, problem_payload: dict[str, object]
) -> None:
    await login_admin(client)
    bad = dict(problem_payload, id="../escape")
    result = await client.post("/api/problems/", json=bad)
    assert result.status_code == 400
    missing = dict(problem_payload)
    missing.pop("testcases")
    assert (await client.post("/api/problems/", json=missing)).status_code == 400

