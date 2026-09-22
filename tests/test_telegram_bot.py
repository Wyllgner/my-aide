from aide.channels.telegram import TelegramError
from aide.channels.telegram_bot import TelegramBot
from aide.core.context import now_in
from aide.llm.base import LLMProvider, LLMResponse
from aide.storage import connect, migrate
from aide.tools import registry as tool_registry


class FakeLLM(LLMProvider):
    def __init__(self, text="ok"):
        self.text = text
        self.vistas = []

    def complete(self, messages, *, fast=False, tools=None, purpose="chat", **extra):
        self.vistas.append(messages)
        return LLMResponse(text=self.text, model="fake")


def _bot(ctx, tmp_path, permitidos=(42,), llm=None):
    object.__setattr__(ctx.config.telegram, "token", "x")
    object.__setattr__(ctx.config.telegram, "allowed_chat_ids", tuple(permitidos))
    caminho = tmp_path / "b.db"
    migrate(connect(caminho))
    bot = TelegramBot(ctx.config, lambda: connect(caminho), llm or FakeLLM(), tool_registry)
    bot.enviadas = []
    bot.editadas = []

    # devolve o que a Bot API devolve: o progresso precisa do message_id para
    # editar a mesma mensagem em vez de mandar outra
    def enviar(chat_id, text, markdown=False):
        bot.enviadas.append((chat_id, text))
        return {"message_id": 100 + len(bot.enviadas)}

    # aceita markdown=: o bot manda formatado e cai para texto puro se recusarem
    bot.client.send_message = enviar
    bot.client.edit_message = (
        lambda chat_id, message_id, text: bot.editadas.append((message_id, text)))
    bot.apagadas = []
    bot.client.delete_message = (
        lambda chat_id, message_id: bot.apagadas.append(message_id))
    # "digitando" também é rede: sem dublê, o guard de rede do conftest acusa
    bot.acoes = []
    bot.client.send_action = (
        lambda chat_id, action="typing": bot.acoes.append((chat_id, action)))
    return bot


def _msg(texto, chat_id=42, update_id=1):
    return {"update_id": update_id, "message": {"chat": {"id": chat_id}, "text": texto}}


def test_responde_comando_de_ajuda(ctx, tmp_path):
    bot = _bot(ctx, tmp_path)
    bot._tratar(_msg("/ajuda"))
    assert "me lembra de" in bot.enviadas[0][1]


def test_informa_o_chat_id(ctx, tmp_path):
    bot = _bot(ctx, tmp_path)
    bot._tratar(_msg("/id"))
    assert "42" in bot.enviadas[0][1]


def test_chat_nao_autorizado_recebe_silencio(ctx, tmp_path):
    """Responder confirmaria o bot e permitiria usá-lo como amplificador de spam."""
    bot = _bot(ctx, tmp_path, permitidos=(42,))
    bot._tratar(_msg("/hoje", chat_id=999))
    assert bot.enviadas == []


def test_chat_nao_autorizado_nao_gasta_llm(ctx, tmp_path):
    llm = FakeLLM()
    bot = _bot(ctx, tmp_path, permitidos=(42,), llm=llm)
    bot._tratar(_msg("me lembra de algo", chat_id=999))
    assert llm.vistas == []


def test_tentativa_e_logada_uma_vez_por_chat(ctx, tmp_path, caplog):
    bot = _bot(ctx, tmp_path, permitidos=(42,))
    with caplog.at_level("WARNING"):
        for _ in range(5):
            bot._tratar(_msg("oi", chat_id=999))
    assert sum("999" in r.getMessage() for r in caplog.records) == 1


def test_conversa_vai_para_o_orquestrador(ctx, tmp_path):
    llm = FakeLLM("Criei a tarefa.")
    bot = _bot(ctx, tmp_path, llm=llm)
    bot._tratar(_msg("me lembra do IPVA"))
    assert bot.enviadas[0][1] == "Criei a tarefa."
    assert llm.vistas


def test_mesma_sessao_entre_mensagens(ctx, tmp_path):
    bot = _bot(ctx, tmp_path)
    primeira = bot._agente(42).session_id
    assert bot._agente(42).session_id == primeira
    assert bot._agente(7).session_id != primeira


