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
    with st.container(key="auth-shell"):
        _auth_form(api)


def _auth_form(api: ApiClient) -> None:
    import time
    import uuid

    from pydantic import ValidationError

    from frontend.components import control
    from oj.schemas import Credentials

    heading("Atelier OJ", note="登录，继续练习。注册后将自动登录并返回当前页面。")
    if flash := st.session_state.pop("flash", None):
        st.warning(flash)
    if error := st.session_state.get("auth_error"):
        st.error(error)
    remaining = max(0, int(st.session_state.get("auth_retry_at", 0) - time.monotonic()))
    if remaining:

        @st.fragment(run_every=1)
        def countdown() -> None:
            seconds = max(0, int(st.session_state.get("auth_retry_at", 0) - time.monotonic()))
            if not seconds:
                st.rerun()
            st.info(f"登录尝试过于频繁，请在 {seconds} 秒后重试。")

        countdown()
    login, register = st.tabs(["登录", "注册"])
    for container, mode, label in [(login, "login", "进入工作台"), (register, "register", "注册")]:
        with container:
            with st.form(f"auth-{mode}"):
                name = st.text_input("用户名", key=f"auth-name-{mode}")
                password = st.text_input("密码", type="password", key=f"auth-password-{mode}")
                confirmation = (
                    st.text_input("确认密码", type="password", key="auth-confirm")
                    if mode == "register"
                    else password
                )
                if st.form_submit_button(label, type="primary", disabled=remaining > 0):
                    try:
                        Credentials(username=name, password=password)
                        if password != confirmation:
                            raise ValueError("两次输入的密码不一致。")
                    except ValidationError as exc:
                        st.error("；".join(e["msg"] for e in exc.errors(include_input=False)))
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state.auth_request = {
                            "action": mode,
                            "username": name,
                            "password": password,
                            "nonce": uuid.uuid4().hex,
                        }
    if pending := st.session_state.get("auth_request"):
        result = control("auth", "auth-bridge", api=api.base_url, **pending).result
        if result:
            st.session_state.pop("auth_request", None)
            payload = result.get("payload", {})
            error = payload.get("error", {})
            fields = error.get("fields", [])
            st.session_state.auth_error = (
                "；".join(f"{f['field']}：{f['message']}" for f in fields)
                or error.get("title")
                or payload.get("msg", "登录失败")
            )
            if "banned" in str(payload.get("msg", "")).casefold():
                st.session_state.auth_error = "账户已被禁用，请联系管理员。"
            if result.get("status") == 429:
                st.session_state.auth_retry_at = time.monotonic() + int(
                    result.get("retryAfter") or 300
                )
            st.rerun()


def logout_control(api: ApiClient, key: str = "account-logout") -> None:
    import uuid

    from frontend.components import control

    if st.button("退出登录", width="stretch", key=key):
        st.session_state.logout_nonce = uuid.uuid4().hex
        st.session_state.logout_owner = key
    if (nonce := st.session_state.get("logout_nonce")) and st.session_state.get(
        "logout_owner"
    ) == key:
        result = control("auth", "logout-bridge", action="logout", nonce=nonce, api=api.base_url)
        if result.result:
            st.session_state.pop("logout_nonce", None)
            st.error("退出请求失败，请重试。")
        # Do not render private pages while browser logout is in progress.
        st.stop()


def profile_page(api: ApiClient) -> None:
    with st.container(key="profile-shell"):
        _profile_content(api)


def _profile_content(api: ApiClient) -> None:
    heading("个人账户", note="你的练习记录与账户信息。")
    result = call(lambda: api.get(f"/api/users/{st.session_state.user['user_id']}"))
    if not result:
        return
    user = result["data"]
    with st.container(border=True):
        st.subheader(user["username"])
        from frontend.ui import local_time

        st.caption(
            f"用户 ID：{user['user_id']} · 加入时间：{local_time(user['join_time'])} 北京时间"
        )
        from frontend.ui import pills, status_label

        pills([status_label(user["role"])])
    a, b = st.columns(2)
    a.metric("提交次数", user["submit_count"])
    b.metric("通过题目", user["resolve_count"])
    with st.expander("修改密码"):
        st.caption("修改后其他设备将退出登录，当前会话保留。")
        with st.form("change-password", clear_on_submit=True):
            current = st.text_input("当前密码", type="password")
            new = st.text_input(
                "新密码", type="password", help="至少 6 个字符，最多 72 个 UTF-8 字节"
            )
            confirm = st.text_input("确认新密码", type="password")
            if st.form_submit_button("更新密码", type="primary"):
                if error := password_change_error(current, new, confirm):
                    st.error(error)
                elif call(
                    lambda: api.post(
                        "/api/auth/password",
                        json={
                            "current_password": current,
                            "new_password": new,
                        },
                    )
                ):
                    st.success("密码已更新，其他设备已退出登录。")
    logout_control(api)
    from frontend.ai import model_settings

    with st.expander("个人模型设置"):
        config = call(lambda: api.get("/api/ai/model-config"))
        if config:
            model_settings(api, config["data"])


def password_change_error(current: str, new: str, confirm: str) -> str | None:
    if not current:
        return "请输入当前密码。"
    if not new:
        return "请输入新密码。"
    if not confirm:
        return "请再次输入新密码以确认。"
    if len(current.encode("utf-8")) > 72:
        return "当前密码超过 72 个 UTF-8 字节，请检查输入或联系管理员。"
    if len(current) < 6:
        return "当前密码不正确，请重新输入。"
    if len(new) < 6:
        return "新密码至少需要 6 个字符。"
    if len(new.encode("utf-8")) > 72:
        return "新密码最多 72 个 UTF-8 字节，请缩短密码。"
    if new != confirm:
        return "两次输入的新密码不一致，请重新确认。"
    if current == new:
        return "新密码不能与当前密码相同，请设置不同的新密码。"
    return None
