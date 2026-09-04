"""Os jobs do daemon e o agendamento deles.

Tudo aqui é determinístico: o job decide se há motivo para falar. A LLM só é
chamada quando já existe algo a dizer — nunca para descobrir se existe.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from aide.core.context import now_in
from aide.scheduler import briefing, rules
from aide.tools import reminders

log = logging.getLogger(__name__)

# folga na comparação de mtime; ver reindex_vault
FOLGA_MTIME = timedelta(seconds=2)

DIAS = {"segunda": "mon", "terça": "tue", "terca": "tue", "quarta": "wed",
        "quinta": "thu", "sexta": "fri", "sábado": "sat", "sabado": "sat",
        "domingo": "sun"}


@dataclass
class JobDeps:
    """O que todo job precisa. Facilita testar sem daemon no ar.

    A conexão é por thread: o APScheduler executa cada job numa worker thread e
    o sqlite3 recusa uma conexão criada em outra. Passe `conn_factory` no daemon;
    em teste ou uso single-thread, `conn` direto já basta.
    """

    config: object
    llm: object
    notifier: object
    conn_factory: Callable[[], object] | None = None
    conn: object | None = None
    embedder: object | None = None
    _local: threading.local = field(default_factory=threading.local, repr=False)

    def db(self):
        if self.conn is not None:
            return self.conn
        if self.conn_factory is None:
            raise RuntimeError("JobDeps precisa de conn ou conn_factory")
        existente = getattr(self._local, "conn", None)
        if existente is None:
            existente = self.conn_factory()
            self._local.conn = existente
        return existente

    @property
    def now(self) -> datetime:
        return now_in(self.config.timezone)


# ---------- jobs ----------


def tick_reminders(deps: JobDeps) -> int:
    """Dispara lembretes vencidos. Roda a cada minuto."""
    conn = deps.db()
    entregues = 0
    for lembrete in reminders.due(conn, deps.now):
        if deps.notifier.send("Lembrete", lembrete["text"]):
            proximo = reminders.mark_delivered(conn, lembrete)
            entregues += 1
            log.info("lembrete %s entregue%s", lembrete["id"],
                     f", próximo em {proximo}" if proximo else "")
    return entregues


def eval_conditions(deps: JobDeps) -> int:
    """Avalia as regras e cobra o que precisa. Este job é o ponto do projeto."""
    achados = [f for f in rules.evaluate(deps.db(), deps.now) if f.severity == 1]
    if not achados:
        return 0

    corpo = "\n".join(f.summary for f in achados[:5])
    if len(achados) > 5:
        corpo += f"\n... e mais {len(achados) - 5}"
    deps.notifier.send("Precisa de você", corpo, urgency="critical")
    return len(achados)


def _briefing_job(deps: JobDeps, tipo: str) -> bool:
    resultado = briefing.gerar(deps.db(), deps.config, deps.llm, deps.now, tipo)
    if resultado.vazio:
        log.info("briefing %s sem conteúdo; nada enviado", tipo)
        return False
    deps.notifier.send(resultado.title, resultado.body, urgency=resultado.urgency)
    return True


def briefing_manha(deps: JobDeps) -> bool:
    return _briefing_job(deps, "manha")


def briefing_noite(deps: JobDeps) -> bool:
    return _briefing_job(deps, "noite")


def revisao_semanal(deps: JobDeps) -> bool:
    return _briefing_job(deps, "semanal")


def queue_work(deps: JobDeps) -> int:
    """Converte pendências pesadas em ordens de trabalho.

    O daemon não executa esse tipo de coisa — ele deixa a fila pronta para
    quando você abrir uma sessão com um executor externo.
    """
    conn = deps.db()
    criadas = 0

    # projeto parado costuma precisar de alguém revisar material, não de uma
    # tarefa a mais na lista
    for achado in rules.evaluate(conn, deps.now):
        if achado.rule != "projeto_parado":
            continue
        ja_existe = conn.execute(
            "SELECT 1 FROM work_orders WHERE status IN ('open', 'claimed')"
            " AND goal = ?", (f"Revisar o projeto parado: {achado.summary}",)
        ).fetchone()
        if ja_existe:
            continue
        conn.execute(
            "INSERT INTO work_orders (goal, context, done_criteria, priority)"
            " VALUES (?, ?, ?, ?)",
            (f"Revisar o projeto parado: {achado.summary}",
             "Ver o que trava o projeto e propor o próximo passo concreto.",
             "Uma decisão registrada: seguir, adiar com data, ou encerrar.", 3),
        )
        criadas += 1

    if criadas:
        log.info("%s ordem(ns) de trabalho enfileirada(s)", criadas)
    return criadas


def reindex_vault(deps: JobDeps) -> int:
    """Reindexa as notas cujo arquivo mudou desde a última indexação.

    O markdown é a fonte da verdade: se você editar uma nota no editor, a busca
    precisa acompanhar — senão ela responde com o texto antigo, calada.
    """
    from pathlib import Path

    from aide.storage import vault
    from aide.storage.search import guardar_vetor, indexar

    conn = deps.db()
    linhas = conn.execute(
        "SELECT id, title, path, updated_at FROM notes WHERE deleted_at IS NULL"
    ).fetchall()

    reindexadas = 0
    for row in linhas:
        caminho = Path(row["path"])
        if not caminho.exists():
            log.warning("arquivo da nota %s sumiu: %s", row["id"], caminho)
            continue

        # datetime('now') do SQLite é UTC; comparar com mtime local atrasaria a
        # reindexação pelo tamanho do fuso (3h aqui) e ninguém entenderia por quê.
        modificado = datetime.fromtimestamp(caminho.stat().st_mtime, tz=UTC)
        indexado = datetime.fromisoformat(row["updated_at"]).replace(tzinfo=UTC)
        # o updated_at do SQLite tem resolução de segundos e o mtime tem fração;
        # sem folga, toda nota recém-criada parece editada e reindexa à toa
        if modificado <= indexado + FOLGA_MTIME:
            continue

        corpo = vault.corpo_de(caminho)
        indexar(conn, row["id"], row["title"], corpo)
        conn.execute("UPDATE notes SET updated_at = datetime('now') WHERE id = ?", (row["id"],))

        embedder = getattr(deps, "embedder", None)
        if embedder is not None:
            try:
                vetor = embedder.embed_one(f"{row['title']}\n\n{corpo}")
            except Exception:
                log.warning("embedding da nota %s falhou", row["id"], exc_info=True)
                vetor = None
            if vetor:
                guardar_vetor(conn, "note", row["id"], f"{row['title']}\n\n{corpo}", vetor)

        reindexadas += 1
        log.info("nota %s reindexada (arquivo mudou)", row["id"])

    return reindexadas


JOBS = {
    "tick_reminders": tick_reminders,
    "eval_conditions": eval_conditions,
    "briefing_manha": briefing_manha,
    "briefing_noite": briefing_noite,
    "revisao_semanal": revisao_semanal,
    "queue_work": queue_work,
    "reindex_vault": reindex_vault,
}


# ---------- agendamento ----------


def _hora(texto: str) -> tuple[int, int]:
    hora, minuto = texto.split(":")
    return int(hora), int(minuto)


def _semanal(texto: str) -> tuple[str, int, int]:
    partes = texto.split()
    if len(partes) != 2 or partes[0].lower() not in DIAS:
        raise ValueError(f"revisao_semanal deve ser 'domingo 19:00'; recebido {texto!r}")
    hora, minuto = _hora(partes[1])
    return DIAS[partes[0].lower()], hora, minuto


def build_scheduler(deps: JobDeps):
    """Monta o APScheduler com os jobs.

    Jobstore em memória de propósito: os jobs são declarados aqui em código e
    re-registrados a cada start, então persistir o agendamento não traria nada
    e custaria o SQLAlchemy inteiro como dependência. O que precisa sobreviver
    a um restart — lembretes pendentes — já vive na tabela `reminders`, e o
    tick seguinte pega tudo que venceu enquanto o daemon estava fora.
    """
    from apscheduler.schedulers.background import BackgroundScheduler

    cfg = deps.config.schedule
    tz = ZoneInfo(deps.config.timezone)
    scheduler = BackgroundScheduler(
        timezone=tz,
        job_defaults={"coalesce": True, "misfire_grace_time": 3600, "max_instances": 1},
    )

    def add(func, job_id, **trigger):
        scheduler.add_job(func, args=[deps], id=job_id, replace_existing=True, **trigger)

    add(tick_reminders, "tick_reminders", trigger="interval", minutes=1)
    add(eval_conditions, "eval_conditions", trigger="interval",
        hours=cfg.regras_a_cada_horas)
    add(queue_work, "queue_work", trigger="interval", hours=cfg.regras_a_cada_horas)
    add(reindex_vault, "reindex_vault", trigger="interval", minutes=15)

    manha_h, manha_m = _hora(cfg.briefing_manha)
    add(briefing_manha, "briefing_manha", trigger="cron", hour=manha_h, minute=manha_m)

    noite_h, noite_m = _hora(cfg.briefing_noite)
    add(briefing_noite, "briefing_noite", trigger="cron", hour=noite_h, minute=noite_m)

    dia, sem_h, sem_m = _semanal(cfg.revisao_semanal)
    add(revisao_semanal, "revisao_semanal", trigger="cron",
        day_of_week=dia, hour=sem_h, minute=sem_m)

    return scheduler