def test_erro_interno_vira_resposta_amigavel(ctx, tmp_path, monkeypatch):
    bot = _bot(ctx, tmp_path)
    monkeypatch.setattr(bot, "_resolver", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    bot._tratar(_msg("oi"))
    assert "erro" in bot.enviadas[0][1].lower()


def test_mensagem_sem_texto_e_ignorada(ctx, tmp_path):
    bot = _bot(ctx, tmp_path)
    bot._tratar({"update_id": 1, "message": {"chat": {"id": 42}}})
    assert bot.enviadas == []


def test_comando_desconhecido(ctx, tmp_path):
    bot = _bot(ctx, tmp_path)
    bot._tratar(_msg("/xpto"))
    assert "/ajuda" in bot.enviadas[0][1]


def test_polling_sobrevive_a_queda_de_rede(ctx, tmp_path):
    bot = _bot(ctx, tmp_path)
    tentativas = []

    def falhar(offset=None, timeout=25):
        tentativas.append(offset)
        if len(tentativas) >= 2:
            bot.stop()
        raise TelegramError("rede fora")

    bot.client.get_updates = falhar
    bot._parar.wait = lambda _s: None  # não esperar de verdade no teste
    bot.run()
    assert len(tentativas) >= 2


def test_offset_avanca_para_nao_reprocessar(ctx, tmp_path):
    bot = _bot(ctx, tmp_path)
    entregues = [[_msg("/id", update_id=10)], []]

    def updates(offset=None, timeout=25):
        if not entregues:
            bot.stop()
            return []
        lote = entregues.pop(0)
        if not lote:
            bot.stop()
        return lote

    bot.client.get_updates = updates
    bot.run()
    assert bot._offset == 11


def test_conflito_de_instancia_para_o_bot(ctx, tmp_path, caplog):
    """409 significa dois daemons no mesmo bot; insistir só atrapalha os dois."""
    bot = _bot(ctx, tmp_path)
    tentativas = []

    def conflito(offset=None, timeout=25):
        tentativas.append(1)
        raise TelegramError('getUpdates falhou (409): Conflict: terminated by other')

    bot.client.get_updates = conflito
    with caplog.at_level("ERROR"):
        bot.run()

    assert len(tentativas) == 1  # não fica insistindo
    assert any("outro my-aide" in r.getMessage() for r in caplog.records)


def test_comando_notas(ctx, tmp_path, registry):
    bot = _bot(ctx, tmp_path)
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    registry.call("notes.create", {"title": "Carro", "body": "trocar óleo"}, ctx)
    bot._conn = ctx.conn  # usar o mesmo banco da fixture
    bot._tratar(_msg("/notas"))
    assert "Carro" in bot.enviadas[0][1]


def test_comando_buscar_com_argumento(ctx, tmp_path, registry):
    bot = _bot(ctx, tmp_path)
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    registry.call("notes.create", {"title": "Carro", "body": "trocar o óleo"}, ctx)
    bot._conn = ctx.conn
    bot._tratar(_msg("/buscar óleo"))
    assert "Carro" in bot.enviadas[0][1]


def test_buscar_sem_argumento_orienta(ctx, tmp_path):
    bot = _bot(ctx, tmp_path)
    bot._tratar(_msg("/buscar"))
    assert "Use: /buscar" in bot.enviadas[0][1]


def test_comando_perfil(ctx, tmp_path, registry):
    bot = _bot(ctx, tmp_path)
    registry.call("memory.save", {"kind": "profile", "key": "treino",
                                  "value": "6h da manhã"}, ctx)
    bot._conn = ctx.conn
    bot._tratar(_msg("/perfil"))
    assert "6h da manhã" in bot.enviadas[0][1]


# ---------- a porta remota ----------

SEGREDO = "TERAPIA-QUINTA-FEIRA"


def _com_privado(bot):
    """Semeia conteúdo privado pelo caminho do dono, no mesmo banco do bot."""
    from aide.tools.registry import ToolContext

    conn = bot._db()
    dono = ToolContext(config=bot.config, conn=conn, actor="cli", ver_privado=True)
    tool_registry.call("tasks.create", {"title": f"Tarefa {SEGREDO}", "private": True}, dono)
    tool_registry.call("tasks.create", {"title": "Comprar pão", "due": "2020-01-01T09:00"}, dono)
    tool_registry.call("memory.save", {"kind": "profile", "key": "saude",
                                       "value": f"perfil {SEGREDO}", "private": True}, dono)
    return bot


def test_telegram_nao_recebe_tarefa_privada(ctx, tmp_path):
    """O Telegram é rede de terceiro: privado não atravessa."""
    bot = _com_privado(_bot(ctx, tmp_path))
    bot._tratar(_msg("/atrasadas"))
    resposta = bot.enviadas[0][1]
    assert "Comprar pão" in resposta
    assert SEGREDO not in resposta


def test_telegram_nao_recebe_perfil_privado(ctx, tmp_path):
    bot = _com_privado(_bot(ctx, tmp_path))
    bot._tratar(_msg("/perfil"))
    assert SEGREDO not in bot.enviadas[0][1]


def test_contexto_do_bot_nega_privado_por_padrao(ctx, tmp_path):
    bot = _bot(ctx, tmp_path)
    assert bot._ctx(42).ver_privado is False


def test_allowlist_vazia_recusa_todo_mundo(ctx, tmp_path):
    """Falhar fechado: `enabled` sem lista não pode virar bot aberto."""
    bot = _bot(ctx, tmp_path, permitidos=())
    bot._tratar(_msg("/hoje", chat_id=42))
    bot._tratar(_msg("/hoje", chat_id=99))
    assert bot.enviadas == []


def test_chat_estranho_nao_alcanca_o_banco(ctx, tmp_path):
    """A allowlist é checada antes de qualquer leitura."""
    bot = _com_privado(_bot(ctx, tmp_path))
    bot._tratar(_msg("/perfil", chat_id=99))
    bot._tratar(_msg("o que você sabe sobre mim?", chat_id=99))
    assert bot.enviadas == []


# ---------- apagar pelo Telegram ----------

def _pedir_para_apagar(bot, tool="tasks.drop", args=None):
    """Simula o que o orquestrador faz ao topar uma tool marcada `confirm`."""
    bot._anotar_confirmacao(42, tool, args or {"id": 1})


def test_apagar_pergunta_antes(ctx, tmp_path, registry):
    """Antes disto o Telegram só sabia dizer 'não autorizado', e ponto."""
    bot = _bot(ctx, tmp_path)
    conn = bot._db()
    conn.execute("INSERT INTO tasks (id, title) VALUES (1, 'Pagar o IPVA')")

    _pedir_para_apagar(bot)
    pergunta = bot._perguntar(bot._pendentes[42])
    assert "Pagar o IPVA" in pergunta
    assert "sim" in pergunta.lower()


def test_sim_apaga_de_verdade(ctx, tmp_path):
    bot = _bot(ctx, tmp_path)
    conn = bot._db()
    conn.execute("INSERT INTO tasks (id, title) VALUES (1, 'Pagar o IPVA')")
    _pedir_para_apagar(bot)

    bot._tratar(_msg("sim"))
    # tasks.drop marca status, não deleted_at: descartar não é o mesmo que sumir
    assert conn.execute("SELECT status FROM tasks WHERE id = 1").fetchone()["status"] == "dropped"
    assert "apaguei" in bot.enviadas[-1][1]


def test_qualquer_outra_coisa_cancela(ctx, tmp_path):
    """O padrão é não apagar: só um sim explícito executa."""
    bot = _bot(ctx, tmp_path)
    conn = bot._db()
    conn.execute("INSERT INTO tasks (id, title) VALUES (1, 'Pagar o IPVA')")
    _pedir_para_apagar(bot)

    bot._tratar(_msg("melhor não"))
    assert conn.execute("SELECT status FROM tasks WHERE id = 1").fetchone()["status"] == "open"
    assert "Cancelado" in bot.enviadas[-1][1]


def test_a_confirmacao_caduca(ctx, tmp_path):
    """Um 'sim' solto meia hora depois não pode apagar o que você esqueceu."""
    import time

    bot = _bot(ctx, tmp_path)
    conn = bot._db()
    conn.execute("INSERT INTO tasks (id, title) VALUES (1, 'Pagar o IPVA')")
    bot._pendentes[42] = ([("tasks.drop", {"id": 1})], time.time() - 999)

    bot._tratar(_msg("sim"))
    assert conn.execute("SELECT status FROM tasks WHERE id = 1").fetchone()["status"] == "open"


def test_o_sim_nao_vai_para_o_modelo(ctx, tmp_path):
    """Confirmar não é conversa; mandar ao modelo gastaria chamada e poderia virar outra coisa."""
    llm = FakeLLM()
    bot = _bot(ctx, tmp_path, llm=llm)
    bot._db().execute("INSERT INTO tasks (id, title) VALUES (1, 'X')")
    _pedir_para_apagar(bot)

    bot._tratar(_msg("sim"))
    assert llm.vistas == []


def test_so_o_chat_que_pediu_confirma(ctx, tmp_path):
    """Pendência é por chat: outro chat não herda o 'sim' alheio."""
    bot = _bot(ctx, tmp_path, permitidos=(42, 99))
    conn = bot._db()
    conn.execute("INSERT INTO tasks (id, title) VALUES (1, 'X')")
    _pedir_para_apagar(bot)

    bot._tratar(_msg("sim", chat_id=99))
    assert conn.execute("SELECT status FROM tasks WHERE id = 1").fetchone()["status"] == "open"
    assert 42 in bot._pendentes


def test_a_pergunta_diz_o_que_vai_sumir(ctx, tmp_path):
    """'tasks.drop {id: 4}' não é pergunta que dá para responder."""
    bot = _bot(ctx, tmp_path)
    bot._db().execute("INSERT INTO notes (id, title, path) VALUES (7, 'Laudo médico', '/x')")
    _pedir_para_apagar(bot, "notes.delete", {"id": 7})
    assert "Laudo médico" in bot._perguntar(bot._pendentes[42])


def test_apaga_varias_de_uma_vez(ctx, tmp_path):
    """Uma volta do modelo pode pedir várias exclusões; guardar só a última
    apagaria uma e perderia as outras caladamente."""
    bot = _bot(ctx, tmp_path)
    conn = bot._db()
    for i, nome in ((1, "Pagar o IPVA"), (2, "Renovar a CNH"), (3, "Levar o carro")):
        conn.execute("INSERT INTO tasks (id, title) VALUES (?, ?)", (i, nome))

    for i in (1, 2, 3):
        bot._anotar_confirmacao(42, "tasks.drop", {"id": i})

    pergunta = bot._perguntar(bot._pendentes[42])
    assert "3 coisas" in pergunta
    for nome in ("Pagar o IPVA", "Renovar a CNH", "Levar o carro"):
        assert nome in pergunta

    bot._tratar(_msg("sim"))
    status = [r["status"] for r in conn.execute("SELECT status FROM tasks ORDER BY id")]
    assert status == ["dropped", "dropped", "dropped"]
    assert "Pagar o IPVA" in bot.enviadas[-1][1]


def test_o_nao_cancela_o_lote_inteiro(ctx, tmp_path):
    bot = _bot(ctx, tmp_path)
    conn = bot._db()
    conn.execute("INSERT INTO tasks (id, title) VALUES (1, 'A')")
    conn.execute("INSERT INTO tasks (id, title) VALUES (2, 'B')")
    bot._anotar_confirmacao(42, "tasks.drop", {"id": 1})
    bot._anotar_confirmacao(42, "tasks.drop", {"id": 2})

    bot._tratar(_msg("não"))
    assert [r["status"] for r in conn.execute("SELECT status FROM tasks")] == ["open", "open"]


def test_o_que_falhou_no_lote_e_dito(ctx, tmp_path):
    """Calar a falha faria você achar que apagou tudo."""
    bot = _bot(ctx, tmp_path)
    bot._db().execute("INSERT INTO tasks (id, title) VALUES (1, 'Existe')")
    bot._anotar_confirmacao(42, "tasks.drop", {"id": 1})
    bot._anotar_confirmacao(42, "tasks.drop", {"id": 999})

    bot._tratar(_msg("sim"))
    resposta = bot.enviadas[-1][1]
    assert "Existe" in resposta
    assert "Não consegui" in resposta
    assert "999" in resposta


def test_o_mesmo_pedido_duas_vezes_conta_uma(ctx, tmp_path):
    bot = _bot(ctx, tmp_path)
    bot._db().execute("INSERT INTO tasks (id, title) VALUES (1, 'A')")
    bot._anotar_confirmacao(42, "tasks.drop", {"id": 1})
    bot._anotar_confirmacao(42, "tasks.drop", {"id": 1})
    assert len(bot._pendentes[42][0]) == 1


def test_o_lote_tem_teto(ctx, tmp_path):
    """Um 'sim' não deveria varrer a base, e ninguém lê trinta itens antes de responder."""
    from aide.channels.telegram_bot import LIMITE_CONFIRMACAO

    bot = _bot(ctx, tmp_path)
    for i in range(LIMITE_CONFIRMACAO + 8):
        bot._anotar_confirmacao(42, "tasks.drop", {"id": i})
    assert len(bot._pendentes[42][0]) == LIMITE_CONFIRMACAO


def test_a_descricao_e_feita_antes_de_apagar(ctx, tmp_path):
    """Depois de apagada a linha some, e a resposta viraria 'apaguei 1'."""
    bot = _bot(ctx, tmp_path)
    bot._db().execute("INSERT INTO notes (id, title, path) VALUES (1, 'Laudo', '/x')")
    bot._anotar_confirmacao(42, "notes.delete", {"id": 1})

    bot._tratar(_msg("sim"))
    assert "Laudo" in bot.enviadas[-1][1]


def test_a_resposta_vai_formatada(ctx, tmp_path):
    bot = _bot(ctx, tmp_path, llm=FakeLLM("#10 Pagar o IPVA (hoje)"))
    bot._tratar(_msg("o que tenho?"))
    assert "`#10`" in bot.enviadas[-1][1]


def test_se_o_telegram_recusar_a_formatacao_manda_sem(ctx, tmp_path):
    """Perder a resposta por causa do negrito seria trocar conteúdo por aparência."""
    from aide.channels.telegram import TelegramError

    bot = _bot(ctx, tmp_path, llm=FakeLLM("#10 Pagar o IPVA (hoje)"))
    tentativas = []

    def recusar_markdown(chat_id, text, markdown=False):
        tentativas.append(markdown)
        if markdown:
            raise TelegramError("400 can't parse entities")
        bot.enviadas.append((chat_id, text))

    bot.client.send_message = recusar_markdown
    bot._tratar(_msg("o que tenho?"))

    assert tentativas == [True, False]
    assert bot.enviadas[-1][1] == "#10 Pagar o IPVA (hoje)"


def test_o_historico_guarda_a_pergunta_e_nao_o_texto_descartado(ctx, tmp_path):
    """O modelo recebe 'não autorizado' e escreve 'não foi possível apagar'. Se
    isso ficar no histórico, na volta seguinte ele lê a própria fala, conclui
    que apagar não funciona e para de chamar a tool — foi o que aconteceu."""
    class LLMQueTentaApagar(FakeLLM):
        def __init__(self):
            super().__init__("Não foi possível apagar: ação não autorizada.")
            self.voltas = 0

        def complete(self, messages, *, fast=False, tools=None, purpose="chat", **extra):
            self.voltas += 1
            if self.voltas == 1:
                from aide.llm.base import LLMResponse
                return LLMResponse(text="", model="fake", tool_calls=[
                    {"id": "1", "function": {"name": "tasks_drop",
                                             "arguments": '{"id": 1}'}}])
            return super().complete(messages, fast=fast, tools=tools, purpose=purpose, **extra)

    bot = _bot(ctx, tmp_path, llm=LLMQueTentaApagar())
    conn = bot._db()
    conn.execute("INSERT INTO tasks (id, title) VALUES (1, 'Pagar o IPVA')")

    bot._tratar(_msg("apaga o IPVA"))

    gravadas = [r["content"] for r in conn.execute(
        "SELECT content FROM messages WHERE role = 'assistant' ORDER BY id")]
    assert any("Quer mesmo" in c for c in gravadas)
    assert not any("não foi possível" in c.lower() for c in gravadas)


def test_o_sim_e_o_desfecho_entram_na_conversa(ctx, tmp_path):
    """Sem isto o transcrito fica com uma pergunta e nenhuma resposta."""
    bot = _bot(ctx, tmp_path)
    conn = bot._db()
    conn.execute("INSERT INTO tasks (id, title) VALUES (1, 'Pagar o IPVA')")
    bot._sessoes[42] = "s-teste"
    bot._anotar_confirmacao(42, "tasks.drop", {"id": 1})

    bot._tratar(_msg("sim"))
    falas = [(r["role"], r["content"]) for r in conn.execute(
        "SELECT role, content FROM messages WHERE session_id = 's-teste' ORDER BY id")]
    assert ("user", "sim") in falas
    assert any(papel == "assistant" and "apaguei" in texto for papel, texto in falas)


def test_hoje_manda_o_prazo_escrito_e_nao_o_iso(ctx, tmp_path):
    """No celular chegava "2026-09-17T23:59-04:00" — carimbo de banco, não prazo."""
    bot = _bot(ctx, tmp_path)
    hoje = (now_in(ctx.config.timezone).replace(hour=23, minute=59)
            .isoformat(timespec="minutes"))
    tool_registry.call("tasks.create", {"title": "Fazer atividade do ICMC", "due": hoje},
                       bot._ctx(42))
    bot._tratar(_msg("/hoje", chat_id=42))

    texto = bot.enviadas[-1][1]
    assert "T23:59" not in texto
    assert "hoje 23:59" in texto


def test_hoje_vazio_diz_que_nada_vence_hoje(ctx, tmp_path):
    bot = _bot(ctx, tmp_path)
    bot._tratar(_msg("/hoje", chat_id=42))
    assert "Nada para hoje" in bot.enviadas[-1][1]


def test_confirmacao_no_telegram_nao_revela_nota_privada(ctx, tmp_path):
    """A pergunta vai por rede de terceiro: pedir para apagar uma nota privada
    devolvia o título dela no Telegram."""
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    bot = _bot(ctx, tmp_path)
    nota = tool_registry.call("notes.create", {"title": "Senha do cofre", "body": "x",
                                              "private": True}, bot._ctx(42)).data

    pergunta = bot._perguntar(([("notes_delete", {"id": nota["id"]})], 0))
    assert "Senha" not in pergunta
    assert "privada" in pergunta


def test_confirmacao_diz_o_que_e_e_nao_so_o_id(ctx, tmp_path):
    bot = _bot(ctx, tmp_path)
    tarefa = tool_registry.call("tasks.create", {"title": "Pagar o IPVA"}, bot._ctx(42)).data

    # o nome vem do modelo, com sublinhado: é a forma que chega de verdade, e
    # era ela que caía no formato cru
    pergunta = bot._perguntar(([("tasks_drop", {"id": tarefa["id"]})], 0))
    assert "Pagar o IPVA" in pergunta
    assert "apagar" in pergunta
    assert "tasks_drop" not in pergunta
    assert "{" not in pergunta


# ---------- sinal de vida enquanto trabalha ----------

def test_mostra_digitando_assim_que_a_mensagem_chega(ctx, tmp_path):
    """É o que diz "chegou, estou nisso" e evita você mandar de novo."""
    bot = _bot(ctx, tmp_path)
    bot._tratar(_msg("oi", chat_id=42))
    assert (42, "typing") in bot.acoes


def test_chat_nao_autorizado_nao_recebe_nem_digitando(ctx, tmp_path):
    """Responder qualquer coisa confirmaria que o bot existe."""
    bot = _bot(ctx, tmp_path)
    bot._tratar(_msg("oi", chat_id=99))
    assert bot.acoes == []
    assert bot.enviadas == []


def test_passo_renova_o_digitando(ctx, tmp_path):
    """O indicador do Telegram dura cinco segundos: sem renovar, ele some no meio
    de um trabalho longo."""
    bot = _bot(ctx, tmp_path)
    passo = bot._contar_passo(42)
    passo("olhando suas tarefas")
    passo("somando os gastos")
    assert bot.acoes.count((42, "typing")) == 2


def test_o_primeiro_passo_aparece_na_hora(ctx, tmp_path):
    """É a mensagem que tira a espera do escuro; esperar para mostrar seria o
    mesmo silêncio de antes, só mais curto."""
    bot = _bot(ctx, tmp_path)
    bot._contar_passo(42)("olhando suas tarefas")

    assert bot.enviadas == [(42, "· olhando suas tarefas")]


def test_os_passos_crescem_na_mesma_mensagem(ctx, tmp_path, monkeypatch):
    """Como no terminal: a lista do que foi consultado vai crescendo. Uma
    mensagem por passo encheria o chat."""
    import aide.channels.telegram_bot as mod

    monkeypatch.setattr(mod, "EDICAO_A_CADA_SEGUNDOS", 0)
    bot = _bot(ctx, tmp_path)
    passo = bot._contar_passo(42)
    passo("olhando suas tarefas")
    passo("somando os gastos")
    passo("olhando a agenda")

    # uma mensagem só, editada
    assert len(bot.enviadas) == 1
    assert bot.editadas[-1][0] == 101
    assert bot.editadas[-1][1] == ("· olhando suas tarefas\n· somando os gastos\n"
                                   "· olhando a agenda")


def test_edicao_respeita_a_folga_do_telegram(ctx, tmp_path):
    """O Telegram recusa edição em rajada: sem a folga, um turno com seis tools
    tentaria seis edições seguidas."""
    bot = _bot(ctx, tmp_path)
    passo = bot._contar_passo(42)
    passo("olhando suas tarefas")
    passo("somando os gastos")

    assert bot.editadas == []          # a segunda caiu dentro da folga


def test_a_lista_sai_do_chat_quando_termina(ctx, tmp_path):
    """Passada a espera, ela só empurra a conversa para cima. O que foi
    consultado continua na trilha de auditoria."""
    bot = _bot(ctx, tmp_path)
    passo = bot._contar_passo(42)
    passo("olhando suas tarefas")
    passo.fechar()

    assert bot.apagadas == [101]


def test_fechar_sem_passo_nenhum_nao_mexe_no_chat(ctx, tmp_path):
    bot = _bot(ctx, tmp_path)
    bot._contar_passo(42).fechar()
    assert bot.enviadas == []
    assert bot.editadas == []
    assert bot.apagadas == []


def test_pensar_nao_vira_passo(ctx, tmp_path):
    """"· pensando" não informaria nada que o "digitando" já não diga."""
    from aide.channels import passos

    bot = _bot(ctx, tmp_path)
    bot._contar_passo(42)(passos.PENSANDO)
    assert bot.enviadas == []
    assert (42, "typing") in bot.acoes


def test_a_lista_de_passos_nao_entra_no_historico(ctx, tmp_path):
    """É relato de trabalho, não fala do assessor: no histórico o modelo leria de
    volta como se tivesse dito."""
    bot = _bot(ctx, tmp_path)
    bot._contar_passo(42)("olhando suas tarefas")

    guardadas = bot._db().execute(
        "SELECT content FROM messages WHERE content LIKE '%olhando%'").fetchall()
    assert guardadas == []


def test_progresso_que_nao_foi_entregue_nao_derruba_a_conversa(ctx, tmp_path):
    from aide.channels.telegram import TelegramError

    bot = _bot(ctx, tmp_path)

    def recusar(*a, **k):
        raise TelegramError("400")

    bot.client.send_message = recusar
    passo = bot._contar_passo(42)
    passo("olhando suas tarefas")   # não levanta
    passo.fechar()


def test_erro_diz_que_a_mensagem_nao_foi_perdida(ctx, tmp_path, monkeypatch):
    """Sem isso a dúvida fica: reenvio ou não?"""
    bot = _bot(ctx, tmp_path)
    monkeypatch.setattr(bot, "_resolver", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    bot._tratar(_msg("oi", chat_id=42))

    assert "não foi perdida" in bot.enviadas[-1][1]


def test_o_progresso_nao_chega_ao_modelo(ctx, tmp_path):
    """Pergunta do dono: isso gasta token? Não. A lista de passos é mensagem do
    Telegram, não fala da conversa: ela não entra em `messages`, então não entra
    no histórico nem no prompt da volta seguinte."""
    vistas = []

    class LLMQueEspia(FakeLLM):
        def complete(self, messages, tools=None, purpose="chat", **kwargs):
            vistas.append([(m.role, m.content or "") for m in messages])
            return super().complete(messages, tools=tools, purpose=purpose, **kwargs)

    bot = _bot(ctx, tmp_path, llm=LLMQueEspia())
    bot._contar_passo(42)("olhando suas tarefas")
    bot._tratar(_msg("e agora?", chat_id=42))

    tudo = " ".join(conteudo for volta in vistas for _, conteudo in volta)
    assert "olhando suas tarefas" not in tudo
