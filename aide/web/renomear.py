"""Renomear ou mover uma nota sem quebrar quem aponta para ela.

Como o Obsidian faz: depois de mover, cada [[link]] e cada [texto](x.md) que
levava à nota passa a levar ao lugar novo, nas outras notas e na própria (os
links markdown dela são relativos à pasta, e a pasta mudou). Só a linha onde
o mapa achou o link é mexida, e nunca dentro de `código`: o texto em volta
fica como você escreveu.
"""

from __future__ import annotations

import logging
import posixpath
import re
from pathlib import Path
from urllib.parse import quote, unquote

from aide.storage import links, vault
from aide.web import grafo
from aide.web.markdown import Citacao

log = logging.getLogger(__name__)

CODIGO = re.compile(r"(`+)(.*?)\1")


def _fora_do_codigo(linha: str, trocar) -> str:
    """Aplica `trocar` só nos trechos da linha fora de `código`."""
    partes, ultimo = [], 0
    for casado in CODIGO.finditer(linha):
        partes.append(trocar(linha[ultimo:casado.start()]))
        partes.append(casado.group(0))
        ultimo = casado.end()
    partes.append(trocar(linha[ultimo:]))
    return "".join(partes)


def _como_wikilink(destino: str, origem: str, indice: links.Indice) -> str:
    """O nome curto, se ele leva ao destino a partir de `origem`; senão o
    caminho — dois arquivos com o mesmo nome exigem a pasta."""
    curto = destino.rpartition("/")[2].removesuffix(".md")
    return curto if indice.resolver(curto, origem) == destino else destino.removesuffix(".md")


def _como_href(destino: str, origem: str) -> str:
    """O caminho relativo à pasta de `origem`, como o Obsidian grava."""
    relativo = posixpath.relpath(destino, origem.rpartition("/")[0] or ".")
    return quote(relativo, safe="/")


def _trocar_na_linha(linha: str, citacao: Citacao, novo_wiki: str, novo_href: str) -> str:
    if citacao.tipo == "wiki":
        padrao = re.compile(r"(!?\[\[)\s*" + re.escape(citacao.alvo) + r"\s*(?=[#|\]])")
        return _fora_do_codigo(linha, lambda t: padrao.sub(
            lambda m: m.group(1) + novo_wiki, t))
    caminho = citacao.alvo.partition("#")[0]
    for escrito in dict.fromkeys((caminho, unquote(caminho))):
        padrao = re.compile(r"\]\(\s*<?" + re.escape(escrito) + r">?(#[^)\s]*)?\s*\)")
        if padrao.search(linha):
            return _fora_do_codigo(linha, lambda t, p=padrao: p.sub(
                lambda m: f"]({novo_href}{m.group(1) or ''})", t))
    return linha


def _reescrever(raiz: Path, mudancas: dict[str, str], ligacoes: list[grafo.Ligacao],
                puladas: list[str] | None = None) -> list[str]:
    """Conserta os links depois que as notas de `mudancas` (velho -> novo)
    mudaram de lugar. `ligacoes` é o mapa de antes da mudança.

    Nunca falha no meio: o arquivo já mudou de lugar, e um erro aqui deixava
    o banco no caminho velho. A nota que não dá para ler ou gravar (fora de
    UTF-8, sem permissão) fica como está e vai para `puladas`."""
    depois = links.indice(raiz)

    def onde_esta(caminho: str) -> str:
        return mudancas.get(caminho, caminho)

    trocas: dict[str, list[tuple[Citacao, str]]] = {}
    for lig in ligacoes:
        # sem destino, ou só "#seção" da própria nota: nada a trocar
        if lig.destino is None or not lig.citacao.alvo or lig.citacao.alvo.startswith("#"):
            continue
        aponta_para_movida = lig.destino in mudancas
        # os links markdown de uma nota movida são relativos à pasta dela
        relativo_de_movida = lig.origem in mudancas and lig.citacao.tipo == "md"
        # [[Ideias]] apontava para Arquivo/Ideias; outra "Ideias" chegou na
        # pasta de quem cita e, pela regra da mesma pasta, roubaria o link.
        # O texto não mudou, mas o destino sim — então o texto passa a dizer
        # o caminho, para continuar levando aonde levava
        roubado = (lig.citacao.tipo == "wiki" and not aponta_para_movida
                   and depois.resolver(lig.citacao.alvo, onde_esta(lig.origem)) != lig.destino)
        if aponta_para_movida or relativo_de_movida or roubado:
            trocas.setdefault(onde_esta(lig.origem), []).append(
                (lig.citacao, onde_esta(lig.destino)))

    mudadas = []
    for nota, lista in trocas.items():
        try:
            mudou = _reescrever_nota(raiz, nota, lista, depois)
        except (OSError, UnicodeDecodeError, vault.ForaDoVault):
            log.warning("não consegui atualizar os links de %s", nota, exc_info=True)
            if puladas is not None:
                puladas.append(nota)
            continue
        if mudou:
            mudadas.append(nota)
    return mudadas


