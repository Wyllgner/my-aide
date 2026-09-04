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


def test_config_carrega_o_token_do_env(tmp_path, monkeypatch):
    """O comando telegram-id lia os.getenv direto e não enxergava o .env."""
    (tmp_path / "config.yaml").write_text("telegram:\n  enabled: true\n  allowed_chat_ids: [7]\n")
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=abc123\n")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    from aide.config import load_config

    config = load_config(root=tmp_path)
    assert config.telegram.token == "abc123"
    assert config.telegram.usable


def test_reenvia_quando_a_rede_cai(monkeypatch):
    """Connection reset sem retry come a resposta e o usuário fica sem retorno."""
    import urllib.error

    client = TelegramClient(token="x")
    tentativas = []

    class FakeResp:
        def read(self):
            return json.dumps({"ok": True, "result": {"message_id": 1}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        tentativas.append(1)
        if len(tentativas) < 3:
            raise urllib.error.URLError(ConnectionResetError(104, "Connection reset by peer"))
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    assert client.send_message(1, "oi") == {"message_id": 1}
    assert len(tentativas) == 3


def test_desiste_depois_das_tentativas(monkeypatch):
    import urllib.error

    client = TelegramClient(token="x")

    def sempre_falha(req, timeout=None):
        raise urllib.error.URLError("rede fora")

    monkeypatch.setattr("urllib.request.urlopen", sempre_falha)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    with pytest.raises(TelegramError, match="não completou"):
        client.send_message(1, "oi")


def test_erro_http_nao_e_reenviado(monkeypatch):
    """409 e 400 não melhoram na segunda tentativa."""
    import urllib.error

    client = TelegramClient(token="x")
    tentativas = []

    def conflito(req, timeout=None):
        tentativas.append(1)
        raise urllib.error.HTTPError("u", 409, "Conflict", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", conflito)
    with pytest.raises(TelegramError, match="409"):
        client.get_updates()
    assert len(tentativas) == 1
