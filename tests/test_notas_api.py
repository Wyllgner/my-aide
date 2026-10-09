"""As rotas que escrevem no vault pela página."""

import json

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from aide.storage import connect, migrate
from aide.web import criar_app

LOCAL = "http://127.0.0.1:8787"
DA_PAGINA = {"origin": LOCAL, "x-aide": "1", "sec-fetch-site": "same-origin"}


@pytest.fixture
def app(config, tmp_path):
    object.__setattr__(config, "vault_dir", tmp_path / "vault")
    (tmp_path / "vault" / "Inbox").mkdir(parents=True)
    (tmp_path / "vault" / "Inbox" / "Nota.md").write_text("---\ntitle: Nota\n---\n\noi\n")

    def conn_factory():
        conn = connect(tmp_path / "w.db")
        migrate(conn)
        return conn

    return criar_app(config, conn_factory)


@pytest.fixture
def cliente(app):
    return TestClient(app, base_url=LOCAL, headers=DA_PAGINA)


@pytest.fixture
def vault_dir(app):
    from pathlib import Path

    return Path(app.state.config.vault_dir)


def _abrir(cliente, caminho="Inbox/Nota.md"):
    resposta = cliente.get("/api/notas/arquivo", params={"caminho": caminho})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _salvar(cliente, texto, versao, caminho="Inbox/Nota.md"):
    return cliente.put("/api/notas/arquivo",
                       json={"caminho": caminho, "texto": texto, "versao": versao})


def _trilha(app):
    return app.state.conn_factory().execute(
        "SELECT actor, tool, args_json FROM audit ORDER BY id").fetchall()


# ---------- abrir e salvar ----------

def test_abrir_devolve_o_arquivo_inteiro(cliente):
    nota = _abrir(cliente)
    assert nota["texto"] == "---\ntitle: Nota\n---\n\noi\n"
    assert nota["versao"]


def test_salvar_grava_e_devolve_a_versao_nova(cliente, vault_dir):
    nota = _abrir(cliente)
    resposta = _salvar(cliente, "novo texto", nota["versao"])
    assert resposta.status_code == 200
    assert (vault_dir / "Inbox" / "Nota.md").read_text() == "novo texto"
    assert resposta.json()["versao"] == _abrir(cliente)["versao"]


def test_salvar_por_cima_de_mudanca_de_fora_e_conflito(cliente, vault_dir):
    """O assessor fez um append enquanto a nota estava aberta."""
    import os

    nota = _abrir(cliente)
    arquivo = vault_dir / "Inbox" / "Nota.md"
    arquivo.write_text(arquivo.read_text() + "\nescrito pelo assessor\n")
    os.utime(arquivo, ns=(arquivo.stat().st_mtime_ns + 10**9,) * 2)

    resposta = _salvar(cliente, "o que eu digitei", nota["versao"])
    assert resposta.status_code == 409
    assert "escrito pelo assessor" in resposta.json()["texto"]
    assert "escrito pelo assessor" in arquivo.read_text()


def test_salvar_devolve_a_previa(cliente):
    resposta = _salvar(cliente, "# Novo\n\n**forte**", _abrir(cliente)["versao"])
    assert '<h1 id="s-novo">Novo</h1>' in resposta.json()["html"]
    assert "<strong>forte</strong>" in resposta.json()["html"]


def test_conflito_devolve_a_previa_do_disco(cliente, vault_dir):
    import os

    nota = _abrir(cliente)
    arquivo = vault_dir / "Inbox" / "Nota.md"
    arquivo.write_text("# Do disco")
    os.utime(arquivo, ns=(arquivo.stat().st_mtime_ns + 10**9,) * 2)
    assert "Do disco</h1>" in _salvar(cliente, "meu", nota["versao"]).json()["html"]


def test_salvar_entra_na_busca(cliente, app):
    from aide.storage.search import buscar_texto

    _salvar(cliente, "palavrarara", _abrir(cliente)["versao"])
    assert buscar_texto(app.state.conn_factory(), "palavrarara")


def test_salvar_com_private_marca_a_nota(cliente, app):
    _salvar(cliente, "---\nprivate: true\n---\n\nSEGREDO", _abrir(cliente)["versao"])
    assert app.state.conn_factory().execute(
        "SELECT private FROM notes").fetchone()[0] == 1


def test_salvar_nota_que_sumiu(cliente, vault_dir):
    versao = _abrir(cliente)["versao"]
    (vault_dir / "Inbox" / "Nota.md").unlink()
    assert _salvar(cliente, "x", versao).status_code == 404


def test_nota_grande_demais_e_recusada(cliente):
    resposta = _salvar(cliente, "x" * (2 * 1024 * 1024 + 1), _abrir(cliente)["versao"])
    assert resposta.status_code == 413


