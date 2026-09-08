from __future__ import annotations

import copy
import json
from typing import Any

import pandas as pd
import streamlit as st

from oj.difficulty import DIFFICULTIES


def sync_case_detail(rows: list[dict[str, Any]], chosen: int, detail: str, prefix: str) -> None:
    """Commit blurred multiline input to the same payload used by save and browser backup."""
    updated = copy.deepcopy(rows)
    raw = st.session_state[f"{detail}-files"]
    try:
        files = json.loads(raw)
    except ValueError:
        files = raw  # Preserve invalid input so the user can repair it without losing other edits.
    updated[chosen] = {
        "input": st.session_state[f"{detail}-input"],
        "output": st.session_state[f"{detail}-output"],
        "files": files,
    }
    st.session_state[f"{prefix}-override"] = updated
    st.session_state[f"{prefix}-grid-epoch"] = st.session_state.get(f"{prefix}-grid-epoch", 0) + 1
    st.session_state[f"{prefix}-selected-{st.session_state[f'{prefix}-grid-epoch']}"] = chosen


def problem_form(value: dict[str, Any], key: str) -> dict[str, Any]:
    p = copy.deepcopy(value)
    basics, statement, samples, cases, limits, preview = st.tabs(
        ["基本信息", "题面与格式", "样例", "测试点", "高级设置", "预览"]
    )
    with basics:
        columns = st.columns(2)
        for index, (field, label) in enumerate(
            [
                ("id", "题号"),
                ("title", "题目标题"),
                ("author", "作者"),
                ("source", "来源"),
            ]
        ):
            p[field] = columns[index % 2].text_input(
                label, value=p.get(field, ""), key=f"{key}-{field}"
            )
        values = [d["value"] for d in DIFFICULTIES]
        existing = p.get("difficulty", "")
        if existing not in values:
            values.append(existing)
        selected = st.selectbox(
            "难度", [*values, "自定义…"], index=values.index(existing), key=f"{key}-difficulty"
        )
        p["difficulty"] = (
            st.text_input("自定义难度", value=existing, key=f"{key}-custom-difficulty")
            if selected == "自定义…"
            else selected
        )
        tags = st.text_input(
            "标签（逗号分隔）", value=", ".join(p.get("tags", [])), key=f"{key}-tags"
        )
        p["tags"] = [x.strip() for x in tags.replace("，", ",").split(",") if x.strip()]
        with st.expander("难度说明"):
            for level in DIFFICULTIES:
                st.write(f"**{level['label']}**：{level['description']}")
    with statement:
        for field, label in [
            ("description", "题目描述"),
            ("input_description", "输入格式"),
            ("output_description", "输出格式"),
            ("constraints", "数据范围"),
            ("hint", "解题提示"),
        ]:
            p[field] = st.text_area(
                label,
                value=p.get(field, ""),
                height=150 if field == "description" else 100,
                key=f"{key}-{field}",
            )
    for container, field, label in [(samples, "samples", "样例"), (cases, "testcases", "测试点")]:
        with container:
            rows = st.session_state.pop(f"{key}-{field}-override", p.get(field, []))
            epoch = st.session_state.get(f"{key}-{field}-grid-epoch", 0)
            plain = [
                {
                    "input": c["input"],
                    "output": c["output"],
                    "files": (
                        c["files"]
                        if isinstance(c.get("files"), str)
                        else json.dumps(c.get("files", {}), ensure_ascii=False)
                    ),
                }
                for c in rows
            ]
            changed = st.data_editor(
                pd.DataFrame(plain, columns=["input", "output", "files"]).astype(str),
                num_rows="dynamic",
                hide_index=True,
                width="stretch",
                key=f"{key}-{field}-grid-{epoch}",
                column_config={
                    "input": st.column_config.TextColumn("输入"),
                    "output": st.column_config.TextColumn("期望输出"),
                    "files": st.column_config.TextColumn("附加文件 JSON"),
                },
            )
            decoded = []
            for row in changed.fillna("").to_dict("records"):
                try:
                    files = json.loads(row.get("files") or "{}")
                    if not isinstance(files, dict):
                        raise ValueError("附加文件必须为 JSON 对象。")
                    decoded.append(
                        {
                            "input": row.get("input") or "",
                            "output": row.get("output") or "",
                            "files": files,
                        }
                    )
                except ValueError:
                    st.error(f"{label}的附加文件必须为 JSON 对象。")
                    decoded.append(
                        {
                            "input": row.get("input") or "",
                            "output": row.get("output") or "",
                            "files": row.get("files"),
                        }
                    )
            p[field] = decoded
            with st.expander(f"逐项编辑{label}（支持多行）"):
                if decoded:
                    chosen = st.selectbox(
                        f"选择{label}",
                        range(len(decoded)),
                        format_func=lambda i, label=label: f"{label} {i + 1}",
                        key=f"{key}-{field}-selected-{epoch}",
                    )
                    detail_key = f"{key}-{field}-detail-{epoch}-{chosen}"
                    detail_args = (decoded, chosen, detail_key, f"{key}-{field}")
                    a, b = st.columns(2)
                    a.text_area(
                        "输入",
                        value=decoded[chosen]["input"],
                        height=150,
                        key=f"{detail_key}-input",
                        on_change=sync_case_detail,
                        args=detail_args,
                    )
                    b.text_area(
                        "期望输出",
                        value=decoded[chosen]["output"],
                        height=150,
                        key=f"{detail_key}-output",
                        on_change=sync_case_detail,
                        args=detail_args,
                    )
                    with st.expander("附加文件（高级）"):
                        st.text_area(
                            "附加文件 JSON",
                            value=(
                                decoded[chosen]["files"]
                                if isinstance(decoded[chosen]["files"], str)
                                else json.dumps(decoded[chosen]["files"], ensure_ascii=False)
                            ),
                            key=f"{detail_key}-files",
                            on_change=sync_case_detail,
                            args=detail_args,
                        )
                    st.caption("离开输入框后自动同步到草稿，再点击保存。空白与换行原样保留。")
                else:
                    st.caption("先在表格末行添加一个条目。")
            st.caption("双击单元格编辑；使用末行添加数据，选择行后可删除。空白与换行按原样保存。")
    with limits:
        if st.session_state.get("user", {}).get("role") == "admin":
            p["public_cases"] = st.checkbox(
                "公开测试点日志", value=p.get("public_cases", False), key=f"{key}-public"
            )
        for field, label, default, lower, upper in [
            ("time_limit", "时间 / 秒", 3.0, 0.0, 30.0),
            ("memory_limit", "内存 / MB", 128, 16, 2048),
        ]:
            inherited = st.checkbox(
                f"{label}：继承语言配置", value=p.get(field) is None, key=f"{key}-{field}-inherit"
            )
            number = st.number_input(
                label,
                min_value=lower,
                max_value=upper,
                value=p.get(field) or default,
                disabled=inherited,
                key=f"{key}-{field}",
            )
            p[field] = None if inherited else number
    with preview:
        from frontend.workspace import statement as render_statement

        st.subheader(p.get("title") or "未命名题目")
        time_limit = p.get("time_limit")
        memory_limit = p.get("memory_limit")
        st.caption(
            f"时间：{str(time_limit) + ' 秒' if time_limit is not None else '继承语言配置'} · "
            f"内存：{str(memory_limit) + ' MB' if memory_limit is not None else '继承语言配置'}"
        )
        render_statement(p)
    return p


def draft_payload(draft: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(draft.get(key) if draft.get(key) is not None else default)
        for key, default in {
            "base_problem_id": None,
            "requirement": "",
            "problem": {},
            "reference_solution": "",
            "brute_solution": "",
            "generator_code": "",
            "review": {},
        }.items()
    }
