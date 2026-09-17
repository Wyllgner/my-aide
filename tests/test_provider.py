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


def test_pede_reasoning_effort_none_por_padrao(monkeypatch):
    """Sem isso, modelo de raciocínio gasta todo o output pensando e volta vazio."""
    provider = _provider(monkeypatch)
    assert provider._reasoning_effort == "none"


def test_desce_a_escada_de_reasoning_effort(monkeypatch):
    """gpt-5-nano recusa 'none' mas aceita 'minimal'; desistir custaria 20x mais."""
    provider = _provider(monkeypatch)
    payload = {"reasoning_effort": "none"}
    error = FakeStatusError("Unsupported value: 'reasoning_effort' does not support 'none'")

    assert provider._adapt_payload(payload, error) is True
    assert payload["reasoning_effort"] == "minimal"

    assert provider._adapt_payload(payload, error) is True
    assert "reasoning_effort" not in payload

    # chegou ao fim da escada: não vale reenviar de novo
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


def test_a_sessao_e_a_volta_chegam_ao_registro_de_uso(monkeypatch, config):
    """Passados como argumento, não guardados no provedor: é o que deixa o
    mesmo provedor atender o bot e o daemon em threads diferentes sem trocar
    as contas de uma conversa com as de outra."""
    from types import SimpleNamespace

    registrado = {}

    def sink(model, purpose, entrada, saida, latencia, sessao=None, turno=None):
        registrado.update(sessao=sessao, turno=turno)

    class FakeOpenAI:
        def __init__(self, **kw):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._criar))

        def _criar(self, **payload):
            msg = SimpleNamespace(content="ok", tool_calls=None)
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                                   usage=SimpleNamespace(prompt_tokens=10,
                                                         completion_tokens=2))

    monkeypatch.setattr("aide.llm.openai_provider.OpenAI", lambda **kw: FakeOpenAI())

    from aide.llm.base import Message
    from aide.llm.openai_provider import OpenAIProvider

    provedor = OpenAIProvider(config, usage_sink=sink)
    provedor.complete([Message(role="user", content="oi")], sessao="s7", turno=42)
    assert registrado == {"sessao": "s7", "turno": 42}
