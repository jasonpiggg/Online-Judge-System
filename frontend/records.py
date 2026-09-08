from __future__ import annotations

from typing import Any

import streamlit as st

from frontend.client import ApiClient
from frontend.components import diff
from frontend.navigation import back, go, page_number, pagination
from frontend.ui import call, heading


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
        st.dataframe(shown, width="stretch", hide_index=True)
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
        score, total = d.get("score"), d.get("counts")
        if status == "error":
            st.error(d.get("error_info") or "评测服务异常")
        elif total and score == total:
            st.success("全部通过")
        else:
            st.warning("评测完成 · 未全部通过")
        st.metric(
            "得分", f"{score if score is not None else '—'} / {total if total is not None else '—'}"
        )
        if total and score is not None:
            st.progress(min(1.0, max(0.0, score / total)))
        st.caption(
            f"{d.get('problem_id', '')} · {d.get('language', '')} · {d.get('created_at', '')}"
        )
        evaluation = d.get("evaluation", {})
        verdict = evaluation.get("verdict")
        labels = {
            "CE": "编译失败",
            "WA": "答案错误",
            "TLE": "超出时间限制",
            "MLE": "超出内存限制",
            "RE": "运行时错误",
            "empty": "没有测试点",
            "unknown": "评测明细不完整",
            "partial": "部分通过",
            "failed": "测试未通过",
        }
        if verdict in labels:
            st.write(labels[verdict])
        if evaluation.get("passed_cases") is not None and evaluation.get("total_cases"):
            st.caption(f"通过测试点：{evaluation['passed_cases']} / {evaluation['total_cases']}")
        for field, title in [
            ("compile_info", "编译诊断"),
            ("run_info", "运行信息"),
            ("error_info", "错误信息"),
        ]:
            value = d.get(field)
            message = value.get("message", "") if isinstance(value, dict) else value
            if message:
                with st.expander(title):
                    st.code(str(message), language=None, wrap_lines=False)
        logs = call(lambda: api.get(f"/api/submissions/{submission_id}/log"))
        if logs:
            _render_case_details(logs["data"], f"submission-{submission_id}")
        if d.get("code"):
            with st.expander("本次提交代码", expanded=True):
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
        a, b, c = st.columns(3)
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
            index=statuses.index(st.query_params.get("status"))
            if st.query_params.get("status") in statuses
            else 0,
        )
        outcome = st.selectbox(
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
    for row in rows:
        with st.container(border=True):
            a, b = st.columns([5, 1])
            a.write(f"#{row['submission_id']} · {row.get('problem_id', '')} · {row['status']}")
            a.caption(
                f"{row.get('score', '—')} / {row.get('counts', '—')} · "
                f"{row.get('language', '')} · {row.get('created_at', '')}"
            )
            if b.button("查看详情", key=f"record-{row['submission_id']}"):
                go("submission", id=row["submission_id"], title=f"提交 #{row['submission_id']}")


def submission_page(api: ApiClient) -> None:
    if st.button("返回来源"):
        back()
    submission_id = st.query_params.get("id", "")
    if not submission_id.isdigit():
        st.error("请提供有效的提交编号。")
        return
    heading(f"提交 #{submission_id}")
    submission_result(api, submission_id)
