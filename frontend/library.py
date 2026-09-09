from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st

from frontend.client import ApiClient
from frontend.navigation import bounded_page, go, pagination
from frontend.ui import call, heading, navigate, pills
from frontend.workspace import statement as statement
from oj.difficulty import DIFFICULTIES, normalize_difficulty

BREAKPOINT_JS = """export default function(c) {
      const media = window.matchMedia('(max-width: 760px)');
      let previous = c.data.mobile;
      const update = () => {
        if (previous !== media.matches) {
          // Use the native sidebar toggle once on entering the narrow layout.
          // Do not force it closed on reruns: users can still open the menu.
          if (media.matches) {
            document.querySelector('[data-testid="stSidebar"][aria-expanded="true"] '
              + '[data-testid="stSidebarCollapseButton"] button')?.click();
          }
          previous = media.matches;
          c.setStateValue('mobile', media.matches);
        }
      };
      update(); media.addEventListener('change', update);
      return () => media.removeEventListener('change', update);
    }"""


def breakpoint(**kwargs: Any) -> Any:
    # Register inside the active Streamlit runtime, not during module import/pytest collection.
    return st.components.v2.component("oj_breakpoint", js=BREAKPOINT_JS)(**kwargs)


def library_page(api: ApiClient) -> None:
    heading("题库", note="按状态继续练习，或搜索下一道题。")
    result = call(
        lambda: api.get(
            "/api/problems/", params={"include_metadata": True, "include_progress": True}
        )
    )
    if not result:
        return
    problems = result["data"]
    levels = [level["label"] for level in DIFFICULTIES]
    levels += sorted({p.get("difficulty", "") for p in problems} - set(levels) - {""})
    progress_options = ["全部状态", "未开始", "尝试中", "已通过"]
    progress_value = st.query_params.get("progress", "全部状态")
    progress_index = (
        progress_options.index(progress_value) if progress_value in progress_options else 0
    )
    if st.session_state.get("mobile"):
        query = st.text_input(
            "搜索题目",
            placeholder="题号、标题或标签",
            key="library-search",
            value=st.query_params.get("q", ""),
        )
        with st.expander("筛选与题目管理"):
            level = st.selectbox(
                "难度",
                ["全部难度", *levels],
                index=(
                    ["全部难度", *levels].index(st.query_params.get("difficulty", "全部难度"))
                    if st.query_params.get("difficulty", "全部难度") in ["全部难度", *levels]
                    else 0
                ),
            )
            progress_filter = st.selectbox("学习状态", progress_options, index=progress_index)
            if st.button("新建题目", icon=":material/add:", width="stretch"):
                created = call(lambda: api.post("/api/problem-drafts/", json={}))
                if created:
                    go("draft", id=created["data"]["id"], title="新建题目")
    else:
        a, b, c, d = st.columns([3, 1.1, 1.1, 1.2], vertical_alignment="bottom")
        query = a.text_input(
            "搜索题目",
            placeholder="题号、标题或标签",
            key="library-search",
            value=st.query_params.get("q", ""),
        )
        level = b.selectbox(
            "难度",
            ["全部难度", *levels],
            index=(
                ["全部难度", *levels].index(st.query_params.get("difficulty", "全部难度"))
                if st.query_params.get("difficulty", "全部难度") in ["全部难度", *levels]
                else 0
            ),
        )
        progress_filter = c.selectbox("学习状态", progress_options, index=progress_index)
        if d.button("新建题目", icon=":material/add:", type="secondary", width="stretch"):
            created = call(lambda: api.post("/api/problem-drafts/", json={}))
            if created:
                go("draft", id=created["data"]["id"], title="新建题目")

    signature = (query, level, progress_filter)
    previous = st.session_state.get("library-filter", signature)
    st.session_state["library-filter"] = signature
    if previous != signature:
        st.query_params["page"] = "1"
    st.query_params.update(q=query, difficulty=level, progress=progress_filter)
    with st.popover("难度说明"):
        for item in DIFFICULTIES:
            st.write(f"**{item['label']}**：{item['description']}")

    def progress_label(item: dict[str, Any]) -> str:
        progress = item.get("progress", {})
        if progress.get("passed"):
            return "已通过"
        return "尝试中" if progress.get("attempts", 0) else "未开始"

    items = [
        p
        for p in problems
        if query.casefold() in (p["id"] + p["title"] + " ".join(p.get("tags", []))).casefold()
        and (level == "全部难度" or (p.get("difficulty") or "未分级") == level)
        and (progress_filter == "全部状态" or progress_label(p) == progress_filter)
    ]
    st.caption(f"共 {len(items)} 道题目")
    page = bounded_page(len(items))
    if not items:
        st.info("没有找到匹配的题目。试试其他关键词，或创建第一道题。")
        return
    with st.container(key="library-list"):
        for item in items[(page - 1) * 10 : page * 10]:
            with st.container(key=f"list-row-problem-{item['id']}"):
                mobile = st.session_state.get("mobile", False)
                if mobile:
                    text = st.container()
                    with st.container(horizontal=True, vertical_alignment="center"):
                        difficulty_col = st.container(width="stretch")
                        progress_col = st.container(width="stretch")
                        action = st.container(width="content")
                else:
                    text, difficulty_col, progress_col, action = st.columns(
                        [4, 1, 1.2, 1], vertical_alignment="center"
                    )
                with text:
                    st.html(
                        '<div class="oj-problem-row oj-row-title">'
                        f"<h3>{escape(item['title'])}</h3>"
                        f'<span class="oj-kicker">{escape(item["id"])}</span></div>',
                    )
                    pills(item.get("tags", []))
                with difficulty_col:
                    difficulty = escape(item.get("difficulty") or "未分级")
                    value = normalize_difficulty(item.get("difficulty") or "")
                    tone = next(level["tone"] for level in DIFFICULTIES if level["value"] == value)
                    st.html(f'<span class="oj-status difficulty-{tone}">{difficulty}</span>')
                progress = item.get("progress", {})
                with progress_col:
                    label = progress_label(item)
                    css = "pass" if label == "已通过" else "wait" if label == "尝试中" else ""
                    st.html(f'<span class="oj-status {css}">{label}</span>')
                    if progress.get("attempts"):
                        st.caption(f"{progress['attempts']} 次提交")
                if action.button("开始做题", key=f"open-{item['id']}", width="stretch"):
                    navigate("workspace", current_problem=item["id"])

    pagination(len(items), position="bottom")
