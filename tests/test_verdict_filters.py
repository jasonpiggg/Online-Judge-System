from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.conftest import login_admin


@pytest.mark.parametrize(
    "verdict,score,maximum,cases,compile_info",
    [
        ("AC", 20, 20, ["AC", "AC"], None),
        ("partial", 10, 20, ["AC", "WA"], None),
        ("CE", 0, 20, [], '{"result":"error"}'),
        ("WA", 0, 20, ["WA", "WA"], None),
        ("TLE", 0, 20, ["TLE", "TLE"], None),
        ("MLE", 0, 20, ["MLE", "MLE"], None),
        ("RE", 0, 20, ["RE", "RE"], None),
        ("failed", 0, 20, ["WA", "RE"], None),
        ("empty", 0, 0, [], None),
        ("unknown", 10, 20, [], None),
    ],
)
async def test_verdict_filter_matches_visible_classification(
    app: FastAPI,
    client: AsyncClient,
    problem_payload: dict[str, Any],
    verdict: str,
    score: int,
    maximum: int,
    cases: list[str],
    compile_info: str | None,
) -> None:
    await login_admin(client)
    await client.post("/api/problems/", json=problem_payload)
    uid = (await app.state.db.fetchone("SELECT id FROM users WHERE role='admin'"))[0]
    for _ in range(2):
        sid = await app.state.db.execute(
            "INSERT INTO submissions(user_id,problem_id,language,code,status,score,counts,"
            "compile_info,created_at,updated_at) VALUES(?,'sum_2','python','secret',"
            "'success',?,?,?,'2026-09-01','2026-09-01')",
            (uid, score, maximum, compile_info),
        )
        for i, result in enumerate(cases):
            await app.state.db.execute(
                "INSERT INTO submission_cases VALUES(?,?,?,0,0,'')", (sid, i, result)
            )
    params = {
        "all_users": True,
        "verdict": verdict,
        "page": 2,
        "page_size": 1,
        "include_metadata": True,
    }
    response = await client.get("/api/submissions/", params=params)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 2 and len(data["submissions"]) == 1
    assert data["submissions"][0]["evaluation"]["verdict"] == verdict
    assert "code" not in data["submissions"][0]
    # Filtering cannot reveal hidden verdicts, even through the returned count.
    await app.state.db.execute("UPDATE users SET role='user' WHERE id=?", (uid,))
    response = await client.get(
        "/api/submissions/",
        params={
            "user_id": uid,
            "verdict": verdict,
            "include_metadata": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["total"] == 0
    private = await client.get("/api/submissions/", params={"user_id": uid, "verdict": "private"})
    assert private.json()["data"]["total"] == 2
