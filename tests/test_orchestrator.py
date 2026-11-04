import json

import pytest

from aide.config import load_config
from aide.core.orchestrator import (
    COBRANCA,
    NAO_LANCOU,
    Orchestrator,
    anuncia_gasto,
    record_usage,
)
from aide.llm.base import LLMProvider, LLMResponse
from aide.storage import connect, migrate


class FakeLLM(LLMProvider):
    def __init__(self, sink=None):
        self.seen = []
        self.sink = sink

    def complete(self, messages, *, fast=False, tools=None, purpose="chat", **extra):
        self.seen.append(messages)
        if self.sink:
            self.sink("fake-model", purpose, 10, 5, 42)
        return LLMResponse(text=f"ok:{messages[-1].content}", model="fake-model",
                           input_tokens=10, output_tokens=5)


def _agent(tmp_path):
    config = load_config()
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    llm = FakeLLM(sink=record_usage(conn))
    return Orchestrator(config, conn, llm), conn, llm


def test_persiste_a_conversa(tmp_path):
    agent, conn, _ = _agent(tmp_path)
    assert agent.ask("oi") == "ok:oi"
    agent.ask("de novo")
    rows = conn.execute("SELECT role, content FROM messages ORDER BY id").fetchall()
    assert [r["role"] for r in rows] == ["user", "assistant", "user", "assistant"]


def test_prompt_tem_system_e_historico(tmp_path):
    agent, _, llm = _agent(tmp_path)
    agent.ask("primeira")
    agent.ask("segunda")
    sent = llm.seen[-1]
    assert sent[0].role == "system"
    assert "assessor pessoal" in sent[0].content
    assert sent[-1].content == "segunda"
    assert any(m.content == "primeira" for m in sent)


def test_historico_respeita_o_limite(tmp_path):
    agent, _, llm = _agent(tmp_path)
    for i in range(20):
        agent.ask(f"m{i}")
    assert len(llm.seen[-1]) <= agent.config.history_messages + 1


def test_uso_de_llm_e_registrado(tmp_path):
    agent, conn, _ = _agent(tmp_path)
    agent.ask("oi")
    row = conn.execute("SELECT model, input_tokens, output_tokens FROM llm_usage").fetchone()
    assert row["model"] == "fake-model"
    assert row["input_tokens"] == 10


def test_migrate_e_idempotente(tmp_path):
    conn = connect(tmp_path / "m.db")
    aplicadas = migrate(conn)
    assert aplicadas[0] == "001_init.sql"
    assert aplicadas == sorted(aplicadas)  # ordem numérica
    assert migrate(conn) == []


def test_sink_aceita_conexao_e_fabrica(tmp_path):
    """sqlite3.Connection tem __call__, então callable() não distingue os dois."""
    from aide.storage import connect, migrate

    conn = connect(tmp_path / "u.db")
    migrate(conn)

    record_usage(conn)("m", "p", 1, 2, 3)
    record_usage(lambda: conn)("m", "p", 4, 5, 6)

    linhas = conn.execute("SELECT input_tokens FROM llm_usage ORDER BY id").fetchall()
    assert [r["input_tokens"] for r in linhas] == [1, 4]


# ---------- o prompt conhece as categorias declaradas ----------

def test_prompt_usa_as_categorias_que_tem_teto(ctx):
    """Sem isto o modelo escrevia "transporte" onde o teto é "uber", e a regra de
    orçamento, que casa por nome exato, não encontrava nada."""
    from aide.config import GastosConfig
    from aide.core.context import system_prompt

    object.__setattr__(ctx.config, "gastos",
                       GastosConfig(tetos_centavos={"uber": 50_00, "dates": 200_00}))
    texto = system_prompt(ctx.config).content
    assert "uber, dates" in texto
    assert "assinatura" not in texto


def test_sem_teto_o_prompt_mantem_as_categorias_de_sempre(ctx):
    from aide.core.context import system_prompt

    texto = system_prompt(ctx.config).content
    assert "alimentação" in texto


