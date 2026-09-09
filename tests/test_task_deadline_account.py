from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.conftest import login_admin


async def test_password_change_revokes_other_sessions(client: AsyncClient) -> None:
    await login_admin(client)
    old_cookie = client.cookies.get("oj_session")
    client.cookies.clear()
    await login_admin(client)
    current = client.cookies.get("oj_session")
    bad = await client.post(
        "/api/auth/password",
        json={
            "current_password": "incorrect",
            "new_password": "newsecret123",
        },
    )
    assert bad.status_code == 400
    changed = await client.post(
        "/api/auth/password",
        json={
            "current_password": "admintestpassword",
            "new_password": "newsecret123",
        },
    )
    assert changed.status_code == 200
    assert (await client.get("/api/auth/me")).status_code == 200
    client.cookies.clear()
    client.cookies.set("oj_session", old_cookie)
    assert (await client.get("/api/auth/me")).status_code == 401
    client.cookies.clear()
    assert (
        await client.post(
            "/api/auth/login",
            json={
                "username": "admin",
                "password": "admintestpassword",
            },
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/auth/login",
            json={
                "username": "admin",
                "password": "newsecret123",
            },
        )
    ).status_code == 200
    assert current != old_cookie


async def test_password_change_requires_identity_and_valid_bytes(client: AsyncClient) -> None:
    assert (await client.post("/api/auth/password", json={})).status_code == 401
    await login_admin(client)
    for password in ["short", "密" * 25, "admintestpassword"]:
        assert (
            await client.post(
                "/api/auth/password",
                json={
                    "current_password": "admintestpassword",
                    "new_password": password,
                },
            )
        ).status_code == 400


@pytest.mark.parametrize("expired", [False, True])
async def test_task_deadline_cancels_work_and_counts_queue(
    app: FastAPI,
    monkeypatch: Any,
    expired: bool,
) -> None:
    service = app.state.ai_authoring
    # An old deployment's 7200-second setting must still obey the four-minute cap.
    service.settings.ai_task_timeout_seconds = 7200 if expired else 0.05
    created = datetime.now(UTC) - timedelta(seconds=241 if expired else 0)
    await app.state.db.execute(
        "INSERT INTO ai_tasks(id,user_id,requirement,status,progress,created_at,updated_at) "
        "VALUES(?,1,'test','pending','queued',?,?)",
        ("deadline-test", created.isoformat(), created.isoformat()),
    )
    started = False
    cancelled = False

    async def slow(_task_id: str) -> None:
        nonlocal started, cancelled
        started = True
        try:
            await asyncio.sleep(10)
        finally:
            cancelled = True

    monkeypatch.setattr(service, "_author", slow)
    await asyncio.wait_for(service._run("deadline-test"), 2)
    row = await app.state.db.fetchone("SELECT * FROM ai_tasks WHERE id='deadline-test'")
    assert row["status"] == "failed"
    assert "4 分钟" in row["error"]
    assert started is not expired
    assert cancelled is not expired


async def test_archiving_preserves_terminal_elapsed_time(app: FastAPI, client: AsyncClient) -> None:
    await login_admin(client)
    created = datetime.now(UTC) - timedelta(seconds=60)
    finished = created + timedelta(seconds=12)
    await app.state.db.execute(
        "INSERT INTO ai_tasks(id,user_id,requirement,status,progress,created_at,updated_at) "
        "VALUES(?,1,'test','completed','done',?,?)",
        ("timer-archive", created.isoformat(), finished.isoformat()),
    )
    assert (await client.delete("/api/ai/problem-tasks/timer-archive")).status_code == 200
    task = (await client.get("/api/ai/problem-tasks/timer-archive")).json()["data"]
    assert task["updated_at"] == finished.isoformat()
