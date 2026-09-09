"""Native Streamlit routes plus bounded, account-scoped task navigation."""

from __future__ import annotations

from typing import Any

import streamlit as st

DETAILS = {"workspace", "editor", "draft", "ai_task", "submission", "public_log"}
PARAMS = {
    "id",
    "q",
    "difficulty",
    "progress",
    "page",
    "user_id",
    "problem_id",
    "section",
    "draft_page",
    "task_page",
    "language",
    "message_page",
    "status",
    "outcome",
    "users_page",
    "audit_page",
    "submission_id",
}


def route(page: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "page": page,
        "params": {k: str(v) for k, v in (params or {}).items() if k in PARAMS and v is not None},
    }


def identity(entry: dict[str, Any]) -> tuple[str, str]:
    return entry["page"], entry.get("params", {}).get("id", "")


def go(page: str, *, title: str = "", **params: Any) -> None:
    target = route(page, params)
    current = st.session_state.get("current_route", route("library"))
    slots = st.session_state.setdefault("task_slots", [])
    if page in DETAILS:
        existing = next((s for s in slots if identity(s["current"]) == identity(target)), None)
        active = next((s for s in slots if s["key"] == st.session_state.get("active_slot")), None)
        if existing:
            existing["current"] = target
            st.session_state.active_slot = existing["key"]
        elif active and current["page"] in DETAILS:
            active["history"].append(current)
            active["history"] = active["history"][-20:]
            active["current"] = target
            active["title"] = title or params.get("id", page)
        else:
            if len(slots) >= 40:
                st.warning("已打开 40 个任务，请先关闭不需要的页面。")
                return
            import uuid

            slot = {
                "key": uuid.uuid4().hex,
                "current": target,
                "origin": current,
                "history": [],
                "title": title or params.get("id", page),
            }
            slots.append(slot)
            st.session_state.active_slot = slot["key"]
    else:
        st.session_state.pop("active_slot", None)
    st.switch_page(st.session_state.pages[page], query_params=target["params"])


def back() -> None:
    slots = st.session_state.get("task_slots", [])
    active = next((s for s in slots if s["key"] == st.session_state.get("active_slot")), None)
    if active:
        target = active["history"].pop() if active["history"] else active["origin"]
        if target["page"] in DETAILS:
            active["current"] = target
        else:
            # Returning to the origin leaves the task available without selecting it.
            st.session_state.pop("active_slot", None)
        st.switch_page(st.session_state.pages[target["page"]], query_params=target["params"])
    go("library")


