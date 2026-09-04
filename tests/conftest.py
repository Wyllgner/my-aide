"""Fixtures compartilhadas.

Regra da suíte: teste não fala com a rede. O `.env` do projeto tem credenciais
reais, então uma config carregada sem cuidado manda mensagem de verdade para o
Telegram do dono. `sem_rede` fecha essa porta para todos os testes.
"""

import pytest

from aide.config import load_config
from aide.storage import connect, migrate
from aide.tools import registry as tool_registry
from aide.tools.registry import ToolContext


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch):
    """Nenhum teste pode abrir conexão sem pedir explicitamente.

    Um teste que precise simular HTTP sobrescreve urlopen no seu próprio
    monkeypatch, que tem precedência sobre este.
    """

    def recusar(*args, **kwargs):
        raise AssertionError(
            "teste tentou acessar a rede. Use um dublê em vez da API real."
        )

    monkeypatch.setattr("urllib.request.urlopen", recusar)


@pytest.fixture
def config():
    """Config do projeto, com as credenciais reais neutralizadas."""
    cfg = load_config()
    object.__setattr__(cfg.telegram, "enabled", False)
    object.__setattr__(cfg.telegram, "token", None)
    object.__setattr__(cfg.telegram, "allowed_chat_ids", ())
    object.__setattr__(cfg, "notify_channels", ("console",))
    object.__setattr__(cfg.llm, "api_key", "sk-test")
    return cfg


@pytest.fixture
def ctx(tmp_path, config):
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    return ToolContext(config=config, conn=conn, actor="test")


@pytest.fixture
def registry():
    return tool_registry


@pytest.fixture
def config_fake(config):
    """Config com um canal de notificação inválido, para testar o fallback."""
    object.__setattr__(config, "notify_channels", ("console", "xpto"))
    return config
