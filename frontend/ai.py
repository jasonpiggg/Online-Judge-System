from __future__ import annotations

from typing import Any

import streamlit as st

from frontend.client import ApiClient
from frontend.editor import clean_problem, load_editor
from frontend.library import statement
from frontend.ui import call, heading


def money(amount: float, currency: str = "USD") -> str:
    symbol = "¥" if currency == "CNY" else "$"
    return f"{symbol}{amount:.6f} {currency}"


def model_settings(api: ApiClient, config: dict[str, Any]) -> None:
    if config.get("system_configured"):
        st.success("系统模型已配置")
        st.caption("无需填写密钥即可使用；保存个人配置后将优先使用个人模型。")
    else:
        st.info("系统模型未配置。请联系管理员，或填写个人模型配置。")
    if config.get("personal_configured"):
        st.caption("当前使用个人配置。删除后恢复系统默认；已开始的任务不受影响。")
        with st.popover("移除个人配置"):
            st.warning("只删除你的个人配置，不影响其他用户或系统模型。")
            if st.button("确认移除个人配置"):
                if call(lambda: api.delete("/api/ai/model-config")):
                    st.rerun()
    st.subheader("个人模型配置（可选）")
    st.caption("密钥只加密保存在后端。费用按下方单价计算，需与服务商账单核对。")
    with st.form("ai-settings"):
        url = st.text_input(
            "兼容 API 基地址", value=config.get("provider_url", "https://api.openai.com/v1")
        )
        model = st.text_input("模型名称", value=config.get("model", ""))
        secret = st.text_input(
            "API key",
            type="password",
            help="已有个人配置时可留空保留。首次覆盖系统默认必须提供自己的密钥。",
        )
        currency = st.selectbox(
            "计价币种（不进行汇率换算）",
            ["USD", "CNY"],
            index=1 if config.get("currency") == "CNY" else 0,
        )
        a, b, c = st.columns(3)
        inp = a.number_input(
            "输入单价（所选币种）",
            min_value=0.0,
            value=float(config.get("input_price", 0)),
            format="%.6f",
        )
        out = b.number_input(
            "输出单价（所选币种）",
            min_value=0.0,
            value=float(config.get("output_price", 0)),
            format="%.6f",
        )
        unit = c.number_input(
            "计价 Token 数", min_value=1, value=int(config.get("price_unit", 1_000_000))
        )
        cache_enabled = st.checkbox(
            "单独设置缓存命中输入单价",
            value=config.get("cached_input_price") is not None,
            help="不勾选时，缓存 Token 按普通输入单价计算。",
        )
        cached_price = st.number_input(
            "缓存命中单价（所选币种）",
            min_value=0.0,
            value=float(config.get("cached_input_price") or 0),
            format="%.6f",
        )
        if st.form_submit_button("保存模型配置", type="primary"):
            body = {
                "provider_url": url,
                "model": model,
                "input_price": inp,
                "output_price": out,
                "price_unit": unit,
                "currency": currency,
                "cached_input_price": cached_price if cache_enabled else None,
            }
            if secret:
                body["api_key"] = secret
            if call(lambda: api.put("/api/ai/model-config", json=body)):
                st.toast("配置已保存，密钥不会回显。")
                st.rerun()


def ai_result(
    api: ApiClient,
    result: dict[str, Any],
    ready: bool,
    baseline: dict[str, Any] | None = None,
) -> None:
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
            oracle = verification.get("independent_oracle", {})
            if oracle.get("status") == "passed":
                st.success(f"独立 oracle 随机对拍通过：{oracle['generated_cases']} 组。")
            else:
                st.warning(oracle.get("message", "尚未完成独立 oracle 对拍。"))
            st.metric("Mutation score", f"{verification.get('mutation_score', 0):.2f}%")
            st.caption(verification["note"])
        else:
            st.warning("尚未通过全部本地质量验证，不能一键入库。")
    accepted_problem = dict(problem)
    if baseline:
        sections = {
            "题面": ["title", "description", "input_description", "output_description"],
            "约束与限制": ["constraints", "time_limit", "memory_limit"],
            "样例": ["samples"],
            "测试点": ["testcases"],
            "元数据": ["difficulty", "tags", "hint", "source", "author"],
        }
        changed = {
            title: fields
            for title, fields in sections.items()
            if any(baseline.get(field) != problem.get(field) for field in fields)
        }
        if changed:
            st.subheader("逐字段采纳")
            st.caption("只勾选要写入编辑器的分区；未勾选部分保持原题。")
            accepted_problem = dict(baseline)
            for title, fields in changed.items():
                accept = st.checkbox(f"采纳：{title}", value=True, key=f"accept-{title}")
                with st.expander(f"查看 {title} 差异"):
                    before, after = st.columns(2)
                    before.caption("修改前")
                    before.json({field: baseline.get(field) for field in fields})
                    after.caption("AI 建议")
                    after.json({field: problem.get(field) for field in fields})
                if accept:
                    accepted_problem.update({field: problem.get(field) for field in fields})
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
            use_accepted = baseline is not None and target == baseline.get("id")
            data = dict(accepted_problem if use_accepted else problem)
            if target:
                data["id"] = target
            load_editor(
                data,
                update=bool(target),
                assets={
                    "reference_solution": result["reference_solution"],
                    "brute_solution": result.get("brute_solution", ""),
                    "generator_code": result.get("generator_code", ""),
                    "review": {
                        "review": result["review"],
                        "coverage": result["coverage"],
                        "wrong_solutions": result["wrong_solutions"],
                        "verification": result.get("verification", {}),
                    },
                },
            )


