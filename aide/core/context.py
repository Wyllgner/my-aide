"""Montagem do prompt. Por enquanto: system prompt + histórico da sessão."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aide.llm.base import Message

PROMPTS_DIR = Path(__file__).parent / "prompts"


def now_in(timezone: str) -> datetime:
    return datetime.now(ZoneInfo(timezone))


def system_prompt(config) -> Message:
    template = (PROMPTS_DIR / "system.md").read_text()
    text = template.format(
        user_name=config.user_name or "seu usuário",
        now=now_in(config.timezone).strftime("%A, %d/%m/%Y %H:%M"),
        timezone=config.timezone,
    )
    return Message(role="system", content=text)


def build(config, history: list[Message]) -> list[Message]:
    recent = history[-config.history_messages :]
    return [system_prompt(config), *recent]
