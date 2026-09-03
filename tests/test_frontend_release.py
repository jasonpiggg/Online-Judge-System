from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from frontend.client import ApiClient


def test_account_switch_clears_private_workspace_state() -> None:
    app = AppTest.from_string("""
import streamlit as st
from frontend.account import activate_user
if st.button("switch"):
    activate_user({"user_id": 2, "username": "second", "role": "user"})
""")
    app.session_state.workspace_user_id = "1"
    app.session_state.user = {"user_id": 1, "username": "first", "role": "user"}
    app.session_state["draft-sum_2-python"] = "private source"
    app.session_state["last-sum_2"] = 99
    app.session_state.editor_drafts = {"new": {"description": "private draft"}}
    app.session_state.ai_task_id = "private-task"
    app.session_state.mobile = True

    app.run().button[0].click().run()

    assert not app.exception
    assert app.session_state.user["user_id"] == 2
    assert app.session_state.workspace_user_id == "2"
    assert app.session_state.mobile is True
    assert "draft-sum_2-python" not in app.session_state
    assert "last-sum_2" not in app.session_state
    assert "editor_drafts" not in app.session_state
    assert "ai_task_id" not in app.session_state


@pytest.mark.parametrize("role", ["admin", "user"])
def test_native_navigation_role_scope(monkeypatch: Any, role: str) -> None:
    monkeypatch.setattr(ApiClient, "request", lambda *_a, **_k: {"code": 200, "data": []})
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "frontend/app.py"))
    app.session_state.user = {"user_id": "1", "username": "tester", "role": role}
    app.session_state.mobile = True
    app.run(timeout=20)
    assert not app.exception
    assert ("admin" in app.session_state.pages) == (role == "admin")
    assert app.session_state.mobile is True  # No component result must not reset viewport state.
    assert "library" in app.session_state.pages and "workspace" in app.session_state.pages


@pytest.mark.parametrize("update", [False, True])
def test_ai_load_common_editor_preserves_content(
    monkeypatch: Any, update: bool, problem_payload: dict[str, Any]
) -> None:
    import frontend.editor as editor

    targets = []
    monkeypatch.setattr(editor, "navigate", lambda *args, **kw: targets.append((args, kw)))
    app = AppTest.from_string("""
import streamlit as st
from frontend.editor import load_editor
if st.button("load"):
    load_editor(st.session_state.payload, update=st.session_state.update_mode)
""")
    app.session_state.payload = {
        **problem_payload,
        "samples": [{"input": "  x\n", "output": " x\n"}],
        "verification": {"extra": True},
    }
    app.session_state.update_mode = update
    app.run().button[0].click().run()
    assert not app.exception
    key = problem_payload["id"] if update else "new"
    draft = app.session_state.editor_drafts[key]
    assert draft["samples"][0]["input"] == "  x\n"
    assert "verification" not in draft
    assert bool(targets[0][1]["editing_problem"]) == update


def test_401_preserves_non_sensitive_draft(monkeypatch: Any) -> None:
    from frontend.client import ApiError

    def expired(*_a: Any, **_k: Any) -> Any:
        raise ApiError(401, "expired")

    monkeypatch.setattr(ApiClient, "request", expired)
    app = AppTest.from_string("""
import streamlit as st
from frontend.ui import call
from frontend.client import ApiClient
if st.session_state.get("user"):
    call(lambda: ApiClient().get("/api/problems/"))
else:
    st.info(st.session_state.get("flash", ""))
""")
    app.session_state.user = {"user_id": "1"}
    app.session_state["draft-sum-python"] = " print('preserve')\n"
    app.run()
    assert not app.exception
    assert app.session_state["draft-sum-python"] == " print('preserve')\n"
    assert "登录已过期" in app.info[0].value
