from __future__ import annotations

from typing import Any

import streamlit as st

from frontend.client import ApiClient
from frontend.components import diff
from frontend.navigation import back, go, page_number, pagination
from frontend.ui import (
    call,
    data_table,
    heading,
    local_time,
    result_summary,
    status_label,
    verdict_label,
)


def _render_case_details(data: dict[str, Any], key: str = "cases") -> list[dict[str, Any]] | None:
    cases = data.get("details")
    if cases is None:
        st.info("此题未公开测试点明细；提交者只能查看总得分和总分。")
        return None
    if not cases:
        st.info("尚无测试点结果。")
        return []
    failed = st.checkbox("只看未通过测试点", key=f"{key}-failed")
    filtered = [c for c in cases if c["result"] != "AC"] if failed else cases
    selected_results = st.multiselect(
        "测试点结果类型", sorted({c["result"] for c in cases}), key=f"{key}-results"
    )
    if selected_results:
        filtered = [c for c in filtered if c["result"] in selected_results]
    count = len(filtered)
    if st.session_state.get(f"{key}-page", 1) > max(1, (count + 9) // 10):
        st.session_state[f"{key}-page"] = 1
    page = st.number_input(
        "测试点页码", min_value=1, max_value=max(1, (count + 9) // 10), key=f"{key}-page"
    )
    shown = filtered[(page - 1) * 10 : page * 10]
    st.caption(f"共 {count} 个测试点 · 每页 10 个")
    if shown:
        data_table(shown)
        chosen = st.selectbox(
            "测试点详情",
            shown,
            format_func=lambda c: f"#{c['id']} · {c['result']}",
            key=f"{key}-selected",
        )
        a, b = st.columns(2)
        a.metric("用时 / 秒", chosen["time"])
        b.metric("内存 / MB", chosen["memory"])
    return cases


def submission_result(api: ApiClient, submission_id: str) -> None:
    terminal_key = f"terminal-{submission_id}"

    @st.fragment(run_every=None if st.session_state.get(terminal_key) else 1)
    def render() -> None:
        response = call(
            lambda: api.get(f"/api/submissions/{submission_id}", params={"include_metadata": True})
        )
        if not response:
            return
        d = response["data"]
        if d["status"] != "pending" and not st.session_state.get(terminal_key):
            st.session_state[terminal_key] = True
            st.rerun()
        st.subheader("评测结果")
        status = d["status"]
        if status == "pending":
            st.info("正在评测……")
            return
        result_summary(d)
        st.caption(
            f"{d.get('problem_id', '')} · {d.get('language', '')} "
            f"· {local_time(d.get('created_at'))} 北京时间"
        )
        for field, title in [
            ("compile_info", "编译诊断"),
            ("run_info", "运行信息"),
            ("error_info", "错误信息"),
        ]:
            value = d.get(field)
            message = value.get("message", "") if isinstance(value, dict) else value
            if message:
                with st.expander(
                    title,
                    expanded=field in {"compile_info", "run_info"}
                    and verdict_label(d)[1] == "fail",
                ):
                    st.code(str(message), language=None, wrap_lines=False)
        logs = call(lambda: api.get(f"/api/submissions/{submission_id}/log"))
        if logs:
            _render_case_details(logs["data"], f"submission-{submission_id}")
        if d.get("code"):
            with st.expander("本次提交代码", expanded=False):
                st.code(d["code"], language=d.get("language", "python"), wrap_lines=False)
                st.download_button(
                    "下载代码", d["code"], file_name=f"submission-{submission_id}.txt"
                )
            deleted = d.get("problem_deleted", False)
            snapshot_key = f"restore-snapshot-{submission_id}"
            pid, language = d["problem_id"], d["language"]
            if not deleted and snapshot_key not in st.session_state:
                remote = call(lambda: api.get(f"/api/workspace-drafts/{pid}/{language}"))
                if remote:
                    st.session_state[snapshot_key] = remote["data"] or {"code": "", "revision": 0}
            snapshot = st.session_state.get(snapshot_key)
            if snapshot:
                with st.expander("与当前草稿比较"):
                    if st.button("刷新比较基线", key=f"restore-refresh-{submission_id}"):
                        st.session_state.pop(snapshot_key, None)
                        st.session_state[f"restore-confirm-{submission_id}"] = False
                        st.rerun()
                    diff(
                        {"code": snapshot["code"]},
                        {"code": d["code"]},
                        f"restore-diff-{submission_id}",
                    )
            confirmed = st.checkbox(
                "确认用本次代码替换工作区草稿",
                key=f"restore-confirm-{submission_id}",
                disabled=deleted,
            )
            if st.button(
                "载入到做题工作区",
                key=f"restore-{submission_id}",
                disabled=deleted or not confirmed or not snapshot,
            ):
                pid, language = d["problem_id"], d["language"]
                if snapshot:
                    revision = snapshot["revision"]
                    saved = call(
                        lambda: api.put(
                            f"/api/workspace-drafts/{pid}/{language}",
                            json={"code": d["code"], "expected_revision": revision},
                        )
                    )
                    if saved:
                        from frontend.workspace import source_key

                        st.session_state.pop(source_key(pid, language), None)
                        go("workspace", id=pid, language=language)
            if deleted:
                st.info("原题已删除，历史记录保留；不能继续做题或重测。")
        if st.session_state.user["role"] == "admin":
            if st.button(
                "重新评测", key=f"rejudge-{submission_id}", disabled=d.get("problem_deleted", False)
            ):
                if call(lambda: api.put(f"/api/submissions/{submission_id}/rejudge")):
                    st.session_state.pop(terminal_key, None)
                    st.rerun()

    render()


def records_page(api: ApiClient) -> None:
    heading("提交记录", note="筛选记录，查看结果或恢复源码。")
    with st.expander("查询公开日志"):
        public_id = st.text_input("公开提交 ID", key="public-log-id")
        if st.button("查询公开日志") and public_id:
            go("public_log", id=public_id)
    admin = st.session_state.user["role"] == "admin"
    with st.form("record-filters"):
        if admin:
            a, b, c, extra = st.columns([2, 2, 1.5, 2])
        else:
            a, c, extra = st.columns([2, 1.5, 2])
            b = a
        pid = a.text_input("题号", value=st.query_params.get("problem_id", ""))
        uid = (
            b.text_input("用户 ID（留空为全站）", value=st.query_params.get("user_id", ""))
            if admin
            else str(st.session_state.user["user_id"])
        )
        statuses = ["全部", "pending", "success", "error"]
        outcomes = ["全部结果", "全部通过", "未全部通过"]
        status = c.selectbox(
            "状态",
            statuses,
            format_func=status_label,
            index=statuses.index(st.query_params.get("status"))
            if st.query_params.get("status") in statuses
            else 0,
        )
        outcome = extra.selectbox(
            "完成结果",
            outcomes,
            index=outcomes.index(st.query_params.get("outcome"))
            if st.query_params.get("outcome") in outcomes
            else 0,
        )
        if st.form_submit_button("查询", type="primary"):
            st.query_params.update(
                problem_id=pid, user_id=uid, page="1", status=status, outcome=outcome
            )
            st.rerun()
    params: dict[str, Any] = {"page": page_number(), "page_size": 10, "include_metadata": True}
    uid = st.query_params.get("user_id", "") if admin else str(st.session_state.user["user_id"])
    if uid:
        params["user_id"] = uid
    elif admin:
        params["all_users"] = True
    if pid := st.query_params.get("problem_id"):
        params["problem_id"] = pid
    status = st.query_params.get("status", "全部")
    if status != "全部":
        params["status"] = status
    outcome = st.query_params.get("outcome", "全部结果")
    if outcome != "全部结果":
        params["outcome"] = "passed" if outcome == "全部通过" else "not_passed"
    result = call(lambda: api.get("/api/submissions/", params=params))
    if not result:
        return
    pagination(result["data"]["total"])
    rows = result["data"]["submissions"]
    if not rows:
        st.info("没有符合条件的提交记录。")
    with st.container(key="record-list"):
        for row in rows:
            with st.container(key=f"list-row-record-{row['submission_id']}"):
                a, b = st.columns([5, 1], vertical_alignment="center")
                label, tone = verdict_label(row)
                a.write(f"**#{row['submission_id']} · {row.get('problem_id', '')}**")
                a.html(f'<span class="oj-status {tone}">{label}</span>')
                a.caption(
                    f"{row.get('score', '—')} / {row.get('counts', '—')} · "
                    f"{row.get('language', '')} · {local_time(row.get('created_at'))} 北京时间"
                )
                if b.button("查看详情", key=f"record-{row['submission_id']}"):
                    go("submission", id=row["submission_id"], title=f"提交 #{row['submission_id']}")
    pagination(result["data"]["total"], position="bottom")


def submission_page(api: ApiClient) -> None:
    if st.button("返回来源"):
        back()
    submission_id = st.query_params.get("id", "")
    if not submission_id.isdigit():
        st.error("请提供有效的提交编号。")
        return
    heading(f"提交 #{submission_id}")
    submission_result(api, submission_id)
