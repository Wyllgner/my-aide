from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aide.scheduler import rules

TZ = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 9, 3, 10, 0, tzinfo=TZ)


def _achados(conn, nome):
    return [f for f in rules.evaluate(conn, AGORA) if f.rule == nome]


def test_atrasada_e_encontrada(ctx, registry):
    registry.call("tasks.create", {"title": "Boleto", "due": "2026-08-30T09:00"}, ctx)
    achados = _achados(ctx.conn, "atrasadas")
    assert len(achados) == 1
    assert "venceu há 4 dia" in achados[0].summary


def test_tarefa_no_prazo_nao_aparece(ctx, registry):
    registry.call("tasks.create", {"title": "Futuro", "due": "2026-09-30T09:00"}, ctx)
    assert _achados(ctx.conn, "atrasadas") == []


def test_concluida_nao_e_cobrada(ctx, registry):
    task = registry.call("tasks.create", {"title": "X", "due": "2026-08-01T09:00"}, ctx).data
    registry.call("tasks.complete", {"id": task["id"]}, ctx)
    assert _achados(ctx.conn, "atrasadas") == []


def test_tres_adiamentos_viram_pergunta(ctx, registry):
    task = registry.call("tasks.create", {"title": "Dentista", "due": "2026-09-10T09:00"}, ctx).data
    for _ in range(2):
        registry.call("tasks.snooze", {"id": task["id"], "until": "2026-09-20T09:00"}, ctx)
    assert _achados(ctx.conn, "adiada_demais") == []

    registry.call("tasks.snooze", {"id": task["id"], "until": "2026-09-25T09:00"}, ctx)
    achados = _achados(ctx.conn, "adiada_demais")
    assert len(achados) == 1
    assert "ainda importa" in achados[0].summary
    assert achados[0].severity == 1


def test_projeto_parado(ctx, registry):
    registry.call("tasks.create", {"title": "X", "project": "abandonado"}, ctx)
    antigo = (AGORA - timedelta(days=20)).isoformat(timespec="minutes")
    ctx.conn.execute("UPDATE tasks SET last_touched_at = ?, created_at = ?", (antigo, antigo))
    achados = _achados(ctx.conn, "projeto_parado")
    assert len(achados) == 1 and "abandonado" in achados[0].summary


def test_projeto_ativo_nao_aparece(ctx, registry):
    registry.call("tasks.create", {"title": "X", "project": "vivo"}, ctx)
    assert _achados(ctx.conn, "projeto_parado") == []


def test_zumbi_precisa_ser_antiga_e_sem_prazo(ctx, registry):
    registry.call("tasks.create", {"title": "Velha"}, ctx)
    registry.call("tasks.create", {"title": "Com prazo", "due": "2026-12-01T09:00"}, ctx)
    antigo = (AGORA - timedelta(days=40)).isoformat(timespec="minutes")
    ctx.conn.execute("UPDATE tasks SET created_at = ?, last_touched_at = ?", (antigo, antigo))
    achados = _achados(ctx.conn, "zumbi")
    assert [f.refs[0] for f in achados] == [1]


def test_contato_atrasado(ctx):
    antigo = (AGORA - timedelta(days=30)).isoformat(timespec="minutes")
    ctx.conn.execute(
        "INSERT INTO people (name, last_contact_at, cadence_days) VALUES (?, ?, ?)",
        ("Fulano", antigo, 21),
    )
    achados = _achados(ctx.conn, "contato_atrasado")
    assert len(achados) == 1 and "Fulano" in achados[0].summary


def test_contato_em_dia_nao_aparece(ctx):
    recente = (AGORA - timedelta(days=2)).isoformat(timespec="minutes")
    ctx.conn.execute(
        "INSERT INTO people (name, last_contact_at, cadence_days) VALUES (?, ?, ?)",
        ("Ciclano", recente, 21),
    )
    assert _achados(ctx.conn, "contato_atrasado") == []


def test_banco_vazio_nao_gera_ruido(ctx):
    assert rules.evaluate(ctx.conn, AGORA) == []


