from aide.channels.telegram import TelegramError
from aide.channels.telegram_bot import TelegramBot
from aide.llm.base import LLMProvider, LLMResponse
from aide.storage import connect, migrate
from aide.tools import registry as tool_registry


class FakeLLM(LLMProvider):
    def __init__(self, text="ok"):
        self.text = text
        self.vistas = []

    def complete(self, messages, *, fast=False, tools=None, purpose="chat"):
        self.vistas.append(messages)
        return LLMResponse(text=self.text, model="fake")


def _bot(ctx, tmp_path, permitidos=(42,), llm=None):
    object.__setattr__(ctx.config.telegram, "token", "x")
    object.__setattr__(ctx.config.telegram, "allowed_chat_ids", tuple(permitidos))
    caminho = tmp_path / "b.db"
    migrate(connect(caminho))
    bot = TelegramBot(ctx.config, lambda: connect(caminho), llm or FakeLLM(), tool_registry)
    bot.enviadas = []
    bot.client.send_message = lambda chat_id, text: bot.enviadas.append((chat_id, text))
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


def test_chat_nao_autorizado_nao_recebe_dados(ctx, tmp_path):
    bot = _bot(ctx, tmp_path, permitidos=(42,))
    bot._tratar(_msg("/hoje", chat_id=999))
    destino, texto = bot.enviadas[0]
    assert destino == 999
    assert "pessoal" in texto
    assert "#" not in texto  # nenhuma tarefa vazou


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
