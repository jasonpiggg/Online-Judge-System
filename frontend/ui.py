from __future__ import annotations

from collections.abc import Callable
from html import escape
from typing import Any

import streamlit as st

from frontend.client import ApiError

CSS = """
<style>
body,.stApp {font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei',sans-serif;}
[data-testid="stHeader"] {background:#f5f7fbea;}
[data-testid="stMainBlockContainer"] {max-width:1440px;padding:3.5rem 2.5rem 4rem!important;}
h1,h2,h3 {letter-spacing:-.025em;}
[data-testid="stSidebar"][aria-expanded="true"] {width:256px!important;min-width:256px!important;}
[data-testid="stAppDeployButton"] {display:none;}
[data-testid="stSidebar"] [data-testid="stPageLink"] a {
 min-height:48px;border-radius:10px;padding:10px 12px;}
[data-testid="stSidebar"] [data-testid="stPageLink"] p {font-size:17px;font-weight:600;}
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] {
 background:#29456c;color:white;}
[data-testid="stWidgetLabel"] p {font-size:15px;font-weight:500;}
[data-testid="stCaptionContainer"] {font-size:13px;color:#66758a;}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {color:#b9c9df;}
.stButton button,.stFormSubmitButton button {min-height:44px;font-weight:600;}
[data-baseweb="input"], [data-baseweb="select"]>div {min-height:44px;}
.oj-header {margin:0 0 24px;}.oj-header h1 {margin:0;font-size:30px;font-weight:750;}
.oj-header p {margin:8px 0 0;color:#66758a;font-size:15px;}
.oj-brand {display:flex;align-items:center;gap:12px;margin:0 0 18px;font-size:22px;font-weight:750;}
.oj-mark {display:inline-grid;place-items:center;width:38px;height:38px;border-radius:11px;
 background:#3563e9;color:white;font:600 20px monospace;}
.oj-hero {padding:24px 28px;background:#eaf0fe;border:1px solid #dce6fc;border-radius:14px;
 margin:0 0 24px;}.oj-hero h2 {font-size:24px;margin:0 0 8px;}
.oj-hero p {color:#506585;margin:0;}
.oj-pill {display:inline-block;padding:4px 10px;border-radius:6px;background:#eef3fb;
 color:#4f6585;font-size:13px;margin:0 5px 4px 0;}
.oj-status {padding:7px 12px;border-radius:7px;font-weight:650;display:inline-block;}
.oj-status.pass {color:#10784f;background:#e5f6ee;}
.oj-status.fail {color:#ac3944;background:#fdebed;}
.oj-status.wait {color:#8b6416;background:#fff3d5;}
.st-key-account-footer {margin-top:40px;border-top:1px solid #30465f;padding-top:20px;}
.st-key-editor-panel,.st-key-statement-panel {
 background:white;border:1px solid #e2e8f2;border-radius:12px;padding:20px;}
[data-testid="stVerticalBlockBorderWrapper"]>div {background:white;}
[data-testid="stForm"] {background:white;}
@media(max-width:760px){
 [data-testid="stMainBlockContainer"]{padding:3rem 1rem 3rem!important;}
 .oj-header h1{font-size:26px;}
 .oj-hero{padding:20px;}.oj-hero h2{font-size:21px;}
 [data-testid="stSidebar"][aria-expanded="true"]{min-width:256px;width:256px;}
}
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
        st.error(str(exc))
    except RuntimeError as exc:
        st.error(str(exc))
    return None


def navigate(page: str, **state: Any) -> None:
    st.session_state.update(state)
    st.switch_page(st.session_state.pages[page])


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
