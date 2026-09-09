from __future__ import annotations

import json
from typing import Any

import streamlit as st
from pydantic import ValidationError

from frontend.client import ApiClient
from frontend.editor import clean_problem
from frontend.navigation import back, bounded_page, go, pagination, panel_query
from frontend.records import _render_case_details
from frontend.ui import call, heading, result_summary
from oj.schemas import DraftProblem


def read_json_file(upload: Any) -> dict[str, Any]:
    if upload.size > 10 * 1024 * 1024:
        raise ValueError("JSON 文件不能超过 10 MB。")
    text = upload.getvalue().decode("utf-8-sig", errors="strict")
    value = json.loads(text)
    if not isinstance(value, dict) or not value:
        raise ValueError("请提供单道题目的 JSON 对象。")
    return DraftProblem.model_validate(value).model_dump()


def resources_page(api: ApiClient) -> None:
    if st.session_state.user["role"] == "admin":
        from frontend.admin import admin_page

        aliases = {"题目": "题目管理", "语言": "语言", "公开日志": "公开日志"}
        if panel_query.get("section", "题目") in aliases:
            panel_query.section = aliases[panel_query.get("section", "题目")]
        # Preserve old bookmarked filters at the same URL without navigating.
        for key in ("q", "id", "page"):
            target = (
                "public_log_id" if key == "id" and panel_query.get("section") == "公开日志" else key
            )
            scoped = panel_query._key(target)
            if key in st.query_params and scoped not in st.query_params:
                panel_query[target] = st.query_params[key]
        admin_page(api)
        return
    heading("资源", note="管理题目、评测语言与公开日志。")
    options = ["题目", "语言", "公开日志"]
    current = panel_query.get("section", "题目")
    section = st.segmented_control(
        "资源类型", options, default=current if current in options else "题目"
    )
    if section:
        panel_query.section = section
    if section == "语言":
        from frontend.admin import language_page

        language_page(api)
        return
    if section == "公开日志":
        public_log_content(api)
        return
    problem_list_content(api)


def problem_list_content(api: ApiClient) -> None:
    if st.button("新建题目", type="primary"):
        result = call(lambda: api.post("/api/problem-drafts/", json={}))
        if result:
            go("draft", id=result["data"]["id"], title="新建题目")
    with st.expander("导入题目 JSON"):
        upload = st.file_uploader("选择题目 JSON", type=["json"], key="resource-json-file")
        text = st.text_area("或粘贴题目 JSON", key="resource-json-text")
        if st.button("导入为草稿"):
            try:
                data = (
                    read_json_file(upload)
                    if upload
                    else DraftProblem.model_validate(json.loads(text)).model_dump()
                )
                if not data.get("id"):
                    raise ValueError("导入题目必须包含题号。")
                existing = api.get("/api/problems/")["data"]
                if any(p["id"] == data["id"] for p in existing):
                    raise ValueError("题号已存在，请从原题进入编辑，避免覆盖。")
                result = call(lambda: api.post("/api/problem-drafts/", json={"problem": data}))
                if result:
                    go("draft", id=result["data"]["id"], title=data.get("title", "导入草稿"))
            except (ValueError, UnicodeError, ValidationError):
                st.error("导入失败：请检查 JSON 字段、文件编码、题号是否重复及大小限制。")
    result = call(lambda: api.get("/api/problems/", params={"include_metadata": True}))
    if not result:
        return
    search = st.text_input("搜索题号或标题", value=panel_query.get("q", ""))
    if search != panel_query.get("q", ""):
        panel_query.page = "1"
    panel_query.q = search
    filtered = [
        p for p in result["data"] if search.casefold() in f"{p['id']} {p['title']}".casefold()
    ]
    page = bounded_page(len(filtered))
    if not filtered:
        st.info("没有找到相关题目，请调整搜索条件。")
        return
    with st.container(key="resource-list"):
        for p in filtered[(page - 1) * 10 : page * 10]:
            with st.container(key=f"list-row-resource-{p['id']}"):
                title, a, b = st.columns([4, 1, 1], vertical_alignment="center")
                title.write(f"**{p['title']}**")
                title.caption(p["id"])
                if a.button("查看详情", key=f"resource-view-{p['id']}"):
                    panel_query.id = p["id"]
                if b.button("编辑题目", key=f"resource-edit-{p['id']}"):
                    draft = call(lambda p=p: api.post(f"/api/problems/{p['id']}/editing-draft"))
                    if draft:
                        go("draft", id=draft["data"]["id"], title=p["title"])
                if panel_query.get("id") == p["id"]:
                    detail = call(lambda p=p: api.get(f"/api/problems/{p['id']}"))
                    if detail:
                        from frontend.ui import pills

                        pills(
                            [
                                detail["data"].get("difficulty") or "未分级",
                                *detail["data"].get("tags", []),
                            ]
                        )
                        st.caption(
                            f"来源：{detail['data'].get('source') or '—'} "
                            f"· 作者：{detail['data'].get('author') or '—'}"
                        )
                        with st.expander("题面预览"):
                            from frontend.workspace import statement

                            statement(detail["data"])
                        with st.expander("题目 JSON"):
                            st.json(detail["data"], expanded=False)
                        st.download_button(
                            "下载题目 JSON",
                            json.dumps(clean_problem(detail["data"]), ensure_ascii=False, indent=2),
                            file_name=f"{p['id']}.json",
                            key=f"export-{p['id']}",
                        )
                        if st.session_state.user["role"] == "admin":
                            from frontend.editor import delete_dialog

                            visible = st.toggle(
                                "公开测试点日志",
                                value=detail["data"].get("public_cases", False),
                                key=f"visible-{p['id']}",
                            )
                            if st.button("保存日志可见性", key=f"visibility-save-{p['id']}"):
                                if call(
                                    lambda p=p, visible=visible: api.put(
                                        f"/api/problems/{p['id']}/log_visibility",
                                        json={"public_cases": visible},
                                    )
                                ):
                                    st.success("日志可见性已更新")

                            if st.button("删除题目", key=f"delete-{p['id']}"):
                                delete_dialog(api, detail["data"])
    pagination(len(filtered), position="bottom")


def public_log_page(api: ApiClient) -> None:
    heading("公开评测日志")
    if st.button("返回来源"):
        back()
    public_log_content(api)


def public_log_content(api: ApiClient, *, parameter: str = "id") -> None:
    sid = st.text_input("公开提交 ID", value=panel_query.get(parameter, ""))
    if st.button("查询"):
        panel_query[parameter] = sid
        st.rerun()
    if not sid:
        st.info("输入提交编号后查询。")
        return
    result = call(lambda: api.get(f"/api/submissions/{sid}/log"))
    if result:
        d = result["data"]
        result_summary(d)
        _render_case_details(d, "public-log")
