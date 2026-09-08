from __future__ import annotations

from collections.abc import Callable
from html import escape
from typing import Any

import streamlit as st

from frontend.client import ApiError

CSS = """
<style>
body,.stApp {font-family:system-ui,'Microsoft YaHei',sans-serif;color:#1d293d;background:#fff}
[data-testid="stHeader"] {background:#ffffffee}
[data-testid="stMainBlockContainer"] {max-width:1440px;padding:1.5rem 2rem 4rem}
h1,h2,h3 {font-family:inherit;letter-spacing:-.015em}
[data-testid="stAppDeployButton"] {display:none}
[data-testid="stWidgetLabel"] p,.stButton button,[data-testid="stCaptionContainer"] {font-size:14px}
.stButton button,.stFormSubmitButton button {min-height:40px;border-radius:8px}
[data-testid="stCaptionContainer"] {color:#617087}
.oj-header {margin:0 0 20px}.oj-header h1{margin:0;font-size:28px}
.oj-header p{margin:8px 0;color:#617087}
.oj-pill,.oj-status {display:inline-block;border:1px solid #e3eaf3;background:#f5f8fe;
border-radius:8px;padding:4px 9px;margin:3px;font-size:14px}
.oj-status.pass{color:#197348}.oj-status.fail{color:#b42332}.oj-status.wait{color:#8c6415}
[data-testid="stExpander"],[data-testid="stForm"]{border-color:#e3eaf3;border-radius:12px}
[data-testid="stMetricValue"]{font-size:24px}
.st-key-task-bar {position:sticky;top:3rem;z-index:90;background:#fff;
border-bottom:1px solid #e3eaf3;padding:6px 0}
pre,code {font-family:'JetBrains Mono',Consolas,monospace}
.st-key-section-nav {position:sticky;top:7rem;background:#fff;z-index:80}
@media(max-width:760px){[data-testid="stMainBlockContainer"]{padding:1rem .75rem 3rem}
.stButton button{min-height:44px}.oj-header h1{font-size:24px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;animation:none!important;transition:none!important}}
</style>
"""


def apply_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def heading(kicker: str, title: str = "", note: str = "") -> None:
    st.markdown(
        f'<div class="oj-header"><h1>{escape(title or kicker)}</h1><p>{escape(note)}</p></div>',
        unsafe_allow_html=True,
    )


def call(action: Callable[[], dict[str, Any]]) -> dict[str, Any] | None:
    try:
        return action()
    except ApiError as exc:
        if exc.status == 401 and st.session_state.get("user"):
            st.session_state.pop("user", None)
            st.session_state.flash = "登录已过期，请重新登录。草稿仍保留在当前会话。"
            st.rerun()
        if exc.status == 403 and "banned" in exc.server_message.casefold():
            st.session_state.pop("user", None)
            st.session_state.flash = "账户已被禁用，请联系管理员。"
            st.rerun()
        st.error(str(exc))
    except RuntimeError as exc:
        st.error(str(exc))
    return None


def navigate(page: str, **state: Any) -> None:
    from frontend.navigation import go

    st.session_state.update(state)
    pid = state.get("current_problem")
    go(page, **({"id": pid} if pid else {}))


def pills(values: list[str]) -> None:
    st.markdown(
        "".join(f'<span class="oj-pill">{escape(v)}</span>' for v in values), unsafe_allow_html=True
    )


def pager(key: str, count: int | None = None, size: int = 10, has_next: bool = False) -> int:
    page = st.session_state.get(key, 1)
    last = max(1, (count + size - 1) // size) if count is not None else None
    if last and page > last:
        page = last
        st.session_state[key] = page
    with st.container(horizontal=True, vertical_alignment="center"):
        if st.button("上一页", key=f"{key}-prev", disabled=page == 1):
            st.session_state[key] = page - 1
            st.rerun()
        st.caption(f"{page} / {last} 页" if last else f"第 {page} 页")
        if st.button("下一页", key=f"{key}-next", disabled=page >= last if last else not has_next):
            st.session_state[key] = page + 1
            st.rerun()
    return page