def test_abrir_o_que_nao_existe(cliente):
    resposta = cliente.get("/api/notas/arquivo", params={"caminho": "Inbox/Nada.md"})
    assert resposta.status_code == 404


# ---------- criar e apagar ----------

def test_criar_nota_em_pasta_nova(cliente, vault_dir):
    resposta = cliente.post("/api/notas/arquivo", json={"caminho": "Projetos/Reunião.md"})
    assert resposta.status_code == 201
    assert (vault_dir / "Projetos" / "Reunião.md").read_text() == ""


def test_criar_nao_sobrescreve(cliente, vault_dir):
    resposta = cliente.post("/api/notas/arquivo", json={"caminho": "Inbox/Nota.md"})
    assert resposta.status_code == 409
    assert "oi" in (vault_dir / "Inbox" / "Nota.md").read_text()


def test_criar_pasta(cliente, vault_dir):
    assert cliente.post("/api/notas/pasta", json={"caminho": "Projetos/Casa"}).status_code == 201
    assert (vault_dir / "Projetos" / "Casa").is_dir()
    assert cliente.post("/api/notas/pasta", json={"caminho": "Projetos/Casa"}).status_code == 409


def test_apagar_manda_para_a_lixeira_e_tira_da_busca(cliente, app, vault_dir):
    from aide.storage.search import buscar_texto

    _salvar(cliente, "palavrarara", _abrir(cliente)["versao"])
    resposta = cliente.delete("/api/notas/arquivo", params={"caminho": "Inbox/Nota.md"})
    assert resposta.status_code == 200
    assert not (vault_dir / "Inbox" / "Nota.md").exists()
    assert (vault_dir / ".trash" / "Nota.md").read_text() == "palavrarara"
    assert buscar_texto(app.state.conn_factory(), "palavrarara") == []


# ---------- caminho ----------

FORA = ["../fora.md", "/etc/passwd", ".trash/Nota.md", "Inbox/../../fora.md",
        "Inbox\\Nota.md", ".obsidian/workspace.md"]


@pytest.mark.parametrize("caminho", FORA)
def test_nenhuma_rota_sai_do_vault(cliente, tmp_path, caminho):
    assert cliente.get("/api/notas/arquivo", params={"caminho": caminho}).status_code == 400
    assert cliente.put("/api/notas/arquivo", json={"caminho": caminho, "texto": "x",
                                                    "versao": "0"}).status_code == 400
    assert cliente.post("/api/notas/arquivo", json={"caminho": caminho}).status_code == 400
    assert cliente.post("/api/notas/pasta", json={"caminho": caminho}).status_code == 400
    assert cliente.delete("/api/notas/arquivo", params={"caminho": caminho}).status_code == 400
    assert not (tmp_path / "fora.md").exists()


def test_so_arquivo_md_e_nota(cliente, vault_dir):
    """Senão "salvar nota" gravaria um .sh ou um .bashrc dentro do vault."""
    assert cliente.post("/api/notas/arquivo", json={"caminho": "rodar.sh"}).status_code == 400
    assert not (vault_dir / "rodar.sh").exists()


def test_link_simbolico_para_fora_nao_e_seguido(cliente, vault_dir, tmp_path):
    segredo = tmp_path / "segredo.md"
    segredo.write_text("SENHA")
    (vault_dir / "Inbox" / "atalho.md").symlink_to(segredo)
    resposta = cliente.get("/api/notas/arquivo", params={"caminho": "Inbox/atalho.md"})
    assert resposta.status_code == 400
    assert "SENHA" not in resposta.text


# ---------- a fronteira ----------

@pytest.mark.parametrize("cabecalhos", [
    {},
    {"origin": "http://evil.example", "x-aide": "1"},
    {"origin": LOCAL},
    {"origin": LOCAL, "x-aide": "1", "sec-fetch-site": "cross-site"},
])
def test_escrita_de_fora_da_pagina_nao_toca_no_disco(app, vault_dir, cabecalhos):
    cliente = TestClient(app, base_url=LOCAL)
    antes = (vault_dir / "Inbox" / "Nota.md").read_text()
    versao = cliente.get("/api/notas/arquivo", params={"caminho": "Inbox/Nota.md"}).json()["versao"]
    respostas = [
        cliente.put("/api/notas/arquivo", headers=cabecalhos,
                    json={"caminho": "Inbox/Nota.md", "texto": "invadido", "versao": versao}),
        cliente.post("/api/notas/arquivo", headers=cabecalhos, json={"caminho": "Invasor.md"}),
        cliente.post("/api/notas/pasta", headers=cabecalhos, json={"caminho": "Invasor"}),
        cliente.delete("/api/notas/arquivo", headers=cabecalhos,
                       params={"caminho": "Inbox/Nota.md"}),
    ]
    assert all(r.status_code == 403 for r in respostas)
    assert (vault_dir / "Inbox" / "Nota.md").read_text() == antes
    assert not (vault_dir / "Invasor.md").exists()
    assert not (vault_dir / "Invasor").exists()


