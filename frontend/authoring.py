"""Drafts, review, local verification and explicit AI requests in native Streamlit."""

from __future__ import annotations

import copy
import json
import uuid
from typing import Any

import streamlit as st

from frontend.ai import model_settings, money
from frontend.client import ApiClient, ApiError
from frontend.components import control, diff, rich_text
from frontend.forms import draft_payload, problem_form
from frontend.navigation import back, go, page_number, pagination
from frontend.ui import call, data_table, heading, local_time, status_label


def encoded(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def equivalent_draft(left: Any, right: Any) -> bool:
    """Ignore widget-only empty defaults while preserving all meaningful edits."""

    def clean(value: Any) -> Any:
        if isinstance(value, bool):
            return ("boolean", value)  # Python otherwise considers False == 0 and True == 1.
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items() if v not in (None, "", [], {})}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value

    return clean(left) == clean(right)


def list_data(value: Any, field: str) -> dict[str, Any]:
    if isinstance(value, list):
        st.warning("当前后端返回兼容列表；以下计数表示本次返回的记录。")
        return {field: value, "total": len(value)}
    return value


def start_task(api: ApiClient, body: dict[str, Any]) -> None:
    signature = json.dumps(body, sort_keys=True, ensure_ascii=False)
    pending = st.session_state.get("authoring-request")
    if not pending or pending["signature"] != signature:
        pending = {"signature": signature, "key": uuid.uuid4().hex}
        st.session_state["authoring-request"] = pending
    response = call(
        lambda: api.post(
            "/api/ai/problem-tasks/",
            json={**body, "workflow_version": 2},
            headers={"Idempotency-Key": pending["key"]},
        )
    )
    if response:
        st.session_state.pop("authoring-request", None)
        go("ai_task", id=response["data"]["task_id"], title="AI 任务")


def authoring_page(api: ApiClient) -> None:
    heading("命题中心", note="从不完整的想法开始，保存草稿，再检查与发布。")
    if st.button("新建空白草稿", type="primary"):
        d = call(lambda: api.post("/api/problem-drafts/", json={}))
        if d:
            go("draft", id=d["data"]["id"], title="新建草稿")
    tabs = st.tabs(
        ["命题草稿", "AI 任务", "生成整题", "模型设置"], key="authoring-tab", on_change="rerun"
    )
    config = call(lambda: api.get("/api/ai/model-config"))
    if tabs[3].open:
        with tabs[3]:
            if config:
                model_settings(api, config["data"])
    if tabs[2].open:
        with tabs[2]:
            st.caption(
                "个人配置优先于系统配置；系统分阶段模型策略以任务的实际计价记录为准。请求不会自动重试。"
            )
            with st.form("generate-problem"):
                requirement = st.text_area(
                    "命题需求", placeholder="知识点、难度、数据范围和预期覆盖的边界场景。"
                )
                reference = st.text_input("参考题号（可选）")
                if st.form_submit_button(
                    "生成整题",
                    type="primary",
                    disabled=not config or not config["data"]["api_key_configured"],
                ):
                    start_task(
                        api,
                        {
                            "requirement": requirement,
                            "problem_id": reference or None,
                            "action": "generate",
                            "target_section": "all",
                        },
                    )
    if tabs[0].open:
        with tabs[0]:
            archived = st.checkbox("包含归档草稿")
            drafts = call(
                lambda: api.get(
                    "/api/problem-drafts/",
                    params={
                        "include_metadata": True,
                        "include_archived": archived,
                        "page": page_number("draft_page"),
                        "page_size": 10,
                    },
                )
            )
            if drafts:
                drafts["data"] = list_data(drafts["data"], "drafts")
                pagination(drafts["data"]["total"], "draft_page")
                if not drafts["data"]["drafts"]:
                    st.info("还没有草稿。可手动新建、导入 JSON 或生成整题。")
                with st.container(key="draft-list"):
                    for d in drafts["data"]["drafts"]:
                        with st.container(key=f"list-row-draft-{d['id']}"):
                            info, action = st.columns([5, 1], vertical_alignment="center")
                            info.write(f"**{d['problem'].get('title') or '未命名草稿'}**")
                            info.caption(
                                f"{status_label(d['status'])} · v{d['revision']} "
                                f"· {local_time(d.get('updated_at'))} 北京时间"
                            )
                            if action.button("打开草稿", key=f"draft-list-{d['id']}"):
                                go("draft", id=d["id"], title=d["problem"].get("title") or "草稿")
    if tabs[1].open:
        with tabs[1]:
            archived = st.checkbox("包含归档任务")
            tasks = call(
                lambda: api.get(
                    "/api/ai/problem-tasks/",
                    params={
                        "include_metadata": True,
                        "include_archived": archived,
                        "page": page_number("task_page"),
                        "page_size": 10,
                    },
                )
            )
            if tasks:
                tasks["data"] = list_data(tasks["data"], "tasks")
                pagination(tasks["data"]["total"], "task_page")
                if not tasks["data"]["tasks"]:
                    st.info("还没有任务。")
                with st.container(key="ai-task-list"):
                    for t in tasks["data"]["tasks"]:
                        with st.container(key=f"list-row-task-{t['id']}"):
                            info, action = st.columns([5, 1], vertical_alignment="center")
                            info.write(f"**{status_label(t['action'])}**")
                            info.caption(
                                f"{status_label(t['status'])} "
                                f"· {local_time(t.get('updated_at'))} 北京时间"
                            )
                            if action.button("打开任务", key=f"task-list-{t['id']}"):
                                go("ai_task", id=t["id"], title="AI 任务")


