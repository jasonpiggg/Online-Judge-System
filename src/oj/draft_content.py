"""Semantic draft equality shared by persistence and the Streamlit editor."""

from typing import Any


def equivalent_draft(left: Any, right: Any) -> bool:
    def clean(value: Any) -> Any:
        if isinstance(value, bool):
            return ("boolean", value)
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items() if v not in (None, "", [], {})}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value

    return bool(clean(left) == clean(right))
