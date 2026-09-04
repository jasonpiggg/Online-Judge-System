from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient

from tests.conftest import login_admin


async def test_workspace_draft_roundtrip_and_account_isolation(
    client: AsyncClient, app: FastAPI, problem_payload: dict[str, Any]
) -> None:
    path = "/api/workspace-drafts/sum_2/python"
    assert (await client.get(path)).status_code == 401

    await login_admin(client)
    await client.post("/api/problems/", json=problem_payload)
    first = await client.put(path, json={"code": "  print(3)\n"})
    assert first.status_code == 200
    assert first.json()["data"]["revision"] == 1
    assert first.json()["data"]["code"] == "  print(3)\n"

    second = await client.put(path, json={"code": ""})
    assert second.json()["data"]["revision"] == 2
    assert (await client.get(path)).json()["data"]["code"] == ""

    await client.post("/api/users/", json={"username": "other", "password": "secret1"})
    await client.post(
        "/api/auth/login", json={"username": "other", "password": "secret1"}
    )
    assert (await client.get(path)).json()["data"] is None
    own = await client.put(path, json={"code": "print(4)"})
    assert own.json()["data"]["revision"] == 1

    assert (await client.delete(path)).status_code == 200
    assert (await client.get(path)).json()["data"] is None
    assert len(await app.state.db.fetchall("SELECT * FROM workspace_drafts")) == 1


async def test_workspace_draft_validation(
    client: AsyncClient, problem_payload: dict[str, Any]
) -> None:
    await login_admin(client)
    assert (
        await client.put("/api/workspace-drafts/missing/python", json={"code": "x"})
    ).status_code == 404
    await client.post("/api/problems/", json=problem_payload)
    assert (
        await client.put("/api/workspace-drafts/sum_2/missing", json={"code": "x"})
    ).status_code == 404
    assert (
        await client.put("/api/workspace-drafts/../python", json={"code": "x"})
    ).status_code in {400, 404}
