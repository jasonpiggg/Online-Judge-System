"""The native, vertical problem workspace and revision-aware source editor."""

from __future__ import annotations

from typing import Any

import streamlit as st

from frontend.client import ApiClient, ApiError
from frontend.components import control, diff, rich_text
from frontend.navigation import back, bounded_page, go, page_number, pagination
from frontend.ui import call, heading, local_time, pills, verdict_label


def source_key(pid: str, language: str) -> str:
    return f"source:{st.session_state.user['user_id']}:{pid}:{language}"


def replace_source(source: dict[str, Any], code: str) -> None:
    source.update(code=code, epoch=source["epoch"] + 1)


def save_source(api: ApiClient, pid: str, language: str, source: dict[str, Any]) -> bool:
    if source.get("conflict"):
        return False
    if source["code"] == source["saved"]:
        return True
    try:
        saved = api.put(
            f"/api/workspace-drafts/{pid}/{language}",
            json={"code": source["code"], "expected_revision": source["revision"]},
        )["data"]
        source.update(saved=saved["code"], revision=saved["revision"], error="")
        return True
    except ApiError as exc:
        if exc.status == 409:
            remote = call(lambda: api.get(f"/api/workspace-drafts/{pid}/{language}"))
            if remote:
                source["conflict"] = remote["data"] or {"code": "", "revision": 0}
        else:
            st.error(str(exc))
        source["error"] = str(exc)
    except RuntimeError as exc:
        source["error"] = str(exc)
    return False


@st.fragment
def source_editor(
    api: ApiClient, pid: str, language: str, names: list[str] | None = None
) -> dict[str, Any] | None:
    key = source_key(pid, language)
    with st.container(horizontal=True, vertical_alignment="center", key="editor-toolbar"):
        chosen = st.selectbox(
            "编程语言",
            names or [language],
            index=(names or [language]).index(language),
            key=f"language-{pid}-{language}",
            width=180,
            label_visibility="collapsed",
        )
        if chosen != language:
            st.query_params.language = chosen
            st.rerun()
        size = st.number_input(
            "代码字号",
            12,
            24,
            14,
            key=f"{key}:size",
            width=90,
            label_visibility="collapsed",
            help="代码字号（12–24px）",
        )
        imports = st.popover("导入与导出源码")
    if key not in st.session_state:
        result = call(lambda: api.get(f"/api/workspace-drafts/{pid}/{language}"))
        if result is None:
            return None
        remote = result["data"] or {"code": "", "revision": 0}
        st.session_state[key] = dict(
            code=remote["code"], saved=remote["code"], revision=remote["revision"], epoch=0
        )
    source = st.session_state[key]
    pending = st.session_state.get("workspace_import")
    if pending and pending["pid"] == pid and pending["language"] == language:
        replace_source(source, pending["code"])
        st.session_state.pop("workspace_import", None)
    with imports:
        uploaded = st.file_uploader("导入 UTF-8 源码", key=f"{key}:upload")
        if uploaded:
            registered = call(lambda: api.get("/api/languages/", params={"include_metadata": True}))
            metadata = registered["data"]["languages"] if registered else []
            extension = "." + uploaded.name.rsplit(".", 1)[-1].lower()
            matches = [item["name"] for item in metadata if item["file_ext"].lower() == extension]
            choices = matches or [item["name"] for item in metadata]
            if len(matches) != 1:
                st.info("扩展名未唯一对应语言，请明确选择导入目标。")
            target = (
                st.selectbox("导入目标语言", choices, key=f"{key}:import-language")
                if choices
                else None
            )
            confirmed = st.checkbox("确认替换目标语言的草稿", key=f"{key}:import-confirm")
            if st.button("载入文件", key=f"{key}:import", disabled=not target or not confirmed):
                try:
                    if uploaded.size > 1_000_000:
                        raise ValueError("源码文件不能超过 1 MB。")
                    imported = uploaded.getvalue().decode("utf-8-sig")
                    if len(imported) > 200_000:
                        raise ValueError("源码不能超过 200000 个字符。")
                    st.session_state.workspace_import = {
                        "pid": pid,
                        "language": target,
                        "code": imported,
                    }
                    st.rerun()
                except (ValueError, UnicodeError) as exc:
                    st.error(str(exc))
        download_area = st.container()
    event = control(
        "editor",
        f"{key}:editor",
        code=source["code"],
        language=language,
        size=size,
        revision=source["revision"],
        epoch=source["epoch"],
        saved=source["saved"],
        resolveBackup=source.get("backup_resolution", 0),
        storageKey=f"oj-streamlit-backup:{key}",
        owner=str(st.session_state.user["user_id"]),
    )
    if (
        event.backup
        and isinstance(event.backup, dict)
        and isinstance(event.backup.get("code"), str)
    ):
        source["backup"] = event.backup
    if event.edit and event.edit.get("epoch") == source["epoch"]:
        source["code"] = event.edit["code"]
    if event.submit:
        source["code"] = event.submit["code"]
    if backup := source.get("backup"):
        st.warning("发现尚未同步的浏览器源码。请比较后选择，当前服务端内容仍保留。")
        diff({"code": source["code"]}, {"code": backup["code"]}, f"{key}:backup-diff")
        a, b = st.columns(2)
        if a.button("恢复浏览器备份", key=f"{key}:restore"):
            source["backup_resolution"] = source.get("backup_resolution", 0) + 1
            replace_source(source, backup["code"])
            source.pop("backup", None)
            st.rerun()
        if b.button("保留当前源码", key=f"{key}:discard-backup"):
            source["backup_resolution"] = source.get("backup_resolution", 0) + 1
            source.pop("backup", None)
            replace_source(source, source["code"])
            st.rerun()
    if conflict := source.get("conflict"):
        st.warning("另一页面已保存新版本。请选择要保留的内容；覆盖时仍会检查版本。")
        diff({"code": conflict["code"]}, {"code": source["code"]}, f"{key}:conflict-diff")
        st.download_button(
            "下载本地冲突副本",
            source["code"],
            file_name=f"{pid}-conflict.txt",
            key=f"{key}:conflict-download",
        )
        a, b = st.columns(2)
        if a.button("采用服务端版本", key=f"{key}:remote"):
            replace_source(source, conflict["code"])
            source.update(saved=conflict["code"], revision=conflict["revision"])
            source.pop("conflict", None)
            st.rerun()
        if b.button("保留本地并保存", key=f"{key}:local"):
            source.update(saved=conflict["code"], revision=conflict["revision"])
            source.pop("conflict", None)
            save_source(api, pid, language, source)
            st.rerun()
    elif not source.get("backup"):
        save_source(api, pid, language, source)
        if source.get("conflict"):
            st.rerun()
    st.session_state.unsaved = source["code"] != source["saved"]
    with download_area:
        st.download_button(
            "下载源码", source["code"], file_name=f"{pid}.{language}", key=f"{key}:download"
        )
    with st.container(horizontal=True, vertical_alignment="center", key="editor-footer"):
        st.caption(
            "已保存 · Ctrl / ⌘ + Enter 提交"
            if not st.session_state.unsaved
            else source.get("error") or "尚未同步，浏览器保留备份"
        )
        clicked = st.button("提交评测", type="primary", key=f"{key}:submit")
        if source.get("error") and not source.get("conflict"):
            if st.button("重新同步源码", key=f"{key}:retry-save"):
                save_source(api, pid, language, source)
                st.rerun()
    if clicked or event.submit:
        if not source["code"].strip():
            st.warning("请先编写代码。")
        elif save_source(api, pid, language, source):
            response = call(
                lambda: api.post(
                    "/api/submissions/",
                    json={"problem_id": pid, "language": language, "code": source["code"]},
                )
            )
            if response:
                st.session_state["scroll_to_results"] = str(response["data"]["submission_id"])
                st.session_state[f"last-{pid}"] = response["data"]["submission_id"]
                st.query_params.submission_id = str(response["data"]["submission_id"])
                st.rerun()
    return source


