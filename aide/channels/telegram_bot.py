"""O bot: recebe mensagens no Telegram e responde com o mesmo core.

Long polling numa thread. Não é um segundo assessor — é outra porta para o
mesmo orquestrador e o mesmo toolbelt.
"""

from __future__ import annotations

import logging
import threading
import time

from aide.channels.telegram import TelegramClient, TelegramError
from aide.core.orchestrator import Orchestrator

log = logging.getLogger(__name__)

BACKOFF_INICIAL = 5
BACKOFF_MAXIMO = 300

AJUDA = """Comandos:
/hoje - o que precisa de você hoje
/atrasadas - o que passou do prazo
/checar - o que as regras estão vendo
/notas - suas notas mais recentes
/buscar <termo> - procura nas notas por significado
/perfil - o que eu sei sobre você
/id - o id deste chat
/ajuda - isto aqui

Fora isso, é só falar normalmente:
"me lembra de pagar o IPVA sexta"
"adia o dentista pra semana que vem"
"já paguei o boleto"
"anota que decidimos cortar 20% da nuvem"
"o que eu tinha anotado sobre o carro?"
"""


class TelegramBot:
    def __init__(self, config, conn_factory, llm, registry, embedder=None):
        self.config = config
        self.conn_factory = conn_factory
        self.llm = llm
        self.registry = registry
        self.embedder = embedder
        self.client = TelegramClient(config.telegram.token)
        self.permitidos = set(config.telegram.allowed_chat_ids)
        self._offset: int | None = None
        self._parar = threading.Event()
        self._sessoes: dict[int, str] = {}
        self._recusados: set[int] = set()
        self._conn = None

    # ---------- ciclo de vida ----------

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self.run, name="telegram-bot", daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        self._parar.set()

    def run(self) -> None:
        log.info("bot do telegram no ar (chats permitidos: %s)", sorted(self.permitidos))
        backoff = BACKOFF_INICIAL

        while not self._parar.is_set():
            try:
                for update in self.client.get_updates(offset=self._offset):
                    self._offset = update["update_id"] + 1
                    self._tratar(update)
                backoff = BACKOFF_INICIAL
            except TelegramError as exc:
                if "409" in str(exc):
                    # o Telegram só entrega updates para um getUpdates por bot;
                    # insistir aqui só faz os dois daemons se atrapalharem.
                    log.error(
                        "outro my-aide já está atendendo este bot. "
                        "Encerre o outro 'aide serve' (ou o serviço do systemd) "
                        "e suba um só. O bot deste processo fica parado."
                    )
                    return
                # rede caiu ou o Telegram está fora: espera e tenta de novo
                log.warning("polling falhou (%s); nova tentativa em %ss", exc, backoff)
                self._parar.wait(backoff)
                backoff = min(backoff * 2, BACKOFF_MAXIMO)
            except Exception:
                log.exception("erro inesperado no bot; seguindo")
                self._parar.wait(BACKOFF_INICIAL)

    # ---------- tratamento ----------

    def _db(self):
        if self._conn is None:
            self._conn = self.conn_factory()
        return self._conn

    def _tratar(self, update: dict) -> None:
        mensagem = update.get("message") or update.get("edited_message")
        if not mensagem:
            return

        chat_id = mensagem.get("chat", {}).get("id")
        texto = (mensagem.get("text") or "").strip()
        if not texto:
            return

        if chat_id not in self.permitidos:
            # Silêncio de propósito. Um bot do Telegram é público — qualquer um
            # que saiba o nome consegue mandar mensagem. Responder confirmaria
            # que o bot está ativo e deixaria um estranho nos usar como
            # amplificador de spam, até o Telegram limitar o bot por excesso de
            # envio. O chat id de quem tentou fica no log, que é onde importa.
            self._recusar(chat_id)
            return

        try:
            resposta = self._resolver(chat_id, texto)
        except Exception:
            log.exception("falha ao tratar mensagem")
            resposta = "Deu erro aqui do meu lado. Tenta de novo?"

        self._responder(chat_id, resposta)

    def _recusar(self, chat_id: int) -> None:
        """Registra a tentativa uma vez por chat, para o log não virar enxurrada."""
        if chat_id not in self._recusados:
            self._recusados.add(chat_id)
            log.warning("chat não autorizado %s tentou falar com o bot", chat_id)

    def _resolver(self, chat_id: int, texto: str) -> str:
        if texto.startswith("/"):
            partes = texto.split(maxsplit=1)
            nome = partes[0].lstrip("/").lower()
            resto = partes[1].strip() if len(partes) > 1 else ""
            return self._comando(chat_id, nome, resto)
        return self._agente(chat_id).ask(texto)

    def _ctx(self, chat_id: int):
        from aide.tools.registry import ToolContext

        return ToolContext(config=self.config, conn=self._db(),
                           actor=f"telegram:{chat_id}", embedder=self.embedder)

    def _comando(self, chat_id: int, nome: str, resto: str = "") -> str:
        from aide.scheduler import rules

        if nome in {"start", "ajuda", "help"}:
            return AJUDA
        if nome == "id":
            return f"chat id: {chat_id}"
        if nome in {"hoje", "atrasadas"}:
            filtro = "today" if nome == "hoje" else "overdue"
            tarefas = self.registry.call(
                "tasks.list", {"filter": filtro}, self._ctx(chat_id)).data
            if not tarefas:
                return "Nada por aqui."
            return "\n".join(
                f"#{t['id']} {t['title']}" + (f" — {t['due_at']}" if t["due_at"] else "")
                for t in tarefas
            )
        if nome == "notas":
            linhas = self.registry.call("notes.list", {"limit": 15}, self._ctx(chat_id)).data
            if not linhas:
                return "Nenhuma nota ainda."
            return "\n".join(f"#{n['id']} {n['title']}" for n in linhas)
        if nome == "buscar":
            if not resto:
                return "Use: /buscar <o que você procura>"
            achados = self.registry.call(
                "notes.search", {"query": resto}, self._ctx(chat_id)).data
            if not achados:
                return "Não achei nada sobre isso."
            return "\n\n".join(
                f"#{a['id']} {a['title']}\n{(a.get('trecho') or '').strip()[:200]}"
                for a in achados
            )
        if nome == "perfil":
            fatos = self.registry.call("memory.list", {}, self._ctx(chat_id)).data
            if not fatos:
                return "Ainda não sei nada sobre você."
            return "\n".join(f"{f['key']}: {f['value']}" for f in fatos)
        if nome == "checar":
            achados = rules.evaluate(self._db(), self._agora())
            return "\n".join(f.summary for f in achados) if achados else "Nada pedindo atenção."
        return f"Não conheço /{nome}. Use /ajuda."

    def _agora(self):
        from aide.core.context import now_in

        return now_in(self.config.timezone)

    def _agente(self, chat_id: int) -> Orchestrator:
        """Uma sessão por chat, para a conversa ter continuidade."""
        session_id = self._sessoes.get(chat_id)
        if session_id is None:
            session_id = f"tg{chat_id}-{int(time.time())}"
            self._sessoes[chat_id] = session_id
        return Orchestrator(
            self.config, self._db(), self.llm, session_id=session_id,
            registry=self.registry, actor=f"telegram:{chat_id}", embedder=self.embedder,
            # sem confirmação interativa por aqui: tool 'confirm' é recusada
            confirm=lambda name, args: False,
        )

    def _responder(self, chat_id: int, texto: str) -> None:
        try:
            self.client.send_message(chat_id, texto)
        except TelegramError as exc:
            log.warning("não consegui responder %s: %s", chat_id, exc)