def test_prompt_escreve_o_dia_da_semana_em_portugues(ctx):
    """`%A` segue o locale da máquina, que aqui é C: o modelo lia "Monday"."""
    from aide.core.context import system_prompt

    texto = system_prompt(ctx.config).content
    assert "Monday" not in texto and "Sunday" not in texto
    assert any(dia in texto for dia in
               ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"))


# ---------- avisos de progresso ----------

def test_conta_cada_passo_para_quem_quiser_ouvir(ctx, registry):
    """A conversa fica muda enquanto o modelo pensa e chama tools; sem isso não
    há como o canal mostrar "digitando" nem dizer em que ponto está."""
    from aide.core.orchestrator import Orchestrator

    class LLMComTool:
        def __init__(self):
            self.vezes = 0

        def complete(self, messages, tools=None, purpose="chat", **kwargs):
            from aide.llm.base import LLMResponse

            self.vezes += 1
            if self.vezes == 1:
                return LLMResponse(text="", model="dublê", tool_calls=[
                    {"id": "1", "function": {"name": "tasks_list", "arguments": "{}"}}])
            return LLMResponse(text="pronto", model="dublê", tool_calls=[])

    ditos = []
    agente = Orchestrator(ctx.config, ctx.conn, LLMComTool(), registry=registry,
                          progresso=ditos.append)
    assert agente.ask("o que tenho pra hoje?") == "pronto"

    # manda o nome da tool, não a frase: o Telegram escreve o mesmo passo de
    # dois jeitos (fazendo e feito), e quem sabe disso é o canal
    assert "pensando" in ditos
    assert "tasks_list" in ditos
    # a ordem importa: pensar vem antes de agir
    assert ditos.index("pensando") < ditos.index("tasks_list")


def test_ouvinte_quebrado_nao_derruba_a_conversa(ctx, registry):
    """O aviso é enfeite; perder a resposta por causa dele seria trocar o
    silêncio por um erro."""
    from aide.core.orchestrator import Orchestrator

    class LLMSimples:
        def complete(self, messages, tools=None, purpose="chat", **kwargs):
            from aide.llm.base import LLMResponse

            return LLMResponse(text="tudo bem", model="dublê", tool_calls=[])

    def explode(frase):
        raise RuntimeError("boom")

    agente = Orchestrator(ctx.config, ctx.conn, LLMSimples(), registry=registry,
                          progresso=explode)
    assert agente.ask("oi") == "tudo bem"


def test_sem_ouvinte_nada_muda(ctx, registry):
    from aide.core.orchestrator import Orchestrator

    class LLMSimples:
        def complete(self, messages, tools=None, purpose="chat", **kwargs):
            from aide.llm.base import LLMResponse

            return LLMResponse(text="oi", model="dublê", tool_calls=[])

    assert Orchestrator(ctx.config, ctx.conn, LLMSimples(), registry=registry).ask("oi") == "oi"


def test_prompt_ensina_a_seguir_e_a_criar_links(ctx):
    """Sem isto as tools existem e o assessor nunca as usa."""
    from aide.core.context import system_prompt

    texto = system_prompt(ctx.config, ctx.conn).content
    assert "`notes.links`" in texto
    assert "`relacionadas`" in texto
    assert "nao_encontradas" in texto


# ---------- dizer que anotou sem ter anotado ----------

class _LLMRoteirizado:
    """Responde na ordem dada; um dict vira chamada de tool."""

    def __init__(self, *falas):
        self.falas = list(falas)
        self.vistas = []

    def complete(self, messages, tools=None, purpose="chat", **kwargs):
        self.vistas.append(list(messages))
        fala = self.falas.pop(0)
        if isinstance(fala, dict):
            chamada = {"id": "c1", "function": {"name": fala["tool"],
                                                "arguments": json.dumps(fala["args"])}}
            return LLMResponse(text="", model="m", input_tokens=1, output_tokens=1,
                               tool_calls=[chamada])
        return LLMResponse(text=fala, model="m", input_tokens=1, output_tokens=1)


_GASTO = {"tool": "expenses_add", "args": {"amount": "73,99", "description": "alimentação"}}
_FALSA = "Anotei, R$ 73,99 em alimentação · casal (#95)."
_CERTA = "Anotei, R$ 73,99 em alimentação (#1)."


def _gastos(ctx):
    return ctx.conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]