def _reescrever_nota(raiz: Path, nota: str, lista: list[tuple[Citacao, str]],
                     depois: links.Indice) -> bool:
    """Troca os links de uma nota; True se o texto mudou."""
    arquivo = vault.resolver(raiz, nota)
    texto = arquivo.read_text(encoding="utf-8")
    linhas = texto.split("\n")
    for citacao, destino in lista:
        if citacao.linha >= len(linhas):
            continue
        linhas[citacao.linha] = _trocar_na_linha(
            linhas[citacao.linha], citacao,
            _como_wikilink(destino, nota, depois), _como_href(destino, nota))
    novo = "\n".join(linhas)
    if novo == texto:
        return False
    vault.gravar(arquivo, novo)
    return True


def _novo_link_do_elemento(citacao: Citacao, destino: str, desenho: str,
                           depois: links.Indice) -> str:
    """O link do elemento (em `citacao.trecho`, como está no arquivo) levando
    a `destino`, no mesmo formato: [[...]], nome solto ou caminho .md relativo
    ao desenho. Seção e apelido ficam."""
    escrito = citacao.trecho
    if citacao.tipo == "md":
        fragmento = escrito.partition("#")[2]
        return _como_href(destino, desenho) + ("#" + fragmento if fragmento else "")
    nome = _como_wikilink(destino, desenho, depois)
    if escrito.startswith("[["):
        return re.sub(r"^\[\[\s*" + re.escape(citacao.alvo) + r"\s*(?=[#|\]])",
                      lambda _: "[[" + nome, escrito, count=1)
    resto = escrito.partition("#")
    return nome + resto[1] + resto[2]


def _reescrever_desenhos(raiz: Path, notas: dict[str, str], desenhos_: dict[str, str],
                         ligacoes: list[grafo.Ligacao],
                         puladas: list[str] | None = None) -> list[str]:
    """Conserta o link dos elementos dos desenhos (`Mapa.de_desenhos`, de
    antes da mudança) depois que notas (`notas`) e desenhos (`desenhos_`)
    mudaram de lugar — velho -> novo. A mesma regra das notas: o link que
    levava à movida, o .md relativo de um desenho movido e o que outra nota
    de mesmo nome roubaria. Devolve os desenhos que mudaram.

    `desenhos.gravar` mantém a marca de privado do disco; a versão do
    elemento sobe, e a tela aberta vê o desenho mudado por fora."""
    import json
    import time

    from aide.storage import desenhos

    depois = links.indice(raiz)
    trocas: dict[str, dict[str, str]] = {}
    for lig in ligacoes:
        if lig.destino is None:
            continue
        desenho = desenhos_.get(lig.origem, lig.origem)
        destino = notas.get(lig.destino, lig.destino)
        if (destino != lig.destino or lig.citacao.tipo == "md" and desenho != lig.origem
                or lig.citacao.tipo == "wiki"
                and depois.resolver(lig.citacao.alvo, desenho) != destino):
            novo = _novo_link_do_elemento(lig.citacao, destino, desenho, depois)
            if novo != lig.citacao.trecho:
                trocas.setdefault(desenho, {})[lig.citacao.trecho] = novo

    mudados = []
    for desenho, por_link in trocas.items():
        try:
            arquivo = desenhos.resolver(raiz, desenho)
            _, dados = desenhos.ler(arquivo)
            mudou = False
            for elemento in dados.get("elements", []):
                link = elemento.get("link")
                if isinstance(link, str) and link.strip() in por_link:
                    elemento["link"] = por_link[link.strip()]
                    elemento["version"] = elemento.get("version", 0) + 1
                    elemento["updated"] = int(time.time() * 1000)
                    mudou = True
            if not mudou:
                continue
            desenhos.gravar(arquivo, json.dumps(dados, ensure_ascii=False, indent=2) + "\n")
        except (OSError, desenhos.DesenhoInvalido, vault.ForaDoVault):
            log.warning("não consegui atualizar os links do desenho %s", desenho, exc_info=True)
            if puladas is not None:
                puladas.append(desenho)
            continue
        mudados.append(desenho)
    return mudados


