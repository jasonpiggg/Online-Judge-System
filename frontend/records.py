from __future__ import annotations

from html import escape

import streamlit as st

from frontend.client import ApiClient
from frontend.ui import call, heading, pager


def submission_result(api: ApiClient, submission_id: str) -> None:
    terminal_key = f"terminal-{submission_id}"

    @st.fragment(run_every=None if st.session_state.get(terminal_key) else 1)
    def render() -> None:
        result = call(lambda: api.get(f"/api/submissions/{submission_id}"))
        if not result:
            return
        data = result["data"]
        status = data["status"]
        if status != "pending" and not st.session_state.get(terminal_key):
            st.session_state[terminal_key] = True
            st.rerun()
        passed = status == "success" and data["score"] == data["counts"]
        label = ("评测中" if status == "pending" else
                 "全部通过" if passed else "评测完成 · 未全部通过")
        if status == "error":
            label = "评测服务异常"
        color = "wait" if status == "pending" else "pass" if passed else "fail"
        st.markdown(f'<span class="oj-status {color}">{escape(label)}</span>',
                    unsafe_allow_html=True)
        st.caption(f"提交 #{submission_id}")
        if status == "pending":
            st.caption("正在逐测试点运行，请稍候……")
            return
        st.metric("得分", f"{data.get('score') or 0} / {data.get('counts') or 0}")
        for field, title in [("compile_info", "编译信息"), ("run_info", "运行信息")]:
            if data.get(field):
                with st.expander(title):
                    st.write(data[field])
        if data.get("error_info"):
            st.error(data["error_info"])
        logs = call(lambda: api.get(f"/api/submissions/{submission_id}/log"))
        if logs:
            st.dataframe(logs["data"]["details"], width="stretch", hide_index=True)
    render()


def records_page(api: ApiClient) -> None:
    heading("提交记录", note="每一次尝试都值得记录。选择记录可展开测试点详情。")
    page = st.session_state.get("records-page", 1)
    result = call(lambda: api.get("/api/submissions/", params={
        "user_id": st.session_state.user["user_id"], "page": page, "page_size": 10,
    }))
    if not result:
        return
    pager("records-page", result["data"]["total"])
    for item in result["data"]["submissions"]:
        sid = item["submission_id"]
        with st.expander(f"#{sid} · {item['problem_id']} · {item['status']}"):
            submission_result(api, str(sid))
    if not result["data"]["submissions"]:
        st.info("还没有提交记录。从题库选择一道题，开始第一次尝试。")
