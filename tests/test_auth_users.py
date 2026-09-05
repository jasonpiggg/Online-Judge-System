from __future__ import annotations

import asyncio

from httpx import AsyncClient

from oj.errors import APIError
from oj.login_rate_limit import LoginRateLimiter
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
    assert banned.json()["error"]["id"] == "account_disabled"


async def test_validation_uses_400(client: AsyncClient) -> None:
    response = await client.post("/api/users/", json={"username": "x", "password": "1"})
    assert response.status_code == 400
    assert response.json()["code"] == 400
    assert response.json()["error"]["id"] == "validation_error"

    invalid_login = await client.post(
        "/api/auth/login",
        json={"username": "bad name", "password": "secret1"},
    )
    assert invalid_login.status_code == 400
    assert invalid_login.json()["error"]["id"] == "validation_error"


async def test_login_error_ids_and_dummy_password_check(
    client: AsyncClient, monkeypatch: object
) -> None:
    import oj.routers.auth_users as auth_users

    await client.post("/api/users/", json={"username": "alice", "password": "secret1"})
    calls: list[bytes] = []
    original = auth_users.verify_password

    async def recording_verify(password: str, password_hash: bytes) -> bool:
        calls.append(password_hash)
        return await original(password, password_hash)

    monkeypatch.setattr(auth_users, "verify_password", recording_verify)  # type: ignore[attr-defined]
    missing = await client.post(
        "/api/auth/login", json={"username": "nobody", "password": "secret1"}
    )
    wrong = await client.post(
        "/api/auth/login", json={"username": "alice", "password": "wrongpw"}
    )
    assert missing.status_code == wrong.status_code == 401
    assert missing.json()["error"]["id"] == "user_not_found"
    assert wrong.json()["error"]["id"] == "incorrect_password"
    assert calls[0] == auth_users.DUMMY_PASSWORD_HASH


async def test_login_rate_limit_is_atomic_for_concurrent_failures(client: AsyncClient) -> None:
    responses = await asyncio.gather(
        *[
            client.post(
                "/api/auth/login",
                json={"username": "parallel-user", "password": "wrongpw"},
            )
            for _ in range(7)
        ]
    )
    statuses = [item.status_code for item in responses]
    assert statuses.count(401) == 5
    assert statuses.count(429) == 2
    limited = next(item for item in responses if item.status_code == 429)
    assert limited.json()["error"]["id"] == "login_rate_limited"
    assert int(limited.headers["Retry-After"]) >= 1


async def test_login_rate_limit_recovers_after_lockout() -> None:
    now = [0.0]
    limiter = LoginRateLimiter(
        account_limit=2,
        account_window=5,
        client_limit=3,
        client_window=10,
        lockout=5,
        clock=lambda: now[0],
    )
    for _ in range(2):
        await limiter.record_failure(await limiter.begin("client", "alice"))
    try:
        await limiter.begin("client", "alice")
    except APIError as error:
        assert error.code == 429
        assert error.headers["Retry-After"] == "5"
    else:
        raise AssertionError("locked account was accepted")
    now[0] = 5
    attempt = await limiter.begin("client", "alice")
    await limiter.record_success(attempt)

    for username in ("a-user", "b-user", "c-user"):
        await limiter.record_failure(await limiter.begin("other-client", username))
    try:
        await limiter.begin("other-client", "d-user")
    except APIError as error:
        assert error.code == 429
    else:
        raise AssertionError("locked client was accepted")
    now[0] = 10
    await limiter.record_success(await limiter.begin("other-client", "d-user"))


async def test_login_rate_limit_bounds_expired_and_attacker_controlled_keys() -> None:
    now = [0.0]
    limiter = LoginRateLimiter(
        account_limit=2,
        account_window=5,
        client_limit=20,
        client_window=10,
        lockout=5,
        max_keys=3,
        clock=lambda: now[0],
    )
    for index in range(8):
        await limiter.record_failure(await limiter.begin(f"client-{index}", f"user-{index}"))
    assert len(limiter._accounts) <= 3
    assert len(limiter._clients) <= 3

    now[0] = 20
    await limiter.record_success(await limiter.begin("fresh-client", "fresh-user"))
    assert not limiter._accounts
    assert not limiter._clients

