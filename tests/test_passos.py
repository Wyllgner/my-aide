"""O que o assessor está fazendo agora, em palavras.

Sem sinal durante o trabalho não há como saber se travou, e a reação natural é
mandar a mesma coisa de novo, o que faz o assessor trabalhar duas vezes.
"""

from aide.channels import passos


def test_frase_por_tool_nas_duas_formas():
    """A lista mostra as duas ao mesmo tempo: o que terminou e o que está em
    andamento. Sem o passado, o passo concluído continuaria escrito como se
    ainda estivesse acontecendo."""
    assert passos.fazendo("notes.search") == "procurando nas suas notas"
    assert passos.feito("notes.search") == "procurei nas suas notas"
    assert passos.fazendo("expenses.summary") == "somando seus gastos do mês"
    assert passos.feito("expenses.summary") == "somei seus gastos do mês"


def test_aceita_o_nome_com_sublinhado():
    """É a forma que o modelo devolve, e a que chega no aviso."""
    assert passos.fazendo("notes_search") == passos.fazendo("notes.search")
    assert passos.feito("notes_search") == passos.feito("notes.search")


def test_nenhuma_frase_cita_o_nome_da_tool():
    """Quem lê não tem por que saber que existe uma `tasks.list`."""
    for fazendo, feito in passos.FRASES.values():
        assert "." not in fazendo and "_" not in fazendo, fazendo
        assert "." not in feito and "_" not in feito, feito


def test_tool_sem_frase_propria_nao_fica_muda():
    """Um passo que não aparece é o silêncio que este módulo existe para tirar."""
    assert "xpto" in passos.fazendo("xpto.fazer_coisa")
    assert "xpto" in passos.feito("xpto.fazer_coisa")


def test_toda_tool_registrada_tem_as_duas_frases():
    """Tool nova sem frase cai no genérico, que serve mas é pior: este teste
    lembra de escrever a frase junto com a tool."""
    import aide.cli  # noqa: F401  (registra as tools)
    from aide.tools import registry

    sem_frase = [n for n in registry.names() if n not in passos.FRASES]
    assert sem_frase == [], sem_frase
    incompletas = [n for n, par in passos.FRASES.items() if len(par) != 2 or not all(par)]
    assert incompletas == [], incompletas
