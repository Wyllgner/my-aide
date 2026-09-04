"""Wrapper fino sobre a API da OpenAI: retry, timeout e log de uso."""

from __future__ import annotations

import logging
import time
from typing import Any

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

from aide.llm.base import LLMProvider, LLMResponse, Message

log = logging.getLogger(__name__)

RETRYABLE = (APIConnectionError, RateLimitError)


class OpenAIProvider(LLMProvider):
    def __init__(self, config, usage_sink=None):
        if not config.llm.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY não definida. Copie .env.example para .env e preencha."
            )
        self.cfg = config.llm
        self.client = OpenAI(api_key=self.cfg.api_key, timeout=self.cfg.timeout_seconds)
        # callable(model, purpose, in_tokens, out_tokens, latency_ms) -> None
        self.usage_sink = usage_sink

    def complete(
        self,
        messages: list[Message],
        *,
        fast: bool = False,
        tools: list[dict[str, Any]] | None = None,
        purpose: str = "chat",
    ) -> LLMResponse:
        model = self.cfg.model_fast if fast else self.cfg.model_chat
        payload: dict[str, Any] = {
            "model": model,
            "messages": [m.to_api() for m in messages],
            "temperature": self.cfg.temperature,
            "max_tokens": self.cfg.max_output_tokens,
        }
        if tools:
            payload["tools"] = tools

        started = time.monotonic()
        completion = self._call_with_retry(payload)
        latency_ms = int((time.monotonic() - started) * 1000)

        choice = completion.choices[0].message
        usage = completion.usage
        response = LLMResponse(
            text=choice.content or "",
            model=model,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            latency_ms=latency_ms,
            tool_calls=[tc.model_dump() for tc in (choice.tool_calls or [])],
        )

        if self.usage_sink:
            self.usage_sink(
                model, purpose, response.input_tokens, response.output_tokens, latency_ms
            )
        return response

    def _call_with_retry(self, payload: dict[str, Any]):
        delay = 1.0
        last: Exception | None = None

        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                return self.client.chat.completions.create(**payload)
            except RETRYABLE as exc:
                last = exc
                if attempt == self.cfg.max_retries:
                    break
                log.warning("openai falhou (%s), tentativa %s; aguardando %.1fs",
                            type(exc).__name__, attempt, delay)
                time.sleep(delay)
                delay *= 2
            except APIStatusError as exc:
                # 4xx que não é rate limit: reenviar não resolve.
                raise RuntimeError(f"OpenAI recusou a chamada ({exc.status_code}): {exc}") from exc

        raise RuntimeError(f"OpenAI indisponível após {self.cfg.max_retries} tentativas") from last