def section_result(api: ApiClient, data: dict[str, Any]) -> None:
    result = data["result"]
    target = result["target_section"]
    st.subheader("样例修改建议" if target == "samples" else "题面修改建议")
    st.write(result["review"])
    st.info("这是局部建议，不代表整题通过评测质量门禁；采纳后仍需在编辑器中人工确认并保存。")
    if not result.get("reviewed"):
        st.warning("已保留初稿，但第二阶段复审尚未通过。")
    if target == "samples":
        for index, sample in enumerate(result["problem"]["samples"], 1):
            with st.expander(f"样例 {index}"):
                st.code(sample["input"], language=None)
                st.code(sample["output"], language=None)
    else:
        statement(result["problem"])
    confirmed = st.checkbox(
        "我已检查这些修改，准备载入编辑器", key=f"patch-confirm-{data['task_id']}"
    )
    if st.button(
        "载入局部修改到编辑器",
        disabled=not confirmed or data["status"] != "completed",
        key=f"patch-apply-{data['task_id']}",
    ):
        # Reject stale suggestions rather than overwrite a newer saved draft/problem.
        editor_key = str(result["problem"]["id"]) if data.get("problem_id") else "new"
        local = st.session_state.get("editor_drafts", {}).get(editor_key)
        if local is not None and clean_problem(local) != result["baseline"]:
            st.error("编辑器已有不同的未保存内容，请先处理这些修改，避免覆盖。")
            return
        assets = None
        if data.get("draft_id"):
            current = call(lambda: api.get(f"/api/problem-drafts/{data['draft_id']}"))
            if not current:
                return
            if current["data"]["revision"] != result.get("source_draft_revision"):
                st.error("草稿已发生变化，请基于最新版本重新发起局部修改。")
                return
            saved = current["data"]
            assets = {
                "reference_solution": saved.get("reference_solution", ""),
                "brute_solution": saved.get("brute_solution", ""),
                "generator_code": saved.get("generator_code", ""),
                "review": {
                    **saved.get("review", {}),
                    "section_review": result["review"],
                    "verification": result["verification"],
                },
            }
        elif data.get("problem_id"):
            current = call(lambda: api.get(f"/api/problems/{data['problem_id']}"))
            if not current:
                return
            if clean_problem(current["data"]) != result["baseline"]:
                st.error("原题已发生变化，请先检查最新内容，避免覆盖。")
                return
        load_editor(result["problem"], update=bool(data.get("problem_id")), assets=assets)


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
            "completed": "任务完成",
            "failed": "未通过",
            "cancelled": "已取消",
        }
        st.markdown(f"**{labels[data['status']]}** · {data['progress']}")
        usage = data["usage"]
        a, b, c = st.columns(3)
        a.metric("输入 Token", f"{usage['input_tokens']:,}")
        b.metric("输出 Token", f"{usage['output_tokens']:,}")
        c.metric("累计费用", money(usage["cost"], usage.get("currency", "USD")))
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
                for phase, value in details["phases"].items():
                    pricing = value.get("pricing", details.get("pricing", {}))
                    currency = pricing.get("currency", usage.get("currency", "USD"))
                    st.caption(
                        f"{phase} · {value.get('routing_reason', '历史记录')} · "
                        f"每 {pricing['price_unit']:,} Token："
                        f"输入 {pricing['input_price']} / 输出 {pricing['output_price']} {currency}"
                    )
                    if pricing.get("cached_input_price") is not None:
                        cached = value.get("cached_input_tokens")
                        st.caption(
                            f"缓存命中输入单价：{pricing['cached_input_price']} {currency}；"
                            f"缓存 Token：{cached if cached is not None else '未提供'}"
                        )
                st.caption("费用是按配置单价计算的估算账单；未报告缓存量时按普通输入计价。")
        if not finished and st.button("中断生成", icon=":material/stop_circle:"):
            if call(lambda: api.put(f"/api/ai/problem-tasks/{task_id}/cancel")):
                st.rerun()
        if data.get("error"):
            st.error(data["error"])
        if data["status"] in {"failed", "cancelled"}:
            with st.expander("按原需求重新发起（会产生新费用）"):
                st.caption("原记录和费用不会删除。新任务使用当前配置和修复后的流程，不会自动执行。")
                approved = st.checkbox("我确认重新调用模型并承担新费用", key=f"retry-ok-{task_id}")
                if st.button("创建新的修改任务", disabled=not approved, key=f"retry-{task_id}"):
                    payload = {
                        key: data.get(key)
                        for key in (
                            "requirement",
                            "problem_id",
                            "draft_id",
                            "action",
                            "target_section",
                        )
                    }
                    payload["action"] = payload["action"] or "generate"
                    payload["target_section"] = payload["target_section"] or "all"
                    created = call(lambda: api.post("/api/ai/problem-tasks/", json=payload))
                    if created:
                        st.session_state.ai_task_id = created["data"]["task_id"]
                        st.rerun()
        if data.get("result"):
            if data["result"].get("kind") == "incomplete_output":
                st.warning("已保留模型原始输出，尚未形成可用题目，不能直接发布。")
                st.download_button(
                    "下载已保留输出",
                    data["result"]["text"],
                    file_name=f"{task_id}-partial.txt",
                    mime="text/plain",
                )
                return
            if data["result"].get("kind") == "section_patch":
                section_result(api, data)
                return
            verification = data["result"].get("verification", {})
            baseline = None
            if data.get("problem_id"):
                original = call(lambda: api.get(f"/api/problems/{data['problem_id']}"))
                baseline = original["data"] if original else None
            ai_result(
                api,
                data["result"],
                ready=data["status"] == "completed"
                and bool(verification.get("quality_gate_passed")),
                baseline=baseline,
            )

    poll()


