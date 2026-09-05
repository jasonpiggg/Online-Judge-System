from __future__ import annotations

import asyncio

from httpx import AsyncClient

from tests.conftest import login_admin


async def _create_finished_submission(
    client: AsyncClient, problem_payload: dict[str, object]
) -> str:
    await client.post("/api/problems/", json=problem_payload)
    result = await client.post(
        "/api/submissions/",
        json={
            "problem_id": "sum_2",
            "language": "python",
            "code": "print(sum(map(int,input().split())))",
        },
    )
    submission_id = result.json()["data"]["submission_id"]
    for _ in range(100):
        detail = await client.get(f"/api/submissions/{submission_id}")
        if detail.json()["data"]["status"] != "pending":
            break
        await asyncio.sleep(0.03)
    return submission_id


async def test_private_public_logs_and_audit(
    client: AsyncClient, problem_payload: dict[str, object]
) -> None:
    alice = await client.post(
        "/api/users/", json={"username": "alice", "password": "secret1"}
    )
    alice_id = alice.json()["data"]["user_id"]
    await client.post("/api/users/", json={"username": "bobby", "password": "secret2"})
    await client.post(
        "/api/auth/login", json={"username": "alice", "password": "secret1"}
    )
    submission_id = await _create_finished_submission(client, problem_payload)
    own_log = await client.get(f"/api/submissions/{submission_id}/log")
    assert own_log.status_code == 200
    own_data = own_log.json()["data"]
    assert len(own_data["details"]) == 2
    assert set(own_data) == {"details", "score", "counts"}

    client.cookies.clear()
    await client.post(
        "/api/auth/login", json={"username": "bobby", "password": "secret2"}
    )
    assert (await client.get(f"/api/submissions/{submission_id}/log")).status_code == 403

    client.cookies.clear()
    await login_admin(client)
    visibility = await client.put(
        "/api/problems/sum_2/log_visibility", json={"public_cases": True}
    )
    assert visibility.status_code == 200
    admin_log = (await client.get(f"/api/submissions/{submission_id}/log")).json()["data"]
    assert set(admin_log) == {"details", "score", "counts"}
    audit = await client.get("/api/logs/access/", params={"user_id": alice_id})
    assert audit.status_code == 200
    assert audit.json()["data"][0]["status"] == "200"

    client.cookies.clear()
    await client.post(
        "/api/auth/login", json={"username": "bobby", "password": "secret2"}
    )
    public_log = await client.get(f"/api/submissions/{submission_id}/log")
    assert public_log.status_code == 200
    public_data = public_log.json()["data"]
    assert set(public_data) == {"details", "score", "counts"}


async def test_admin_reset(client: AsyncClient, problem_payload: dict[str, object]) -> None:
    await login_admin(client)
    await client.post("/api/problems/", json=problem_payload)
    reset = await client.post("/api/reset/")
    assert reset.status_code == 200
    assert (await client.get("/api/problems/")).status_code == 401
    await login_admin(client)
    assert (await client.get("/api/problems/")).json()["data"] == []
