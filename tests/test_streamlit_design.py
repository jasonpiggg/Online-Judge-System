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


def test_bottom_pagination_jump() -> None:
    app = AppTest.from_string("""
from frontend.navigation import pagination
pagination(120)
""").run()
    assert not app.exception
    app.number_input[0].set_value(7)
    app.button(key="pager-page-bottom-go").click().run()
    assert not app.exception
    assert app.query_params["page"] == ["7"]
    assert any(b.label == "7" for b in app.button)
    app.button(key="pager-page-bottom-0").click().run()
    assert app.query_params["page"] == ["1"]


@pytest.mark.parametrize(
    ("page", "last", "expected"),
    [
        (1, 1, [1]),
        (3, 5, [1, 2, 3, 4, 5]),
        (1, 15, [1, 2, 3, None, 15]),
        (7, 15, [1, None, 5, 6, 7, 8, 9, None, 15]),
        (15, 15, [1, None, 13, 14, 15]),
        (4, 6, [1, 2, 3, 4, 5, 6]),
    ],
)
def test_pager_endpoint_and_neighbor_rules(
    page: int, last: int, expected: list[int | None]
) -> None:
    from frontend.navigation import page_links

    assert page_links(page, last) == expected


def test_empty_pagers_render_no_controls() -> None:
    app = AppTest.from_string("""
from frontend.navigation import pagination
pagination(0)
pagination(0, position="bottom")
""").run()
    assert not app.exception
    assert not app.button
    assert not app.number_input
    assert not app.caption


@pytest.mark.parametrize(
    ("current", "new", "confirm", "message"),
    [
        ("", "", "", "请输入当前密码"),
        ("secret1", "", "", "请输入新密码"),
        ("secret1", "secret2", "", "请再次输入"),
        ("short", "secret2", "secret2", "当前密码不正确"),
        ("secret1", "short", "short", "至少需要 6"),
        ("secret1", "密" * 25, "密" * 25, "最多 72"),
        ("secret1", "secret2", "different", "不一致"),
        ("secret1", "secret1", "secret1", "不能与当前密码相同"),
        ("secret1", "secret2", "secret2", None),
    ],
)
def test_password_input_feedback(current: str, new: str, confirm: str, message: str | None) -> None:
    from frontend.account import password_change_error

    error = password_change_error(current, new, confirm)
    assert error is None if message is None else message in str(error)


def test_admin_panel_filters_are_independent_and_bookmarkable() -> None:
    app = AppTest.from_string("""
import streamlit as st
from frontend.navigation import panel_query
st.session_state.user = {"role":"admin"}
st.session_state.current_route = {"page":"admin"}
st.query_params.section = "题目管理"
panel_query.q = "sum"
panel_query.page = "3"
st.query_params.section = "用户"
assert panel_query.get("q", "") == ""
panel_query.q = "admin"
st.query_params.section = "题目管理"
assert panel_query.get("q") == "sum"
assert panel_query.get("page") == "3"
st.session_state.user = {"role":"user"}
assert panel_query.get("q", "") == ""
""").run()
    assert not app.exception