def ai_page(api: ApiClient) -> None:
    heading("命题中心", note="草稿、AI 修改任务、验证证据与费用集中管理")
    result = call(lambda: api.get("/api/ai/model-config"))
    if not result:
        return
    config = result["data"]
    configured = config["api_key_configured"]
    work, history, settings = st.tabs(
        ["新建任务", "草稿与任务历史", "模型设置 · " + ("已配置" if configured else "未配置")]
    )
    with settings:
        model_settings(api, config)
    with work:
        if not configured:
            st.info("首次使用请在「模型设置」配置服务商、模型和密钥。")
        else:
            if config.get("source") == "system":
                st.success("系统模型已配置")
                st.caption(
                    "使用系统默认策略；管理员启用分流后，入门初稿/简单润色走 Flash，"
                    "复杂命题、测试设计和最终复审走高质量模型。阶段详情显示实际档位。"
                    "两阶段各调用一次，不自动重试付费请求。"
                )
            else:
                st.caption(
                    f"当前个人模型：{config.get('model', '')} · "
                    "两阶段各调用一次，不自动重试付费请求。"
                )
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
    with history:
        tasks = call(lambda: api.get("/api/ai/problem-tasks/"))
        drafts = call(lambda: api.get("/api/problem-drafts/"))
        if tasks and tasks["data"]:
            st.subheader("最近任务")
            labels = {
                "pending": "排队中",
                "running": "进行中",
                "completed": "已完成",
                "failed": "失败",
                "cancelled": "已取消",
            }
            for item in tasks["data"]:
                with st.container(border=True):
                    text, action = st.columns([4, 1], vertical_alignment="center")
                    text.markdown(
                        f"**{labels.get(item['status'], item['status'])}** · "
                        f"{item['action']} / {item['target_section']}"
                    )
                    text.caption(
                        f"{item.get('problem_id') or '新题'} · "
                        f"{money(item['cost'], item.get('currency', 'USD'))} · "
                        f"{item['updated_at']}"
                    )
                    if action.button("打开", key=f"open-ai-{item['id']}", width="stretch"):
                        st.session_state.ai_task_id = item["id"]
                        st.rerun()
        else:
            st.info("还没有 AI 任务。可在题目编辑器中局部发起，或在这里生成新题。")
        if drafts and drafts["data"]:
            st.subheader("命题草稿")
            st.dataframe(
                [
                    {
                        "草稿": item["id"],
                        "题目": item["problem"].get("title", "未命名"),
                        "状态": item["status"],
                        "版本": item["revision"],
                        "更新时间": item["updated_at"],
                    }
                    for item in drafts["data"]
                    if item["status"] != "archived"
                ],
                hide_index=True,
                width="stretch",
            )