def save_draft(api: ApiClient, did: str, state: dict[str, Any]) -> bool:
    if state.get("conflict"):
        st.warning("请先处理草稿版本冲突。")
        return False
    if equivalent_draft(state["local"], state["saved"]):
        return True
    try:
        r = api.put(
            f"/api/problem-drafts/{did}",
            json={**state["local"], "revision": state["revision"], "change_summary": "编辑草稿"},
        )["data"]
        state.update(local=draft_payload(r), saved=draft_payload(r), revision=r["revision"])
        return True
    except ApiError as exc:
        if exc.status == 409:
            r = call(lambda: api.get(f"/api/problem-drafts/{did}"))
            if r:
                state["conflict"] = r["data"]
        st.error(str(exc))
    except RuntimeError as exc:
        st.error(str(exc))
    return False


def draft_page(api: ApiClient) -> None:
    if st.button("返回来源"):
        back()
    did = st.query_params.get("id", "")
    result = call(lambda: api.get(f"/api/problem-drafts/{did}")) if did else None
    if not result:
        st.info("请选择草稿。")
        return
    d = result["data"]
    key = f"draft-state-{did}"
    if key not in st.session_state:
        st.session_state[key] = dict(
            local=draft_payload(d), saved=draft_payload(d), revision=d["revision"], epoch=0
        )
    state = st.session_state[key]
    if d["revision"] != state["revision"]:
        if equivalent_draft(state["local"], state["saved"]):
            state.update(
                local=draft_payload(d),
                saved=draft_payload(d),
                revision=d["revision"],
                epoch=state["epoch"] + 1,
            )
        else:
            state["conflict"] = d
    heading(
        d["problem"].get("title") or "未命名草稿",
        note=f"{status_label(d['status'])} · v{state['revision']} · 保存草稿无需填写全部字段",
    )
    if d["status"] in {"ready", "published"} and st.session_state.user["role"] == "admin":
        if st.button("题目管理", key=f"draft-problem-management-{did}"):
            go("resources", section="题目", id=d["problem"].get("id"))
    if conflict := state.get("conflict"):
        st.warning("草稿已在别处更新，双方内容均保留。")
        diff(draft_payload(conflict), state["local"], f"draft-conflict-{did}")
        st.download_button(
            "下载本地冲突副本", encoded(state["local"]), file_name=f"{did}-conflict.json"
        )
        a, b = st.columns(2)
        if a.button("采用服务端草稿"):
            state.update(
                local=draft_payload(conflict),
                saved=draft_payload(conflict),
                revision=conflict["revision"],
                epoch=state["epoch"] + 1,
            )
            state.pop("conflict", None)
            st.rerun()
        if b.button("以本地草稿覆盖此版本"):
            state.update(saved=draft_payload(conflict), revision=conflict["revision"])
            state.pop("conflict", None)
            if save_draft(api, did, state):
                st.rerun()
    local = copy.deepcopy(state["local"])
    prefix = f"draft-{did}-{state['epoch']}"
    with st.expander("JSON 导入导出"):
        export_area = st.container()
        file = st.file_uploader("导入题目 JSON 文件", type=["json"], key=f"{prefix}-file")
        raw = st.text_area("粘贴题目 JSON", key=f"{prefix}-json")
        if st.button("载入 JSON 到草稿"):
            from frontend.resources import read_json_file
            from oj.schemas import DraftProblem

            try:
                imported = (
                    read_json_file(file)
                    if file
                    else DraftProblem.model_validate(json.loads(raw)).model_dump()
                )
                state["local"]["problem"] = imported
                state["epoch"] += 1
                st.rerun()
            except (ValueError, UnicodeError) as exc:
                st.error(str(exc))
    local["requirement"] = st.text_area(
        "命题需求 / 修改要求", value=local["requirement"], key=f"{prefix}-requirement"
    )
    local["problem"] = problem_form(local["problem"], prefix)
    save_area = st.container(key="draft-save-bar")
    review_valid = True
    st.subheader("验证资产", anchor="validation-assets")
    with st.expander("验证资产与审查意见", expanded=st.query_params.get("section") == "assets"):
        for field, title in [
            ("reference_solution", "参考解"),
            ("brute_solution", "独立解法"),
            ("generator_code", "数据生成器"),
        ]:
            local[field] = st.text_area(
                title, value=local[field], height=180, key=f"{prefix}-{field}"
            )
        review = st.text_area(
            "审查资产 JSON（review、coverage、wrong_solutions）",
            value=encoded(local["review"]),
            height=150,
            key=f"{prefix}-review",
        )
        try:
            decoded = json.loads(review)
            if not isinstance(decoded, dict):
                raise ValueError("审查资产必须为 JSON 对象。")
            local["review"] = decoded
        except ValueError as exc:
            st.error(str(exc))
            review_valid = False
    state["local"] = local
    if not review_valid:
        st.session_state.unsaved = True
        st.warning("请先修正审查资产 JSON。其他表单内容仍保留在当前会话。")
        st.stop()
    with export_area:
        if st.button("准备导出当前内容"):
            state["export"] = copy.deepcopy(local)
        snapshot = state.get("export")
        changed = snapshot != local
        st.caption("准备导出会收集当前表单值，不会保存到服务器；修改内容后请重新准备。")
        st.download_button(
            "导出题目 JSON",
            encoded((snapshot or local)["problem"]),
            file_name=f"{did}.json",
            disabled=changed,
        )
        st.download_button(
            "导出全部草稿资产",
            encoded(snapshot or local),
            file_name=f"{did}-assets.json",
            disabled=changed,
        )
    dirty = not equivalent_draft(local, state["saved"])
    st.session_state.unsaved = dirty
    backup = control(
        "backup",
        f"draft-backup-{did}",
        storageKey=f"oj-streamlit-draft:{st.session_state.user['user_id']}:{did}",
        payload=local,
        saved=state["saved"],
        resolveBackup=state.get("backup_resolution", 0),
        revision=state["revision"],
    )
    if backup.backup:
        state["backup"] = backup.backup
    if restored := state.get("backup"):
        st.warning("发现浏览器未同步草稿。比较后可载入，保存仍受版本检查保护。")
        diff(local, restored["payload"], f"draft-backup-diff-{did}")
        if st.button("载入浏览器草稿"):
            from oj.schemas import ProblemDraftCreate

            try:
                restored_payload = ProblemDraftCreate.model_validate(
                    restored["payload"]
                ).model_dump()
            except ValueError:
                st.error("浏览器备份格式无效，请忽略备份或下载后手动修复。")
            else:
                state["backup_resolution"] = state.get("backup_resolution", 0) + 1
                state["local"] = draft_payload(restored_payload)
                state["epoch"] += 1
                state.pop("backup", None)
                st.rerun()
        if st.button("忽略浏览器草稿"):
            state["backup_resolution"] = state.get("backup_resolution", 0) + 1
            state.pop("backup", None)
            st.rerun()
    with save_area:
        with st.container(horizontal=True, vertical_alignment="center"):
            if st.button("保存草稿", type="primary"):
                if save_draft(api, did, state):
                    st.toast("草稿已保存")
                    st.rerun()
            st.caption("有未保存修改" if dirty else "已保存")
    with st.expander("版本记录"):
        versions = call(lambda: api.get(f"/api/problem-drafts/{did}/revisions"))
        if versions and versions["data"]:
            v = st.selectbox(
                "历史版本",
                versions["data"],
                format_func=lambda x: (
                    f"v{x['revision']} · {x['change_summary']} · {x['created_at']}"
                ),
            )
            diff(local, draft_payload(v["snapshot"]), f"draft-version-{did}")
            if st.button("载入此版本（保存时新增版本）"):
                state["local"] = draft_payload(v["snapshot"])
                state["epoch"] += 1
                st.rerun()
    with st.expander("AI 修改"):
        action = st.selectbox(
            "修改方式",
            ["revise", "review", "tests", "generate"],
            format_func=lambda x: {
                "revise": "局部修改",
                "review": "全面审查",
                "tests": "设计测试",
                "generate": "补全整题并验证",
            }[x],
        )
        section = st.selectbox(
            "修改范围",
            ["all", "statement", "constraints", "samples", "testcases"],
            format_func=lambda x: {
                "all": "整题",
                "statement": "题面",
                "constraints": "约束",
                "samples": "样例",
                "testcases": "测试点",
            }[x],
        )
        explanations = {
            "revise": "局部修改返回差异建议，审阅采纳后再检查；不会自动发布。",
            "review": "全面审查题面与验证资产，返回最小修正；采纳后仍需验证。",
            "tests": "设计覆盖边界与错误解法的测试点，返回供审阅的修改建议。",
            "generate": "补全题面、参考解与验证资产，并执行完整质量验证；费用通常较高。",
        }
        st.caption(explanations[action])
        if st.button("保存并发起 AI 修改"):
            if save_draft(api, did, state):
                start_task(
                    api,
                    {
                        "draft_id": did,
                        "requirement": local["requirement"],
                        "action": action,
                        "target_section": "all" if action in {"review", "generate"} else section,
                    },
                )
    st.subheader("检查与发布")
    if st.button("前往补充验证资产"):
        go("draft", id=did, section="assets")
    st.caption(
        "基础检查验证结构和可运行性；完整验证额外检查独立对拍与错误解法。两者均在本地执行，不调用模型。"
    )
    a, b = st.columns(2)
    for column, label, mode in [(a, "保存并基础检查", "basic"), (b, "保存并完整验证", "full")]:
        if column.button(label):
            if save_draft(api, did, state):
                r = call(
                    lambda mode=mode: api.post(
                        f"/api/problem-drafts/{did}/verify",
                        json={"mode": mode},
                        headers={"Idempotency-Key": uuid.uuid4().hex},
                    )
                )
                if r:
                    go("ai_task", id=r["data"]["task_id"], title="本地验证")
    if report := d.get("review", {}).get("verification"):
        verification_report(report)
    if d["status"] != "ready":
        st.caption("发布前请先保存草稿并通过检查。")
    elif dirty:
        st.caption("当前有未保存修改；保存并重新检查后可发布。")
    confirmed = st.checkbox("已审阅当前草稿，确认发布到题库")
    if st.button(
        "发布题目", disabled=d["status"] != "ready" or dirty or not confirmed, type="primary"
    ):
        r = call(lambda: api.post(f"/api/problem-drafts/{did}/publish"))
        if r:
            go("workspace", id=r["data"]["id"])
    with st.expander("归档草稿"):
        st.warning("归档会中断关联的进行中任务。")
        if st.checkbox("确认归档") and st.button("归档"):
            if call(lambda: api.delete(f"/api/problem-drafts/{did}")):
                go("ai")


