from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

from streamlit.testing.v1 import AppTest

from frontend.assistant import code_candidates
from frontend.client import ApiClient, ApiError


def test_code_candidates_preserve_multiple_blocks_and_ignore_unclosed_output() -> None:
    assert code_candidates("```python\na = 1\n```\n\n```cpp\nint a;\n```") == [
        ("python", "a = 1\n"),
        ("cpp", "int a;\n"),
    ]
    assert code_candidates("```python\nunfinished") == []


def test_revision_conflict_keeps_local_and_remote_code(monkeypatch: Any) -> None:
    def request(_self: ApiClient, method: str, _path: str, **_kw: Any) -> Any:
        if method == "PUT":
            raise ApiError(409, "updated elsewhere")
        return {"data": {"code": "remote", "revision": 8}}

    monkeypatch.setattr(ApiClient, "request", request)
    app = AppTest.from_string("""
import streamlit as st
from frontend.workspace import save_source
from frontend.client import ApiClient
st.session_state.source = {'code': 'local', 'saved': 'old', 'revision': 7, 'epoch': 0}
save_source(ApiClient(), 'sum_2', 'python', st.session_state.source)
""").run()
    assert not app.exception
    source = app.session_state.source
    assert source["code"] == "local" and source["saved"] == "old"
    assert source["revision"] == 7
    assert source["conflict"] == {"code": "remote", "revision": 8}


def test_partial_draft_form_preserves_empty_cases_and_custom_difficulty(monkeypatch: Any) -> None:
    import frontend.workspace as workspace

    monkeypatch.setattr(workspace, "statement", lambda *_a, **_kw: None)
    app = AppTest.from_string("""
import streamlit as st
from frontend.forms import problem_form
st.session_state.user = {'role': 'user'}
value = {'difficulty': '课程自定义', 'samples': [], 'testcases': []}
st.session_state.value = problem_form(value, 'partial')
""").run()
    assert not app.exception
    assert app.session_state.value["difficulty"] == "课程自定义"
    assert app.session_state.value["samples"] == []
    assert app.session_state.value["testcases"] == []
    assert app.session_state.value["time_limit"] is None


def test_draft_save_uses_expected_revision_and_does_not_publish(monkeypatch: Any) -> None:
    calls = []

    def request(_self: ApiClient, method: str, path: str, **kw: Any) -> Any:
        calls.append((method, path, copy.deepcopy(kw)))
        return {"data": {**kw["json"], "revision": 2}}

    monkeypatch.setattr(ApiClient, "request", request)
    app = AppTest.from_string("""
import streamlit as st
from frontend.authoring import save_draft
from frontend.forms import draft_payload
from frontend.client import ApiClient
st.session_state.value = {
    'local': draft_payload({'problem': {'title': 'partial'}}), 'saved': {}, 'revision': 1}
save_draft(ApiClient(), 'test-draft', st.session_state.value)
""").run()
    assert not app.exception
    assert len(calls) == 1 and calls[0][:2] == ("PUT", "/api/problem-drafts/test-draft")
    assert calls[0][2]["json"]["revision"] == 1
    assert app.session_state.value["revision"] == 2


def test_auth_bridge_receives_validated_intent_without_python_login(monkeypatch: Any) -> None:
    import frontend.components as components

    events = []

    def control(mode: str, _key: str, **data: Any) -> Any:
        events.append((mode, data))
        return SimpleNamespace(result=None)

    monkeypatch.setattr(components, "control", control)
    monkeypatch.setattr(
        ApiClient,
        "request",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            AssertionError("Authentication must use browser cookies")
        ),
    )
    app = AppTest.from_string("""
from frontend.account import auth_screen
from frontend.client import ApiClient
auth_screen(ApiClient())
""").run()
    app.text_input(key="auth-name-login").set_value("tester")
    app.text_input(key="auth-password-login").set_value("汉" * 24)
    next(b for b in app.button if b.label == "进入工作台").click().run()
    assert not app.exception
    assert events[-1][0] == "auth"
    assert events[-1][1]["action"] == "login"
    assert len(events[-1][1]["password"].encode()) == 72
