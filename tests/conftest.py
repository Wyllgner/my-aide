import pytest

from aide.config import load_config
from aide.storage import connect, migrate
from aide.tools import registry as tool_registry
from aide.tools.registry import ToolContext


@pytest.fixture
def ctx(tmp_path):
    config = load_config()
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    return ToolContext(config=config, conn=conn, actor="test")


@pytest.fixture
def registry():
    return tool_registry


@pytest.fixture
def config_fake(tmp_path):
    from aide.config import load_config

    config = load_config()
    object.__setattr__(config, "notify_channels", ("console", "xpto"))
    return config
