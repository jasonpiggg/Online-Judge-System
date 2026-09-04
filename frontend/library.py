from __future__ import annotations

import time
from html import escape
from typing import Any

import streamlit as st
from streamlit_ace import st_ace

from frontend.client import ApiClient
from frontend.ui import call, heading, navigate, pager, pills

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
    levels = sorted({p.get("difficulty", "") for p in problems} - {""})
    if st.session_state.get("mobile"):
        query = st.text_input("搜索题目", placeholder="题号、标题或标签", key="library-search")
        with st.expander("筛选与题目管理"):
            level = st.selectbox("难度", ["全部难度", *levels])
            progress_filter = st.selectbox("学习状态", ["全部状态", "未开始", "尝试中", "已通过"])
            if st.button("新建题目", icon=":material/add:", width="stretch"):
                navigate("editor", editing_problem=None)
    else:
        a, b, c, d = st.columns([3, 1.1, 1.1, 1.2], vertical_alignment="bottom")
        query = a.text_input("搜索题目", placeholder="题号、标题或标签", key="library-search")
        level = b.selectbox("难度", ["全部难度", *levels])
        progress_filter = c.selectbox("学习状态", ["全部状态", "未开始", "尝试中", "已通过"])
        if d.button("新建题目", icon=":material/add:", type="primary", width="stretch"):
            navigate("editor", editing_problem=None)

    def progress_label(item: dict[str, Any]) -> str:
        progress = item.get("progress", {})
        if progress.get("passed"):
            return "已通过"
        return "尝试中" if progress.get("attempts", 0) else "未开始"

    items = [
        p
        for p in problems
        if query.casefold() in (p["id"] + p["title"] + " ".join(p.get("tags", []))).casefold()
        and (level == "全部难度" or p.get("difficulty") == level)
        and (progress_filter == "全部状态" or progress_label(p) == progress_filter)
    ]
    st.caption(f"共 {len(items)} 道题目")
    page = pager("library-page", len(items))
    if not items:
        st.info("没有找到匹配的题目。试试其他关键词，或创建第一道题。")
    for item in items[(page - 1) * 10 : page * 10]:
        with st.container(border=True):
            text, progress_col, action = st.columns([4, 1.1, 1], vertical_alignment="center")
            with text:
                st.markdown(
                    '<div class="oj-problem-row"><span class="oj-kicker">'
                    f'{escape(item["id"])}</span>'
                    f"<h3>{escape(item['title'])}</h3></div>",
                    unsafe_allow_html=True,
                )
                pills([item.get("difficulty") or "未分级", *item.get("tags", [])])
            progress = item.get("progress", {})
            with progress_col:
                label = progress_label(item)
                css = "pass" if label == "已通过" else "wait" if label == "尝试中" else ""
                st.markdown(
                    f'<span class="oj-status {css}">{label}</span>', unsafe_allow_html=True
                )
                if progress.get("attempts"):
                    st.caption(f"{progress['attempts']} 次提交")
            if action.button("开始做题", key=f"open-{item['id']}", width="stretch"):
                navigate("workspace", current_problem=item["id"])


def statement(problem: dict[str, Any]) -> None:
    st.markdown(problem["description"])
    st.markdown("### 输入格式")
    st.write(problem["input_description"])
    st.markdown("### 输出格式")
    st.write(problem["output_description"])
    st.markdown("### 样例")
    for index, sample in enumerate(problem["samples"], 1):
        st.caption(f"样例 {index}")
        a, b = st.columns(2)
        a.markdown("**输入**")
        a.code(sample["input"], language=None)
        b.markdown("**输出**")
        b.code(sample["output"], language=None)
    st.markdown("### 数据范围")
    st.write(problem["constraints"])
    if problem.get("hint"):
        with st.expander("解题提示"):
            st.write(problem["hint"])


@st.fragment(run_every=1)
def autosave_workspace_draft(api: ApiClient, problem_id: str, language: str) -> None:
    draft_key = f"draft-{problem_id}-{language}"
    synced_key = f"draft-synced-{problem_id}-{language}"
    dirty_key = f"draft-dirty-at-{problem_id}-{language}"
    code = st.session_state.get(draft_key, "")
    synced = st.session_state.get(synced_key)
    if synced is not None and code == synced:
        st.caption("已保存 · 每分钟最多提交 3 次")
        return
    dirty_at = float(st.session_state.get(dirty_key, time.monotonic()))
    if time.monotonic() - dirty_at < 0.8:
        st.caption("正在保存草稿… · 每分钟最多提交 3 次")
        return
    saved = call(
        lambda: api.put(
            f"/api/workspace-drafts/{problem_id}/{language}",
            json={"code": code},
        )
    )
    if saved:
        st.session_state[synced_key] = code
        st.caption("已保存 · 每分钟最多提交 3 次")
    else:
        st.caption("草稿待保存 · 每分钟最多提交 3 次")


