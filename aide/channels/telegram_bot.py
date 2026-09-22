"""O bot: recebe mensagens no Telegram e responde com o mesmo core.

Long polling numa thread. Não é um segundo assessor — é outra porta para o
mesmo orquestrador e o mesmo toolbelt.
"""

from __future__ import annotations

import logging
import threading
import time

from aide.channels import formato
from aide.channels.telegram import TelegramClient, TelegramError
from aide.core.orchestrator import Orchestrator

log = logging.getLogger(__name__)

BACKOFF_INICIAL = 5
BACKOFF_MAXIMO = 300

# Quanto tempo uma confirmação pendente vale. Passado isso ela caduca: um "sim"
# solto meia hora depois não pode apagar algo que você já esqueceu ter pedido.
VALIDADE_CONFIRMACAO = 120

# Teto por confirmação. Um "sim" não deveria conseguir varrer a base inteira
# de uma vez, e uma pergunta com trinta itens ninguém lê antes de responder.
LIMITE_CONFIRMACAO = 12

SIM = {"sim", "s", "confirmo", "confirmar", "pode", "pode apagar", "isso",
       "ok", "claro", "apaga", "apagar"}

AJUDA = """Comandos:
/hoje - o que precisa de você hoje
/atrasadas - o que passou do prazo
/checar - o que as regras estão vendo
/gastos - quanto você gastou esse mês
/notas - suas notas mais recentes
/buscar <termo> - procura nas notas por significado
/perfil - o que eu sei sobre você
/id - o id deste chat
/ajuda - isto aqui

Fora isso, é só falar normalmente:
"me lembra de pagar o IPVA sexta"
"adia o dentista pra semana que vem"
"já paguei o boleto"
"10,50 almoço com a KA"
"quanto gastei esse mês?"
"anota que decidimos cortar 20% da nuvem"
"apaga a tarefa do IPVA"   (ele pergunta antes)
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
        # chat -> (lista de (tool, args), quando o pedido começou)
        #
        # Lista e não uma ação só: o modelo devolve várias chamadas numa volta
        # quando você pede "apaga o IPVA e a CNH", e guardar só a última
        # apagaria uma e perderia a outra caladamente.
        self._pendentes: dict[int, tuple[list[tuple[str, dict]], float]] = {}
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
        pendente = self._pendente_valido(chat_id)
        if pendente and not texto.startswith("/"):
            return self._responder_confirmacao(chat_id, texto, pendente)

        if texto.startswith("/"):
            partes = texto.split(maxsplit=1)
            nome = partes[0].lstrip("/").lower()
            resto = partes[1].strip() if len(partes) > 1 else ""
            return self._comando(chat_id, nome, resto)

        agente = self._agente(chat_id)
        resposta = agente.ask(texto)
        pedido = self._pendentes.get(chat_id)
        if pedido:
            # O modelo recebeu "não autorizado" e vai dizer isso. Quem responde
            # aqui é a pergunta, que é o que faltava: a tool exige um "tem
            # certeza?" de gente, e conversa é justamente onde dá para pedir.
            pergunta = self._perguntar(pedido)
            # e o histórico guarda a pergunta, não o texto descartado: senão o
            # modelo lê depois que apagar falhou e para de tentar
            agente.corrigir_ultima_resposta(pergunta)
            return pergunta
        return resposta

    # ---------- confirmação em dois passos ----------

    def _pendente_valido(self, chat_id: int):
        pedido = self._pendentes.get(chat_id)
        if not pedido:
            return None
        if time.time() - pedido[1] > VALIDADE_CONFIRMACAO:
            self._pendentes.pop(chat_id, None)
            return None
        return pedido

    def _anotar_confirmacao(self, chat_id: int, nome: str, args: dict) -> bool:
        """Chamado pelo orquestrador. Sempre nega agora e guarda para perguntar.

        Acumula: uma volta do modelo pode pedir várias exclusões, e todas têm
        de caber na mesma pergunta.
        """
        acoes, desde = self._pendentes.get(chat_id) or ([], time.time())
        if (nome, args) not in [(n, a) for n, a in acoes]:
            acoes.append((nome, dict(args)))
        self._pendentes[chat_id] = (acoes[:LIMITE_CONFIRMACAO], desde)
        return False

    def _descrever(self, nome: str, args: dict) -> str:
        """O que vai ser apagado, em palavras — não `tasks.drop {'id': 4}`."""
        alvo = args.get("id") or args.get("name") or args.get("key")
        tabela = {"tasks.drop": ("tasks", "title"), "notes.delete": ("notes", "title"),
                  "expenses.delete": ("expenses", "description"),
                  "work_orders.drop": ("work_orders", "goal")}.get(nome)
        if tabela and isinstance(alvo, int):
            coluna = tabela[1]
            linha = self._db().execute(
                f"SELECT {coluna} FROM {tabela[0]} WHERE id = ?", (alvo,)).fetchone()
            if linha:
                return f'"{linha[coluna]}" (#{alvo})'
        return f"{alvo}" if alvo else nome

    @staticmethod
    def _verbo(nome: str) -> str:
        return {"memory.forget": "esquecer",
                "people.remove": "parar de acompanhar"}.get(nome, "apagar")

    RODAPE = "Responda sim para confirmar. Qualquer outra coisa cancela."

    def _perguntar(self, pedido) -> str:
        acoes, _ = pedido
        if len(acoes) == 1:
            nome, args = acoes[0]
            pergunta = f"Quer mesmo {self._verbo(nome)} {self._descrever(nome, args)}?"
        else:
            linhas = "\n".join(f"· {self._verbo(n)} {self._descrever(n, a)}"
                               for n, a in acoes)
            # a interrogação fica no fim da frase, não sozinha depois da lista
            pergunta = f"Quer mesmo fazer estas {len(acoes)} coisas?\n{linhas}"
        return f"{pergunta}\n\n{self.RODAPE}"

    def _responder_confirmacao(self, chat_id: int, texto: str, pedido) -> str:
        acoes, _ = pedido
        self._pendentes.pop(chat_id, None)

        if texto.strip().lower().rstrip("!.") not in SIM:
            return self._registrar_desfecho(chat_id, texto, "Cancelado, não apaguei nada.")

        feitas, falhas = [], []
        for nome, args in acoes:
            # descreve antes de executar: depois de apagada, a linha some e
            # a resposta viraria "apaguei 4" em vez do nome da tarefa
            descricao = self._descrever(nome, args)
            resultado = self.registry.call(nome, args, self._ctx(chat_id))
            if resultado.ok:
                feitas.append(descricao)
                log.info("[telegram:%s] %s confirmado e executado", chat_id, nome)
            else:
                falhas.append(f"{descricao}: {resultado.error}")

        partes = []
        if feitas:
            partes.append("Pronto, apaguei " + (feitas[0] if len(feitas) == 1
                                                else "\n" + "\n".join(f"· {f}" for f in feitas)))
        if falhas:
            # o que deu certo já está feito; calar as falhas faria você achar
            # que apagou tudo
            partes.append("Não consegui:\n" + "\n".join(f"· {f}" for f in falhas))
        return self._registrar_desfecho(
            chat_id, texto, "\n\n".join(partes) if partes else "Nada a fazer.")

    def _registrar_desfecho(self, chat_id: int, pedido_do_usuario: str, resposta: str) -> str:
        """O sim e o que veio dele entram na conversa.

        Sem isto o transcrito fica com uma pergunta e nenhuma resposta, e na
        volta seguinte o modelo não sabe se a exclusão aconteceu.
        """
        sessao = self._sessoes.get(chat_id)
        if sessao:
            conn = self._db()
            for papel, conteudo in (("user", pedido_do_usuario), ("assistant", resposta)):
                conn.execute(
                    "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                    (sessao, papel, conteudo))
        return resposta

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
        if nome == "gastos":
            dados = self.registry.call(
                "expenses.summary", {"periodo": resto or "mes"}, self._ctx(chat_id))
            if not dados.ok:
                return dados.error
            if not dados.data["quantos"]:
                return "Nenhum gasto nesse período."
            linhas = [f"{dados.data['total']} em "
                      f"{formato.plural(dados.data['quantos'], 'lançamento')}"]
            linhas += [f"  {c['category']}: {c['valor']}"
                       for c in dados.data["por_categoria"]]
            return "\n".join(linhas)
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
            fatos = self.registry.call(
                "memory.list", {"kind": "profile"}, self._ctx(chat_id)).data
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
            # nega agora e guarda o pedido: a pergunta vai na resposta, e a
            # execução espera o "sim" da próxima mensagem
            confirm=lambda nome, args: self._anotar_confirmacao(chat_id, nome, args),
        )

    def _responder(self, chat_id: int, texto: str) -> None:
        """Manda com relevo; se o Telegram recusar a formatação, manda sem.

        O Markdown legado dele é frágil: um caractere escapado fora de hora faz
        a mensagem inteira ser recusada com 400. Perder a resposta por causa do
        negrito seria trocar o conteúdo pela aparência, então a segunda
        tentativa vai em texto puro.
        """
        from aide.channels.formato import conversa_para_telegram

        try:
            self.client.send_message(chat_id, conversa_para_telegram(texto), markdown=True)
            return
        except TelegramError as exc:
            log.info("telegram recusou a formatação (%s); reenviando sem", exc)

        try:
            self.client.send_message(chat_id, texto)
        except TelegramError as exc:
            log.warning("não consegui responder %s: %s", chat_id, exc)