def test_anunciar_sem_gravar_cobra_a_tool_e_o_gasto_entra(ctx, registry):
    llm = _LLMRoteirizado(_FALSA, _GASTO, _CERTA)
    agente = Orchestrator(ctx.config, ctx.conn, llm, registry=registry)
    assert agente.ask("73,99 alimentação") == _CERTA
    assert _gastos(ctx) == 1
    assert llm.vistas[1][-1].content == COBRANCA


def test_a_fala_falsa_nao_fica_no_historico(ctx, registry):
    agente = Orchestrator(ctx.config, ctx.conn, _LLMRoteirizado(_FALSA, _GASTO, _CERTA),
                          registry=registry)
    agente.ask("73,99 alimentação")
    falas = [r[0] for r in ctx.conn.execute("SELECT content FROM messages")]
    assert _FALSA not in falas and COBRANCA not in falas


def test_insistir_em_anunciar_vira_aviso_de_que_nao_lancou(ctx, registry):
    agente = Orchestrator(ctx.config, ctx.conn, _LLMRoteirizado(_FALSA, _FALSA),
                          registry=registry)
    assert agente.ask("73,99 alimentação") == NAO_LANCOU
    assert _gastos(ctx) == 0
    falas = [r[0] for r in ctx.conn.execute("SELECT content FROM messages")]
    assert _FALSA not in falas and NAO_LANCOU in falas


def test_lancamento_de_verdade_passa_sem_cobranca(ctx, registry):
    llm = _LLMRoteirizado(_GASTO, _CERTA)
    agente = Orchestrator(ctx.config, ctx.conn, llm, registry=registry)
    assert agente.ask("73,99 alimentação") == _CERTA
    assert len(llm.vistas) == 2


def test_tool_que_falhou_nao_autoriza_dizer_que_anotou(ctx, registry):
    ruim = {"tool": "expenses_add", "args": {"amount": "abc", "description": "x"}}
    llm = _LLMRoteirizado(ruim, _FALSA, "Não consegui ler o valor.")
    agente = Orchestrator(ctx.config, ctx.conn, llm, registry=registry)
    assert agente.ask("abc de alimentação") == "Não consegui ler o valor."
    assert llm.vistas[2][-1].content == COBRANCA


def test_tool_de_leitura_nao_autoriza_dizer_que_anotou(ctx, registry):
    leitura = {"tool": "expenses_list", "args": {}}
    agente = Orchestrator(ctx.config, ctx.conn, _LLMRoteirizado(leitura, _FALSA, _FALSA),
                          registry=registry)
    assert agente.ask("73,99 alimentação") == NAO_LANCOU


@pytest.mark.parametrize("texto", [
    "Anotei, R$ 73,99 em alimentação (#95).", "Pronto, lancei R$ 10 no mercado.",
    "Registrado: #95.", "ok, anotado: R$ 5,00", "**Anotei** R$ 5,00",
])
def test_reconhece_anuncio_de_gasto(texto):
    assert anuncia_gasto(texto)


@pytest.mark.parametrize("texto", [
    "Não anotei o gasto de R$ 5,00.", "Sim, o #94 foi lançado hoje.",
    "Seus últimos gastos:\n#94 Casa (R$ 8,16)", "Anotei isso sobre você.",
    "Quer que eu lance os R$ 73,99?", "O #95 não aparece nos lançamentos.",
])
def test_nao_confunde_conversa_com_anuncio(texto):
    assert not anuncia_gasto(texto)


def test_prompt_proibe_confirmar_sem_a_tool(ctx):
    from aide.core.context import system_prompt

    assert "sem a tool ter devolvido" in system_prompt(ctx.config).content
