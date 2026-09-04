from __future__ import annotations

from functools import partial

import streamlit as st

from frontend.account import activate_user, auth_screen, profile_page
from frontend.admin import admin_page
from frontend.ai import ai_page
from frontend.client import ApiClient
from frontend.editor import editor_page
from frontend.library import breakpoint, library_page, workspace_page
from frontend.records import records_page
from frontend.ui import apply_theme, call

st.set_page_config(
    page_title="Atelier OJ · 在线评测",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="auto",
)
apply_theme()
mobile = breakpoint(
    data={"mobile": st.session_state.get("mobile")},
    on_mobile_change=lambda: None,
    key="viewport-breakpoint",
    height=0,
).mobile
if mobile is not None:
    st.session_state.mobile = bool(mobile)
else:
    st.session_state.setdefault("mobile", False)
api = ApiClient()


if not st.session_state.get("user"):
    if message := st.session_state.pop("flash", None):
        st.info(message)
    auth_screen(api)
else:
    profile = call(
        lambda: api.get(f"/api/users/{st.session_state.user['user_id']}")
    )
    if not profile:
        st.stop()
    activate_user(profile["data"])
    user = st.session_state.user
    definitions = [
        ("library", "题库", ":material/menu_book:", partial(library_page, api)),
        ("records", "提交记录", ":material/history:", partial(records_page, api)),
        ("ai", "命题中心", ":material/experiment:", partial(ai_page, api)),
    ]
    if user["role"] == "admin":
        definitions.append(("admin", "管理中心", ":material/tune:", partial(admin_page, api)))
    definitions += [
        ("profile", "个人账户", ":material/account_circle:", partial(profile_page, api)),
        ("workspace", "做题工作区", ":material/code:", partial(workspace_page, api)),
        ("editor", "题目编辑", ":material/edit_note:", partial(editor_page, api)),
    ]
    pages = {
        key: st.Page(fn, title=title, icon=icon, url_path=key, default=key == "library")
        for key, title, icon, fn in definitions
    }
    st.session_state.pages = pages
    nav = st.navigation(list(pages.values()), position="hidden")
    with st.sidebar:
        st.markdown(
            '<div class="oj-brand"><span class="oj-mark">{ }</span>Atelier OJ</div>',
            unsafe_allow_html=True,
        )
        st.caption("在线评测 · 编程实验室")
        for key, title, icon, _ in definitions:
            if key not in {"workspace", "editor"}:
                st.page_link(pages[key], label=title, icon=icon, width="stretch")
        with st.container(key="account-footer"):
            st.write(f"**{user['username']}**")
            st.caption("管理员" if user["role"] == "admin" else "学习者")
            if st.button("退出登录", icon=":material/logout:", width="stretch"):
                if call(lambda: api.post("/api/auth/logout")):
                    st.session_state.pop("user", None)
                    st.rerun()
    nav.run()
