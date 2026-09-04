from typing import Any

from httpx import AsyncClient

from tests.conftest import login_admin


async def test_admin_user_search_is_literal_and_permission_checked(client: AsyncClient) -> None:
    await login_admin(client)
    created = (
        await client.post(
            "/api/users/",
            json={
                "username": "math%_Student",
                "password": "test-password",
            },
        )
    ).json()["data"]
    for query in ["%_", "STUDENT", created["user_id"]]:
        found = (
            await client.get("/api/users/", params={"q": query, "page": 1, "page_size": 1})
        ).json()["data"]
        assert found["total"] == 1 and found["users"][0]["user_id"] == created["user_id"]
    assert (await client.get("/api/users/", params={"q": "' OR 1=1--"})).json()["data"][
        "total"
    ] == 0
    await client.post(
        "/api/auth/login", json={"username": "math%_Student", "password": "test-password"}
    )
    assert (await client.get("/api/users/", params={"q": "admin"})).status_code == 403


async def test_submission_names_preserve_metadata_and_owner_boundaries(
    client: AsyncClient,
    app: Any,
    problem_payload: dict[str, Any],
) -> None:
    await login_admin(client)
    await client.post("/api/problems/", json=problem_payload)
    owner = (
        await client.post(
            "/api/users/", json={"username": "student-record", "password": "secret123"}
        )
    ).json()["data"]
    # Insert a completed record: this verifies API metadata without invoking another judge.
    sid = await app.state.db.execute(
        "INSERT INTO submissions(user_id,problem_id,language,code,status,created_at,updated_at) "
        "VALUES(?,?,?,'private source','error','2026-09-04','2026-09-04')",
        (int(owner["user_id"]), "sum_2", "python"),
    )
    data = (
        await client.get("/api/submissions/", params={"all_users": True, "include_metadata": True})
    ).json()["data"]
    assert data["submissions"][0]["username"] == "student-record"
    assert "code" not in data["submissions"][0]
    legacy = (await client.get("/api/submissions/", params={"all_users": True})).json()["data"]
    assert "username" not in legacy["submissions"][0]
    detail = (
        await client.get(f"/api/submissions/{sid}", params={"include_metadata": True})
    ).json()["data"]
    assert detail["username"] == "student-record" and detail["code"] == "private source"
    await client.post("/api/users/", json={"username": "other-student", "password": "secret123"})
    await client.post(
        "/api/auth/login", json={"username": "other-student", "password": "secret123"}
    )
    assert (await client.get(f"/api/submissions/{sid}?include_metadata=true")).status_code == 403
    assert (
        await client.get("/api/submissions/?all_users=true&include_metadata=true")
    ).status_code == 403


async def test_role_audit_has_pagination_and_is_admin_only(client: AsyncClient) -> None:
    await login_admin(client)
    target = (
        await client.post("/api/users/", json={"username": "audit-target", "password": "secret123"})
    ).json()["data"]["user_id"]
    for role in ["banned", "user"]:
        await client.put(f"/api/users/{target}/role", json={"role": role})
    result = (await client.get("/api/logs/roles/?page=1&page_size=1")).json()["data"]
    assert len(result) == 1 and result[0]["new_role"] == "user"
    assert result[0]["actor_name"] == "admin" and result[0]["target_name"] == "audit-target"
    assert (await client.get("/api/logs/roles/?page=2&page_size=1")).json()["data"][0][
        "new_role"
    ] == "banned"
    assert (await client.get("/api/logs/roles/?page=3&page_size=1")).json()["data"] == []
    metadata = (
        await client.get(
            "/api/logs/roles/",
            params={"page": 1, "page_size": 1, "include_metadata": True},
        )
    ).json()["data"]
    assert metadata["total"] == 2 and len(metadata["logs"]) == 1
    assert (await client.get("/api/logs/roles/?page_size=101")).status_code == 400
    await client.post("/api/auth/login", json={"username": "audit-target", "password": "secret123"})
    assert (await client.get("/api/logs/roles/")).status_code == 403
    await client.post("/api/auth/logout")
    assert (await client.get("/api/logs/roles/")).status_code == 401
