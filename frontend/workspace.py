"""The native, vertical problem workspace and revision-aware source editor."""

from __future__ import annotations

from typing import Any

import streamlit as st

from frontend.client import ApiClient, ApiError
from frontend.components import control, diff, rich_text
from frontend.navigation import back, go, page_number, pagination
from frontend.ui import call, heading, pills


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
def source_editor(api: ApiClient, pid: str, language: str) -> dict[str, Any] | None:
    key = source_key(pid, language)
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
    size = st.slider("代码字号", 12, 24, 14, key=f"{key}:size")
    with st.expander("导入与导出源码"):
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
    st.caption(
        "已保存 · Ctrl / ⌘ + Enter 提交"
        if not st.session_state.unsaved
        else source.get("error") or "尚未同步，浏览器保留备份"
    )
    if source.get("error") and not source.get("conflict"):
        if st.button("重新同步源码", key=f"{key}:retry-save"):
            save_source(api, pid, language, source)
            st.rerun()
    clicked = st.button("提交评测", type="primary", key=f"{key}:submit")
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
            a.code(sample["input"], language=None)
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
    st.caption(
        f"时间 {p.get('time_limit')} 秒 · 内存 {p.get('memory_limit')} MB · "
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
            st.session_state[f"language-{pid}"] = selected
    language = st.selectbox(
        "编程语言",
        names,
        index=names.index(selected) if selected in names else 0,
        key=f"language-{pid}",
    )
    st.query_params["language"] = language
    source = source_editor(api, pid, language)
    st.header("结果", anchor="results")
    if sid := st.query_params.get("submission_id") or st.session_state.get(f"last-{pid}"):
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
            pagination(records["data"]["total"])
            for row in records["data"]["submissions"]:
                if st.button(
                    f"#{row['submission_id']} · {row['status']} · {row.get('created_at', '')}",
                    key=f"history-{row['submission_id']}",
                ):
                    go("submission", id=row["submission_id"], title=f"提交 #{row['submission_id']}")
    st.header("做题助手", anchor="assistant")
    if source:
        assistant_panel(api, pid, language, source)
