from __future__ import annotations

from typing import Any

import streamlit as st

from frontend.client import ApiClient
from frontend.editor import load_editor
from frontend.library import statement
from frontend.ui import call, heading


def model_settings(api: ApiClient, config: dict[str, Any]) -> None:
    st.caption("密钥只加密保存在后端。费用按下方单价计算，需与服务商账单核对。")
    with st.form("ai-settings"):
        url = st.text_input(
            "兼容 API 基地址", value=config.get("provider_url", "https://api.openai.com/v1")
        )
        model = st.text_input("模型名称", value=config.get("model", ""))
        secret = st.text_input("API key", type="password", help="已配置时留空表示保留原密钥。")
        a, b, c = st.columns(3)
        inp = a.number_input(
            "输入单价（USD）",
            min_value=0.0,
            value=float(config.get("input_price", 0)),
            format="%.6f",
        )
        out = b.number_input(
            "输出单价（USD）",
            min_value=0.0,
            value=float(config.get("output_price", 0)),
            format="%.6f",
        )
        unit = c.number_input(
            "计价 Token 数", min_value=1, value=int(config.get("price_unit", 1_000_000))
        )
        if st.form_submit_button("保存模型配置", type="primary"):
            body = {
                "provider_url": url,
                "model": model,
                "input_price": inp,
                "output_price": out,
                "price_unit": unit,
            }
            if secret:
                body["api_key"] = secret
            if call(lambda: api.put("/api/ai/model-config", json=body)):
                st.success("配置已保存，密钥不会回显。")


def ai_result(api: ApiClient, result: dict[str, Any], ready: bool) -> None:
    problem = result["problem"]
    st.subheader(problem["title"])
    a, b, c, d = st.tabs(["题面", "测试点", "参考解", "审查与验证"])
    with a:
        statement(problem)
    with b:
        st.caption(f"{len(problem['testcases'])} 个测试点 · 输入和输出原样显示")
        for i, case in enumerate(problem["testcases"], 1):
            with st.expander(f"测试点 {i}"):
                st.code(case["input"], language=None)
                st.code(case["output"], language=None)
    with c:
        st.code(result["reference_solution"], language="python")
    with d:
        st.write(result["review"])
        for category, title in [
            ("basic", "基础覆盖"),
            ("boundary", "边界覆盖"),
            ("scale", "规模与复杂度"),
        ]:
            st.markdown(f"**{title}**")
            st.write(result["coverage"][category])
        for i, wrong in enumerate(result["wrong_solutions"], 1):
            with st.expander(f"典型错误解法 {i} · {wrong['reason']}"):
                st.code(wrong["code"], language="python")
        verification = result.get("verification")
        if verification:
            st.success(
                f"参考解通过 {verification['samples']} 个样例"
                f"和 {verification['testcases']} 个测试点。"
            )
            for item in verification["wrong_solutions"]:
                st.write(f"错误解法 {item['index']} 被测试点 {item['rejected_by']} 拒绝。")
            st.caption(verification["note"])
        else:
            st.warning("尚未通过全部本地质量验证，不能一键入库。")
    if ready:
        st.divider()
        st.subheader("审阅后载入题目编辑器")
        mode = st.radio("保存方式", ["新建题目", "更新已有题目"], horizontal=True)
        target = None
        if mode == "更新已有题目":
            items = call(lambda: api.get("/api/problems/"))
            if items and items["data"]:
                choices = {p["id"]: p["title"] for p in items["data"]}
                target = st.selectbox(
                    "更新目标题目", list(choices), format_func=lambda v: f"{v} · {choices[v]}"
                )
            else:
                st.info("当前没有可更新的题目。")
        confirmed = st.checkbox(
            "我已审阅生成内容，进入编辑器后仍需手动保存", key="ai-review-confirm"
        )
        if st.button(
            "载入编辑器",
            type="primary",
            disabled=not confirmed or (mode == "更新已有题目" and not target),
        ):
            data = dict(problem)
            if target:
                data["id"] = target
            load_editor(data, update=bool(target))


def task_panel(api: ApiClient, task_id: str) -> None:
    terminal = st.session_state.get(f"ai-terminal-{task_id}", False)

    @st.fragment(run_every=None if terminal else "1s")
    def poll() -> None:
        response = call(lambda: api.get(f"/api/ai/problem-tasks/{task_id}"))
        if not response:
            return
        data = response["data"]
        finished = data["status"] in {"completed", "failed", "cancelled"}
        if finished and not st.session_state.get(f"ai-terminal-{task_id}"):
            st.session_state[f"ai-terminal-{task_id}"] = True
            st.rerun()
        labels = {
            "pending": "排队中",
            "running": "进行中",
            "completed": "验证通过",
            "failed": "未通过",
            "cancelled": "已取消",
        }
        st.markdown(f"**{labels[data['status']]}** · {data['progress']}")
        usage = data["usage"]
        a, b, c = st.columns(3)
        a.metric("输入 Token", f"{usage['input_tokens']:,}")
        b.metric("输出 Token", f"{usage['output_tokens']:,}")
        c.metric("累计费用", f"${usage['cost']:.6f}")
        st.caption(
            "服务商 usage"
            if usage["source"] == "provider"
            else "估算用量（包含未获服务商 usage 的阶段）"
        )
        if data.get("usage_details"):
            with st.expander("阶段用量与计价依据"):
                details = data["usage_details"]
                st.dataframe(
                    [{"阶段": key, **value} for key, value in details["phases"].items()],
                    hide_index=True,
                )
                pricing = details["pricing"]
                st.caption(
                    f"每 {pricing['price_unit']:,} Token：输入 ${pricing['input_price']}"
                    f" / 输出 ${pricing['output_price']}"
                )
        if not finished and st.button("中断生成", icon=":material/stop_circle:"):
            if call(lambda: api.put(f"/api/ai/problem-tasks/{task_id}/cancel")):
                st.rerun()
        if data.get("error"):
            st.error(data["error"])
        if data.get("result"):
            ai_result(api, data["result"], ready=data["status"] == "completed")

    poll()


def ai_page(api: ApiClient) -> None:
    heading("AI 命题", note="需求 → 生成与批判 → 本地验证 → 人工审阅入库")
    result = call(lambda: api.get("/api/ai/model-config"))
    if not result:
        return
    config = result["data"]
    configured = config["api_key_configured"]
    work, settings = st.tabs(["命题工作区", "模型设置 · " + ("已配置" if configured else "未配置")])
    with settings:
        model_settings(api, config)
    with work:
        if not configured:
            st.info("首次使用请在「模型设置」配置服务商、模型和密钥。")
        else:
            st.caption(f"当前模型：{config['model']} · 两阶段各调用一次，不自动重试付费请求。")
        items = call(lambda: api.get("/api/problems/"))
        choices = {p["id"]: p["title"] for p in items["data"]} if items else {}
        with st.form("ai-requirement"):
            requirement = st.text_area(
                "命题需求",
                placeholder="说明知识点、难度、数据范围与期望覆盖的边界场景……",
                height=140,
            )
            reference = st.selectbox(
                "参考已有题目（可选）",
                [None, *choices],
                format_func=lambda v: "不参考" if v is None else f"{v} · {choices[v]}",
            )
            if st.form_submit_button("生成并验证", type="primary", disabled=not configured):
                created = call(
                    lambda: api.post(
                        "/api/ai/problem-tasks/",
                        json={"requirement": requirement, "problem_id": reference},
                    )
                )
                if created:
                    st.session_state.ai_task_id = created["data"]["task_id"]
        if task_id := st.session_state.get("ai_task_id"):
            task_panel(api, task_id)
