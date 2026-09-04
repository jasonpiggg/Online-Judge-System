"""Shared difficulty taxonomy used by validation, prompts and the web client."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict, cast


class DifficultyLevel(TypedDict):
    value: str
    label: str
    tone: str
    description: str
    aliases: list[str]


DIFFICULTIES = cast(
    list[DifficultyLevel],
    json.loads(Path(__file__).with_name("difficulties.json").read_text(encoding="utf-8")),
)
ALIASES = {
    alias.casefold(): level["value"]
    for level in DIFFICULTIES
    for alias in [level["value"], *level["aliases"]]
}


def normalize_difficulty(value: str, *, legacy: bool = True) -> str:
    key = value.strip().casefold()
    if key in ALIASES:
        return ALIASES[key]
    if legacy:
        # Read old custom labels without rewriting the user's historical files.
        return ""
    raise ValueError("难度须为入门、简单、中等、困难、挑战或留空（未分级）")


DIFFICULTY_RULES = (
    "\nDifficulty standard v1: problem.difficulty must be one of "
    + json.dumps([level["value"] for level in DIFFICULTIES], ensure_ascii=False)
    + ". Use these Chinese canonical values, never English labels or custom levels.\n"
    + "\n".join(f"{level['label']}: {level['description']}" for level in DIFFICULTIES)
    + "\nClassify by required reasoning and algorithmic skill, not test count or score.\n"
)
