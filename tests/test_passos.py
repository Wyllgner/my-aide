"""O que o assessor está fazendo agora, em palavras.

Sem sinal durante o trabalho não há como saber se travou, e a reação natural é
mandar a mesma coisa de novo, o que faz o assessor trabalhar duas vezes.
"""

from aide.channels import passos


def test_frase_por_tool():
    assert passos.descrever("notes.search") == "procurando nas suas notas"
    assert passos.descrever("expenses.add") == "anotando o gasto"


def test_aceita_o_nome_com_sublinhado():
    """É a forma que o modelo devolve, e a que chega no aviso."""
    assert passos.descrever("notes_search") == passos.descrever("notes.search")


def test_tool_sem_frase_propria_nao_fica_muda():
    """Um passo que não aparece é o silêncio que este módulo existe para tirar."""
    frase = passos.descrever("xpto.fazer_coisa")
    assert frase
    assert "xpto" in frase


def test_toda_tool_registrada_tem_frase():
    """Tool nova sem frase cai no genérico, que serve mas é pior: este teste
    lembra de escrever a frase junto com a tool."""
    import aide.cli  # noqa: F401  (registra as tools)
    from aide.tools import registry

    sem_frase = [n for n in registry.names() if n not in passos.FRASES]
    assert sem_frase == [], sem_frase