def statement(problem: dict[str, Any]) -> None:
    for field, title in [
        ("description", "题目描述"),
        ("input_description", "输入格式"),
        ("output_description", "输出格式"),
    ]:
        rich_text(f"### {title}\n\n{problem.get(field, '')}", f"statement-{problem['id']}-{field}")
    st.subheader("样例")
    for n, sample in enumerate(problem.get("samples", []), 1):
        with st.container(border=True):
            st.caption(f"样例 {n}")
            a, b = st.columns(2)
            a.caption("输入")
            a.code(sample["input"], language=None)
            b.caption("输出")
            b.code(sample["output"], language=None)
            if sample.get("files"):
                st.json(sample["files"])
    rich_text(f"### 数据范围\n{problem.get('constraints', '')}", f"constraints-{problem['id']}")
    if problem.get("hint"):
        with st.expander("解题提示"):
            rich_text(problem["hint"], f"hint-{problem['id']}")


def workspace_page(api: ApiClient) -> None:
    from frontend.assistant import assistant_panel
    from frontend.records import submission_result

    pid = st.query_params.get("id", "")
    result = call(lambda: api.get(f"/api/problems/{pid}")) if pid else None
    if not result:
        st.info("请选择一道题目。")
        return
    p = result["data"]
    listing = call(lambda: api.get("/api/problems/"))
    ids = [v["id"] for v in listing["data"]] if listing else [pid]
    index = ids.index(pid) if pid in ids else 0
    with st.container(horizontal=True):
        if st.button("返回来源"):
            back()
        for label, offset in [("上一题", -1), ("下一题", 1)]:
            if st.button(label, disabled=not 0 <= index + offset < len(ids)):
                go("workspace", id=ids[index + offset])
        if st.button("编辑题目"):
            draft = call(lambda: api.post(f"/api/problems/{pid}/editing-draft"))
            if draft:
                go("draft", id=draft["data"]["id"], title=p["title"])
    heading(p["title"], note=f"{pid} · 阅读、编写、验证与改进")
    pills([p.get("difficulty") or "未分级", *p.get("tags", [])])
    inherited = p.get("limit_inheritance", {})
    if inherited:
        st.caption(
            " · ".join(
                f"{label}继承语言配置"
                for field, label in [("time_limit", "时间"), ("memory_limit", "内存")]
                if inherited.get(field)
            )
        )
    time_limit, memory_limit = p.get("time_limit"), p.get("memory_limit")
    st.caption(
        f"时间 {str(time_limit) + ' 秒' if time_limit is not None else '继承语言配置'} · "
        f"内存 {str(memory_limit) + ' MB' if memory_limit is not None else '继承语言配置'} · "
        f"来源 {p.get('source') or '—'} · 作者 {p.get('author') or '—'}"
    )
    if st.session_state.user["role"] == "admin":
        with st.popover("题目管理"):
            visible = st.toggle(
                "公开测试点日志", value=p.get("public_cases", False), key=f"workspace-visible-{pid}"
            )
            if st.button("保存日志可见性"):
                if call(
                    lambda: api.put(
                        f"/api/problems/{pid}/log_visibility", json={"public_cases": visible}
                    )
                ):
                    st.success("日志可见性已更新")
            if st.button("删除题目"):
                from frontend.editor import delete_dialog

                delete_dialog(api, p)
    with st.container(horizontal=True, key="section-nav"):
        for name, anchor in [
            ("题面", "statement"),
            ("代码", "code"),
            ("结果", "results"),
            ("助手", "assistant"),
        ]:
            st.markdown(f"[{name}](#{anchor})")
    with st.container(key="statement-panel"):
        st.header("题面", anchor="statement")
        statement(p)
    st.header("代码", anchor="code")
    languages = call(lambda: api.get("/api/languages/"))
    if not languages or not languages["data"]["name"]:
        st.info("请先在资源页面登记语言。")
        return
    names = languages["data"]["name"]
    selected = st.query_params.get("language", "python")
    if pending := st.session_state.get("workspace_import"):
        if pending["pid"] == pid:
            selected = pending["language"]
    language = selected if selected in names else names[0]
    st.query_params["language"] = language
    with st.container(key="editor-panel"):
        source = source_editor(api, pid, language, names)
    st.header("结果", anchor="results")
    if sid := st.query_params.get("submission_id") or st.session_state.get(f"last-{pid}"):
        with st.container(key="result-panel"):
            submission_result(api, str(sid))
    else:
        st.info("提交代码后将在这里显示评测结果。")
    with st.expander("本题提交历史"):
        records = call(
            lambda: api.get(
                "/api/submissions/",
                params={
                    "problem_id": pid,
                    "user_id": st.session_state.user["user_id"],
                    "page": page_number(),
                    "page_size": 10,
                    "include_metadata": True,
                },
            )
        )
        if records:
            bounded_page(records["data"]["total"])
            if not records["data"]["total"]:
                st.info("暂无本题提交记录，提交代码后可在这里查看。")
            for row in records["data"]["submissions"]:
                with st.container(border=True, key=f"history-card-{row['submission_id']}"):
                    details, action = st.columns([4, 1], vertical_alignment="center")
                    label, tone = verdict_label(row)
                    details.markdown(f"**提交 #{row['submission_id']}**")
                    code = (row.get("evaluation") or {}).get("verdict", "")
                    verdict = (
                        f"{code} · {label}"
                        if code in {"AC", "WA", "RE", "CE", "TLE", "MLE"}
                        else label
                    )
                    details.html(f'<span class="oj-status {tone}">{verdict}</span>')
                    details.caption(
                        f"{row.get('language', '—')} · 得分 {row.get('score', '—')} / "
                        f"{row.get('counts', '—')} · {local_time(row.get('created_at'))} 北京时间"
                    )
                    if action.button("查看详情", key=f"history-{row['submission_id']}"):
                        go(
                            "submission",
                            id=row["submission_id"],
                            title=f"提交 #{row['submission_id']}",
                        )
            pagination(records["data"]["total"], position="bottom")
    st.header("做题助手", anchor="assistant")
    assistant = st.expander("AI 做题助手", key=f"assistant-expanded-{pid}", on_change="rerun")
    if source and assistant.open:
        with assistant:
            assistant_panel(api, pid, language, source)
