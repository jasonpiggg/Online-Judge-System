from __future__ import annotations

import streamlit as st

from frontend.client import ApiClient
from frontend.ui import call, heading


def activate_user(user: dict[str, object]) -> None:
    """Bind UI state to an identity without leaking drafts across account switches."""
    user_id = str(user["user_id"])
    previous = st.session_state.get("workspace_user_id")
    if previous is not None and str(previous) != user_id:
        preserved = {
            key: st.session_state[key]
            for key in ("http_session", "mobile")
            if key in st.session_state
        }
        st.session_state.clear()
        st.session_state.update(preserved)
    st.session_state.workspace_user_id = user_id
    st.session_state.user = user


def auth_screen(api: ApiClient) -> None:
    st.markdown(
        '<div class="oj-brand"><span class="oj-mark">{ }</span>Atelier OJ</div>',
        unsafe_allow_html=True,
    )
    st.divider()
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        heading("专注解题，\n看见进步。", note="一个清晰、可靠的编程练习空间。")
        st.markdown(
            '<div class="oj-hero"><h2>从思路到通过，少一点打断。</h2>'
            "<p>在同一页阅读题目、编写代码与查看结果。每个测试点都有答案。</p></div>",
            unsafe_allow_html=True,
        )
        for title, description in [
            ("01  阅读与编写", "题面、样例与代码同屏，思路不必来回切换。"),
            ("02  真实评测", "运行 Python / C++14，查看时间、内存和逐点结果。"),
            ("03  回顾与改进", "保留提交记录，使用 AI 辅助命题并验证测试数据。"),
        ]:
            st.markdown(f"**{title}**")
            st.caption(description)
    with right, st.container(border=True):
        st.subheader("欢迎回来")
        st.caption("登录你的工作区，继续上一次思考。")
        login, register = st.tabs(["登录", "注册账户"])
        with login, st.form("login"):
            username = st.text_input("用户名", placeholder="输入用户名", key="login-name")
            password = st.text_input("密码", type="password", key="login-password")
            if st.form_submit_button("进入工作台", type="primary", width="stretch"):
                result = call(
                    lambda: api.post(
                        "/api/auth/login",
                        json={
                            "username": username,
                            "password": password,
                        },
                    )
                )
                if result:
                    activate_user(result["data"])
                    st.rerun()
        with register, st.form("register"):
            username = st.text_input("新用户名", help="3–40 个字符")
            password = st.text_input("设置密码", type="password", help="至少 6 个字符")
            if st.form_submit_button("注册", width="stretch"):
                if call(
                    lambda: api.post(
                        "/api/users/",
                        json={
                            "username": username,
                            "password": password,
                        },
                    )
                ):
                    st.success("账户已创建。请切换到登录标签进入工作区。")
        with st.expander("本地演示账户"):
            st.caption("管理员：admin / admintestpassword。仅用于本地课程实验。")


def profile_page(api: ApiClient) -> None:
    heading("个人账户", note="你的练习记录与账户信息。")
    result = call(lambda: api.get(f"/api/users/{st.session_state.user['user_id']}"))
    if not result:
        return
    user = result["data"]
    a, b, c = st.columns(3)
    a.metric("提交次数", user["submit_count"])
    b.metric("通过题目", user["resolve_count"])
    c.metric("账户角色", "管理员" if user["role"] == "admin" else "学习者")
    with st.container(border=True):
        st.subheader(user["username"])
        st.write(f"用户 ID：{user['user_id']}")
        st.caption(f"加入时间：{user['join_time']}")
