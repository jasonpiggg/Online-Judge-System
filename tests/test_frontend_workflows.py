from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from streamlit.testing.v1 import AppTest

from frontend.client import ApiClient, ApiError
from frontend.editor import clean_problem
from tests.conftest import login_admin


def test_editor_preserves_inheritance_and_whitespace() -> None:
    data = clean_problem({"id": "x", "time_limit": 3, "memory_limit": 128,
                          "limit_inheritance": {"time_limit": True},
                          "samples": [{"input": "  x\n", "output": " x\n"}]})
    assert data["time_limit"] is None
    assert data["memory_limit"] == 128
    assert data["samples"][0]["input"] == "  x\n"


def test_editor_add_cases_and_draft(monkeypatch: Any) -> None:
    monkeypatch.setattr(ApiClient, "request", lambda *_a, **_k: {"code": 200, "data": {}})
    app = AppTest.from_string('''
import streamlit as st
from frontend.editor import editor_page
from frontend.client import ApiClient
st.session_state.user = {"user_id": "1", "role": "admin"}
editor_page(ApiClient())
''').run(timeout=20)
    assert not app.exception
    app.text_input[0].set_value("draft_test").run()
    app.text_input[1].set_value("测试草稿").run()
    next(b for b in app.button if b.label == "添加测试点").click().run()
    assert len(app.session_state.editor_drafts["new"]["testcases"]) == 2
    assert app.session_state.editor_drafts["new"]["title"] == "测试草稿"
    next(b for b in app.button if b.label == "移除测试点 2").click().run()
    assert len(app.session_state.editor_drafts["new"]["testcases"]) == 1
    next(b for b in app.button if b.label == "创建题目").click().run()
    assert app.error  # Missing required description, constraints, etc.


def test_login_api_error_is_visible(monkeypatch: Any) -> None:
    def rejected(*_args: Any, **_kwargs: Any) -> Any:
        raise ApiError(401, "用户名或密码错误")

    monkeypatch.setattr(ApiClient, "request", rejected)
    app = AppTest.from_string('''
from frontend.account import auth_screen
from frontend.client import ApiClient
auth_screen(ApiClient())
''').run()
    next(b for b in app.button if b.label == "进入工作台").click().run()
    assert app.error[0].value == "用户名或密码错误"


async def test_admin_all_records_and_metadata(
    client: AsyncClient, problem_payload: dict[str, Any]
) -> None:
    await login_admin(client)
    await client.post("/api/problems/", json=problem_payload)
    await client.post("/api/submissions/", json={
        "problem_id": "sum_2", "language": "python", "code": "print(3)",
    })
    assert (await client.get("/api/submissions/")).status_code == 400
    result = await client.get("/api/submissions/", params={
        "all_users": True, "include_metadata": True, "page": 1, "page_size": 10,
    })
    assert result.status_code == 200
    row = result.json()["data"]["submissions"][0]
    assert row["problem_id"] == "sum_2" and row["language"] == "python"
    await client.post("/api/users/", json={"username": "alice", "password": "secret1"})
    await client.post("/api/auth/login", json={"username": "alice", "password": "secret1"})
    assert (await client.get("/api/submissions/", params={"all_users": True})).status_code == 403
