"""O wrapper precisa se virar com dialetos diferentes de modelo."""

from types import SimpleNamespace

from aide.config import load_config
from aide.llm.base import Message
from aide.llm.openai_provider import OpenAIProvider


class FakeStatusError(Exception):
    """`_adapt_payload` só lê o texto do erro; não vale acoplar o teste ao SDK."""


def _provider(monkeypatch):
    config = load_config()
    object.__setattr__(config.llm, "api_key", "sk-test")
    monkeypatch.setattr("aide.llm.openai_provider.OpenAI", lambda **kw: SimpleNamespace())
    return OpenAIProvider(config)


def test_troca_max_tokens_por_max_completion_tokens(monkeypatch):
    provider = _provider(monkeypatch)
    payload = {"max_completion_tokens": 100}
    error = FakeStatusError("Unsupported parameter: 'max_completion_tokens'. Use 'max_tokens'.")
    assert provider._adapt_payload(payload, error) is True
    assert "max_tokens" in payload and "max_completion_tokens" not in payload
    assert provider._token_param == "max_tokens"


def test_ativa_reasoning_effort_para_modelo_de_raciocinio(monkeypatch):
    provider = _provider(monkeypatch)
    payload = {}
    error = FakeStatusError("To use function tools, set reasoning_effort to 'none'.")
    assert provider._adapt_payload(payload, error) is True
    assert payload["reasoning_effort"] == "none"
    # a segunda recusa igual não deve virar loop
    assert provider._adapt_payload(payload, error) is False


def test_remove_temperature_quando_nao_suportada(monkeypatch):
    provider = _provider(monkeypatch)
    payload = {"temperature": 0.3}
    error = FakeStatusError("Unsupported value: 'temperature' is not supported.")
    assert provider._adapt_payload(payload, error) is True
    assert "temperature" not in payload


def test_erro_desconhecido_nao_e_adaptado(monkeypatch):
    provider = _provider(monkeypatch)
    assert provider._adapt_payload({}, FakeStatusError("model not found")) is False


def test_mensagem_de_tool_vai_com_tool_call_id():
    msg = Message(role="tool", content="{}", tool_call_id="abc")
    assert msg.to_api() == {"role": "tool", "tool_call_id": "abc", "content": "{}"}
