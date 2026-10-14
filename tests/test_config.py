"""O carregamento da config avisa quando os arquivos de segredo estão abertos."""

from aide.config import load_config


def test_avisa_quando_env_ou_config_local_estao_legiveis(tmp_path, caplog):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-x\n")
    (tmp_path / "config.local.yaml").write_text("gastos: {}\n")
    (tmp_path / ".env").chmod(0o644)
    (tmp_path / "config.local.yaml").chmod(0o664)
    with caplog.at_level("WARNING"):
        load_config(tmp_path)
    assert ".env é legível por outras contas" in caplog.text
    assert "config.local.yaml é legível por outras contas" in caplog.text


def test_fechados_nao_avisam(tmp_path, caplog):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-x\n")
    (tmp_path / ".env").chmod(0o600)
    with caplog.at_level("WARNING"):
        load_config(tmp_path)
    assert "legível por outras contas" not in caplog.text