def mover(raiz: Path, de: str, para: str, puladas: list[str] | None = None,
          desenhos_mudados: list[str] | None = None) -> list[str]:
    """Move a nota `de` para `para` (caminhos no vault) e conserta os links.

    Devolve os caminhos das notas cujo texto mudou; as que não deu para
    atualizar vão para `puladas`. Com `desenhos_mudados`, conserta também o
    link dos elementos dos desenhos e põe ali os que mudaram (desenho não
    entra no índice: por isso fora da lista das notas). Quem chama já
    conferiu os dois caminhos e cuida do índice e da auditoria.
    """
    mapa = grafo.mapa(raiz)
    vault.mover(vault.resolver(raiz, de), vault.resolver(raiz, para))
    mudadas = _reescrever(raiz, {de: para}, mapa.ligacoes, puladas)
    if desenhos_mudados is not None:
        desenhos_mudados += _reescrever_desenhos(raiz, {de: para}, {}, mapa.de_desenhos, puladas)
    return mudadas


def mover_pasta(raiz: Path, de: str, para: str, puladas: list[str] | None = None,
                desenhos_mudados: list[str] | None = None) -> tuple[dict[str, str], list[str]]:
    """Move a pasta `de` para `para` e conserta os links das notas de dentro.

    Devolve (velho -> novo de cada nota movida, notas cujo texto mudou). Link
    por nome curto continua valendo; quem muda é [[Pasta/Nota]] e o link
    markdown relativo que entra ou sai da pasta. `desenhos_mudados` como no
    `mover`; os desenhos de dentro da pasta vão junto.
    """
    from aide.storage import desenhos

    origem = vault.resolver(raiz, de, pasta=True)
    destino = vault.resolver(raiz, para, pasta=True)
    if destino == origem or destino.is_relative_to(origem):
        raise ValueError("uma pasta não pode ir para dentro dela mesma")
    indice = links.indice(raiz)
    prefixo = de.rstrip("/") + "/"
    mudancas = {c: para.rstrip("/") + "/" + c[len(prefixo):]
                for c in indice.caminhos if c.startswith(prefixo)}
    mapa = grafo.mapa(raiz, indice)
    de_desenhos = {c: para.rstrip("/") + "/" + c[len(prefixo):]
                   for c in desenhos.indice(raiz).por_caminho.values() if c.startswith(prefixo)}
    vault.mover_pasta(origem, destino)
    mudadas = _reescrever(raiz, mudancas, mapa.ligacoes, puladas)
    if desenhos_mudados is not None:
        desenhos_mudados += _reescrever_desenhos(raiz, mudancas, de_desenhos, mapa.de_desenhos,
                                                 puladas)
    return mudancas, mudadas


