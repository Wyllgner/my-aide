"""Gasto recorrente: um cadastro que vira um lançamento comum por mês."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from aide.tools import expenses, recorrentes
from aide.tools.registry import ToolContext

FUSO = ZoneInfo("America/Porto_Velho")


@pytest.fixture
def em_novembro(monkeypatch):
    def no_dia(ano=2026, mes=11, dia=4):
        quando = datetime(ano, mes, dia, 10, 0, tzinfo=FUSO)
        monkeypatch.setattr(expenses, "now_in", lambda _fuso: quando)
        monkeypatch.setattr(recorrentes, "now_in", lambda _fuso: quando)
        return quando
    no_dia()
    return no_dia


def _claude(ctx, registry, **extra):
    args = {"amount": "110", "description": "claude", "day": 5, "category": "pessoal", **extra}
    return registry.call("expenses.add_recurring", args, ctx)


def _meses(ctx):
    return [r[0] for r in ctx.conn.execute(
        "SELECT substr(spent_at, 1, 10) FROM expenses WHERE deleted_at IS NULL"
        " ORDER BY spent_at").fetchall()]


def test_lanca_um_gasto_por_mes_ate_o_horizonte(ctx, registry, em_novembro):
    feito = _claude(ctx, registry).data
    assert feito["valor"] == "R$ 110,00"
    assert feito["proxima"].startswith("2026-11-05")
    meses = _meses(ctx)
    assert len(meses) == recorrentes.HORIZONTE_MESES
    assert meses[0] == "2026-11-05" and meses[-1] == "2027-10-05"


def test_cada_lancamento_conta_no_mes_em_que_cai(ctx, registry, em_novembro):
    object.__setattr__(ctx.config.gastos, "tetos_centavos", {"pessoal": 50000})
    _claude(ctx, registry)
    novembro = registry.call("expenses.budgets", {}, ctx).data["tetos"][0]
    assert novembro["gasto"] == "R$ 0,00" and novembro["a_cair"] == "R$ 110,00"
    assert novembro["sobra"] == "R$ 390,00"
    dezembro = registry.call("expenses.budgets", {"month": "2026-12"}, ctx).data["tetos"][0]
    assert dezembro["gasto"] == "R$ 110,00"


def test_dia_31_cai_no_ultimo_dia_do_mes_curto(ctx, registry, em_novembro):
    _claude(ctx, registry, day=31)
    assert "2026-11-30" in _meses(ctx)
    assert "2027-02-28" in _meses(ctx)


def test_gerar_de_novo_nao_duplica(ctx, registry, em_novembro):
    quando = em_novembro()
    _claude(ctx, registry)
    assert recorrentes.lancar_recorrentes(ctx.conn, quando) == 0
    assert len(_meses(ctx)) == recorrentes.HORIZONTE_MESES


def test_virada_do_mes_estende_o_horizonte(ctx, registry, em_novembro):
    _claude(ctx, registry)
    assert recorrentes.lancar_recorrentes(ctx.conn, em_novembro(2026, 12, 1)) == 1
    assert _meses(ctx)[-1] == "2027-11-05"


def test_mes_apagado_nao_volta_e_o_resto_continua(ctx, registry, em_novembro):
    quando = em_novembro()
    _claude(ctx, registry)
    dezembro = ctx.conn.execute(
        "SELECT id FROM expenses WHERE recurring_month = '2026-12'").fetchone()[0]
    assert registry.call("expenses.delete", {"id": dezembro}, ctx).ok
    assert recorrentes.lancar_recorrentes(ctx.conn, quando) == 0
    meses = _meses(ctx)
    assert "2026-12-05" not in meses and "2027-01-05" in meses


def test_apagar_um_mes_avisa_que_a_recorrencia_continua(ctx, registry, em_novembro):
    feito = _claude(ctx, registry).data
    dezembro = ctx.conn.execute(
        "SELECT id FROM expenses WHERE recurring_month = '2026-12'").fetchone()[0]
    aviso = registry.call("expenses.delete", {"id": dezembro}, ctx).data["aviso"]
    assert "continua" in aviso and str(feito["id"]) in aviso


def test_job_estende_o_horizonte(ctx, registry, config, em_novembro, monkeypatch):
    from aide.core import context
    from aide.scheduler.jobs import JobDeps, lancar_recorrentes

    _claude(ctx, registry)
    virada = datetime(2026, 12, 1, 10, 0, tzinfo=FUSO)
    monkeypatch.setattr(context, "now_in", lambda _fuso: virada)
    deps = JobDeps(config=config, llm=None, notifier=None, conn=ctx.conn)
    assert lancar_recorrentes(deps) == 1
    assert lancar_recorrentes(deps) == 0


def test_cancelar_tira_o_futuro_e_guarda_o_que_caiu(ctx, registry, em_novembro):
    feito = _claude(ctx, registry).data
    quando = em_novembro(2026, 12, 20)
    cancelado = registry.call("expenses.cancel_recurring", {"id": feito["id"]}, ctx).data
    assert cancelado["meses_removidos"] == recorrentes.HORIZONTE_MESES - 2
    assert _meses(ctx) == ["2026-11-05", "2026-12-05"]
    assert recorrentes.lancar_recorrentes(ctx.conn, quando) == 0
    assert registry.call("expenses.recurring", {}, ctx).data == []


def test_cancelar_de_verdade_pede_confirmacao(registry):
    assert registry.get("expenses.cancel_recurring").safety == "confirm"


@pytest.mark.parametrize("dia", [0, 32, "x"])
def test_recusa_dia_que_nao_existe(ctx, registry, em_novembro, dia):
    assert "dia" in _claude(ctx, registry, day=dia).error
    assert _meses(ctx) == []


def test_exige_o_dia(ctx, registry, em_novembro):
    resposta = registry.call("expenses.add_recurring",
                             {"amount": "110", "description": "claude"}, ctx)
    assert "day" in resposta.error


def test_recusa_comecar_num_mes_passado(ctx, registry, em_novembro):
    assert "passado" in _claude(ctx, registry, start_month="2026-10").error


def test_comeca_no_mes_seguinte_quando_o_deste_ja_foi_lancado(ctx, registry, em_novembro):
    _claude(ctx, registry, start_month="2026-12")
    assert _meses(ctx)[0] == "2026-12-05"


def test_recusa_a_mesma_recorrencia_duas_vezes(ctx, registry, em_novembro):
    _claude(ctx, registry)
    assert "já existe" in _claude(ctx, registry, description="Claude").error
    assert len(_meses(ctx)) == recorrentes.HORIZONTE_MESES


def test_lancamento_segue_forma_categoria_e_tag(ctx, registry, em_novembro):
    _claude(ctx, registry, method="credito", tag="claude")
    gasto = registry.call("expenses.list", {"periodo": "2026-12"}, ctx).data[0]
    assert (gasto["method"], gasto["category"], gasto["tag"]) == ("credito", "pessoal", "claude")


def test_privado_nao_aparece_para_quem_nao_ve(ctx, registry, config, em_novembro):
    feito = _claude(ctx, registry, private=True).data
    outro = ToolContext(config=config, conn=ctx.conn, ver_privado=False)
    assert registry.call("expenses.recurring", {}, outro).data == []
    assert "privado" in registry.call("expenses.cancel_recurring",
                                      {"id": feito["id"]}, outro).error
    assert registry.call("expenses.list", {"periodo": "2026-12"}, outro).data == []
