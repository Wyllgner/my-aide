import json

import pytest

from aide.channels.telegram import (
    LIMITE_MENSAGEM,
    TelegramClient,
    TelegramError,
    TelegramNotifier,
)


class FakeClient(TelegramClient):
    def __init__(self, erro=None):
        super().__init__(token="x")
        self.chamadas = []
        self.erro = erro

    def call(self, method, params=None, timeout=None):
        self.chamadas.append((method, params))
        if self.erro:
            raise self.erro
        return {"message_id": 1}


def test_token_vazio_falha():
    with pytest.raises(ValueError):
        TelegramClient(token="")


def test_notifier_junta_titulo_e_corpo():
    client = FakeClient()
    assert TelegramNotifier(client, 42).send("Lembrete", "Pagar boleto") is True
    _, params = client.chamadas[0]
    assert params["chat_id"] == 42
    assert params["text"] == "Lembrete\n\nPagar boleto"


def test_notifier_sem_corpo_manda_so_o_titulo():
    client = FakeClient()
    TelegramNotifier(client, 42).send("Lembrete", "")
    assert client.chamadas[0][1]["text"] == "Lembrete"


def test_falha_de_rede_nao_derruba_o_daemon():
    client = FakeClient(erro=TelegramError("timeout"))
    assert TelegramNotifier(client, 42).send("t", "b") is False


def test_mensagem_longa_e_cortada():
    client = FakeClient()
    client.send_message(1, "x" * (LIMITE_MENSAGEM + 500))
    texto = client.chamadas[0][1]["text"]
    assert len(texto) <= LIMITE_MENSAGEM
    assert texto.endswith("[...cortado]")


def test_get_updates_passa_o_offset():
    client = FakeClient()
    client.get_updates(offset=7)
    metodo, params = client.chamadas[0]
    assert metodo == "getUpdates" and params["offset"] == 7


def test_resposta_nao_ok_vira_erro(monkeypatch):
    client = TelegramClient(token="x")

    class FakeResp:
        def read(self):
            return json.dumps({"ok": False, "description": "chat not found"}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: FakeResp())
    with pytest.raises(TelegramError, match="chat not found"):
        client.send_message(1, "oi")


def test_canal_telegram_sem_config_nao_quebra(ctx):
    from aide.channels.notify import build_notifier

    object.__setattr__(ctx.config, "notify_channels", ("telegram",))
    notifier = build_notifier(ctx.config)
    assert notifier.send("t", "b") is True  # cai no console
