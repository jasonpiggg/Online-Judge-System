from __future__ import annotations

import streamlit as st
from pydantic import ValidationError

from frontend.client import ApiClient
from frontend.navigation import bounded_page, page_number, pagination, panel_query
from frontend.ui import call, data_table, heading, status_label
from oj.schemas import Credentials


@st.dialog("恢复初始实验数据")
def reset_dialog(api: ApiClient) -> None:
    st.error("此操作将清除运行数据、恢复初始题目和管理员，并退出全部会话。")
    confirmed = st.text_input("输入 RESET 确认", key="reset-confirm")
    if st.button("取消"):
        st.rerun()
    if st.button("确认重置", type="primary", disabled=confirmed != "RESET"):
        if call(lambda: api.post("/api/reset/")):
            st.session_state.clear()
            st.rerun()


def admin_page(api: ApiClient) -> None:
    heading("管理中心", note="管理账户与评测配置。危险操作需要额外确认。")
    sections = [
        "用户",
        "角色审计",
        "全站提交",
        "题目管理",
        "语言",
        "公开日志",
        "访问审计",
        "系统设置",
    ]
    selected = panel_query.get("section", "用户")
    selected = selected if selected in sections else "用户"
    if st.session_state.get("admin-section-url") != selected:
        st.session_state["admin-section"] = selected
    section = (
        st.selectbox("管理模块", sections, index=None, key="admin-section")
        if st.session_state.get("mobile")
        else st.segmented_control(
            "管理模块",
            sections,
            key="admin-section",
            label_visibility="collapsed",
        )
    )
    section = section or selected
    if section:
        panel_query["section"] = section
        st.session_state["admin-section-url"] = section
    with st.container(border=True, key="admin-content-panel"):
        st.subheader(section or "系统设置")
        if section == "用户":
            search = st.text_input("搜索用户名或用户 ID", value=panel_query.get("q", ""))
            if search != panel_query.get("q", ""):
                panel_query.update(q=search, users_page="1")
            page = page_number("users_page")
            result = call(
                lambda: api.get("/api/users/", params={"page": page, "page_size": 10, "q": search})
            )
            if not result:
                return
            bounded_page(result["data"]["total"], "users_page")
            if not result["data"]["total"]:
                st.info("没有找到相关账户，请调整搜索条件。")
            users = result["data"]["users"]
            data_table(users)
            pagination(result["data"]["total"], "users_page")
            if users:
                with st.container(border=True):
                    st.subheader("修改用户角色")
                    who = st.selectbox(
                        "目标用户", users, format_func=lambda x: f"{x['user_id']} · {x['username']}"
                    )
                    with st.expander("用户资料"):
                        detail = call(lambda: api.get(f"/api/users/{who['user_id']}"))
                        if detail:
                            person = detail["data"]
                            st.write(f"{person['username']} · {status_label(person['role'])}")
                            st.caption(
                                f"提交 {person['submit_count']} 次 · "
                                f"通过 {person['resolve_count']} 题"
                            )
                    role = st.selectbox(
                        "角色",
                        ["user", "admin", "banned"],
                        format_func=status_label,
                        index=["user", "admin", "banned"].index(who["role"]),
                    )
                    changing = role != who["role"]
                    if changing and str(who["user_id"]) == str(st.session_state.user["user_id"]):
                        st.warning("正在修改当前登录账户；降权或禁用后管理入口会立即消失。")
                    confirmed = st.checkbox(
                        f"确认将 {who['username']} 从 {who['role']} 改为 {role}",
                        disabled=not changing,
                    )
                    if st.button(
                        "保存角色", type="primary", disabled=not changing or not confirmed
                    ):
                        if call(
                            lambda: api.put(
                                f"/api/users/{who['user_id']}/role", json={"role": role}
                            )
                        ):
                            st.toast("角色已更新")
                            st.rerun()
            with st.expander("创建新账户"):
                with st.form("admin-create-user"):
                    name = st.text_input("用户名")
                    password = st.text_input("初始密码", type="password")
                    admin = st.checkbox("创建为管理员")
                    if st.form_submit_button("创建账户"):
                        try:
                            Credentials(username=name, password=password)
                        except ValidationError as exc:
                            st.error("；".join(e["msg"] for e in exc.errors(include_input=False)))
                            return
                        endpoint = "/api/users/admin" if admin else "/api/users/"
                        if call(
                            lambda: api.post(
                                endpoint, json={"username": name, "password": password}
                            )
                        ):
                            st.success("账户已创建")
        elif section == "全站提交":
            from frontend.records import records_content

            records_content(api)
        elif section == "题目管理":
            from frontend.resources import problem_list_content

            problem_list_content(api)
        elif section == "公开日志":
            from frontend.resources import public_log_content

            public_log_content(api, parameter="public_log_id")
        elif section == "角色审计":
            result = call(
                lambda: api.get(
                    "/api/logs/roles/",
                    params={"page": page_number(), "page_size": 10, "include_metadata": True},
                )
            )
            if result:
                bounded_page(result["data"]["total"])
                data_table(result["data"]["logs"])
                if not result["data"]["logs"]:
                    st.info("还没有角色修改记录。")
                pagination(result["data"]["total"], position="bottom")
        elif section == "语言":
            language_page(api)
        elif section == "访问审计":
            with st.form("audit-filters"):
                a, b = st.columns(2)
                uid = a.text_input("用户 ID（留空为全部）", value=panel_query.get("user_id", ""))
                pid = b.text_input("题号（留空为全部）", value=panel_query.get("problem_id", ""))
                if st.form_submit_button("查询访问审计"):
                    panel_query.update(user_id=uid, problem_id=pid, audit_page="1")
                    st.rerun()
            uid, pid = panel_query.get("user_id", ""), panel_query.get("problem_id", "")
            params = {"page_size": 10, "page": page_number("audit_page"), "include_metadata": True}
            if uid:
                params["user_id"] = uid
            if pid:
                params["problem_id"] = pid
            if not uid and not pid.strip():
                st.info("请填写用户 ID 或题号后查询访问审计。")
                return
            result = call(lambda: api.get("/api/logs/access/", params=params))
            if result:
                bounded_page(result["data"]["total"], "audit_page")
                data_table(result["data"]["logs"])
                if not result["data"]["logs"]:
                    st.info("当前筛选条件下没有访问日志。")
                pagination(result["data"]["total"], "audit_page", position="bottom")
        else:
            st.subheader("实验环境")
            st.info("完整评测请使用 Linux/WSL，单 Uvicorn worker，仅绑定 localhost。")
            st.subheader("恢复初始状态")
            st.caption("保留数据升级不需要重置。此操作仅用于重新开始课程演示。")
            if st.button("重置实验系统", type="secondary"):
                reset_dialog(api)


