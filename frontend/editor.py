from __future__ import annotations

import copy
import json
from typing import Any

import streamlit as st
from pydantic import ValidationError

from frontend.client import ApiClient
from frontend.library import statement
from frontend.ui import call, heading, navigate
from oj.difficulty import DIFFICULTIES, normalize_difficulty
from oj.schemas import Problem


def clean_problem(value: dict[str, Any]) -> dict[str, Any]:
    data = {k: copy.deepcopy(v) for k, v in value.items() if k in Problem.model_fields}
    for field, inherited in value.get("limit_inheritance", {}).items():
        if inherited:
            data[field] = None
    return data


def load_editor(
    value: dict[str, Any], update: bool = False, assets: dict[str, Any] | None = None
) -> None:
    data = clean_problem(value)
    key = str(data["id"]) if update else "new"
    st.session_state.setdefault("editor_drafts", {})[key] = data
    if assets:
        st.session_state.setdefault("authoring_assets", {})[key] = copy.deepcopy(assets)
    st.session_state.editor_revision = st.session_state.get("editor_revision", 0) + 1
    navigate("editor", editing_problem=data if update else None)


@st.dialog("确认删除题目")
def delete_dialog(api: ApiClient, problem: dict[str, Any]) -> None:
    st.warning(f"将删除 {problem['id']} · {problem['title']}。已有提交记录不会删除。")
    st.download_button(
        "先下载题目备份",
        json.dumps(clean_problem(problem), ensure_ascii=False, indent=2),
        file_name=f"{problem['id']}.json",
        mime="application/json",
    )
    confirm = st.text_input("输入题号确认删除", key="delete-confirm-id")
    a, b = st.columns(2)
    if a.button("取消", width="stretch"):
        st.rerun()
    if b.button("确认删除", type="primary", width="stretch", disabled=confirm != problem["id"]):
        if call(lambda: api.delete(f"/api/problems/{problem['id']}")):
            st.session_state.pop("current_problem", None)
            st.session_state.pop("editing_problem", None)
            navigate("library")


