"""Renomear ou mover uma nota sem quebrar quem aponta para ela.

Como o Obsidian faz: depois de mover, cada [[link]] e cada [texto](x.md) que
levava à nota passa a levar ao lugar novo, nas outras notas e na própria (os
links markdown dela são relativos à pasta, e a pasta mudou). Só a linha onde
o mapa achou o link é mexida, e nunca dentro de `código`: o texto em volta
fica como você escreveu.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path
from urllib.parse import quote, unquote

from aide.storage import links, vault
from aide.web import grafo
from aide.web.markdown import Citacao

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


def mover(raiz: Path, de: str, para: str) -> list[str]:
    """Move a nota `de` para `para` (caminhos no vault) e conserta os links.

    Devolve os caminhos das notas cujo texto mudou. Quem chama já conferiu
    os dois caminhos e cuida do índice e da auditoria.
    """
    antes = links.indice(raiz)
    ligacoes = grafo.mapa(raiz, antes).ligacoes
    vault.mover(vault.resolver(raiz, de), vault.resolver(raiz, para))
    depois = links.indice(raiz)

    def onde_esta(caminho: str) -> str:
        return para if caminho == de else caminho

    # (nota, linha) -> citações a trocar ali, com o destino de cada uma
    trocas: dict[str, list[tuple[Citacao, str]]] = {}
    for lig in ligacoes:
        # sem destino, ou só "#seção" da própria nota: nada a trocar
        if lig.destino is None or not lig.citacao.alvo or lig.citacao.alvo.startswith("#"):
            continue
        aponta_para_a_movida = lig.destino == de
        # os links markdown da própria nota movida são relativos à pasta dela
        relativo_da_movida = lig.origem == de and lig.citacao.tipo == "md" and lig.destino != de
        if aponta_para_a_movida or relativo_da_movida:
            trocas.setdefault(onde_esta(lig.origem), []).append(
                (lig.citacao, onde_esta(lig.destino)))

    mudadas = []
    for nota, lista in trocas.items():
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
        if novo != texto:
            vault.gravar(arquivo, novo)
            mudadas.append(nota)
    return mudadas
