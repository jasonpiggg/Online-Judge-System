from __future__ import annotations

import asyncio

from httpx import AsyncClient

from tests.conftest import login_admin


async def _wait_result(client: AsyncClient, submission_id: str) -> dict[str, object]:
    for _ in range(100):
        result = await client.get(f"/api/submissions/{submission_id}")
        if result.json()["data"]["status"] != "pending":
            return result.json()["data"]
        await asyncio.sleep(0.03)
    raise AssertionError("submission did not finish")


async def test_submit_list_detail_and_rejudge(
    client: AsyncClient, problem_payload: dict[str, object]
) -> None:
    await client.post("/api/users/", json={"username": "alice", "password": "secret1"})
    await client.post(
        "/api/auth/login", json={"username": "alice", "password": "secret1"}
    )
    await client.post("/api/problems/", json=problem_payload)
    submitted = await client.post(
        "/api/submissions/",
        json={
            "problem_id": "sum_2",
            "language": "python",
            "code": "a,b=map(int,input().split())\nprint(a+b)",
        },
    )
    assert submitted.status_code == 200
    submission_id = submitted.json()["data"]["submission_id"]
    result = await _wait_result(client, submission_id)
    assert result["score"] == result["counts"] == 20
    listing = await client.get("/api/submissions/", params={"problem_id": "sum_2"})
    assert listing.json()["data"]["total"] == 1
    assert (await client.get("/api/submissions/")).status_code == 400

    client.cookies.clear()
    await login_admin(client)
    rejudge = await client.put(f"/api/submissions/{submission_id}/rejudge")
    assert rejudge.json()["data"]["status"] == "pending"


async def test_submission_rate_limit(
    client: AsyncClient, problem_payload: dict[str, object]
) -> None:
    await login_admin(client)
    await client.post("/api/problems/", json=problem_payload)
    body = {"problem_id": "sum_2", "language": "python", "code": "print(0)"}
    for _ in range(3):
        assert (await client.post("/api/submissions/", json=body)).status_code == 200
    assert (await client.post("/api/submissions/", json=body)).status_code == 429


async def test_progress_and_outcome_filters(
    client: AsyncClient, problem_payload: dict[str, object]
) -> None:
    await client.post("/api/users/", json={"username": "alice", "password": "secret1"})
    await client.post(
        "/api/auth/login", json={"username": "alice", "password": "secret1"}
    )
    await client.post("/api/problems/", json=problem_payload)
    ids = []
    for code in ["a,b=map(int,input().split())\nprint(a+b)", "print(0)"]:
        result = await client.post(
            "/api/submissions/",
            json={"problem_id": "sum_2", "language": "python", "code": code},
        )
        ids.append(result.json()["data"]["submission_id"])
    for submission_id in ids:
        await _wait_result(client, submission_id)

    passed = await client.get(
        "/api/submissions/", params={"problem_id": "sum_2", "outcome": "passed"}
    )
    failed = await client.get(
        "/api/submissions/", params={"problem_id": "sum_2", "outcome": "not_passed"}
    )
    assert passed.json()["data"]["total"] == 1
    assert failed.json()["data"]["total"] == 1

    problems = await client.get(
        "/api/problems/", params={"include_metadata": True, "include_progress": True}
    )
    progress = problems.json()["data"][0]["progress"]
    assert progress["attempts"] == 2
    assert progress["passed"] == 1
    assert progress["best_ratio"] == 1