def test_formulario_de_outro_site_nao_salva(app, vault_dir):
    """O ataque clássico: <form method=post> com texto simples, sem JSON."""
    cliente = TestClient(app, base_url=LOCAL)
    resposta = cliente.post("/api/notas/arquivo", data={"caminho": "Invasor.md"},
                            headers={"origin": "http://evil.example"})
    assert resposta.status_code == 403
    assert not (vault_dir / "Invasor.md").exists()


def test_leitura_por_outro_host_e_recusada(app):
    resposta = TestClient(app, base_url="http://evil.example").get(
        "/api/notas/arquivo", params={"caminho": "Inbox/Nota.md"})
    assert resposta.status_code == 421
    assert "oi" not in resposta.text


# ---------- auditoria ----------

def test_toda_escrita_fica_na_trilha_sem_o_texto(cliente, app):
    _salvar(cliente, "SEGREDO", _abrir(cliente)["versao"])
    cliente.post("/api/notas/arquivo", json={"caminho": "Outra.md"})
    cliente.post("/api/notas/pasta", json={"caminho": "Pasta"})
    cliente.delete("/api/notas/arquivo", params={"caminho": "Outra.md"})
    trilha = _trilha(app)
    assert [r["tool"] for r in trilha] == ["notas.salvar", "notas.criar",
                                          "notas.criar_pasta", "notas.apagar"]
    assert all(r["actor"] == "web" for r in trilha)
    assert json.loads(trilha[0]["args_json"]) == {"caminho": "Inbox/Nota.md"}
    assert not any("SEGREDO" in (r["args_json"] or "") for r in trilha)


def test_abrir_nao_entra_na_trilha(cliente, app):
    _abrir(cliente)
    assert _trilha(app) == []


def test_abrir_nota_enorme_e_recusado(cliente, vault_dir):
    (vault_dir / "Inbox" / "Export.md").write_text("x" * (2 * 1024 * 1024 + 1))
    resposta = cliente.get("/api/notas/arquivo", params={"caminho": "Inbox/Export.md"})
    assert resposta.status_code == 413


# ---------- mover ----------

def _mover(cliente, de, para):
    return cliente.post("/api/notas/mover", json={"de": de, "para": para})


def test_mover_nota(cliente, vault_dir):
    resposta = _mover(cliente, "Inbox/Nota.md", "Projetos/Renomeada.md")
    assert resposta.status_code == 200
    assert resposta.json()["caminho"] == "Projetos/Renomeada.md"
    assert (vault_dir / "Projetos" / "Renomeada.md").exists()
    assert not (vault_dir / "Inbox" / "Nota.md").exists()


def test_mover_para_nome_que_existe_e_conflito(cliente, vault_dir):
    (vault_dir / "Outra.md").write_text("fica")
    assert _mover(cliente, "Inbox/Nota.md", "Outra.md").status_code == 409
    assert (vault_dir / "Outra.md").read_text() == "fica"


def test_mover_o_que_nao_existe(cliente):
    assert _mover(cliente, "Inbox/Nada.md", "X.md").status_code == 404


@pytest.mark.parametrize("de, para", [
    ("Inbox/Nota.md", "../fora.md"), ("Inbox/Nota.md", ".trash/x.md"),
    ("../../etc/passwd", "x.md"), ("Inbox/Nota.md", "x.sh"),
])
def test_mover_nao_sai_do_vault(cliente, tmp_path, de, para):
    assert _mover(cliente, de, para).status_code == 400
    assert not (tmp_path / "fora.md").exists()


def test_mover_fica_na_trilha(cliente, app):
    _mover(cliente, "Inbox/Nota.md", "Nova.md")
    trilha = _trilha(app)
    assert trilha[-1]["tool"] == "notas.mover"
    assert json.loads(trilha[-1]["args_json"]) == {"caminho": "Inbox/Nota.md → Nova.md",
                                                  "links_atualizados": []}


def test_a_trilha_diz_quais_notas_o_mover_reescreveu(cliente, app, vault_dir):
    (vault_dir / "Quem aponta.md").write_text("[[Nota]]")
    _mover(cliente, "Inbox/Nota.md", "Nova.md")
    assert json.loads(_trilha(app)[-1]["args_json"])["links_atualizados"] == ["Quem aponta.md"]


def test_mover_de_outra_origem_e_recusado(app, vault_dir):
    resposta = TestClient(app, base_url=LOCAL).post(
        "/api/notas/mover", json={"de": "Inbox/Nota.md", "para": "X.md"},
        headers={"origin": "http://evil.example", "x-aide": "1"})
    assert resposta.status_code == 403
    assert (vault_dir / "Inbox" / "Nota.md").exists()


