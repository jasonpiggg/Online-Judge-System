from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from oj.config import Settings
from oj.main import bootstrap, create_app


@pytest.fixture
async def app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    settings = Settings(
        database_path=tmp_path / "oj.db",
        problem_dir=tmp_path / "problems",
        seed_problem_dir=tmp_path / "seeds",
    )
    application = create_app(settings)
    await application.state.db.initialize()
    await bootstrap(application.state.db)
    await application.state.problems.initialize()
    yield application


@pytest.fixture
def problem_payload() -> dict[str, object]:
    return {
        "id": "sum_2",
        "title": "两数之和",
        "description": "输入两个整数，输出它们的和。",
        "input_description": "一行两个整数 a 和 b。",
        "output_description": "输出 a+b。",
        "samples": [{"input": "1 2\n", "output": "3\n"}],
        "constraints": "|a|, |b| <= 10^9",
        "testcases": [
            {"input": "1 2\n", "output": "3\n"},
            {"input": "-5 8\n", "output": "3\n"},
        ],
    }


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as http:
        yield http


async def login_admin(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admintestpassword"},
    )
    assert response.status_code == 200

