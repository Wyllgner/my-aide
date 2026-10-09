"""O histórico de em que dias cada nota foi mexida."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from aide.storage import atividade, connect, migrate

FUSO = ZoneInfo("America/Porto_Velho")


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "a.db")
    migrate(c)
    return c


@pytest.fixture
def raiz(tmp_path):
    pasta = tmp_path / "vault"
    (pasta / "Inbox").mkdir(parents=True)
    (pasta / "Inbox" / "Nota.md").write_text("x")
    return pasta


def _linhas(conn):
    return [tuple(r) for r in conn.execute(
        "SELECT caminho, dia, vezes FROM note_activity ORDER BY dia, caminho")]


def test_uma_linha_por_nota_por_dia(conn, raiz):
    """O salvamento automático grava a cada pausa; o banco guarda o dia."""
    dia = datetime(2026, 10, 1, 9, tzinfo=FUSO)
    for minuto in range(5):
        atividade.registrar(conn, raiz, raiz / "Inbox" / "Nota.md",
                            dia + timedelta(minutes=minuto), "pagina")
    atividade.registrar(conn, raiz, raiz / "Inbox" / "Nota.md", dia + timedelta(days=1), "pagina")
    assert _linhas(conn) == [("Inbox/Nota.md", "2026-10-01", 5), ("Inbox/Nota.md", "2026-10-02", 1)]


def test_arquivo_fora_do_vault_nao_e_registrado(conn, raiz, tmp_path):
    atividade.registrar(conn, raiz, tmp_path / "fora.md", datetime.now(FUSO), "pagina")
    assert _linhas(conn) == []


def test_mover_leva_o_historico_e_soma_no_mesmo_dia(conn, raiz):
    dia = datetime(2026, 10, 1, 9, tzinfo=FUSO)
    atividade.registrar(conn, raiz, raiz / "Inbox" / "Nota.md", dia, "pagina")
    (raiz / "Nova.md").write_text("x")
    atividade.registrar(conn, raiz, raiz / "Nova.md", dia, "pagina")
    atividade.mover(conn, "Inbox/Nota.md", "Nova.md")
    assert _linhas(conn) == [("Nova.md", "2026-10-01", 2)]


def test_por_dia_desde(conn, raiz):
    for d in (1, 5, 9):
        atividade.registrar(conn, raiz, raiz / "Inbox" / "Nota.md",
                            datetime(2026, 10, d, 9, tzinfo=FUSO), "assessor")
    assert atividade.por_dia(conn, date(2026, 10, 5)) == {("Inbox/Nota.md", "2026-10-05"),
                                                         ("Inbox/Nota.md", "2026-10-09")}


def test_painel_conta_dias_passados_que_o_mtime_perdeu(conn, raiz):
    """A nota foi mexida dia 2 e hoje: o mtime só sabe de hoje."""
    from aide.web import visao

    agora = datetime(2026, 10, 8, 12, tzinfo=FUSO)
    atividade.registrar(conn, raiz, raiz / "Inbox" / "Nota.md", datetime(2026, 10, 2, 9, tzinfo=FUSO),
                        "pagina")
    v = visao.montar(raiz, agora, dias=10, conn=conn)
    por_dia = dict(v.atividade)
    assert por_dia["2026-10-02"] == 1


def test_assessor_e_pagina_registram(ctx, registry, tmp_path):
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    nota = registry.call("notes.create", {"title": "Obra", "body": "x"}, ctx).data
    registry.call("notes.append", {"id": nota["id"], "body": "y"}, ctx)
    linhas = list(ctx.conn.execute("SELECT caminho, vezes, origem FROM note_activity"))
    assert [tuple(r) for r in linhas] == [("Inbox/Obra.md", 2, "assessor")]


def test_reconciliacao_registra_o_que_mudou_por_fora(conn, raiz):
    from aide.storage.reconciliacao import reconciliar

    reconciliar(conn, raiz)
    assert [r[0] for r in _linhas(conn)] == ["Inbox/Nota.md"]
    assert conn.execute("SELECT origem FROM note_activity").fetchone()[0] == "fora"
