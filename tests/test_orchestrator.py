from aide.config import load_config
from aide.core.orchestrator import Orchestrator, record_usage
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