def ligar(raiz: Path, alvo: str, para: str, puladas: list[str] | None = None) -> list[str]:
    """Faz os links quebrados para `alvo` (o nome como foi escrito) levarem à
    nota `para`, que existe — o conserto de um nome digitado errado. Seção e
    apelido ([[alvo#seção|apelido]]) ficam como estavam.

    Devolve as notas cujo texto mudou; as que não deu para gravar vão para
    `puladas`, como no mover."""
    from aide.web.markdown import chave_link

    chave = chave_link(alvo.rpartition("/")[2])
    trocas: dict[str, list[tuple[Citacao, str]]] = {}
    for lig in grafo.mapa(raiz).quebrados():
        nome = lig.citacao.caminho_pedido(lig.origem).rpartition("/")[2]
        if chave_link(nome) == chave:
            trocas.setdefault(lig.origem, []).append((lig.citacao, para))
    depois = links.indice(raiz)
    mudadas = []
    for nota, lista in trocas.items():
        try:
            mudou = _reescrever_nota(raiz, nota, lista, depois)
        except (OSError, UnicodeDecodeError, vault.ForaDoVault):
            log.warning("não consegui religar os links de %s", nota, exc_info=True)
            if puladas is not None:
                puladas.append(nota)
            continue
        if mudou:
            mudadas.append(nota)
    return mudadas


def mover_desenho(raiz: Path, de: str, para: str,
                  puladas: list[str] | None = None) -> list[str]:
    """Move o desenho `de` para `para` e conserta os [[...excalidraw]] das notas.

    O mapa de notas não conhece link de desenho, então este lê as notas aqui
    mesmo, uma vez, antes de mover. Troca o link que levava ao desenho e,
    como no mover de nota, o que outro desenho de mesmo nome passaria a
    "roubar" pela regra da mesma pasta: o texto vira o caminho de antes.

    Devolve as notas cujo texto mudou; as que não deu para ler ou gravar vão
    para `puladas`. Quem chama já conferiu os dois caminhos."""
    from aide.storage import desenhos
    from aide.web.markdown import citacoes
    from aide.web.notas_api import TAMANHO_MAXIMO

    antes = desenhos.indice(raiz)
    citadas: dict[str, list[tuple[Citacao, str]]] = {}
    for nota in links.indice(raiz).caminhos:
        try:
            arquivo = vault.resolver(raiz, nota)
            if arquivo.stat().st_size > TAMANHO_MAXIMO:
                continue
            texto = arquivo.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, vault.ForaDoVault):
            continue
        for citacao in citacoes(texto, de_desenho=True):
            destino = antes.resolver(citacao.alvo, nota)
            if destino is not None:
                citadas.setdefault(nota, []).append((citacao, destino))

    vault.mover(desenhos.resolver(raiz, de), desenhos.resolver(raiz, para))
    depois = desenhos.indice(raiz)

    def como_link(destino: str, nota: str) -> str:
        curto = destino.rpartition("/")[2]
        return curto if depois.resolver(curto, nota) == destino else destino

    mudadas = []
    for nota, lista in citadas.items():
        trocas = []
        for citacao, destino in lista:
            novo_destino = para if destino == de else destino
            if novo_destino != destino or depois.resolver(citacao.alvo, nota) != destino:
                trocas.append((citacao, como_link(novo_destino, nota)))
        if not trocas:
            continue
        try:
            arquivo = vault.resolver(raiz, nota)
            texto = arquivo.read_text(encoding="utf-8")
            linhas = texto.split("\n")
            for citacao, novo in trocas:
                if citacao.linha < len(linhas):
                    linhas[citacao.linha] = _trocar_na_linha(linhas[citacao.linha], citacao,
                                                             novo, "")
            novo_texto = "\n".join(linhas)
            if novo_texto == texto:
                continue
            vault.gravar(arquivo, novo_texto)
        except (OSError, UnicodeDecodeError, vault.ForaDoVault):
            log.warning("não consegui atualizar os links de desenho em %s", nota, exc_info=True)
            if puladas is not None:
                puladas.append(nota)
            continue
        mudadas.append(nota)
    return mudadas
