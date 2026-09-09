from __future__ import annotations

from collections.abc import Callable
from functools import partial

import streamlit as st

from frontend.account import activate_user, auth_screen, logout_control, profile_page
from frontend.admin import admin_page
from frontend.authoring import authoring_page, draft_page, task_page
from frontend.client import ApiClient, ApiError
from frontend.components import control
from frontend.editor import editor_page
from frontend.library import breakpoint, library_page
from frontend.navigation import DETAILS, restore_slots, route, task_bar
from frontend.records import records_page, submission_page
from frontend.resources import public_log_page, resources_page
from frontend.ui import apply_theme, call
from frontend.workspace import workspace_page

st.set_page_config(
    page_title="Atelier OJ · 在线评测",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)
apply_theme()
api = ApiClient()
if not st.session_state.get("user") and api.session.cookies:
    try:
        activate_user(api.get("/api/auth/me")["data"])
    except ApiError:
        api.session.cookies.clear()
    except RuntimeError as exc:
        st.error(str(exc))
        st.stop()


def guarded(fn: Callable[[ApiClient], None], admin: bool = False) -> None:
    if not st.session_state.get("user"):
        auth_screen(api)
        return
    profile = call(lambda: api.get("/api/auth/me"))
    if not profile:
        return
    activate_user(profile["data"])
    if admin and st.session_state.user["role"] != "admin":
        st.error("此页面仅管理员可访问。")
        return
    task_bar()
    fn(api)


definitions = [
    ("library", "题库", library_page),
    ("records", "提交记录", records_page),
    ("ai", "命题中心", authoring_page),
    ("resources", "资源", resources_page),
    ("profile", "个人账户", profile_page),
    ("admin", "管理中心", admin_page),
]
definitions += [
    ("workspace", "做题工作区", workspace_page),
    ("editor", "题目编辑", editor_page),
    ("draft", "命题草稿", draft_page),
    ("ai_task", "AI 任务", task_page),
    ("submission", "提交详情", submission_page),
    ("public_log", "公开日志", public_log_page),
]
pages = {
    key: st.Page(
        partial(guarded, fn, key == "admin"),
        title=title,
        url_path=key,
        default=key == "library",
        visibility="hidden"
        if key in DETAILS
        or key == "admin"
        and st.session_state.get("user", {}).get("role") != "admin"
        else "visible",
    )
    for key, title, fn in definitions
}
st.session_state.pages = pages
nav = st.navigation(
    list(pages.values()), position="top" if st.session_state.get("user") else "hidden"
)
responsive = breakpoint(
    data={"mobile": st.session_state.get("mobile")},
    key="viewport-state",
    on_mobile_change=lambda: None,
    height=0,
)
if isinstance(responsive.mobile, bool):
    st.session_state.mobile = responsive.mobile
current = nav.url_path or "library"
st.session_state.pop("active_slot", None)
st.session_state.current_route = route(current, st.query_params.to_dict())
for slot in st.session_state.get("task_slots", []):
    if (
        current in DETAILS
        and slot["current"]["page"] == current
        and slot["current"]["params"].get("id") == st.query_params.get("id")
    ):
        slot["current"] = st.session_state.current_route
        st.session_state.active_slot = slot["key"]
        break
if st.session_state.get("user"):
    user = st.session_state.user
    bridge = control(
        "state",
        f"browser-state-{user['user_id']}",
        owner=str(user["user_id"]),
        api=api.base_url,
        payload=st.session_state.get("task_slots"),
        url=current,
        dirty=bool(st.session_state.get("unsaved")),
    )
    if isinstance(bridge.restored, list) and not st.session_state.get("slots_restored"):
        st.session_state.task_slots = restore_slots(bridge.restored)
        st.session_state.slots_restored = True
        st.rerun()
    if not st.session_state.get("slots_restored"):
        st.info("正在恢复页面状态……")
        st.stop()
    if current in DETAILS and not any(
        s["current"]["page"] == current
        and s["current"]["params"].get("id") == st.query_params.get("id")
        for s in st.session_state.get("task_slots", [])
    ):
        import uuid

        slots = st.session_state.setdefault("task_slots", [])
        if len(slots) < 40:
            slot = {
                "key": uuid.uuid4().hex,
                "current": st.session_state.current_route,
                "origin": route("library"),
                "history": [],
                "title": st.query_params.get("id", nav.title),
            }
            slots.append(slot)
            st.session_state.active_slot = slot["key"]
            st.rerun()
    with st.container(horizontal=True, vertical_alignment="center", key="brand-bar"):
        st.html('<div class="oj-brand">Atelier <span>OJ</span></div>')
        with st.popover(f"{user['username']} · 账户"):
            st.caption("管理员" if user["role"] == "admin" else "学习者")
            st.page_link(pages["profile"], label="个人账户")
            logout_control(api, key="header-logout")

nav.run()
