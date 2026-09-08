"""Local, narrowly scoped browser controls; all business data uses Python REST clients."""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Any

import streamlit as st


@st.cache_resource
def _assets() -> tuple[str, str]:
    assets = Path(__file__).with_name("assets")
    return (
        gzip.decompress((assets / "oj-components.js.gz").read_bytes()).decode(),
        gzip.decompress((assets / "oj-components.css.gz").read_bytes()).decode(),
    )


def _control() -> Any:
    js, css = _assets()
    return st.components.v2.component(
        "atelier_controls",
        js=js,
        css=css,
        isolate_styles=False,
    )


def control(mode: str, key: str, **data: Any) -> Any:
    return _control()(
        key=key,
        data={"mode": mode, **data},
        on_edit_change=lambda: None,
        on_submit_change=lambda: None,
        on_backup_change=lambda: None,
        on_result_change=lambda: None,
        on_restored_change=lambda: None,
        height=0 if mode in {"state", "backup"} else "content",
    )


def rich_text(text: str, key: str) -> None:
    control("markdown", key, text=text)


def diff(before: dict[str, Any], after: dict[str, Any], key: str) -> None:
    control("diff", key, before=before, after=after)
