from __future__ import annotations

import copy
import json
from typing import Any

import pandas as pd
import streamlit as st

from frontend.components import rich_text
from oj.difficulty import DIFFICULTIES


def problem_form(value: dict[str, Any], key: str) -> dict[str, Any]:
    p = copy.deepcopy(value)
    basics, statement, samples, cases, limits, preview = st.tabs(
        ["基本信息", "题面与格式", "样例", "测试点", "高级设置", "预览"]
    )
    with basics:
        for field, label in [
            ("id", "题号"),
            ("title", "题目标题"),
            ("author", "作者"),
            ("source", "来源"),
        ]:
            p[field] = st.text_input(label, value=p.get(field, ""), key=f"{key}-{field}")
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
            rows = p.get(field, [])
            plain = [
                {
                    "input": c["input"],
                    "output": c["output"],
                    "files": json.dumps(c.get("files", {}), ensure_ascii=False),
                }
                for c in rows
            ]
            changed = st.data_editor(
                pd.DataFrame(plain, columns=["input", "output", "files"]).astype(str),
                num_rows="dynamic",
                hide_index=True,
                width="stretch",
                key=f"{key}-{field}",
                column_config={
                    "input": st.column_config.TextColumn("输入"),
                    "output": st.column_config.TextColumn("期望输出"),
                    "files": st.column_config.TextColumn("附加文件 JSON"),
                },
            )
            decoded = []
            for row in changed.fillna("").to_dict("records"):
                try:
                    decoded.append(
                        {
                            "input": row.get("input") or "",
                            "output": row.get("output") or "",
                            "files": json.loads(row.get("files") or "{}"),
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
        rich_text(
            "\n\n".join(
                f"### {label}\n{p.get(field, '')}"
                for field, label in [
                    ("title", "标题"),
                    ("description", "题目描述"),
                    ("input_description", "输入格式"),
                    ("output_description", "输出格式"),
                    ("constraints", "数据范围"),
                ]
            ),
            f"{key}-preview",
        )
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
