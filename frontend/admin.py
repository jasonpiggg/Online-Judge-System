from __future__ import annotations

import streamlit as st

from frontend.client import ApiClient
from frontend.ui import call, heading, pager


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
    section = st.segmented_control(
        "管理模块",
        ["用户", "语言", "访问审计", "系统设置"],
        default="用户",
        label_visibility="collapsed",
    )
    if section == "用户":
        page = st.session_state.get("users-page", 1)
        result = call(lambda: api.get("/api/users/", params={"page": page, "page_size": 10}))
        if not result:
            return
        pager("users-page", result["data"]["total"])
        users = result["data"]["users"]
        st.dataframe(users, width="stretch", hide_index=True)
        if users:
            with st.container(border=True):
                st.subheader("修改用户角色")
                who = st.selectbox(
                    "目标用户", users, format_func=lambda x: f"{x['user_id']} · {x['username']}"
                )
                role = st.selectbox(
                    "角色",
                    ["user", "admin", "banned"],
                    index=["user", "admin", "banned"].index(who["role"]),
                )
                changing = role != who["role"]
                if changing and str(who["user_id"]) == str(st.session_state.user["user_id"]):
                    st.warning("正在修改当前登录账户；降权或禁用后管理入口会立即消失。")
                confirmed = st.checkbox(
                    f"确认将 {who['username']} 从 {who['role']} 改为 {role}",
                    disabled=not changing,
                )
                if st.button("保存角色", type="primary", disabled=not changing or not confirmed):
                    if call(
                        lambda: api.put(f"/api/users/{who['user_id']}/role", json={"role": role})
                    ):
                        st.toast("角色已更新")
                        st.rerun()
        with st.expander("创建新账户"):
            with st.form("admin-create-user"):
                name = st.text_input("用户名")
                password = st.text_input("初始密码", type="password")
                admin = st.checkbox("创建为管理员")
                if st.form_submit_button("创建账户"):
                    endpoint = "/api/users/admin" if admin else "/api/users/"
                    if call(
                        lambda: api.post(endpoint, json={"username": name, "password": password})
                    ):
                        st.success("账户已创建")
    elif section == "语言":
        languages = call(lambda: api.get("/api/languages/", params={"include_metadata": True}))
        if languages:
            st.dataframe(languages["data"]["languages"], width="stretch", hide_index=True)
        with st.expander("注册评测语言", expanded=True), st.form("register-language"):
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
    elif section == "访问审计":
        a, b = st.columns(2)
        uid = a.number_input("用户 ID（0 为全部）", min_value=0, value=0, step=1)
        pid = b.text_input("题号（留空为全部）")
        signature = (uid, pid)
        if st.session_state.get("audit-filter") != signature:
            st.session_state["audit-page"] = 1
            st.session_state["audit-filter"] = signature
        params = {"page_size": 10, "page": st.session_state.get("audit-page", 1)}
        if uid:
            params["user_id"] = uid
        if pid:
            params["problem_id"] = pid
        result = call(lambda: api.get("/api/logs/access/", params=params))
        if result:
            pager("audit-page", has_next=len(result["data"]) == 10)
            st.dataframe(result["data"], width="stretch", hide_index=True)
            if not result["data"]:
                st.info("当前筛选条件下没有访问日志。")
    else:
        st.subheader("实验环境")
        st.info("完整评测请使用 Linux/WSL，单 Uvicorn worker，仅绑定 localhost。")
        st.subheader("恢复初始状态")
        st.caption("保留数据升级不需要重置。此操作仅用于重新开始课程演示。")
        if st.button("重置实验系统", type="secondary"):
            reset_dialog(api)
