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
        # Modelos novos trocaram max_tokens por max_completion_tokens e alguns
        # não aceitam temperature. Em vez de fixar um dialeto por nome de
        # modelo, aprendemos com a primeira recusa e guardamos para as próximas.
        self._token_param = "max_completion_tokens"
        self._send_temperature = True
        self._reasoning_effort: str | None = None

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
            self._token_param: self.cfg.max_output_tokens,
        }
        if self._send_temperature:
            payload["temperature"] = self.cfg.temperature
        if self._reasoning_effort:
            payload["reasoning_effort"] = self._reasoning_effort
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
                if self._adapt_payload(payload, exc):
                    continue  # dialeto ajustado: vale reenviar
                # 4xx que não é rate limit: reenviar não resolve.
                raise RuntimeError(f"OpenAI recusou a chamada ({exc.status_code}): {exc}") from exc

        raise RuntimeError(f"OpenAI indisponível após {self.cfg.max_retries} tentativas") from last

    def _adapt_payload(self, payload: dict[str, Any], exc: APIStatusError) -> bool:
        """Ajusta o payload a um modelo com dialeto diferente. True se vale reenviar."""
        message = str(exc)

        if "max_tokens" in message and "max_completion_tokens" in message:
            other = "max_tokens" if self._token_param == "max_completion_tokens" else "max_completion_tokens"
            payload[other] = payload.pop(self._token_param, self.cfg.max_output_tokens)
            self._token_param = other
            log.info("modelo usa %s; ajustado", other)
            return True

        if "reasoning_effort" in message and self._reasoning_effort is None:
            # modelos de raciocínio exigem effort explícito para usar tools
            # no chat completions; 'none' é o que a própria API sugere.
            self._reasoning_effort = "none"
            payload["reasoning_effort"] = "none"
            log.info("modelo de raciocínio; reasoning_effort=none")
            return True

        if "temperature" in message and "unsupported" in message.lower():
            payload.pop("temperature", None)
            self._send_temperature = False
            log.info("modelo não aceita temperature; removido")
            return True

        return False
