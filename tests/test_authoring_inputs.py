from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from frontend.client import ApiClient


@pytest.mark.parametrize("input_key", ["generation-requirement", "draft-ai-requirement-test"])
def test_request_failure_preserves_input_and_retry_key(monkeypatch: Any, input_key: str) -> None:
    calls: list[dict[str, Any]] = []

    def request(_self: Any, _method: str, _path: str, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("temporary failure")
        return {"data": {"task_id": "task"}}

    monkeypatch.setattr(ApiClient, "request", request)
    monkeypatch.setattr("frontend.authoring.go", lambda *a, **kw: None)
    app = AppTest.from_string("""
import streamlit as st
from frontend.authoring import start_task
from frontend.client import ApiClient
key = st.session_state.input_key
if st.session_state.pop(f"{key}-clear", False):
    st.session_state[key] = ""
text = st.text_area("request", key=key)
if st.button("send"):
    start_task(ApiClient(), {"requirement": text}, clear_input=key)
""")
    app.session_state.input_key = input_key
    app.run().text_area[0].input("original request").run()
    app.button[0].click().run()
    assert app.text_area[0].value == "original request"
    assert app.error
    app.button[0].click().run()
    app.run()
    assert not app.exception
    assert app.text_area[0].value == ""
    assert calls[0]["headers"]["Idempotency-Key"] == calls[1]["headers"]["Idempotency-Key"]
    assert calls[1]["json"]["requirement"] == "original request"
