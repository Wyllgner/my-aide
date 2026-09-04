from datetime import datetime
from zoneinfo import ZoneInfo

from aide.storage import ical

TZ = ZoneInfo("America/Sao_Paulo")

FEED = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:abc-1
DTSTART;TZID=America/Sao_Paulo:20260910T140000
DTEND;TZID=America/Sao_Paulo:20260910T150000
SUMMARY:Reunião com o contador
LOCATION:Escritório
END:VEVENT
BEGIN:VEVENT
UID:abc-2
DTSTART:20260910T173000Z
DTEND:20260910T183000Z
SUMMARY:Chamada com cliente
END:VEVENT
BEGIN:VEVENT
UID:abc-3
DTSTART;VALUE=DATE:20260912
SUMMARY:Feriado
END:VEVENT
END:VCALENDAR
"""


def test_le_evento_com_fuso_declarado():
    eventos = ical.parse(FEED, "America/Sao_Paulo")
    primeiro = eventos[0]
    assert primeiro["title"] == "Reunião com o contador"
    assert primeiro["start_at"] == "2026-09-10T14:00-03:00"
    assert primeiro["location"] == "Escritório"


def test_converte_utc_para_o_fuso_do_usuario():
    """17:30Z é 14:30 em São Paulo; sem converter, o dia inteiro sai errado."""
    evento = next(e for e in ical.parse(FEED, "America/Sao_Paulo")
                  if e["title"] == "Chamada com cliente")
    assert evento["start_at"] == "2026-09-10T14:30-03:00"


def test_evento_de_dia_inteiro():
    evento = next(e for e in ical.parse(FEED, "America/Sao_Paulo")
                  if e["title"] == "Feriado")
    assert evento["dia_inteiro"] is True
    assert evento["start_at"].startswith("2026-09-12")


def test_ordena_por_inicio():
    eventos = ical.parse(FEED, "America/Sao_Paulo")
    assert [e["start_at"] for e in eventos] == sorted(e["start_at"] for e in eventos)


def test_linha_dobrada_e_remontada():
    """O iCal quebra linha longa continuando com espaço; sem remontar, o texto trunca."""
    feed = ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nDTSTART:20260910T140000Z\r\n"
            "SUMMARY:Reunião muito longa que o servidor\r\n  quebrou em duas\r\n"
            "END:VEVENT\r\nEND:VCALENDAR\r\n")
    assert ical.parse(feed, "UTC")[0]["title"] == "Reunião muito longa que o servidor quebrou em duas"


def test_escapes_do_ical():
    feed = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20260910T140000Z\n"
            "SUMMARY:Jantar\\, com a equipe\\nlevar notebook\nEND:VEVENT\nEND:VCALENDAR\n")
    assert ical.parse(feed, "UTC")[0]["title"] == "Jantar, com a equipe levar notebook"


def test_evento_sem_titulo_ou_data_e_descartado():
    feed = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Sem data\nEND:VEVENT\n"
            "BEGIN:VEVENT\nDTSTART:20260910T140000Z\nEND:VEVENT\nEND:VCALENDAR\n")
    assert ical.parse(feed, "UTC") == []


def test_feed_vazio_ou_lixo_nao_quebra():
    assert ical.parse("", "UTC") == []
    assert ical.parse("nada disso é ical", "UTC") == []


def test_detecta_conflito_de_horario():
    eventos = [
        {"title": "A", "start_at": "2026-09-10T14:00", "end_at": "2026-09-10T15:00"},
        {"title": "B", "start_at": "2026-09-10T14:30", "end_at": "2026-09-10T15:30"},
        {"title": "C", "start_at": "2026-09-10T16:00", "end_at": "2026-09-10T17:00"},
    ]
    conflitos = ical.conflitos(eventos)
    assert len(conflitos) == 1
    assert {conflitos[0][0]["title"], conflitos[0][1]["title"]} == {"A", "B"}


def test_encostar_nao_e_conflito():
    """Terminar às 15:00 e começar às 15:00 é agenda apertada, não conflito."""
    eventos = [
        {"title": "A", "start_at": "2026-09-10T14:00", "end_at": "2026-09-10T15:00"},
        {"title": "B", "start_at": "2026-09-10T15:00", "end_at": "2026-09-10T16:00"},
    ]
    assert ical.conflitos(eventos) == []


def test_dia_inteiro_nao_conflita_com_nada():
    eventos = [
        {"title": "Feriado", "start_at": "2026-09-10T00:00", "end_at": "2026-09-11T00:00",
         "dia_inteiro": True},
        {"title": "Reunião", "start_at": "2026-09-10T14:00", "end_at": "2026-09-10T15:00"},
    ]
    assert ical.conflitos(eventos) == []


def test_proximos_respeita_a_janela():
    agora = datetime(2026, 9, 10, 8, 0, tzinfo=TZ)
    eventos = [
        {"title": "hoje", "start_at": "2026-09-10T14:00-03:00"},
        {"title": "daqui a um mês", "start_at": "2026-10-10T14:00-03:00"},
    ]
    assert [e["title"] for e in ical.proximos(eventos, agora, dias=7)] == ["hoje"]


def test_url_invalida_e_recusada():
    import pytest

    with pytest.raises(ValueError, match="http"):
        ical.baixar("file:///etc/passwd")


# ---------- integração com o banco ----------

def test_sincronizar_substitui_o_que_veio_do_feed(ctx, monkeypatch):
    """O feed é a fonte da verdade: evento apagado lá tem de sumir aqui."""
    from aide.tools import events

    object.__setattr__(ctx.config, "calendar_url", "https://exemplo/cal.ics")
    monkeypatch.setattr(ical, "baixar", lambda url, timeout=30: FEED)

    assert events.sincronizar(ctx.conn, ctx.config)["importados"] == 3

    menor = FEED.split("BEGIN:VEVENT")[0] + "BEGIN:VEVENT" + \
        FEED.split("BEGIN:VEVENT")[1] + "END:VCALENDAR\n"
    monkeypatch.setattr(ical, "baixar", lambda url, timeout=30: menor)
    events.sincronizar(ctx.conn, ctx.config)

    total = ctx.conn.execute(
        "SELECT COUNT(*) c FROM events WHERE source='ical'").fetchone()["c"]
    assert total == 1


def test_sincronizar_preserva_evento_local(ctx, monkeypatch):
    from aide.tools import events

    ctx.conn.execute(
        "INSERT INTO events (title, start_at, source) VALUES ('Meu', '2026-09-10T10:00', 'local')")
    object.__setattr__(ctx.config, "calendar_url", "https://exemplo/cal.ics")
    monkeypatch.setattr(ical, "baixar", lambda url, timeout=30: FEED)
    events.sincronizar(ctx.conn, ctx.config)

    locais = ctx.conn.execute(
        "SELECT COUNT(*) c FROM events WHERE source='local'").fetchone()["c"]
    assert locais == 1


def test_sem_url_a_mensagem_ensina_onde_achar(ctx):
    import pytest

    from aide.tools import events

    object.__setattr__(ctx.config, "calendar_url", None)
    with pytest.raises(ValueError, match="Endereço secreto"):
        events.sincronizar(ctx.conn, ctx.config)


def test_feed_fora_do_ar_nao_derruba_o_daemon(ctx, monkeypatch):
    from aide.channels.notify import ConsoleNotifier
    from aide.scheduler import jobs

    object.__setattr__(ctx.config, "calendar_url", "https://exemplo/cal.ics")
    monkeypatch.setattr(ical, "baixar",
                        lambda url, timeout=30: (_ for _ in ()).throw(OSError("fora do ar")))
    deps = jobs.JobDeps(config=ctx.config, llm=None, notifier=ConsoleNotifier(),
                        conn=ctx.conn)
    assert jobs.sync_calendar(deps) == 0


def test_job_sem_calendario_e_no_op(ctx):
    from aide.channels.notify import ConsoleNotifier
    from aide.scheduler import jobs

    object.__setattr__(ctx.config, "calendar_url", None)
    deps = jobs.JobDeps(config=ctx.config, llm=None, notifier=ConsoleNotifier(),
                        conn=ctx.conn)
    assert jobs.sync_calendar(deps) == 0