def test_regra_quebrada_nao_derruba_as_outras(ctx, registry, monkeypatch):
    registry.call("tasks.create", {"title": "Boleto", "due": "2026-08-30T09:00"}, ctx)

    def explode(conn, now, config=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(rules, "_RULES", [("quebrada", explode), *rules._RULES])
    achados = rules.evaluate(ctx.conn, AGORA)
    assert any(f.rule == "atrasadas" for f in achados)


def test_ordena_por_severidade(ctx, registry):
    registry.call("tasks.create", {"title": "Velha"}, ctx)
    antigo = (AGORA - timedelta(days=40)).isoformat(timespec="minutes")
    ctx.conn.execute("UPDATE tasks SET created_at = ?, last_touched_at = ?", (antigo, antigo))
    registry.call("tasks.create", {"title": "Boleto", "due": "2026-08-25T09:00"}, ctx)
    achados = rules.evaluate(ctx.conn, AGORA)
    assert [f.severity for f in achados] == sorted(f.severity for f in achados)


def test_atraso_e_contado_em_dias_de_calendario(ctx):
    """`timedelta.days` trunca: um prazo de anteontem à noite dizia "há 1 dia",
    enquanto a tabela de tarefas dizia "há 2 dias" sobre a mesma linha."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("America/Porto_Velho")
    agora = datetime(2026, 9, 21, 8, 0, tzinfo=tz)
    anteontem = (agora - timedelta(days=2)).replace(hour=23, minute=0)
    ctx.conn.execute("INSERT INTO tasks (title, status, due_at) VALUES (?, 'open', ?)",
                     ("prazo da noite", anteontem.isoformat(timespec="minutes")))

    achado = rules.evaluate(ctx.conn, agora, only=["atrasadas"])[0]
    assert "venceu há 2 dias" in achado.summary


def test_atraso_de_um_dia_se_escreve_ontem(ctx):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("America/Porto_Velho")
    agora = datetime(2026, 9, 21, 8, 0, tzinfo=tz)
    ctx.conn.execute("INSERT INTO tasks (title, status, due_at) VALUES (?, 'open', ?)",
                     ("de ontem", "2026-09-20T09:00-04:00"))

    achado = rules.evaluate(ctx.conn, agora, only=["atrasadas"])[0]
    assert "venceu ontem" in achado.summary
    assert "dia(s)" not in achado.summary


def test_prazo_gravado_em_outro_fuso_e_convertido(ctx):
    """Seis prazos no banco foram gravados com −03; `replace(tzinfo=)` os movia."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("America/Porto_Velho")
    # 21/09 00:30 em São Paulo é ainda 20/09 às 23:30 aqui
    agora = datetime(2026, 9, 21, 8, 0, tzinfo=tz)
    ctx.conn.execute("INSERT INTO tasks (title, status, due_at) VALUES (?, 'open', ?)",
                     ("virada do dia", "2026-09-21T00:30-03:00"))

    achado = rules.evaluate(ctx.conn, agora, only=["atrasadas"])[0]
    assert "venceu ontem" in achado.summary


# ---------- dinheiro ----------

def _gasto(ctx, cents, descricao="algo", categoria=None, dias_atras=0, privado=0):
    from datetime import timedelta

    from aide.core.context import now_in

    quando = (now_in(ctx.config.timezone) - timedelta(days=dias_atras))
    ctx.conn.execute(
        "INSERT INTO expenses (cents, description, category, spent_at, private)"
        " VALUES (?, ?, ?, ?, ?)",
        (cents, descricao, categoria, quando.isoformat(timespec="minutes"), privado))


def _com_teto(ctx, **tetos):
    from aide.config import GastosConfig

    object.__setattr__(ctx.config, "gastos", GastosConfig(tetos_centavos=dict(tetos)))
    return ctx.config


def _sobre_dinheiro(ctx, regra, config=None):
    from aide.core.context import now_in

    return rules.evaluate(ctx.conn, now_in(ctx.config.timezone), only=[regra],
                          config=config or ctx.config)


def test_sem_teto_declarado_o_assessor_nao_opina(ctx):
    """Inventar um limite seria cobrar por algo que você nunca combinou."""
    _gasto(ctx, 500_00, categoria="alimentação")
    assert _sobre_dinheiro(ctx, "orcamento_categoria") == []


def test_teto_estourado_e_cobrado_com_urgencia(ctx):
    config = _com_teto(ctx, alimentação=800_00)
    _gasto(ctx, 850_00, categoria="alimentação")

    achado = _sobre_dinheiro(ctx, "orcamento_categoria", config)[0]
    assert achado.severity == 1
    assert "passou em R$ 50,00" in achado.summary


def test_teto_perto_de_estourar_avisa_antes(ctx):
    config = _com_teto(ctx, transporte=300_00)
    _gasto(ctx, 270_00, categoria="transporte")

    achado = _sobre_dinheiro(ctx, "orcamento_categoria", config)[0]
    assert achado.severity == 2
    assert "90% do teto" in achado.summary


def test_gasto_abaixo_do_aviso_nao_incomoda(ctx):
    config = _com_teto(ctx, transporte=300_00)
    _gasto(ctx, 100_00, categoria="transporte")
    assert _sobre_dinheiro(ctx, "orcamento_categoria", config) == []


def test_privado_entra_na_soma_do_teto_e_nao_no_texto(ctx):
    """Somar mantém o total verdadeiro; nomear entregaria o que a listagem esconde."""
    config = _com_teto(ctx, saúde=200_00)
    _gasto(ctx, 190_00, descricao="consulta que é só minha", categoria="saúde", privado=1)

    achado = _sobre_dinheiro(ctx, "orcamento_categoria", config)[0]
    assert "R$ 190,00" in achado.summary
    assert "só minha" not in achado.summary


def test_mes_anterior_nao_conta_no_teto_do_mes(ctx):
    config = _com_teto(ctx, alimentação=100_00)
    _gasto(ctx, 900_00, categoria="alimentação", dias_atras=40)
    assert _sobre_dinheiro(ctx, "orcamento_categoria", config) == []


# ---------- gasto atípico ----------

def test_sem_historico_nada_e_atipico(ctx):
    """Nos primeiros dias de uso todo lançamento seria fora do normal."""
    _gasto(ctx, 900_00, descricao="geladeira")
    assert _sobre_dinheiro(ctx, "gasto_atipico") == []


def test_gasto_muito_acima_do_normal_e_apontado(ctx):
    for _ in range(10):
        _gasto(ctx, 20_00, descricao="almoço", dias_atras=10)
    _gasto(ctx, 900_00, descricao="geladeira", dias_atras=1)

    achado = _sobre_dinheiro(ctx, "gasto_atipico")[0]
    assert "geladeira" in achado.summary
    assert "R$ 900,00" in achado.summary


def test_gasto_atipico_de_tres_semanas_atras_nao_e_cobrado_hoje(ctx):
    """Cobrar o que já passou não deixa nada a decidir."""
    for _ in range(10):
        _gasto(ctx, 20_00, dias_atras=30)
    _gasto(ctx, 900_00, descricao="geladeira", dias_atras=21)
    assert _sobre_dinheiro(ctx, "gasto_atipico") == []


def test_gasto_atipico_respeita_o_piso(ctx):
    """3x a mediana de gastos miúdos transformaria um café caro em cobrança."""
    for _ in range(10):
        _gasto(ctx, 3_00, descricao="café", dias_atras=10)
    _gasto(ctx, 20_00, descricao="café grande", dias_atras=1)
    assert _sobre_dinheiro(ctx, "gasto_atipico") == []


def test_gasto_privado_nunca_aparece_no_aviso(ctx):
    """Este aviso diz a descrição em voz alta, inclusive no Telegram."""
    for _ in range(10):
        _gasto(ctx, 20_00, dias_atras=10)
    _gasto(ctx, 900_00, descricao="presente surpresa", dias_atras=1, privado=1)
    assert _sobre_dinheiro(ctx, "gasto_atipico") == []
