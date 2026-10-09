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


def mover(raiz: Path, de: str, para: str, puladas: list[str] | None = None) -> list[str]:
    """Move a nota `de` para `para` (caminhos no vault) e conserta os links.

    Devolve os caminhos das notas cujo texto mudou; as que não deu para
    atualizar vão para `puladas`. Quem chama já conferiu os dois caminhos e
    cuida do índice e da auditoria.
    """
    ligacoes = grafo.mapa(raiz).ligacoes
    vault.mover(vault.resolver(raiz, de), vault.resolver(raiz, para))
    return _reescrever(raiz, {de: para}, ligacoes, puladas)


def mover_pasta(raiz: Path, de: str, para: str,
                puladas: list[str] | None = None) -> tuple[dict[str, str], list[str]]:
    """Move a pasta `de` para `para` e conserta os links das notas de dentro.

    Devolve (velho -> novo de cada nota movida, notas cujo texto mudou). Link
    por nome curto continua valendo; quem muda é [[Pasta/Nota]] e o link
    markdown relativo que entra ou sai da pasta.
    """
    origem = vault.resolver(raiz, de, pasta=True)
    destino = vault.resolver(raiz, para, pasta=True)
    if destino == origem or destino.is_relative_to(origem):
        raise ValueError("uma pasta não pode ir para dentro dela mesma")
    indice = links.indice(raiz)
    prefixo = de.rstrip("/") + "/"
    mudancas = {c: para.rstrip("/") + "/" + c[len(prefixo):]
                for c in indice.caminhos if c.startswith(prefixo)}
    ligacoes = grafo.mapa(raiz, indice).ligacoes
    vault.mover_pasta(origem, destino)
    return mudancas, _reescrever(raiz, mudancas, ligacoes, puladas)
