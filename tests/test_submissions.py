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

    other_problem = dict(problem_payload, id="sum_other", title="另一道求和题")
    assert (await client.post("/api/problems/", json=other_problem)).status_code == 200
    other_body = {**body, "problem_id": "sum_other"}
    assert (await client.post("/api/submissions/", json=other_body)).status_code == 200


async def test_deleted_problem_submissions_leave_stats_and_cannot_be_rejudged(
    client: AsyncClient, problem_payload: dict[str, object]
) -> None:
    created_user = await client.post(
        "/api/users/", json={"username": "history-user", "password": "secret1"}
    )
    user_id = created_user.json()["data"]["user_id"]
    await client.post(
        "/api/auth/login", json={"username": "history-user", "password": "secret1"}
    )
    assert (await client.post("/api/problems/", json=problem_payload)).status_code == 200
    submitted = await client.post(
        "/api/submissions/",
        json={
            "problem_id": "sum_2",
            "language": "python",
            "code": "a,b=map(int,input().split())\nprint(a+b)",
        },
    )
    submission_id = submitted.json()["data"]["submission_id"]
    await _wait_result(client, submission_id)
    before = (await client.get("/api/auth/me")).json()["data"]
    assert before["submit_count"] == before["resolve_count"] == 1

    client.cookies.clear()
    await login_admin(client)
    assert (await client.delete("/api/problems/sum_2")).status_code == 200
    detail = await client.get(f"/api/submissions/{submission_id}?include_metadata=true")
    assert detail.json()["data"]["problem_deleted"] is True
    assert (await client.put(f"/api/submissions/{submission_id}/rejudge")).status_code == 409
    assert (await client.post("/api/problems/", json=problem_payload)).status_code == 200

    client.cookies.clear()
    await client.post(
        "/api/auth/login", json={"username": "history-user", "password": "secret1"}
    )
    after = (await client.get("/api/auth/me")).json()["data"]
    assert after["user_id"] == str(user_id)
    assert after["submit_count"] == after["resolve_count"] == 0
    history = await client.get(
        "/api/submissions/",
        params={"user_id": user_id, "include_metadata": True},
    )
    assert history.json()["data"]["submissions"][0]["problem_deleted"] is True
    progress = await client.get(
        "/api/problems/", params={"include_metadata": True, "include_progress": True}
    )
    rebuilt = next(item for item in progress.json()["data"] if item["id"] == "sum_2")
    assert rebuilt["progress"]["attempts"] == rebuilt["progress"]["passed"] == 0


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