def verification_report(report: dict[str, Any]) -> None:
    st.subheader("验证报告")
    if report.get("quality_gate_passed"):
        st.success("完整质量验证通过")
    elif report.get("publishable"):
        st.success("基础检查通过，可发布；不代表完整质量验证通过。")
    else:
        st.warning("检查尚未通过。请按下方问题修复草稿后重新验证。")
    for warning in report.get("warnings", []):
        st.warning(str(warning))
    if checks := report.get("checks"):
        data_table(checks)
    with st.expander("原始验证报告 JSON"):
        st.json(report)


def task_page(api: ApiClient) -> None:
    if st.button("返回来源"):
        back()
    tid = st.query_params.get("id", "")
    if not tid:
        st.info("请选择一个任务。")
        return
    heading("AI 任务", note="任务独立运行；离开页面不会取消。")
    terminal = f"task-terminal-{tid}"

    @st.fragment(run_every=None if st.session_state.get(terminal) else 1)
    def panel() -> None:
        r = call(lambda: api.get(f"/api/ai/problem-tasks/{tid}"))
        if not r:
            return
        t = r["data"]
        done = t["status"] in {"completed", "failed", "cancelled"}
        if done and not st.session_state.get(terminal):
            st.session_state[terminal] = True
            st.rerun()
        st.write(t.get("requirement", ""))
        st.info(
            f"{status_label(t['status'])} · {status_label(t.get('stage', ''))} · "
            f"{t.get('progress', '')}"
        )
        usage = t.get("usage", {})
        st.caption(
            f"输入 Token {usage.get('input_tokens', 0)} · "
            f"输出 Token {usage.get('output_tokens', 0)}"
        )
        st.write(f"累计费用：{money(usage.get('cost', 0), usage.get('currency', 'USD'))}")
        st.caption(
            "服务商 usage"
            if usage.get("source") == "provider"
            else "估算用量（部分阶段未返回服务商 usage）"
        )
        with st.expander("分阶段模型、Token 与计价依据"):
            st.json(t.get("usage_details") or {})
            st.caption(
                "费用根据任务开始时的配置单价计算，不进行汇率换算，需与服务商账单核对。未报告缓存用量时按普通输入计价。"
            )
        source_id = t.get("source_draft_id") or t.get("draft_id")
        if source_id and st.button("打开来源草稿"):
            go("draft", id=source_id, title="命题草稿")
        if not done and st.button("中断任务"):
            if call(lambda: api.put(f"/api/ai/problem-tasks/{tid}/cancel")):
                st.rerun()
        if t.get("error"):
            st.error(t["error"])
        result = t.get("result") or {}
        preview = result.get("problem") or t.get("preview") or {}
        if isinstance(preview, dict):
            for field, label in [
                ("title", "标题"),
                ("description", "题目描述"),
                ("input_description", "输入格式"),
                ("output_description", "输出格式"),
                ("constraints", "数据范围"),
            ]:
                if preview.get(field):
                    rich_text(f"### {label}\n{preview[field]}", f"task-{tid}-{field}")
        for field, label in [
            ("reference_solution", "参考解"),
            ("brute_solution", "独立解法"),
            ("generator_code", "数据生成器"),
        ]:
            if result.get(field):
                with st.expander(label):
                    st.code(result[field], language="python")
        if isinstance(preview, dict) and preview.get("samples"):
            with st.expander("生成样例"):
                for number, sample in enumerate(preview["samples"], 1):
                    st.caption(f"样例 {number}")
                    a, b = st.columns(2)
                    a.caption("输入")
                    a.code(sample.get("input", ""), language=None)
                    b.caption("输出")
                    b.code(sample.get("output", ""), language=None)
        if result.get("review"):
            rich_text(str(result["review"]), f"task-review-{tid}")
        if report := result.get("verification"):
            verification_report(report)
        if result.get("kind") in {"section_patch", "review_patch"}:
            proposal = result.get("proposal") or {"problem": result.get("problem", {})}
            diff(
                result.get("baseline", {}),
                result.get("proposal") or result.get("problem", {}),
                f"task-diff-{tid}",
            )
            approved = st.checkbox("已审阅修改，确认采纳到草稿")
            if st.button(
                "采纳到草稿", disabled=not approved or t["status"] != "completed" or not source_id
            ):
                current = call(lambda: api.get(f"/api/problem-drafts/{source_id}"))
                local = st.session_state.get(f"draft-state-{source_id}")
                if current and (
                    current["data"]["revision"] != result.get("source_draft_revision")
                    or local
                    and local["local"] != local["saved"]
                ):
                    st.error(
                        "草稿已有新版本或未保存修改。请比较后手动合并建议，或基于最新版本重新请求。"
                    )
                elif current:
                    body = draft_payload(current["data"])
                    body["problem"] = proposal["problem"]
                    if result["kind"] == "review_patch":
                        for field in ["reference_solution", "brute_solution", "generator_code"]:
                            body[field] = proposal.get(field, body[field])
                        body["review"].update(
                            {
                                k: proposal[k]
                                for k in ["coverage", "wrong_solutions"]
                                if k in proposal
                            }
                        )
                        body["review"]["review"] = result.get("review", "")
                    saved = call(
                        lambda: api.put(
                            f"/api/problem-drafts/{source_id}",
                            json={
                                **body,
                                "revision": current["data"]["revision"],
                                "change_summary": "采纳 AI 建议",
                            },
                        )
                    )
                    if saved:
                        st.session_state.pop(f"draft-state-{source_id}", None)
                        go("draft", id=source_id)
        if result.get("initial_problem"):
            diff(result["initial_problem"], result.get("problem", {}), f"task-initial-{tid}")
        with st.expander("完整成果与验证资产"):
            st.json(result)
            st.download_button("下载任务成果", encoded(result), file_name=f"{tid}.json")
        if t.get("draft_id") and done and st.button("打开成果草稿"):
            go("draft", id=t["draft_id"])
        if t["status"] in {"failed", "cancelled"}:
            if t.get("action") == "verify":
                st.info("请返回来源草稿修复，再运行本地检查。")
            else:
                if st.button("保留失败成果为恢复草稿"):
                    recovered = call(lambda: api.post(f"/api/ai/problem-tasks/{tid}/save-draft"))
                    if recovered:
                        go("draft", id=recovered["data"]["draft_id"])
                retry = st.checkbox("确认按原需求重新调用模型，可能产生新费用")
                if st.button("重新发起", disabled=not retry):
                    start_task(
                        api,
                        {
                            k: t.get(k)
                            for k in [
                                "requirement",
                                "problem_id",
                                "draft_id",
                                "action",
                                "target_section",
                            ]
                        }
                        | {"resume_task_id": tid},
                    )
        with st.expander("归档任务"):
            if st.checkbox("确认归档并中断尚未完成的任务") and st.button("归档任务"):
                if call(lambda: api.delete(f"/api/ai/problem-tasks/{tid}")):
                    go("ai")

    panel()
