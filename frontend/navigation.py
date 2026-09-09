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


ADMIN_SECTIONS = {
    "用户": "users",
    "角色审计": "roles",
    "全站提交": "records",
    "题目管理": "problems",
    "语言": "languages",
    "公开日志": "logs",
    "访问审计": "access",
    "系统设置": "settings",
}
ADMIN_PARAMS = {
    f"admin_{section}_{key}"
    for section in ADMIN_SECTIONS.values()
    for key in PARAMS | {"public_log_id"}
}


class PanelQuery:
    """Keep each embedded admin panel's filters in its own bookmarkable URL keys."""

    def _key(self, key: str) -> str:
        current = st.session_state.get("current_route", {}).get("page")
        if (
            key != "section"
            and current in {"admin", "resources"}
            and st.session_state.get("user", {}).get("role") == "admin"
        ):
            scope = ADMIN_SECTIONS.get(st.query_params.get("section", "用户"), "users")
            return f"admin_{scope}_{key}"
        return key

    def get(self, key: str, default: Any = None) -> Any:
        return st.query_params.get(self._key(key), default)

    def __setitem__(self, key: str, value: Any) -> None:
        st.query_params[self._key(key)] = value

    def __getattr__(self, key: str) -> Any:
        return st.query_params[self._key(key)]

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value

    def update(self, **values: Any) -> None:
        st.query_params.update({self._key(k): v for k, v in values.items()})


panel_query = PanelQuery()


def route(page: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "page": page,
        "params": {
            k: str(v)
            for k, v in (params or {}).items()
            if k in PARAMS | ADMIN_PARAMS and v is not None
        },
    }


def identity(entry: dict[str, Any]) -> tuple[str, str]:
    return entry["page"], entry.get("params", {}).get("id", "")


def go(page: str, *, title: str = "", **params: Any) -> None:
    if page == "resources" and st.session_state.get("user", {}).get("role") == "admin":
        page = "admin"
        params["section"] = {"题目": "题目管理"}.get(
            params.get("section", "题目"), params.get("section", "题目管理")
        )
    target = route(page, params)
    target["title"] = title or params.get("id", page)
    current = route(
        st.session_state.get("current_route", route("library"))["page"],
        st.query_params.to_dict(),
    )
    slots = st.session_state.setdefault("task_slots", [])
    active_title = next(
        (s["title"] for s in slots if s["key"] == st.session_state.get("active_slot")), ""
    )
    current["title"] = active_title or st.session_state.get("page-title", current["page"])
    if page in DETAILS:
        existing = next((s for s in slots if identity(s["current"]) == identity(target)), None)
        active = next((s for s in slots if s["key"] == st.session_state.get("active_slot")), None)
        if existing:
            existing["current"] = target
            existing["title"] = target["title"]
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
            active["title"] = target.get("title") or target.get("params", {}).get(
                "id", target["page"]
            )
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
                "history": [
                    {**route(e["page"], e["params"]), "title": str(e.get("title", ""))[:100]}
                    for e in entries[2:]
                ],
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
            active = next((s for s in slots if s["key"] == active_key), None)
            target = active["origin"] if active else route("library")
            if active:
                slots.remove(active)
            st.session_state.pop("active_slot", None)
            st.switch_page(st.session_state.pages[target["page"]], query_params=target["params"])
        if st.button("一键清空任务标签", key="clear-task-tabs"):
            st.session_state.task_slots = []
            st.session_state.pop("active_slot", None)
            go("library")


def page_number(name: str = "page") -> int:
    try:
        return min(2**31 - 1, max(1, int(panel_query.get(name, "1"))))
    except ValueError:
        return 1


def page_links(page: int, last: int) -> list[int | None]:
    """Always expose endpoints; ellipses represent only genuinely hidden pages."""
    visible = (
        set(range(1, last + 1))
        if last <= 5
        else {1, last, *range(max(1, page - 2), min(last, page + 2) + 1)}
    )
    result: list[int | None] = []
    previous = 0
    for value in sorted(visible):
        if previous and value > previous + 1:
            result.append(None)
        result.append(value)
        previous = value
    return result


def bounded_page(total: int, name: str = "page", size: int = 10) -> int:
    page = page_number(name)
    last = max(1, (total + size - 1) // size)
    if page > last:
        panel_query[name] = str(last)
        st.rerun()
    return page


def pagination(total: int, name: str = "page", size: int = 10, *, position: str = "bottom") -> int:
    page = bounded_page(total, name, size)
    last = max(1, (total + size - 1) // size)
    if total == 0:
        return 1
    prefix = f"pager-{name}-{position}"

    def move(value: int) -> None:
        panel_query[name] = str(value)
        st.rerun()

    with st.container(
        horizontal=True, vertical_alignment="center", key=f"pagination-{name}-{position}"
    ):
        st.caption(f"第 {page} / {last} 页 · {total} 条", width="content")
        with st.container(
            horizontal=True,
            vertical_alignment="center",
            width="content",
            key=f"pagination-nav-{name}-{position}",
        ):
            entries = [("首页", 1), ("上一页", page - 1)]
            entries.extend(
                (str(n), n) if n is not None else ("…", -1) for n in page_links(page, last)
            )
            entries.extend([("下一页", page + 1), ("尾页", last)])
            for index, (label, value) in enumerate(entries):
                if value == -1:
                    st.caption("…", width="content")
                elif st.button(
                    label,
                    key=f"{prefix}-{index}",
                    type="primary" if label == str(page) else "secondary",
                    disabled=value < 1 or value > last or value == page,
                ):
                    move(value)
        with st.container(
            horizontal=True,
            vertical_alignment="center",
            width="content",
            key=f"pagination-jump-{name}-{position}",
        ):
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
