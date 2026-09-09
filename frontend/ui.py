from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any

import streamlit as st

from frontend.client import ApiError

CSS = "<style>" + Path(__file__).with_name("theme.css").read_text(encoding="utf-8") + "</style>"


def apply_theme() -> None:
    st.html(CSS)


def heading(kicker: str, title: str = "", note: str = "") -> None:
    label = title or kicker
    st.session_state["page-title"] = label
    current = st.session_state.get("current_route", {})
    for slot in st.session_state.get("task_slots", []):
        if slot["key"] == st.session_state.get("active_slot") and slot["current"].get(
            "page"
        ) == current.get("page"):
            if slot["title"] != label:
                slot["title"] = label
                slot["current"]["title"] = label
                st.rerun()  # The task bar is rendered before the page header.
    st.html(
        f'<div class="oj-header"><h1>{escape(title or kicker)}</h1><p>{escape(note)}</p></div>',
    )


def call(action: Callable[[], dict[str, Any]]) -> dict[str, Any] | None:
    try:
        return action()
    except ApiError as exc:
        if exc.status == 401 and st.session_state.get("user"):
            st.session_state.pop("user", None)
            st.session_state.flash = "登录已过期，请重新登录。草稿仍保留在当前会话。"
            st.rerun()
        if exc.status == 403 and "banned" in exc.server_message.casefold():
            st.session_state.pop("user", None)
            st.session_state.flash = "账户已被禁用，请联系管理员。"
            st.rerun()
        st.error(str(exc))
    except RuntimeError as exc:
        st.error(str(exc))
    return None


def navigate(page: str, **state: Any) -> None:
    from frontend.navigation import go

    st.session_state.update(state)
    pid = state.get("current_problem")
    go(page, **({"id": pid} if pid else {}))


def pills(values: list[str]) -> None:
    st.html("".join(f'<span class="oj-pill">{escape(v)}</span>' for v in values))


def pager(key: str, count: int | None = None, size: int = 10, has_next: bool = False) -> int:
    page = st.session_state.get(key, 1)
    last = max(1, (count + size - 1) // size) if count is not None else None
    if last and page > last:
        page = last
        st.session_state[key] = page
    with st.container(horizontal=True, vertical_alignment="center"):
        if st.button("上一页", key=f"{key}-prev", disabled=page == 1):
            st.session_state[key] = page - 1
            st.rerun()
        st.caption(f"{page} / {last} 页" if last else f"第 {page} 页")
        if st.button("下一页", key=f"{key}-next", disabled=page >= last if last else not has_next):
            st.session_state[key] = page + 1
            st.rerun()
    return page


STATUS_LABELS = {
    "pending": "等待中",
    "running": "进行中",
    "success": "评测完成",
    "error": "评测异常",
    "completed": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
    "draft": "草稿",
    "ready": "可发布",
    "published": "已发布",
    "archived": "已归档",
    "generate": "生成整题",
    "revise": "局部修改",
    "review": "全面审查",
    "tests": "设计测试",
    "verify": "本地验证",
    "user": "学习者",
    "admin": "管理员",
    "banned": "已禁用",
    "generation": "生成题目",
    "statement": "生成题面",
    "assets": "生成验证资产",
    "repair": "定向修复",
    "validation": "本地验证",
    "critique": "复核与改进",
    "queued": "等待执行",
    "oracle": "参考解验证",
    "coverage": "覆盖检查",
    "differential": "差分验证",
    "passed": "通过",
    "skipped": "未执行",
    "blocked": "未满足条件",
}


def status_label(value: str) -> str:
    return STATUS_LABELS.get(value, value or "—")


def local_time(value: str | None) -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def verdict_label(data: dict[str, Any]) -> tuple[str, str]:
    status = data.get("status")
    if status == "pending":
        return "正在评测", "wait"
    if status == "error":
        return "评测异常", "fail"
    verdict = (data.get("evaluation") or {}).get("verdict")
    labels = {
        "CE": "编译失败",
        "WA": "答案错误",
        "TLE": "超出时间限制",
        "MLE": "超出内存限制",
        "RE": "运行时错误",
        "empty": "没有测试点",
        "unknown": "明细不完整",
        "partial": "部分通过",
        "failed": "测试未通过",
    }
    if verdict in labels:
        return labels[verdict], "wait" if verdict in {"empty", "unknown"} else "fail"
    score, total = data.get("score"), data.get("counts")
    if total and score == total:
        return "全部通过", "pass"
    if total == 0:
        return "没有测试点", "wait"
    if score is None or total is None:
        return "评测完成 · 得分待确认", "wait"
    return "未全部通过", "fail"


def result_summary(data: dict[str, Any]) -> None:
    label, tone = verdict_label(data)
    score, total = data.get("score"), data.get("counts")
    evaluation = data.get("evaluation") or {}
    detail = ""
    if evaluation.get("total_cases") is not None:
        detail = f" · 通过测试点 {evaluation.get('passed_cases', 0)} / {evaluation['total_cases']}"
    st.html(
        f'<div class="oj-result {tone}" role="status"><strong>{escape(label)}</strong>'
        f"<p>得分 {score if score is not None else '—'} / "
        f"{total if total is not None else '—'}{escape(detail)}</p></div>",
    )


def data_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return  # The owning panel renders its single contextual empty-state message.
    labels = {
        "id": "编号",
        "user_id": "用户 ID",
        "username": "用户名",
        "role": "角色",
        "join_time": "加入时间",
        "submit_count": "提交次数",
        "resolve_count": "通过题目",
        "result": "结果",
        "time": "用时 / 秒",
        "memory": "内存 / MB",
        "name": "语言",
        "file_ext": "扩展名",
        "compile_cmd": "编译命令",
        "run_cmd": "运行命令",
        "time_limit": "时间 / 秒",
        "memory_limit": "内存 / MB",
        "created_at": "时间（北京时间）",
        "problem_id": "题号",
        "action": "操作",
        "old_role": "原角色",
        "new_role": "新角色",
        "actor_id": "操作者 ID",
        "status": "状态",
        "label": "检查项",
        "detail": "说明与建议",
    }
    display = [
        {
            k: local_time(v)
            if k == "created_at"
            else status_label(v)
            if k in {"role", "old_role", "new_role", "status"} and isinstance(v, str)
            else v
            for k, v in row.items()
        }
        for row in rows
    ]
    st.dataframe(display, hide_index=True, width="stretch", column_config=labels)


def task_timer(task: dict[str, Any]) -> None:
    """Persisted timestamps keep elapsed time stable across refreshes."""
    try:
        started = datetime.fromisoformat(task["created_at"])
        end = (
            datetime.now(UTC)
            if task["status"] in {"pending", "running"}
            else datetime.fromisoformat(task["updated_at"])
        )
        seconds = max(0, int((end - started).total_seconds()))
    except (KeyError, TypeError, ValueError):
        return
    st.caption(f"耗时 {seconds // 60:02d}:{seconds % 60:02d} · 总时限 04:00")
    if task["status"] in {"pending", "running"}:
        st.progress(min(seconds / 240, 1.0))