def editor_page(api: ApiClient) -> None:
    existing = st.session_state.get("editing_problem")
    key = str(existing["id"]) if existing else "new"
    drafts = st.session_state.setdefault("editor_drafts", {})
    if key not in drafts:
        drafts[key] = clean_problem(existing or {})
    draft = drafts[key]
    revision = st.session_state.get("editor_revision", 0)
    prefix = f"edit-{key}-{revision}"
    heading(
        "编辑题目" if existing else "新建题目",
        note="分区填写，实时保留草稿。样例和测试点不需要手写 JSON。",
    )

    with st.expander("AI 辅助当前草稿", icon=":material/auto_awesome:"):
        st.caption("从当前上下文发起修改；生成结果会保存为命题草稿，不会直接覆盖或发布。")
        with st.form(f"inline-ai-{key}"):
            target = st.selectbox(
                "修改范围",
                ["testcases", "statement", "constraints", "samples", "review", "all"],
                format_func=lambda value: {
                    "testcases": "测试点",
                    "statement": "题面",
                    "constraints": "约束",
                    "samples": "样例",
                    "review": "完整审查",
                    "all": "整题",
                }[value],
            )
            ai_requirement = st.text_area(
                "具体要求",
                placeholder="例如：补充能卡掉只考虑正数解法的边界测试点，并保持题面不变。",
            )
            if st.form_submit_button("创建 AI 修改任务", type="primary"):
                problem: dict[str, Any] | None
                try:
                    problem = Problem.model_validate(draft).model_dump()
                except ValidationError:
                    problem = None
                assets = st.session_state.get("authoring_assets", {}).get(key, {})
                created_draft = call(
                    lambda: api.post(
                        "/api/problem-drafts/",
                        json={
                            "base_problem_id": existing["id"] if existing else None,
                            "requirement": ai_requirement,
                            "problem": problem,
                            "reference_solution": assets.get("reference_solution", ""),
                            "brute_solution": assets.get("brute_solution", ""),
                            "generator_code": assets.get("generator_code", ""),
                            "review": assets.get("review", {}),
                        },
                    )
                )
                if created_draft:
                    task = call(
                        lambda: api.post(
                            "/api/ai/problem-tasks/",
                            json={
                                "requirement": ai_requirement,
                                "problem_id": existing["id"] if existing else None,
                                "draft_id": created_draft["data"]["id"],
                                "action": "tests" if target == "testcases" else "revise",
                                "target_section": target,
                            },
                        )
                    )
                    if task:
                        st.session_state.ai_task_id = task["data"]["task_id"]
                        navigate("ai")

    def field(label: str, name: str, *, area: bool = False, **kwargs: Any) -> None:
        widget_key = f"{prefix}-{name}"

        def changed() -> None:
            draft[name] = st.session_state[widget_key]

        widget = st.text_area if area else st.text_input
        draft[name] = widget(
            label, value=str(draft.get(name, "")), key=widget_key, on_change=changed, **kwargs
        )

    basic, body, samples, cases, advanced, preview = st.tabs(
        ["基本信息", "题面与格式", "样例", "测试点", "高级设置", "预览"]
    )
    with basic:
        with st.container(border=True):
            a, b = st.columns([1, 2])
            with a:
                field("题号", "id", disabled=bool(existing), help="字母、数字、下划线或连字符")
            with b:
                field("题目标题", "title")
            levels = [level["value"] for level in DIFFICULTIES]
            draft["difficulty"] = st.selectbox(
                "难度",
                levels,
                index=levels.index(normalize_difficulty(draft.get("difficulty", ""))),
                format_func=lambda value: value or "未分级",
                key=f"{prefix}-difficulty",
                help="按解题思维与算法要求分为入门、简单、中等、困难、挑战。",
            )
            tags = st.text_input(
                "标签",
                value=", ".join(draft.get("tags", [])),
                key=f"{prefix}-tags",
                placeholder="用逗号分隔",
            )
            draft["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    with body, st.container(border=True):
        field("题目描述", "description", area=True, height=200)
        a, b = st.columns(2)
        with a:
            field("输入格式", "input_description", area=True)
        with b:
            field("输出格式", "output_description", area=True)
        field("数据范围", "constraints", area=True)
    for container, name, label, maximum in [
        (samples, "samples", "样例", 20),
        (cases, "testcases", "测试点", 100),
    ]:
        with container:
            values = draft.setdefault(name, [{"input": "", "output": ""}])
            st.caption(f"共 {len(values)} 个{label} · 输入和期望输出按原样保存，包括空白字符")
            for i, case in enumerate(values):
                with st.container(border=True):
                    st.markdown(f"**{label} {i + 1}**")
                    left, right = st.columns(2)
                    for col, attr, title in [
                        (left, "input", "输入"),
                        (right, "output", "期望输出"),
                    ]:
                        wk = f"{prefix}-{name}-{i}-{attr}"

                        def remember(
                            case: dict[str, str] = case, attr: str = attr, wk: str = wk
                        ) -> None:
                            case[attr] = st.session_state[wk]

                        case[attr] = col.text_area(
                            f"{label} {i + 1} · {title}",
                            value=case[attr],
                            key=wk,
                            height=100,
                            on_change=remember,
                        )
                    if st.button(
                        f"移除{label} {i + 1}",
                        key=f"{prefix}-rm-{name}-{i}",
                        disabled=len(values) == 1,
                    ):
                        values.pop(i)
                        st.session_state.editor_revision = revision + 1
                        st.rerun()
            if st.button(f"添加{label}", key=f"add-{name}", disabled=len(values) >= maximum):
                values.append({"input": "", "output": ""})
                st.session_state.editor_revision = revision + 1
                st.rerun()
    with advanced, st.container(border=True):
        for name, label, default, minimum, maximum in [
            ("time_limit", "时间限制 / 秒", 3.0, 0.1, 30.0),
            ("memory_limit", "内存限制 / MB", 128, 16, 2048),
        ]:
            inherited = st.checkbox(
                f"{label}：继承语言配置",
                value=draft.get(name) is None,
                key=f"{prefix}-inherit-{name}",
            )
            limit = st.number_input(
                label,
                min_value=minimum,
                max_value=maximum,
                value=draft.get(name) or default,
                disabled=inherited,
                key=f"{prefix}-{name}",
            )
            draft[name] = None if inherited else limit
        field("解题提示", "hint", area=True)
        field("来源", "source")
        field("作者", "author")
        with st.expander("高级：JSON 导入与导出"):
            imported = st.text_area("粘贴完整题目 JSON", key=f"{prefix}-json")
            if st.button("载入 JSON 草稿"):
                try:
                    loaded = Problem.model_validate(json.loads(imported))
                    if existing and loaded.id != existing["id"]:
                        raise ValueError("更新时题号必须与当前题目一致")
                    drafts[key] = loaded.model_dump()
                    st.session_state.editor_revision = revision + 1
                    st.rerun()
                except (ValueError, ValidationError) as exc:
                    st.error(f"无法导入：{exc}")
            st.download_button(
                "导出当前草稿",
                json.dumps(draft, ensure_ascii=False, indent=2),
                file_name="problem-draft.json",
                mime="application/json",
            )
    with preview:
        st.subheader(draft.get("title") or "未命名题目")
        statement(
            {
                **draft,
                "description": draft.get("description", ""),
                "input_description": draft.get("input_description", ""),
                "output_description": draft.get("output_description", ""),
                "constraints": draft.get("constraints", ""),
            }
        )
    confirmed = not existing or st.checkbox(f"确认更新题目 {existing['id']} 的内容")
    if st.button("保存修改" if existing else "创建题目", type="primary", disabled=not confirmed):
        try:
            payload = Problem.model_validate(draft).model_dump()
        except ValidationError as exc:
            for error in exc.errors(include_input=False):
                st.error(f"{' → '.join(map(str, error['loc']))}：{error['msg']}")
            return
        result = call(
            lambda: (
                api.put(f"/api/problems/{existing['id']}", json=payload)
                if existing
                else api.post("/api/problems/", json=payload)
            )
        )
        if result:
            st.session_state.saved_problem = payload["id"]
            st.success("题目已保存。可以继续编辑或打开做题工作区。")
    if st.session_state.get("saved_problem") == draft.get("id"):
        if st.button("查看题目并开始做题"):
            navigate("workspace", current_problem=draft["id"])
