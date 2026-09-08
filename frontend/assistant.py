"""Persistent assistant conversations; polling never starts a paid request."""

from __future__ import annotations

import re
import uuid
from typing import Any

import streamlit as st

from frontend.client import ApiClient
from frontend.components import diff, rich_text
from frontend.navigation import page_number, pagination
from frontend.ui import call


def code_candidates(text: str) -> list[tuple[str, str]]:
    return [
        (m.group(1).strip(), m.group(2))
        for m in re.finditer(r"^```([^\n`]*)\n([\s\S]*?)^```\s*$", text, re.MULTILINE)
        if m.group(2).strip()
    ]


def assistant_panel(api: ApiClient, pid: str, language: str, source: dict[str, Any]) -> None:
    from frontend.workspace import replace_source, save_source

    ck = f"conversation-{pid}"
    if ck not in st.session_state:
        r = call(lambda: api.post("/api/ai/conversations/", json={"problem_id": pid}))
        if not r:
            return
        st.session_state[ck] = r["data"]["id"]
    cid = st.session_state[ck]
    if st.button("新话题", key=f"new-topic-{pid}"):
        if call(lambda: api.post(f"/api/ai/conversations/{cid}/new")):
            st.query_params["message_page"] = "1"
            st.session_state.pop(f"assistant-active-{pid}", None)
            st.rerun()
    st.caption("新话题会停止旧话题中进行的回答；历史任务与费用仍保留在命题中心。")
    history = call(
        lambda: api.get(
            f"/api/ai/conversations/{cid}/messages",
            params={"page": page_number("message_page"), "page_size": 5, "include_metadata": True},
        )
    )
    if history:
        pagination(history["data"]["total"], "message_page", 5)
        for msg in history["data"]["messages"]:
            with st.expander(str(msg["message"])[:100], expanded=False):
                st.write(msg["message"])
                rich_text(msg.get("text") or "尚未生成回答。", f"message-{msg['task_id']}")
                st.caption(f"{msg['status']} · {msg.get('created_at', '')}")
                if st.button("打开回答", key=f"assistant-open-{msg['task_id']}"):
                    st.session_state[f"assistant-active-{pid}"] = msg["task_id"]
                    st.rerun()
            if (
                msg["status"] in {"pending", "running"}
                and f"assistant-active-{pid}" not in st.session_state
            ):
                st.session_state[f"assistant-active-{pid}"] = msg["task_id"]
    with st.form(f"assistant-form-{pid}"):
        message = st.text_area("向助手提问", placeholder="描述困惑、错误现象，或请求检查当前解法。")
        full = st.checkbox("允许提供完整解法")
        include = st.checkbox("附带最近一次提交", value=True)
        if st.form_submit_button("发送", type="primary"):
            body = {
                "message": message,
                "code": source["code"],
                "language": language,
                "full_solution": full,
            }
            last_submission = st.query_params.get("submission_id") or st.session_state.get(
                f"last-{pid}"
            )
            if include and last_submission:
                body["submission_id"] = last_submission
            r = call(
                lambda: api.post(
                    f"/api/ai/conversations/{cid}/messages",
                    json=body,
                    headers={"Idempotency-Key": uuid.uuid4().hex},
                )
            )
            if r:
                st.session_state[f"assistant-active-{pid}"] = r["data"]["task_id"]
                st.query_params["message_page"] = "1"
                st.rerun()
    task_id = st.session_state.get(f"assistant-active-{pid}")
    if not task_id:
        st.info("发送问题后，回答会逐步显示。刷新页面可恢复已有会话。")
        return
    terminal = f"assistant-terminal-{task_id}"

    @st.fragment(run_every=None if st.session_state.get(terminal) else 1)
    def answer() -> None:
        result = call(lambda: api.get(f"/api/ai/assistant-tasks/{task_id}"))
        if not result:
            return
        task = result["data"]
        done = task["status"] in {"completed", "failed", "cancelled"}
        if done and not st.session_state.get(terminal):
            st.session_state[terminal] = True
            st.rerun()
        st.caption(f"{task['status']} · {task.get('progress', '')}")
        text = (
            (task.get("result") or {}).get("text") or (task.get("preview") or {}).get("text") or ""
        )
        rich_text(text or "正在准备回答……", f"answer-{task_id}")
        if task.get("error"):
            st.error(task["error"])
        if not done and st.button("取消回答", key=f"cancel-{task_id}"):
            if call(lambda: api.put(f"/api/ai/assistant-tasks/{task_id}/cancel")):
                st.rerun()
        usage = task.get("usage", {})
        st.caption(
            f"Token {usage.get('total_tokens', 0)} · {usage.get('cost', 0):.6f} "
            f"{usage.get('currency', 'USD')} · "
            f"{'服务商 usage' if usage.get('source') == 'provider' else '估算用量'}"
        )
        candidates = code_candidates(text)
        if candidates and task["status"] == "completed":
            selection = st.selectbox(
                "代码候选",
                range(len(candidates)),
                format_func=lambda i: f"候选 {i + 1} · {candidates[i][0] or '未标记语言'}",
                key=f"candidate-{task_id}",
            )
            lang, code = candidates[selection]
            st.warning("代码块可能只是片段。采纳会替换整份源码，请先比较并检查语言。")
            baseline = task.get("code_snapshot", "")
            diff({"code": source["code"]}, {"code": code}, f"assistant-diff-{task_id}")
            stale = (
                source["code"].replace("\r\n", "\n") != baseline.replace("\r\n", "\n")
                or task.get("language") != language
                or bool(source.get("backup") or source.get("conflict"))
            )
            if stale:
                st.info(
                    "源码或语言已变化，旧建议不能覆盖当前工作区。可复制片段或基于新代码重新提问。"
                )
            approved = st.checkbox("已检查 Diff，确认替换整份源码", key=f"apply-confirm-{task_id}")
            if st.button("采纳代码", disabled=stale or not approved, key=f"apply-{task_id}"):
                before = source["code"]
                replace_source(source, code)
                if save_source(api, pid, language, source):
                    source["undo"] = {"before": before, "after": code}
                st.rerun()
        if undo := source.get("undo"):
            if st.button(
                "撤销最近一次采纳",
                disabled=source["code"].replace("\r\n", "\n")
                != undo["after"].replace("\r\n", "\n"),
                key=f"undo-{task_id}",
            ):
                replace_source(source, undo["before"])
                if save_source(api, pid, language, source):
                    source.pop("undo", None)
                st.rerun()

    answer()