def language_page(api: ApiClient) -> None:
    languages = call(lambda: api.get("/api/languages/", params={"include_metadata": True}))
    if languages:
        data_table(languages["data"]["languages"])
    with st.expander("注册评测语言", expanded=False), st.form("register-language"):
        a, b = st.columns(2)
        name = a.text_input("语言标识", placeholder="python_alt")
        extension = b.text_input("文件扩展名", placeholder=".py")
        compile_cmd = st.text_input(
            "编译命令（可选）", help="仅允许安全可执行程序及 {src}/{exe} 模板"
        )
        run_cmd = st.text_input("运行命令", placeholder="python3 {src}")
        a, b = st.columns(2)
        seconds = a.number_input("默认时间 / 秒", min_value=0.1, max_value=30.0, value=3.0)
        memory = b.number_input("默认内存 / MB", min_value=16, max_value=2048, value=128)
        if st.form_submit_button("注册语言", type="primary"):
            if call(
                lambda: api.post(
                    "/api/languages/",
                    json={
                        "name": name,
                        "file_ext": extension,
                        "compile_cmd": compile_cmd or None,
                        "run_cmd": run_cmd,
                        "time_limit": seconds,
                        "memory_limit": memory,
                    },
                )
            ):
                st.success("语言已注册。题目选择继承限制时将使用此配置。")
