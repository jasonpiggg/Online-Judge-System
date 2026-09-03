from __future__ import annotations

from html import escape

import streamlit as st

from frontend.client import ApiClient
from frontend.ui import call, heading, pager


def submission_result(api: ApiClient, submission_id: str) -> None:
    terminal_key = f"terminal-{submission_id}"

    @st.fragment(run_every=None if st.session_state.get(terminal_key) else 1)
    def render() -> None:
        result = call(
            lambda: api.get(f"/api/submissions/{submission_id}", params={"include_metadata": True})
        )
        if not result:
            return
        data = result["data"]
        status = data["status"]
        if status != "pending" and not st.session_state.get(terminal_key):
            st.session_state[terminal_key] = True
            st.rerun()
        passed = status == "success" and data["score"] == data["counts"]
        label = (
            "评测中" if status == "pending" else "全部通过" if passed else "评测完成 · 未全部通过"
        )
        if status == "error":
            label = "评测服务异常"
        color = "wait" if status == "pending" else "pass" if passed else "fail"
        st.markdown(
            f'<span class="oj-status {color}">{escape(label)}</span>', unsafe_allow_html=True
        )
        st.caption(f"提交 #{submission_id}")
        st.caption(
            f"{data.get('problem_id', '')} · {data.get('language', '')}"
            f" · {data.get('created_at', '')}"
        )
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
            details = logs["data"]["details"]
            if details:
                a, b = st.columns(2)
                a.metric("最大用时 / 秒", max(x["time"] for x in details))
                b.metric("峰值内存 / MB", max(x["memory"] for x in details))
        if data.get("code"):
            with st.expander("查看本次提交代码"):
                st.code(
                    data["code"], language="python" if data.get("language") == "python" else "cpp"
                )
        if st.session_state.user["role"] == "admin":
            if st.button("重新评测", icon=":material/replay:", key=f"rejudge-{submission_id}"):
                if call(lambda: api.put(f"/api/submissions/{submission_id}/rejudge")):
                    st.session_state.pop(terminal_key, None)
                    st.rerun()

    render()


def records_page(api: ApiClient) -> None:
    heading("提交记录", note="每一次尝试都值得记录。选择记录可展开测试点详情。")
    problems = call(lambda: api.get("/api/problems/"))
    if not problems:
        return
    options = {"全部题目": None} | {f"{p['id']} · {p['title']}": p["id"] for p in problems["data"]}
    a, b, c = st.columns(3)
    problem = a.selectbox("题目", list(options))
    status = b.selectbox(
        "评测状态",
        ["全部", "pending", "success", "error"],
        format_func=lambda x: {"pending": "评测中", "success": "已完成", "error": "服务异常"}.get(
            x, x
        ),
    )
    uid = st.session_state.user["user_id"]
    admin = st.session_state.user["role"] == "admin"
    if admin:
        uid = c.number_input("用户 ID（0 为全部用户）", min_value=0, value=0, step=1)
    signature = (problem, status, uid)
    if st.session_state.get("records-filter") != signature:
        st.session_state["records-page"] = 1
        st.session_state["records-filter"] = signature
    page = st.session_state.get("records-page", 1)
    params = {"page": page, "page_size": 10, "include_metadata": True}
    if admin and uid == 0:
        params["all_users"] = True
    else:
        params["user_id"] = uid
    if options[problem]:
        params["problem_id"] = options[problem]
    if status != "全部":
        params["status"] = status
    result = call(lambda: api.get("/api/submissions/", params=params))
    if not result:
        return
    pager("records-page", result["data"]["total"])
    records = result["data"]["submissions"]
    if not records:
        st.info("还没有提交记录。从题库选择一道题，开始第一次尝试。")
        return
    visible = [
        {
            "提交": r["submission_id"],
            "题目": r["problem_id"],
            "用户": r["user_id"],
            "语言": r["language"],
            "状态": r["status"],
            "得分": f"{r.get('score', '—')} / {r.get('counts', '—')}",
            "提交时间": r["created_at"],
        }
        for r in records
    ]
    selection = st.dataframe(
        visible,
        on_select="rerun",
        selection_mode="single-row",
        width="stretch",
        hide_index=True,
        key=f"records-{signature}-{page}",
    )
    rows = selection.selection.rows
    selected = records[rows[0]] if rows else records[0]
    st.subheader(f"提交 #{selected['submission_id']}")
    submission_result(api, str(selected["submission_id"]))
    with st.expander("查看已公开的其他提交测试点日志"):
        public_id = st.text_input("提交 ID", key="public-log-id")
        if st.button("查询公开日志"):
            public = call(lambda: api.get(f"/api/submissions/{public_id}/log"))
            if public:
                st.dataframe(public["data"]["details"], width="stretch", hide_index=True)
