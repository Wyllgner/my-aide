"""Carrega config.yaml (+ config.local.yaml, que sobrepõe) e o .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "openai"
    model_chat: str = "gpt-5.6-luna"
    model_fast: str = "gpt-5-nano"
    temperature: float = 0.3
    max_output_tokens: int = 1200
    timeout_seconds: int = 60
    max_retries: int = 3
    api_key: str | None = None


@dataclass(frozen=True)
class Config:
    timezone: str = "America/Sao_Paulo"
    locale: str = "pt-BR"
    user_name: str = ""
    llm: LLMConfig = field(default_factory=LLMConfig)
    token_budget: int = 8000
    history_messages: int = 12
    data_dir: Path = ROOT / "data"
    vault_dir: Path = ROOT / "vault"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "aide.db"


def load_config(root: Path = ROOT) -> Config:
    load_dotenv(root / ".env")

    raw: dict[str, Any] = {}
    for name in ("config.yaml", "config.local.yaml"):
        path = root / name
        if path.exists():
            raw = _deep_merge(raw, yaml.safe_load(path.read_text()) or {})

    llm_raw = raw.get("llm", {})
    ctx_raw = raw.get("context", {})
    paths_raw = raw.get("paths", {})

    llm = LLMConfig(
        provider=llm_raw.get("provider", "openai"),
        model_chat=llm_raw.get("model_chat", "gpt-5.6-luna"),
        model_fast=llm_raw.get("model_fast", "gpt-5-nano"),
        temperature=float(llm_raw.get("temperature", 0.3)),
        max_output_tokens=int(llm_raw.get("max_output_tokens", 1200)),
        timeout_seconds=int(llm_raw.get("timeout_seconds", 60)),
        max_retries=int(llm_raw.get("max_retries", 3)),
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    def _dir(key: str, default: str) -> Path:
        value = Path(paths_raw.get(key, default))
        return value if value.is_absolute() else root / value

    return Config(
        timezone=raw.get("timezone", "America/Sao_Paulo"),
        locale=raw.get("locale", "pt-BR"),
        user_name=raw.get("user_name", ""),
        llm=llm,
        token_budget=int(ctx_raw.get("token_budget", 8000)),
        history_messages=int(ctx_raw.get("history_messages", 12)),
        data_dir=_dir("data_dir", "data"),
        vault_dir=_dir("vault_dir", "vault"),
    )