def test_mover_atualiza_os_links_e_o_indice_de_quem_apontava(cliente, app, vault_dir):
    from aide.storage.search import buscar_texto

    (vault_dir / "Quem aponta.md").write_text("ver a [[Nota]]")
    resposta = _mover(cliente, "Inbox/Nota.md", "Inbox/Renomeada.md")
    assert resposta.json()["links_atualizados"] == ["Quem aponta.md"]
    assert (vault_dir / "Quem aponta.md").read_text() == "ver a [[Renomeada]]"
    assert buscar_texto(app.state.conn_factory(), "Renomeada")


# ---------- mover pasta ----------

def _mover_pasta(cliente, de, para):
    return cliente.post("/api/notas/mover-pasta", json={"de": de, "para": para})


def test_mover_pasta_leva_as_notas_e_o_indice(cliente, app, vault_dir):
    _salvar(cliente, "conteúdo", _abrir(cliente)["versao"])  # põe a nota no banco
    resposta = _mover_pasta(cliente, "Inbox", "Entrada")
    assert resposta.status_code == 200
    assert resposta.json()["notas_movidas"] == {"Inbox/Nota.md": "Entrada/Nota.md"}
    caminhos = [r[0] for r in app.state.conn_factory().execute("SELECT path FROM notes")]
    assert caminhos == [str(vault_dir / "Entrada" / "Nota.md")]
    assert (vault_dir / "Entrada" / "Nota.md").exists()


@pytest.mark.parametrize("de, para, codigo", [
    ("Inbox", "../fora", 400), (".trash", "Lixo", 400), ("Inbox", ".obsidian", 400),
    ("Nada", "Outra", 404), ("Inbox", "Inbox/Dentro", 400),
])
def test_mover_pasta_recusa(cliente, tmp_path, de, para, codigo):
    assert _mover_pasta(cliente, de, para).status_code == codigo
    assert not (tmp_path / "fora").exists()


def test_mover_pasta_por_cima_de_outra_e_conflito(cliente, vault_dir):
    (vault_dir / "Outra").mkdir()
    assert _mover_pasta(cliente, "Inbox", "Outra").status_code == 409
    assert (vault_dir / "Inbox" / "Nota.md").exists()


def test_mover_pasta_fica_na_trilha(cliente, app):
    _mover_pasta(cliente, "Inbox", "Entrada")
    assert _trilha(app)[-1]["tool"] == "notas.mover_pasta"


# ---------- apagar pasta ----------

def test_apagar_pasta_leva_tudo_para_a_lixeira(cliente, app, vault_dir):
    from aide.storage.search import buscar_texto

    _salvar(cliente, "palavrarara", _abrir(cliente)["versao"])
    (vault_dir / "Inbox" / "Sub").mkdir()
    (vault_dir / "Inbox" / "Sub" / "Outra.md").write_text("x")
    resposta = cliente.delete("/api/notas/pasta", params={"caminho": "Inbox"})
    assert resposta.status_code == 200
    assert resposta.json()["notas"] == 2
    assert not (vault_dir / "Inbox").exists()
    assert (vault_dir / ".trash" / "Inbox" / "Sub" / "Outra.md").exists()
    assert buscar_texto(app.state.conn_factory(), "palavrarara") == []


def test_apagar_pasta_com_o_mesmo_nome_de_uma_na_lixeira(cliente, vault_dir):
    (vault_dir / ".trash" / "Inbox").mkdir(parents=True)
    assert cliente.delete("/api/notas/pasta", params={"caminho": "Inbox"}).status_code == 200
    assert (vault_dir / ".trash" / "Inbox-2" / "Nota.md").exists()


@pytest.mark.parametrize("caminho, codigo", [
    (".trash", 400), ("../", 400), ("Nada", 404), ("Inbox/Nota.md", 404),
])
def test_apagar_pasta_recusa(cliente, vault_dir, caminho, codigo):
    assert cliente.delete("/api/notas/pasta", params={"caminho": caminho}).status_code == codigo
    assert (vault_dir / "Inbox" / "Nota.md").exists()


def test_apagar_pasta_fica_na_trilha(cliente, app):
    cliente.delete("/api/notas/pasta", params={"caminho": "Inbox"})
    trilha = _trilha(app)[-1]
    assert trilha["tool"] == "notas.apagar_pasta"
    assert json.loads(trilha["args_json"]) == {"caminho": "Inbox", "notas": 1}


def test_apagar_pasta_de_outra_origem_e_recusado(app, vault_dir):
    resposta = TestClient(app, base_url=LOCAL).delete(
        "/api/notas/pasta", params={"caminho": "Inbox"},
        headers={"origin": "http://evil.example", "x-aide": "1"})
    assert resposta.status_code == 403
    assert (vault_dir / "Inbox").exists()
