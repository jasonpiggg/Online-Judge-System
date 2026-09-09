"""Public editorial assets and an explicit, version-aware draft restore preview."""

from __future__ import annotations

import copy
from typing import Any

import streamlit as st

from frontend.client import ApiClient
from frontend.components import diff
from frontend.ui import call, local_time


def assets_panel(
    api: ApiClient, pid: str, state: dict[str, Any] | None = None, draft_id: str | None = None
) -> None:
    title = "恢复已发布资产" if state is not None else "参考解与验证资产"
    panel = st.expander(title, key=f"published-assets-{draft_id or pid}", on_change="rerun")
    if not panel.open:
        return
    with panel:
        result = call(lambda: api.get(f"/api/problems/{pid}/assets"))
        if not result:
            return
        data = result["data"]
        if data["status"] == "missing":
            st.info("没有找到与当前题目匹配的已发布资产；不会自动调用 AI 重新生成。")
            return
        if data["status"] == "stale":
            st.warning("题目发布后已修改，以下资产来自旧版本，须重新审阅和验证。")
        if data["status"] == "ambiguous":
            st.warning("找到多个资产不同的历史发布版本，请选择来源并核对内容。")
            sources = data["sources"]
            selected = st.selectbox(
                "资产来源",
                range(len(sources)),
                index=None,
                format_func=lambda i: (
                    f"{local_time(sources[i]['published_at'])} · "
                    f"{sources[i]['source_draft_id']} · v{sources[i]['source_revision']}"
                ),
                key=f"asset-source-{draft_id or pid}",
            )
            if selected is None:
                return
            data = sources[selected]
        assets = data["assets"]
        st.caption("已发布命题资产向所有登录用户开放。参考解供学习使用，有限测试不代表正确性证明。")
        if state is not None:
            before = {key: state["local"][key] for key in assets}
            diff(before, assets, f"restore-assets-{draft_id}")
            st.caption(
                "采纳会替换上方列出的资产并保存当前草稿，题目内容保持当前编辑值；需要重新验证。"
            )
            if st.button("采纳并保存资产", key=f"apply-assets-{draft_id}"):
                from frontend.authoring import save_draft

                original = copy.deepcopy(state["local"])
                state["local"].update(copy.deepcopy(assets))
                if save_draft(api, str(draft_id), state):
                    state["epoch"] += 1
                    st.rerun()
                state["local"] = original
            return
        for key, label in [
            ("reference_solution", "参考解"),
            ("brute_solution", "独立解法"),
            ("generator_code", "数据生成器"),
        ]:
            st.markdown(f"**{label}**")
            if assets.get(key):
                st.code(assets[key], language="python")
            else:
                st.caption("未提供")
        review = assets.get("review", {})
        st.write(review.get("review", ""))
        if review.get("coverage"):
            st.json(review["coverage"])
        for index, wrong in enumerate(review.get("wrong_solutions", []), 1):
            st.markdown(f"**错误解 {index}**")
            st.write(wrong.get("reason", ""))
            st.code(wrong.get("code", ""), language="python")