def code_panel(api: ApiClient, problem: dict[str, Any]) -> None:
    result = call(lambda: api.get("/api/languages/"))
    if not result:
        return
    names = result["data"]["name"]
    preferred = st.session_state.get("preferred-language", "python")
    language = st.selectbox(
        "编程语言",
        names,
        index=names.index(preferred) if preferred in names else 0,
        key="workspace-language",
        on_change=lambda: st.session_state.update(
            {"preferred-language": st.session_state["workspace-language"]}
        ),
    )
    draft_key = f"draft-{problem['id']}-{language}"
    loaded_key = f"draft-loaded-{problem['id']}-{language}"
    synced_key = f"draft-synced-{problem['id']}-{language}"
    dirty_key = f"draft-dirty-at-{problem['id']}-{language}"
    starter = "# 在这里编写解法\n" if language.startswith("py") else "// 在这里编写解法\n"
    if not st.session_state.get(loaded_key):
        remote = call(lambda: api.get(f"/api/workspace-drafts/{problem['id']}/{language}"))
        if remote is None:
            return
        remote_code = remote["data"]["code"] if remote["data"] else starter
        if draft_key not in st.session_state:
            st.session_state[draft_key] = remote_code
        st.session_state[synced_key] = remote["data"]["code"] if remote["data"] else None
        if st.session_state[draft_key] != st.session_state[synced_key]:
            st.session_state[dirty_key] = time.monotonic()
        st.session_state[loaded_key] = True
    code = st_ace(
        value=st.session_state[draft_key],
        language="python" if language.startswith("py") else "c_cpp",
        theme="tomorrow",
        height=380,
        font_size=15,
        tab_size=4,
        auto_update=True,
        key=f"ace-{problem['id']}-{language}",
    )
    if code is not None and code != st.session_state.get(draft_key):
        st.session_state[draft_key] = code
        st.session_state[dirty_key] = time.monotonic()
    autosave_workspace_draft(api, problem["id"], language)
    if st.button("提交评测", icon=":material/play_arrow:", type="primary", width="stretch"):
        if not st.session_state.get(draft_key, "").strip():
            st.warning("请先编写代码。")
            return
        submitted = call(
            lambda: api.post(
                "/api/submissions/",
                json={
                    "problem_id": problem["id"],
                    "language": language,
                    "code": st.session_state[draft_key],
                },
            )
        )
        if submitted:
            saved = call(
                lambda: api.put(
                    f"/api/workspace-drafts/{problem['id']}/{language}",
                    json={"code": st.session_state[draft_key]},
                )
            )
            if saved:
                st.session_state[synced_key] = st.session_state[draft_key]
            st.session_state[f"last-{problem['id']}"] = submitted["data"]["submission_id"]
            st.rerun()


def workspace_page(api: ApiClient) -> None:
    from frontend.editor import delete_dialog
    from frontend.records import submission_result

    if not st.session_state.get("current_problem"):
        st.info("先从题库选择一道题。")
        if st.button("前往题库"):
            navigate("library")
        return
    result = call(lambda: api.get(f"/api/problems/{st.session_state.current_problem}"))
    if not result:
        return
    problem = result["data"]
    listing = call(lambda: api.get("/api/problems/"))
    problem_ids = [item["id"] for item in listing["data"]] if listing else [problem["id"]]
    current_index = problem_ids.index(problem["id"]) if problem["id"] in problem_ids else 0
    back, previous, following, spacer = st.columns([1, 1, 1, 4], vertical_alignment="center")
    if back.button("返回题库", icon=":material/arrow_back:", width="stretch"):
        navigate("library")
    if previous.button(
        "上一题", disabled=current_index == 0, key=f"prev-{problem['id']}", width="stretch"
    ):
        navigate("workspace", current_problem=problem_ids[current_index - 1])
    if following.button(
        "下一题",
        disabled=current_index >= len(problem_ids) - 1,
        key=f"next-{problem['id']}",
        width="stretch",
    ):
        navigate("workspace", current_problem=problem_ids[current_index + 1])
    spacer.caption("草稿跨刷新保存")
    top, actions = st.columns([3, 1], vertical_alignment="center")
    with top:
        heading(problem["title"], note=f"{problem['id']} · 阅读题目，编写并提交你的解法")
    if actions.button("编辑题目", icon=":material/edit:", width="stretch"):
        navigate("editor", editing_problem=problem)
    if st.session_state.user["role"] == "admin":
        with st.popover("题目管理", icon=":material/settings:"):
            public = st.toggle(
                "公开测试点日志", value=problem["public_cases"], key=f"public-{problem['id']}"
            )
            if st.button("保存日志可见性"):
                if call(
                    lambda: api.put(
                        f"/api/problems/{problem['id']}/log_visibility",
                        json={"public_cases": public},
                    )
                ):
                    st.success("日志可见性已更新")
            if st.button("删除题目", icon=":material/delete:"):
                delete_dialog(api, problem)
    inherited = problem.get("limit_inheritance", {})
    pills(
        [
            "时间：继承语言" if inherited.get("time_limit") else f"{problem['time_limit']} 秒",
            "内存：继承语言" if inherited.get("memory_limit") else f"{problem['memory_limit']} MB",
            problem.get("difficulty") or "未分级",
            *problem.get("tags", []),
        ]
    )
    mobile = st.session_state.get("mobile", False)
    last_id = st.session_state.get(f"last-{problem['id']}")
    if mobile:
        description, editor, results = st.tabs(
            ["题目", "代码", "结果"],
            default="结果" if last_id else "题目",
            key=f"work-tabs-{problem['id']}-{last_id or 'new'}",
        )
        with description:
            statement(problem)
        with editor:
            code_panel(api, problem)
        with results:
            if last_id:
                submission_result(api, str(last_id))
            else:
                st.info("提交代码后，评测结果会显示在这里。")
    else:
        left, right = st.columns([1, 1.1], gap="large")
        with left, st.container(key="statement-panel"):
            statement(problem)
        with right, st.container(key="editor-panel"):
            code_panel(api, problem)
            if last_id:
                submission_result(api, str(last_id))