def restore_slots(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result = []
    for slot in value[:40]:
        if not isinstance(slot, dict) or not isinstance(slot.get("key"), str):
            continue
        history = slot.get("history", [])
        if not isinstance(history, list):
            continue
        entries = [slot.get("current"), slot.get("origin"), *history[:20]]
        if any(
            not isinstance(e, dict)
            or e.get("page") not in st.session_state.pages
            or not isinstance(e.get("params"), dict)
            for e in entries
        ):
            continue
        result.append(
            {
                "key": slot["key"][:80],
                "title": str(slot.get("title", "任务"))[:100],
                "current": route(entries[0]["page"], entries[0]["params"]),
                "origin": route(entries[1]["page"], entries[1]["params"]),
                "history": [route(e["page"], e["params"]) for e in entries[2:]],
            }
        )
    return result


def task_bar() -> None:
    slots = st.session_state.get("task_slots", [])
    if not slots:
        return
    active_key = st.session_state.get("active_slot")

    def switch_slot(slot: dict[str, Any]) -> None:
        st.session_state.active_slot = slot["key"]
        target = slot["current"]
        st.switch_page(st.session_state.pages[target["page"]], query_params=target["params"])

    with st.container(key="task-bar", horizontal=True, vertical_alignment="center"):
        if st.session_state.get("mobile"):
            options = [None, *[slot["key"] for slot in slots]]
            chosen = st.selectbox(
                "进行中的任务",
                options,
                index=options.index(active_key) if active_key in options else 0,
                format_func=lambda value: next(
                    (str(s["title"]) for s in slots if s["key"] == value), "选择任务"
                ),
                key=f"mobile-task-selector-{active_key}",
            )
            if chosen and chosen != active_key:
                switch_slot(next(s for s in slots if s["key"] == chosen))
        else:
            with st.container(horizontal=True, key="task-strip"):
                for slot in slots:
                    if st.button(
                        str(slot["title"]),
                        key=f"slot-{slot['key']}",
                        help=str(slot["title"]),
                        type="primary" if slot["key"] == active_key else "secondary",
                    ):
                        switch_slot(slot)
        if st.button("关闭当前任务", key="close-current-task", disabled=not active_key):
            st.session_state.confirm_close = True
        if st.button("一键清空任务标签", key="clear-task-tabs"):
            if st.session_state.get("unsaved"):
                st.session_state.confirm_clear_tabs = True
            else:
                st.session_state.task_slots = []
                st.session_state.pop("active_slot", None)
                go("library")
    if st.session_state.get("confirm_clear_tabs"):
        st.warning("存在未保存内容，清空标签前请保存或备份。后台任务不会取消。")
        if st.button("确认清空标签"):
            st.session_state.task_slots = []
            st.session_state.pop("active_slot", None)
            st.session_state.pop("confirm_clear_tabs", None)
            go("library")
        if st.button("保留标签"):
            st.session_state.pop("confirm_clear_tabs", None)
            st.rerun()
    if st.session_state.get("confirm_close"):
        st.warning(
            "关闭页面不会取消后台任务。请确认未保存内容已有备份；需要停止任务时请使用中断按钮。"
        )
        yes, no = st.columns(2)
        if yes.button("确认关闭", key="close-task-yes"):
            active = next(
                (s for s in slots if s["key"] == st.session_state.get("active_slot")), None
            )
            if active:
                slots.remove(active)
                target = active["origin"]
            else:
                target = route("library")
            st.session_state.pop("confirm_close", None)
            st.session_state.pop("active_slot", None)
            st.switch_page(st.session_state.pages[target["page"]], query_params=target["params"])
        if no.button("取消", key="close-task-no"):
            st.session_state.pop("confirm_close", None)
            st.rerun()


def page_number(name: str = "page") -> int:
    try:
        return min(2**31 - 1, max(1, int(st.query_params.get(name, "1"))))
    except ValueError:
        return 1


def pagination(total: int, name: str = "page", size: int = 10, *, position: str = "top") -> int:
    page = page_number(name)
    last = max(1, (total + size - 1) // size)
    if page > last:
        st.query_params[name] = str(last)
        st.rerun()
    prefix = f"pager-{name}-{position}"

    def move(value: int) -> None:
        st.query_params[name] = str(value)
        st.rerun()

    with st.container(horizontal=True, vertical_alignment="center", key=prefix):
        st.caption(f"第 {page} / {last} 页 · {total} 条", width="content")
        start = max(1, min(page - 2, last - 4))
        end = min(last, start + 4)
        entries = [("首页", 1), ("上一页", page - 1)]
        if start > 1:
            entries.append(("…", -1))
        entries.extend((str(n), n) for n in range(start, end + 1))
        if end < last:
            entries.append(("…", -1))
        entries.extend([("下一页", page + 1), ("尾页", last)])
        for index, (label, value) in enumerate(entries):
            if st.button(
                label,
                key=f"{prefix}-{index}",
                type="primary" if label == str(page) else "secondary",
                disabled=value < 1 or value > last or value == page,
            ):
                move(value)
        st.caption("跳转至：", width="content")
        target = st.number_input(
            "跳转至",
            min_value=1,
            max_value=last,
            value=page,
            step=1,
            key=f"{prefix}-jump-{page}-{last}",
            width=90,
            label_visibility="collapsed",
        )
        if st.button("跳转", key=f"{prefix}-go", disabled=last == 1):
            move(int(target))
    return page
