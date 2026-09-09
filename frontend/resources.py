from __future__ import annotations

import json
from typing import Any

import streamlit as st
from pydantic import ValidationError

from frontend.admin import language_page
from frontend.client import ApiClient
from frontend.editor import clean_problem
from frontend.navigation import back, go, pagination
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
    heading("资源", note="管理题目、评测语言与公开日志。")
    options = ["题目", "语言", "公开日志"]
    current = st.query_params.get("section", "题目")
    section = st.segmented_control(
        "资源类型", options, default=current if current in options else "题目"
    )
    if section:
        st.query_params.section = section
    if section == "语言":
        language_page(api)
        return
    if section == "公开日志":
        sid = st.text_input("公开提交 ID")
        if st.button("查看日志"):
            if sid.strip():
                go("public_log", id=sid.strip())
            else:
                st.warning("请输入提交 ID。")
        return
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
    search = st.text_input("搜索题号或标题", value=st.query_params.get("q", ""))
    if search != st.query_params.get("q", ""):
        st.query_params.page = "1"
    st.query_params.q = search
    filtered = [
        p for p in result["data"] if search.casefold() in f"{p['id']} {p['title']}".casefold()
    ]
    page = pagination(len(filtered))
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
                    st.query_params.id = p["id"]
                if b.button("编辑题目", key=f"resource-edit-{p['id']}"):
                    draft = call(lambda p=p: api.post(f"/api/problems/{p['id']}/editing-draft"))
                    if draft:
                        go("draft", id=draft["data"]["id"], title=p["title"])
                if st.query_params.get("id") == p["id"]:
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
    sid = st.text_input("公开提交 ID", value=st.query_params.get("id", ""))
    if st.button("查询"):
        st.query_params.id = sid
        st.rerun()
    if not sid:
        st.info("输入提交编号后查询。")
        return
    result = call(lambda: api.get(f"/api/submissions/{sid}/log"))
    if result:
        d = result["data"]
        result_summary(d)
        _render_case_details(d, "public-log")
