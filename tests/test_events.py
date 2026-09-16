"""events.list e events.conflicts.

Estas duas nunca tinham rodado — nem em teste, nem na vida, porque a agenda
segue desligada. Foi escrevendo isto que apareceu o alarme falso do dia
inteiro, que a migration 005 conserta.
"""

from datetime import timedelta

import pytest

from aide.core.context import now_in


@pytest.fixture
def agora(ctx):
    return now_in(ctx.config.timezone)


def _evento(ctx, titulo, inicio, fim=None, all_day=0, source="ical"):
    ctx.conn.execute(
        "INSERT INTO events (title, start_at, end_at, source, all_day)"
        " VALUES (?, ?, ?, ?, ?)",
        (titulo, inicio.isoformat(timespec="minutes"),
         fim.isoformat(timespec="minutes") if fim else None, source, all_day),
    )


def test_lista_a_janela_pedida(ctx, registry, agora):
    _evento(ctx, "Hoje", agora + timedelta(hours=2))
    _evento(ctx, "Semana que vem", agora + timedelta(days=9))

    de_sete = registry.call("events.list", {}, ctx)
    assert [e["title"] for e in de_sete.data] == ["Hoje"]

    de_quinze = registry.call("events.list", {"dias": 15}, ctx)
    assert [e["title"] for e in de_quinze.data] == ["Hoje", "Semana que vem"]


def test_inclui_compromisso_que_ja_comecou_hoje(ctx, registry, agora):
    """A janela começa à meia-noite: reunião das 9h ainda importa às 10h."""
    cedo = agora.replace(hour=0, minute=30)
    _evento(ctx, "Cedo", cedo)
    assert [e["title"] for e in registry.call("events.list", {}, ctx).data] == ["Cedo"]


def test_ignora_evento_apagado(ctx, registry, agora):
    _evento(ctx, "Cancelado", agora + timedelta(hours=1))
    ctx.conn.execute("UPDATE events SET deleted_at = datetime('now')")
    assert registry.call("events.list", {}, ctx).data == []


def test_acha_sobreposicao(ctx, registry, agora):
    base = (agora + timedelta(days=1)).replace(hour=14, minute=0)
    _evento(ctx, "Dentista", base, base + timedelta(hours=1))
    _evento(ctx, "Reunião", base + timedelta(minutes=30), base + timedelta(hours=2))

    conflitos = registry.call("events.conflicts", {}, ctx).data
    assert len(conflitos) == 1
    assert "Dentista" in conflitos[0]["a"] and "Reunião" in conflitos[0]["b"]


def test_encostado_nao_e_conflito(ctx, registry, agora):
    """Uma reunião que começa quando a outra acaba não é sobreposição."""
    base = (agora + timedelta(days=1)).replace(hour=14, minute=0)
    _evento(ctx, "A", base, base + timedelta(hours=1))
    _evento(ctx, "B", base + timedelta(hours=1), base + timedelta(hours=2))
    assert registry.call("events.conflicts", {}, ctx).data == []


def test_sem_hora_de_fim_nao_conflita(ctx, registry, agora):
    base = (agora + timedelta(days=1)).replace(hour=14, minute=0)
    _evento(ctx, "Sem fim", base)
    _evento(ctx, "Com fim", base, base + timedelta(hours=1))
    assert registry.call("events.conflicts", {}, ctx).data == []


def test_dia_inteiro_nao_conflita_com_compromisso_do_dia(ctx, registry, agora):
    """O bug que a migration 005 fecha.

    A flag existia no parse e se perdia ao gravar, então um feriado — que vai
    de 00:00 às 00:00 do dia seguinte — se sobrepunha a tudo naquele dia.
    """
    dia = (agora + timedelta(days=2)).replace(hour=0, minute=0)
    _evento(ctx, "Feriado", dia, dia + timedelta(days=1), all_day=1)
    _evento(ctx, "Dentista", dia.replace(hour=14), dia.replace(hour=15))

    assert registry.call("events.conflicts", {}, ctx).data == []


def test_sincronizar_preserva_o_dia_inteiro(ctx, monkeypatch):
    """O caminho completo: feed -> banco -> conflitos."""
    from aide.tools import events

    feed = (
        "BEGIN:VCALENDAR\r\n"
        "BEGIN:VEVENT\r\nUID:1\r\nSUMMARY:Feriado\r\n"
        "DTSTART;VALUE=DATE:20260920\r\nDTEND;VALUE=DATE:20260921\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nUID:2\r\nSUMMARY:Consulta\r\n"
        "DTSTART:20260920T170000Z\r\nDTEND:20260920T180000Z\r\nEND:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    monkeypatch.setattr("aide.storage.ical.baixar", lambda url: feed)
    object.__setattr__(ctx.config, "calendar_url", "https://exemplo/x.ics")

    assert events.sincronizar(ctx.conn, ctx.config)["importados"] == 2
    linhas = dict(ctx.conn.execute("SELECT title, all_day FROM events").fetchall())
    assert linhas == {"Feriado": 1, "Consulta": 0}


def test_sincronizar_sem_url_explica_o_que_fazer(ctx):
    from aide.tools import events

    object.__setattr__(ctx.config, "calendar_url", None)
    with pytest.raises(ValueError, match="iCal"):
        events.sincronizar(ctx.conn, ctx.config)


def test_sincronizar_nao_apaga_evento_local(ctx, monkeypatch):
    """O feed é dono só do que veio dele."""
    from aide.tools import events

    ctx.conn.execute(
        "INSERT INTO events (title, start_at, source) VALUES ('Meu', '2026-09-20T10:00', 'local')")
    monkeypatch.setattr("aide.storage.ical.baixar",
                        lambda url: "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")
    object.__setattr__(ctx.config, "calendar_url", "https://exemplo/x.ics")

    events.sincronizar(ctx.conn, ctx.config)
    assert [r["title"] for r in ctx.conn.execute("SELECT title FROM events")] == ["Meu"]
