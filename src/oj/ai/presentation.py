"""Conservative checks of prose only; never normalize code or literal test IO."""

from __future__ import annotations

import re
from typing import Any

PROSE_FIELDS = (
    "description",
    "input_description",
    "output_description",
    "constraints",
    "hint",
    "review",
)


def presentation_issues(value: dict[str, Any]) -> list[str]:
    issues = []
    for name in PROSE_FIELDS:
        text = value.get(name)
        if not isinstance(text, str):
            continue
        # Remove code fences and inline code before interpreting dollar delimiters.
        prose = re.sub(r"(`{3,}|~{3,})[^\n]*\n[\s\S]*?\1|`+[^`]*`+", "", text)
        if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", prose):
            issues.append(f"{name}: JSON escaping corrupted prose with control characters")
        tokens = re.split(r"(?<!\\)(\${1,2})", prose)
        opened = ""
        formula = ""
        for index, token in enumerate(tokens):
            if index % 2:
                if not opened:
                    opened, formula = token, ""
                elif token == opened:
                    braces = re.sub(r"\\[{}]", "", formula)
                    depth = 0
                    for char in braces:
                        depth += (char == "{") - (char == "}")
                        if depth < 0:
                            break
                    if depth != 0:
                        issues.append(f"{name}: unbalanced LaTeX braces")
                    if "\t" in formula or "\r" in formula:
                        issues.append(f"{name}: possible JSON-escaped LaTeX command corruption")
                    opened = ""
                else:
                    issues.append(f"{name}: mismatched math delimiters")
            elif opened:
                formula += token
        if opened:
            issues.append(f"{name}: unclosed math delimiter; escape literal dollars as \\$")
    return issues


def check_presentation(value: dict[str, Any]) -> None:
    issues = presentation_issues(value)
    problem = value.get("problem")
    if isinstance(problem, dict):
        issues += presentation_issues(problem)
    if issues:
        raise ValueError("; ".join(issues))
