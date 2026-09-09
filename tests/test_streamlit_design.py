from __future__ import annotations

from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from frontend.authoring import equivalent_draft
from frontend.ui import local_time, verdict_label


@pytest.mark.parametrize(
    ("data", "label"),
    [
        ({"status": "pending"}, "正在评测"),
        ({"status": "success", "score": 0, "counts": 50}, "未全部通过"),
        ({"status": "success", "score": 50, "counts": 50}, "全部通过"),
        ({"status": "success", "score": 0, "counts": 0}, "没有测试点"),
        ({"status": "success", "evaluation": {"verdict": "RE"}}, "运行时错误"),
        ({"status": "error"}, "评测异常"),
    ],
)
def test_evaluation_status_is_not_acceptance(data: dict[str, Any], label: str) -> None:
    assert verdict_label(data)[0] == label


def test_beijing_time_handles_missing_and_offset_dates() -> None:
    assert local_time("2026-09-08T23:30:00Z") == "2026-09-09 07:30"
    assert local_time("2026-09-09T07:30:00+08:00") == "2026-09-09 07:30"
    assert local_time(None) == "—"


def test_draft_empty_defaults_and_meaningful_values() -> None:
    assert equivalent_draft(
        {"problem": {"title": "题目"}},
        {
            "problem": {"title": "题目", "hint": "", "samples": [], "time_limit": None},
        },
    )
    for value in [" ", 0, False, [{"input": "", "output": ""}]]:
        assert not equivalent_draft({}, {"value": value})
    assert not equivalent_draft({"value": False}, {"value": 0})


def test_multiline_case_edit_retains_literal_whitespace(monkeypatch: Any) -> None:
    import frontend.workspace as workspace

    monkeypatch.setattr(workspace, "statement", lambda *_a, **_kw: None)
    app = AppTest.from_string("""
import streamlit as st
from frontend.forms import problem_form
st.session_state.user = {"role":"user"}
value = st.session_state.get("value", {"samples":[{"input":"1 2", "output":"3"}]})
st.session_state.value = problem_form(value, "case-test")
""").run()
    assert not app.exception
    app.text_area(key="case-test-samples-detail-0-0-input").set_value("  1 2\n\n").run()
    assert not app.exception
    assert app.session_state.value["samples"][0]["input"] == "  1 2\n\n"
    app.run()
    assert app.session_state.value["samples"][0]["input"] == "  1 2\n\n"


def test_authoring_manual_retry_reuses_idempotency_key(monkeypatch: Any) -> None:
    import frontend.authoring as authoring

    requests: list[dict[str, str]] = []

    class Client:
        def post(self, _path: str, **kwargs: Any) -> dict[str, Any]:
            requests.append(kwargs["headers"])
            if len(requests) == 1:
                raise RuntimeError("Connection interrupted after request")
            return {"data": {"task_id": "existing-task"}}

    monkeypatch.setattr(authoring, "go", lambda *_a, **_kw: None)
    monkeypatch.setattr(authoring, "ApiClient", Client)
    app = AppTest.from_string("""
import streamlit as st
from frontend.authoring import start_task, ApiClient
if st.button("Generate"):
    start_task(ApiClient(), {"requirement":"Generate a complete sum problem"})
""").run()
    app.button[0].click().run()
    assert len(requests) == 1
    app.button[0].click().run()
    assert len(requests) == 2
    assert requests[0]["Idempotency-Key"] == requests[1]["Idempotency-Key"]


def test_component_keys_escape_reserved_event_delimiter(monkeypatch: Any) -> None:
    import frontend.components as components

    captured: list[str] = []
    monkeypatch.setattr(
        components, "_control", lambda: lambda **kwargs: captured.append(kwargs["key"])
    )
    components.control("markdown", "task-id__with-delimiter")
    components.control("markdown", "task-id__with-delimiter")
    components.control("markdown", "task-id-with-delimiter")
    assert "__" not in captured[0]
    assert captured[0] == captured[1]
    assert captured[0] != captured[2]


def test_pagination_jump_and_paired_controls() -> None:
    app = AppTest.from_string("""
from frontend.navigation import pagination
pagination(120)
pagination(120, position="bottom")
""").run()
    assert not app.exception
    app.number_input[0].set_value(7)
    app.button(key="pager-page-top-go").click().run()
    assert not app.exception
    assert app.query_params["page"] == ["7"]
    assert any(b.label == "7" for b in app.button)
    app.button(key="pager-page-bottom-0").click().run()
    assert app.query_params["page"] == ["1"]
