"""Contrato de provedor de LLM. Trocar de provedor é implementar isto."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class Message:
    role: Role
    content: str = ""
    # preenchido quando o assistente pede uma tool
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    # preenchido quando a mensagem é o resultado de uma tool
    tool_call_id: str | None = None

    def to_api(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": self.role}
        if self.role == "tool":
            payload["tool_call_id"] = self.tool_call_id
            payload["content"] = self.content
            return payload
        payload["content"] = self.content or None
        if self.tool_calls:
            payload["tool_calls"] = self.tool_calls
        return payload


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        messages: list[Message],
        *,
        fast: bool = False,
        tools: list[dict[str, Any]] | None = None,
        purpose: str = "chat",
    ) -> LLMResponse:
        """Uma chamada ao modelo. `fast=True` usa o modelo barato."""
