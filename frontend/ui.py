from __future__ import annotations

from collections.abc import Callable
from html import escape
from typing import Any

import streamlit as st

from frontend.client import ApiError

CSS = """
<style>
body,.stApp {font-family:'Aptos','Noto Sans SC','Microsoft YaHei',sans-serif;}
[data-testid="stHeader"] {background:#f2efe7e8;}
[data-testid="stMainBlockContainer"] {max-width:1440px;padding:3.5rem 2.5rem 4rem!important;}
h1,h2,h3 {font-family:Georgia,'Noto Serif SC','Songti SC',serif;letter-spacing:-.018em;}
[data-testid="stSidebar"][aria-expanded="true"] {width:256px!important;min-width:256px!important;}
[data-testid="stAppDeployButton"] {display:none;}
[data-testid="stSidebar"] [data-testid="stPageLink"] a {
 min-height:46px;border-radius:5px;padding:9px 12px;border-left:2px solid transparent;}
[data-testid="stSidebar"] [data-testid="stPageLink"] p {font-size:16px;font-weight:600;}
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] {
 background:#465348;color:white;border-left-color:#e2a17d;}
[data-testid="stWidgetLabel"] p {font-size:15px;font-weight:500;}
[data-testid="stCaptionContainer"] {font-size:13px;color:#6f716a;}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {color:#c9c8bf;}
.stButton button,.stFormSubmitButton button {min-height:44px;font-weight:600;}
[data-baseweb="input"], [data-baseweb="select"]>div {min-height:44px;}
.oj-header {margin:0 0 24px;}.oj-header h1 {margin:0;font-size:30px;font-weight:750;}
.oj-header p {margin:8px 0 0;color:#6f716a;font-size:15px;}
.oj-brand {display:flex;align-items:center;gap:12px;margin:0 0 18px;font-size:22px;font-weight:750;}
.oj-mark {display:inline-grid;place-items:center;width:38px;height:38px;border-radius:5px;
 background:#b95e43;color:#fffaf1;font:600 19px 'Cascadia Mono',monospace;}
.oj-intro {padding:18px 0 20px;border-top:1px solid #cfc7b9;border-bottom:1px solid #cfc7b9;
 margin:0 0 24px;}.oj-intro h2 {font-size:23px;margin:0 0 6px;}
.oj-intro p {color:#62675f;margin:0;}
.oj-pill {display:inline-block;padding:3px 9px;border-radius:999px;background:#e8e3d8;
 color:#59635a;font-size:12px;margin:0 5px 4px 0;border:1px solid #d8d0c2;}
.oj-status {padding:6px 10px;border-radius:4px;font-weight:650;display:inline-block;}
.oj-status.pass {color:#31634a;background:#dfeadf;border:1px solid #c6d9c8;}
.oj-status.fail {color:#8f463a;background:#f2ded8;border:1px solid #e3c4bc;}
.oj-status.wait {color:#765d24;background:#eee5c9;border:1px solid #dfd1a6;}
.oj-problem-row {padding:3px 0 0;}.oj-problem-row h3 {margin:.1rem 0 .35rem;font-size:20px;}
.oj-kicker {font:600 12px 'Cascadia Mono',monospace;letter-spacing:.08em;color:#8a6b58;}
.st-key-account-footer {margin-top:40px;border-top:1px solid #30465f;padding-top:20px;}
.st-key-editor-panel,.st-key-statement-panel {
 background:#fbf9f3;border:1px solid #d9d2c5;border-radius:6px;padding:20px;}
[data-testid="stVerticalBlockBorderWrapper"]>div {background:#fbf9f3;}
[data-testid="stForm"] {background:#fbf9f3;}
[data-testid="stMetric"] {border-left:2px solid #b95e43;padding-left:12px;}
@media(max-width:760px){
 [data-testid="stMainBlockContainer"]{padding:3rem 1rem 3rem!important;}
 .oj-header h1{font-size:26px;}
 .oj-intro{padding:16px 0;}.oj-intro h2{font-size:21px;}
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
        if exc.status == 403 and "banned" in exc.server_message.casefold():
            st.session_state.pop("user", None)
            st.session_state.flash = "账户已被禁用，请联系管理员。"
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
